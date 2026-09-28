"""Stateful live Risk orchestration over the verified pure D2B1 policy core.

The wrapper owns locks, Kill Switch/data-health persistence, idempotency, reservations,
and public ``RiskDecision`` compatibility. Deterministic policy and sizing are delegated
to ``evaluate_pure_risk``.
"""

import datetime as dt
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.market_data.domain import Quote
from app.services.news.domain import NewsStrategyContext
from app.services.risk.domain import (
    AccountSnapshot,
    RiskDecision,
    RiskPolicy,
    SymbolSpecification,
)
from app.services.risk.fingerprint import (
    compute_evaluation_intent_identity,
    compute_risk_dependency_fingerprint,
)
from app.services.risk.kill_switch import kill_switch_manager
from app.services.risk.live_adapter import (
    baseline_portfolio_snapshot,
    build_live_pure_input,
    portfolio_snapshot_from_live,
    pure_kill_switch_from_live,
    pure_news_from_live,
    pure_quote_from_live,
    quote_stale_evidence,
)
from app.services.risk.policy_core import evaluate_pure_risk
from app.services.risk.policy_domain import (
    DataHealthInputState,
    KillSwitchInputState,
    MarketSafetyState,
    PureKillSwitchInput,
    PureRiskCode,
    PureRiskResult,
)
from app.services.risk.portfolio import portfolio_manager
from app.services.risk.repository import find_existing_decision
from app.services.strategy.domain import SetupCandidate, TradePlanSuggestion, compute_trade_plan_fingerprint


