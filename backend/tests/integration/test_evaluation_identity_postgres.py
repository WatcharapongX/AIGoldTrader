"""SOL-P1-001 real PostgreSQL semantic ownership and legacy compatibility."""

import asyncio

import pytest
from psycopg import sql
from sqlalchemy import func, select
from test_postgres import _alembic, isolated_postgres  # noqa: F401

from app.core.event_loop import new_event_loop
from app.db.session import dispose_engine, get_session_factory
from app.models.strategy import CandidateTransitionRecord, StrategyEvaluationRecord, TradeCandidateRecord
from app.services.strategy.domain import Evaluation, fingerprint
from app.services.strategy.engine import evaluate
from app.services.strategy.identity import projections
from app.services.strategy.repository import persist
from tests.test_evaluation_identity import CONFIG, SCENARIOS, base, news_change, traders

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("separate_traders", [False, True])
def test_dependency_projection_rows_and_fk_postgres(isolated_postgres, separate_traders):  # noqa: F811
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    async def check():
        ctx = base("STRAT01")
        strategies = tuple(f"STRAT0{i}" for i in range(1, 7))
        p = traders(ctx, *strategies)
        if not separate_traders:
            p = (p[0].model_copy(update={"allowed_strategies": strategies}),)
        first = evaluate(ctx, CONFIG, p)
        original_general = {v.id: v.model_dump(mode="json") for v in projections(first)[:4]}
        try:
            async with get_session_factory()() as session:
                generated = await persist(session, first)
                await session.commit()
            # Reconnect: idempotency is a database property, not process cache state.
            async with get_session_factory()() as session:
                assert await persist(session, first) == generated
                for scenario in SCENARIOS:
                    result = evaluate(news_change(ctx, scenario), CONFIG, p)
                    await persist(session, result)
                    await session.commit()
                    for leaf in projections(result):
                        row = await session.get(StrategyEvaluationRecord, leaf.id)
                        candidate = await session.get(TradeCandidateRecord, leaf.candidates[0].id)
                        assert row.payload == leaf.model_dump(mode="json")
                        assert row.payload_hash == fingerprint(row.payload)
                        assert candidate.evaluation_id == row.id
                        assert candidate.payload == row.payload["candidates"][0]
                    for identity, payload in original_general.items():
                        row = await session.get(StrategyEvaluationRecord, identity)
                        assert row.payload == payload
                before = await session.scalar(select(func.count()).select_from(StrategyEvaluationRecord))
                assert before == 4 + 2 * (1 + len(SCENARIOS))
                assert await session.scalar(select(func.count()).select_from(TradeCandidateRecord)) == before
                changes = (await session.scalars(select(CandidateTransitionRecord))).all()
                for change in changes:
                    owner = await session.get(TradeCandidateRecord, change.candidate_id)
                    assert owner.strategy_id in ("STRAT05", "STRAT06")
                clock = await persist(session, result)
                await session.commit()
                assert await persist(session, result) == clock
                assert await session.scalar(select(func.count()).select_from(StrategyEvaluationRecord)) == before
        finally:
            await dispose_engine()

    asyncio.run(check(), loop_factory=new_event_loop)
    assert (
        conn.execute(
            "SELECT count(*) FROM trade_candidates c LEFT JOIN strategy_evaluations e "
            "ON e.id=c.evaluation_id WHERE e.id IS NULL"
        ).fetchone()[0]
        == 0
    )
    _alembic("check")


def test_legacy_ownership_adoption_and_conflict_rollback_postgres(isolated_postgres):  # noqa: F811
    conn, schema = isolated_postgres
    conn.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
    _alembic("upgrade", "head")

    async def check():
        ctx = base("STRAT01")
        first = evaluate(ctx, CONFIG, traders(ctx, "STRAT01", "STRAT05"))
        legacy_payload = first.model_dump(mode="json", exclude={"identity_version", "scope", "component_ids"})
        legacy_id = fingerprint([ctx.id, legacy_payload["profiles"]])
        legacy_payload["id"] = legacy_id
        digest = fingerprint(legacy_payload)
        assert Evaluation.model_validate(legacy_payload).scope == "LEGACY"
        try:
            async with get_session_factory()() as session:
                legacy_row = StrategyEvaluationRecord(
                    id=legacy_id,
                    context_id=ctx.id,
                    symbol=ctx.symbol,
                    source=ctx.source,
                    as_of=ctx.as_of,
                    generated_at=ctx.as_of,
                    payload_hash=digest,
                    payload=legacy_payload,
                )
                session.add(legacy_row)
                await session.flush()
                for c in first.candidates:
                    session.add(
                        TradeCandidateRecord(
                            id=c.id,
                            evaluation_id=legacy_id,
                            profile_id=c.profile_id,
                            strategy_id=c.strategy_id,
                            as_of=ctx.as_of,
                            payload=c.model_dump(mode="json"),
                        )
                    )
                await session.commit()
                clock = await persist(session, first)
                await session.commit()
                assert await persist(session, first) == clock
                assert legacy_row.payload == legacy_payload and legacy_row.payload_hash == digest
                assert await session.scalar(select(func.count()).select_from(TradeCandidateRecord)) == 2
                assert await session.scalar(select(func.count()).select_from(StrategyEvaluationRecord)) == 3
                assert await session.scalar(select(func.count()).select_from(CandidateTransitionRecord)) == 0
                for leaf in projections(first):
                    c = await session.get(TradeCandidateRecord, leaf.candidates[0].id)
                    assert c.evaluation_id == leaf.id
                    assert c.payload == leaf.candidates[0].model_dump(mode="json")
                # An existing canonical leaf with a mismatched immutable candidate is rejected.
                c.payload = {**c.payload, "score": 0}
                await session.flush()
                with pytest.raises(ValueError, match="ownership or payload conflict"):
                    await persist(session, first)
                await session.rollback()
            async with get_session_factory()() as session:
                assert await persist(session, first) == clock
                # Existing legacy snapshots remain independently readable after adoption.
                preserved = await session.get(StrategyEvaluationRecord, legacy_id)
                assert preserved.payload == legacy_payload and preserved.payload_hash == digest
                for leaf in projections(first):
                    candidate = await session.get(TradeCandidateRecord, leaf.candidates[0].id)
                    assert candidate.evaluation_id == leaf.id
                    assert candidate.payload == leaf.candidates[0].model_dump(mode="json")
        finally:
            await dispose_engine()

    asyncio.run(check(), loop_factory=new_event_loop)
    assert (
        conn.execute(
            "SELECT count(*) FROM trade_candidates c LEFT JOIN strategy_evaluations e "
            "ON e.id=c.evaluation_id WHERE e.id IS NULL"
        ).fetchone()[0]
        == 0
    )
