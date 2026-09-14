"""Phase 6.1 account/risk binding and authoritative-input PostgreSQL gate."""

import asyncio
import copy
import datetime as dt
from decimal import Decimal

import httpx
import pytest
from psycopg import sql
from test_postgres import _alembic, isolated_postgres  # noqa: F401

import app.api.ai as ai_api
from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session, get_session_factory
from app.main import create_app
from app.models import Role
from app.models.account import Account, TradingMode
from app.models.risk import AccountSnapshotRecord, RiskDecisionRecord, RiskReservationRecord
from app.models.strategy import TradeCandidateRecord
from app.services.ai.assembler import AIAnalysisInputAssembler
from app.services.ai.orchestrator import AIOrchestrator
from app.services.ai.provider import FixtureAIProvider
from app.services.market_data.domain import Quote
from app.services.market_data.service import MarketService
from app.services.strategy.domain import compute_trade_plan_fingerprint
from app.services.users import create_user
from tests.test_ai_authoritative_api import RecordingOrchestrator, seed_authoritative_chain

pytestmark = pytest.mark.integration


def test_ai_account_reservation_and_authoritative_api_postgres(isolated_postgres, monkeypatch) -> None:  # noqa: F811
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    async def run_matrix() -> None:
        factory = get_session_factory()
        async with factory() as session:
            admin = await create_user(
                session,
                email="phase61-postgres@example.com",
                password="phase61-safe-pass",
                role=Role.ADMIN,
            )
            account_a = Account(
                name="phase61_account_a",
                user_id=admin.id,
                trading_mode=TradingMode.PAPER,
                starting_balance=10000.0,
                base_currency="USD",
                is_active=True,
            )
            account_b = Account(
                name="phase61_account_b",
                user_id=admin.id,
                trading_mode=TradingMode.PAPER,
                starting_balance=10000.0,
                base_currency="USD",
                is_active=True,
            )
            session.add_all([account_a, account_b])
            await session.commit()

            now = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=2)
            snapshot, news, candidate, decision_a, reservation_a = await seed_authoritative_chain(
                session,
                str(account_a.id),
                now,
                "postgres",
            )
            snapshot_b = AccountSnapshotRecord(
                id="account-snapshot-postgres-b",
                account_id=str(account_b.id),
                balance=Decimal("10000.00"),
                equity=Decimal("10000.00"),
                free_margin=Decimal("10000.00"),
                peak_equity=Decimal("10000.00"),
                as_of=now + dt.timedelta(seconds=1),
                payload={"trade_plan_fingerprint": compute_trade_plan_fingerprint(candidate, candidate.plan)},
            )
            decision_b = RiskDecisionRecord(
                id="decision-postgres-newer-b",
                candidate_id=candidate.id,
                plan_id=candidate.plan.id,
                strategy_id=candidate.strategy_id,
                profile_id=candidate.profile_id,
                symbol=candidate.symbol,
                direction=candidate.direction,
                decision="APPROVED",
                requested_risk_pct=Decimal("0.5000"),
                approved_risk_pct=Decimal("0.5000"),
                requested_risk_amount=Decimal("50.00"),
                approved_risk_amount=Decimal("50.00"),
                position_size=Decimal("0.0700"),
                entry_lower=candidate.plan.entry_lower,
                entry_upper=candidate.plan.entry_upper,
                stop_loss=candidate.plan.stop_loss,
                stop_distance=Decimal("5.00"),
                account_snapshot_id=snapshot_b.id,
                policy_version="risk-policy-1.0.0",
                dependency_fingerprint="risk-dependency-postgres-b",
                as_of=now + dt.timedelta(seconds=1),
                expires_at=now + dt.timedelta(minutes=15),
                payload={},
            )
            reservation_b = RiskReservationRecord(
                id="reservation-postgres-b",
                decision_id=decision_b.id,
                account_id=str(account_b.id),
                candidate_id=candidate.id,
                profile_id=candidate.profile_id,
                symbol=candidate.symbol,
                direction=candidate.direction,
                risk_pct=decision_b.approved_risk_pct,
                risk_amount=decision_b.approved_risk_amount,
                position_size=decision_b.position_size,
                status="ACTIVE",
                reserved_at=now,
                reserved_until=now + dt.timedelta(minutes=15),
            )
            session.add_all([snapshot_b, decision_b, reservation_b])
            await session.commit()

            assembled_a = await AIAnalysisInputAssembler.assemble(
                session,
                candidate_id=candidate.id,
                account_id=str(account_a.id),
                current_user=admin,
            )
            assembled_b = await AIAnalysisInputAssembler.assemble(
                session,
                candidate_id=candidate.id,
                account_id=str(account_b.id),
                current_user=admin,
            )
            assert assembled_a.risk_context.decision_id == decision_a.id
            assert assembled_a.risk_context.approved_risk_amount == Decimal("100.00")
            assert assembled_b.risk_context.decision_id == decision_b.id
            assert assembled_b.risk_context.approved_risk_amount == Decimal("50.00")

            mismatches = (
                ("profile_id", "wrong-profile"),
                ("symbol", "EURUSD"),
                ("direction", "SHORT"),
                ("risk_pct", Decimal("0.9999")),
                ("risk_amount", Decimal("99.99")),
                ("position_size", Decimal("0.1300")),
            )
            for field, bad_value in mismatches:
                original = getattr(reservation_a, field)
                setattr(reservation_a, field, bad_value)
                await session.commit()
                mismatched = await AIAnalysisInputAssembler.assemble(
                    session,
                    candidate_id=candidate.id,
                    account_id=str(account_a.id),
                    current_user=admin,
                )
                provider = FixtureAIProvider()
                result = await AIOrchestrator(provider=provider.to_descriptor()).analyze(mismatched)
                assert mismatched.risk_context.reservation_status == "MISMATCHED"
                assert result.status == "BLOCKED_BY_UPSTREAM"
                assert provider.call_history == []
                setattr(reservation_a, field, original)
                await session.commit()

            app = create_app()

            async def override_session():
                async with factory() as request_session:
                    yield request_session

            async def override_user():
                return admin

            app.dependency_overrides[get_session] = override_session
            app.dependency_overrides[get_current_user] = override_user
            market = MarketService(factory, get_settings())
            market.quote = Quote(
                symbol="XAUUSD",
                timestamp=now,
                bid=Decimal("2500.00"),
                ask=Decimal("2500.30"),
                volume=Decimal("1"),
                source="simulated",
                mode="SIMULATED",
                spread=Decimal("0.30"),
                status="CONNECTED",
            )

            async def keep_injected_quote() -> None:
                return None

            monkeypatch.setattr(market, "start", keep_injected_quote)
            app.state.market = market
            recorder = RecordingOrchestrator()
            monkeypatch.setattr(ai_api, "ai_orchestrator", recorder)

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                response = await client.post(
                    "/api/ai-analysis/evaluate",
                    json={"candidate_id": candidate.id, "account_id": str(account_a.id)},
                )
            assert response.status_code == 200, response.text
            assert response.json()["status"] == "READY"
            authoritative = recorder.inputs[0]
            assert authoritative.quote_context.bid == Decimal("2500.00")
            assert authoritative.quote_context.source == "simulated"
            assert authoritative.structure_context.context_id == snapshot.input_id
            assert authoritative.news_context.context_fingerprint == news.fingerprint
            assert authoritative.strategy_context.candidate_id == candidate.id
            assert authoritative.trade_plan_context.plan_id == candidate.plan.id
            assert authoritative.risk_context.decision_id == decision_a.id
            assert authoritative.risk_context.reservation_id == reservation_a.id
            assert authoritative.risk_context.reservation_status == "ACTIVE"
            assert authoritative.kill_switch_context.state == "INACTIVE"

            candidate_row = await session.get(TradeCandidateRecord, candidate.id)
            assert candidate_row is not None
            mutated_payload = copy.deepcopy(candidate_row.payload)
            mutated_payload["plan"]["targets"][0]["price"] = "2511.00"
            candidate_row.payload = mutated_payload
            await session.commit()
            market.quote = market.quote.model_copy(update={"timestamp": dt.datetime.now(dt.UTC)})
            mutated_recorder = RecordingOrchestrator()
            monkeypatch.setattr(ai_api, "ai_orchestrator", mutated_recorder)

            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                mutated_response = await client.post(
                    "/api/ai-analysis/evaluate",
                    json={"candidate_id": candidate.id, "account_id": str(account_a.id)},
                )
            assert mutated_response.status_code == 200, mutated_response.text
            assert mutated_response.json()["status"] == "BLOCKED_BY_UPSTREAM"
            assert mutated_recorder.inputs[0].risk_context.reservation_status == "MISMATCHED"
            assert mutated_recorder.provider.call_history == []

    async def bounded_matrix() -> None:
        await asyncio.wait_for(run_matrix(), timeout=60)

    try:
        asyncio.run(bounded_matrix(), loop_factory=new_event_loop)
    finally:
        asyncio.run(dispose_engine())