class RiskEngine:
    async def evaluate_candidate(
        self,
        session: AsyncSession,
        candidate: SetupCandidate,
        plan: TradePlanSuggestion,
        account: AccountSnapshot,
        policy: RiskPolicy,
        spec: SymbolSpecification,
        quote: Quote | None,
        news_context: NewsStrategyContext | None = None,
        requested_risk_pct: Decimal | None = None,
        as_of: dt.datetime | None = None,
        candidate_lifecycle_status: str | None = None,
        candidate_transition_count: int = 0,
    ) -> RiskDecision:
        now = as_of or dt.datetime.now(dt.UTC)
        plan_fingerprint = compute_trade_plan_fingerprint(candidate, plan)

        # Account-scoped serialization remains live authority.
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy import text

            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"risk_account_{account.account_id}"},
            )

        pure_quote = pure_quote_from_live(quote)
        pure_news = pure_news_from_live(news_context)
        provider_name = "mt5" if (quote and quote.source.startswith("mt5")) else "market_data"
        source_name = quote.source if quote else "default"

        # Preflight delegates safety derivation to the pure core before any persistent
        # automatic trigger is evaluated. UNKNOWN prevents this advisory result from
        # being mistaken for an approval; only its immutable trigger facts are consumed.
        preflight_input = build_live_pure_input(
            as_of=now,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            quote=pure_quote,
            news=pure_news,
            kill_switch=PureKillSwitchInput(state=KillSwitchInputState.UNKNOWN),
            data_health_state=DataHealthInputState.HEALTHY,
            data_health_provider=provider_name,
            data_health_source=source_name,
            data_health_failures=0,
            caller_requested_risk_pct=requested_risk_pct,
            portfolio=baseline_portfolio_snapshot(account, candidate, plan),
            candidate_lifecycle_status=candidate_lifecycle_status,
            candidate_transition_count=candidate_transition_count,
        )
        preflight_result = evaluate_pure_risk(preflight_input)
        quote_is_stale, quote_stale_reason = quote_stale_evidence(preflight_result)

        await kill_switch_manager.evaluate_automatic_triggers(
            session=session,
            account=account,
            policy=policy,
            quote_stale=quote_is_stale,
            quote_stale_reason=quote_stale_reason,
            provider=provider_name,
            source=source_name,
            safety_trigger_facts=preflight_result.safety_trigger_facts,
        )

        # Re-read after persistence so final pure evaluation observes authoritative state.
        ks_check = await kill_switch_manager.check(session)
        ks_state = ks_check.state or await kill_switch_manager.get_state(session)
        data_health_failures = await kill_switch_manager.get_data_health_failures(
            session,
            provider_name,
            source_name,
        )

        # Lock and normalize reservation evidence once. Exactly one retry reservation is
        # excluded; duplicates remain visible and fail closed inside the pure policy.
        active_reservations = await portfolio_manager.get_active_reservations(
            session,
            account.account_id,
            now,
            for_update=True,
        )
        portfolio_snapshot, legacy_current_exposure, _ = portfolio_snapshot_from_live(
            account,
            candidate,
            plan,
            active_reservations,
        )
        data_health_state = (
            DataHealthInputState.DEGRADED if quote_is_stale else DataHealthInputState.HEALTHY
        )
        final_input = build_live_pure_input(
            as_of=now,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            quote=pure_quote,
            news=pure_news,
            kill_switch=pure_kill_switch_from_live(ks_state),
            data_health_state=data_health_state,
            data_health_provider=provider_name,
            data_health_source=source_name,
            data_health_failures=data_health_failures,
            caller_requested_risk_pct=requested_risk_pct,
            portfolio=portfolio_snapshot,
            candidate_lifecycle_status=candidate_lifecycle_status,
            candidate_transition_count=candidate_transition_count,
        )
        pure_result = evaluate_pure_risk(final_input)

        target_risk_pct = pure_result.target_risk_pct
        intent_id = compute_evaluation_intent_identity(
            candidate=candidate,
            plan=plan,
            profile_id=candidate.profile_id,
            account_id=account.account_id,
            requested_risk_pct=target_risk_pct,
        )

        quote_safety_state = pure_result.safety_trigger_facts.quote_safety_state
        legacy_quote_is_stale = quote_safety_state in {
            MarketSafetyState.UNAVAILABLE,
            MarketSafetyState.STALE,
            MarketSafetyState.SPREAD_BLOCKED,
        }
        fingerprint = compute_risk_dependency_fingerprint(
            candidate=candidate,
            plan=plan,
            profile_id=candidate.profile_id,
            account=account,
            policy=policy,
            spec=spec,
            kill_switch=ks_state,
            quote=quote,
            news_prov=pure_result.news_provenance,
            portfolio_exposure_before=legacy_current_exposure,
            requested_risk_pct=target_risk_pct,
            account_is_stale=PureRiskCode.ACCOUNT_STALE in pure_result.blocked_codes,
            quote_is_stale=legacy_quote_is_stale,
            plan_is_expired=PureRiskCode.PLAN_EXPIRED in pure_result.blocked_codes,
            cooldown_active=PureRiskCode.COOLDOWN_ACTIVE in pure_result.blocked_codes,
            candidate_lifecycle_status=candidate_lifecycle_status,
            candidate_transition_count=candidate_transition_count,
        )
        decision_id = f"dec_{fingerprint[:24]}"

        async def release_pending_active_reservations(reason: str) -> None:
            await portfolio_manager.release_candidate_reservations(
                session=session,
                account_id=account.account_id,
                candidate_id=candidate.id,
                now=now,
                reason=reason,
            )

        existing_decision = await find_existing_decision(
            session=session,
            candidate_id=candidate.id,
            profile_id=candidate.profile_id,
            dependency_fingerprint=fingerprint,
            now=now,
        )
        if existing_decision is not None:
            if existing_decision.decision == "BLOCKED":
                reason = (
                    existing_decision.blocked_reasons_th[0]
                    if existing_decision.blocked_reasons_th
                    else "Cached blocked decision reconciliation"
                )
                await release_pending_active_reservations(reason)
            else:
                await portfolio_manager.create_reservation(
                    session=session,
                    decision_id=existing_decision.id,
                    account_id=account.account_id,
                    candidate_id=candidate.id,
                    profile_id=existing_decision.profile_id,
                    symbol=existing_decision.symbol,
                    direction=existing_decision.direction,
                    risk_pct=existing_decision.approved_risk_pct,
                    risk_amount=existing_decision.approved_risk_amount,
                    position_size=existing_decision.position_size,
                    policy=policy,
                    now=now,
                    reserved_until_cap=existing_decision.expires_at,
                )
            return existing_decision

        if pure_result.decision == "BLOCKED":
            reason = (
                pure_result.blocked_reasons_th[0]
                if pure_result.blocked_reasons_th
                else "Pure Risk policy blocked evaluation"
            )
            await release_pending_active_reservations(reason)
        else:
            await portfolio_manager.create_reservation(
                session=session,
                decision_id=decision_id,
                account_id=account.account_id,
                profile_id=candidate.profile_id,
                symbol=candidate.symbol,
                direction=plan.direction,
                risk_pct=pure_result.approved_risk_pct,
                risk_amount=pure_result.approved_risk_amount,
                position_size=pure_result.position_size,
                policy=policy,
                now=now,
                candidate_id=candidate.id,
            )

        return self._to_live_decision(
            pure_result=pure_result,
            decision_id=decision_id,
            evaluation_intent_id=intent_id,
            dependency_fingerprint=fingerprint,
            trade_plan_fingerprint=plan_fingerprint,
            candidate=candidate,
            plan=plan,
            account=account,
            policy=policy,
            spec=spec,
            now=now,
        )

    @staticmethod
    def _to_live_decision(
        *,
        pure_result: PureRiskResult,
        decision_id: str,
        evaluation_intent_id: str,
        dependency_fingerprint: str,
        trade_plan_fingerprint: str,
        candidate: SetupCandidate,
        plan: TradePlanSuggestion,
        account: AccountSnapshot,
        policy: RiskPolicy,
        spec: SymbolSpecification,
        now: dt.datetime,
    ) -> RiskDecision:
        is_blocked = pure_result.decision == "BLOCKED"
        requested_risk_pct = (
            policy.max_risk_per_trade_pct
            if is_blocked
            else pure_result.normalized_requested_risk_pct
        )
        requested_risk_amount = (
            (policy.max_risk_per_trade_pct / Decimal("100") * account.equity).quantize(
                Decimal("0.01")
            )
            if is_blocked
            else pure_result.normalized_requested_risk_amount
        )
        approved_risk_pct = (
            Decimal("0.0000") if is_blocked else pure_result.approved_risk_pct
        )
        approved_risk_amount = (
            Decimal("0.00") if is_blocked else pure_result.approved_risk_amount
        )
        position_size = Decimal("0.0000") if is_blocked else pure_result.position_size
        expires_at = (
            now + dt.timedelta(seconds=policy.reservation_ttl_seconds)
            if is_blocked
            else min(plan.expires_at, now + dt.timedelta(seconds=policy.reservation_ttl_seconds))
        )
        return RiskDecision(
            id=decision_id,
            evaluation_intent_id=evaluation_intent_id,
            candidate_id=candidate.id,
            plan_id=plan.id,
            strategy_id=candidate.strategy_id,
            strategy_version=candidate.strategy_version,
            profile_id=candidate.profile_id,
            symbol=candidate.symbol,
            direction=plan.direction,
            decision=pure_result.decision,
            requested_risk_pct=requested_risk_pct,
            approved_risk_pct=approved_risk_pct,
            requested_risk_amount=requested_risk_amount,
            approved_risk_amount=approved_risk_amount,
            position_size=position_size,
            entry_lower=Decimal(str(plan.entry_lower)),
            entry_upper=Decimal(str(plan.entry_upper)),
            stop_loss=Decimal(str(plan.stop_loss)),
            stop_distance=pure_result.stop_distance,
            portfolio_exposure_before=pure_result.portfolio_exposure_before,
            portfolio_exposure_after=pure_result.portfolio_exposure_after,
            account_id=account.account_id,
            account_snapshot_id=account.id,
            symbol_specification_id=spec.id,
            policy_version=policy.version,
            reasons_th=pure_result.reasons_th,
            warnings_th=pure_result.warnings_th,
            blocked_reasons_th=pure_result.blocked_reasons_th,
            as_of=now,
            expires_at=expires_at,
            dependency_fingerprint=dependency_fingerprint,
            trade_plan_fingerprint=trade_plan_fingerprint,
            market_provenance=pure_result.market_provenance,
            news_provenance=pure_result.news_provenance,
            execution_blocked="NO_EXECUTION_ANALYSIS_ONLY",
        )


risk_engine = RiskEngine()
