"""Phase 5 repository layer for immutable risk decisions, reservations, policies, and snapshots."""

import datetime as dt

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import (
    AccountSnapshotRecord,
    RiskDecisionRecord,
    RiskPolicyRecord,
    SymbolSpecificationRecord,
)
from app.services.risk.domain import (
    AccountSnapshot,
    RiskDecision,
    RiskPolicy,
    SymbolSpecification,
    default_gold_spec,
)


async def get_active_policy(session: AsyncSession) -> RiskPolicy:
    row = (
        await session.scalars(
            select(RiskPolicyRecord)
            .where(RiskPolicyRecord.is_active == True)  # noqa: E712
            .order_by(RiskPolicyRecord.created_at.desc())
            .limit(1)
        )
    ).first()

    if row is None:
        return RiskPolicy()
    return RiskPolicy.model_validate(row.payload)


async def save_policy(session: AsyncSession, policy: RiskPolicy) -> RiskPolicy:
    now = dt.datetime.now(dt.UTC)
    record = RiskPolicyRecord(
        id=f"pol_{policy.version}",
        version=policy.version,
        is_active=True,
        created_at=now,
        payload=policy.model_dump(mode="json"),
    )
    session.add(record)
    await session.flush()
    return policy


async def get_or_create_symbol_spec(
    session: AsyncSession, symbol: str = "XAUUSD", source: str = "simulated"
) -> SymbolSpecification:
    row = (
        await session.scalars(
            select(SymbolSpecificationRecord)
            .where(
                SymbolSpecificationRecord.symbol == symbol,
                SymbolSpecificationRecord.source == source,
            )
            .order_by(SymbolSpecificationRecord.observed_at.desc())
            .limit(1)
        )
    ).first()

    if row is None:
        spec = default_gold_spec(source=source)
        rec = SymbolSpecificationRecord(
            id=spec.id,
            symbol=spec.symbol,
            source=spec.source,
            tick_size=spec.tick_size,
            tick_value=spec.tick_value,
            contract_size=spec.contract_size,
            volume_min=spec.volume_min,
            volume_max=spec.volume_max,
            volume_step=spec.volume_step,
            digits=spec.digits,
            observed_at=spec.observed_at,
            payload=spec.model_dump(mode="json"),
        )
        session.add(rec)
        await session.flush()
        return spec

    return SymbolSpecification.model_validate(row.payload)


async def get_or_create_account_snapshot(
    session: AsyncSession,
    account_id: str = "default_paper_account",
    user_id: str = "system",
    now: dt.datetime | None = None,
) -> AccountSnapshot:
    at = now or dt.datetime.now(dt.UTC)
    row = (
        await session.scalars(
            select(AccountSnapshotRecord)
            .where(AccountSnapshotRecord.account_id == account_id)
            .order_by(AccountSnapshotRecord.as_of.desc())
            .limit(1)
        )
    ).first()

    if row is None:
        # Default baseline test account snapshot with $10,000 equity
        snapshot = AccountSnapshot(
            id=f"snap_{account_id}_{int(at.timestamp())}",
            account_id=account_id,
            balance=10000,
            equity=10000,
            free_margin=10000,
            daily_realized_pnl=0,
            weekly_realized_pnl=0,
            peak_equity=10000,
            open_risk_pct=0,
            reserved_risk_pct=0,
            consecutive_losses=0,
            trading_mode="PAPER",
            source="CONFIGURED_TEST",
            as_of=at,
        )
        rec = AccountSnapshotRecord(
            id=snapshot.id,
            account_id=snapshot.account_id,
            balance=snapshot.balance,
            equity=snapshot.equity,
            free_margin=snapshot.free_margin,
            daily_realized_pnl=snapshot.daily_realized_pnl,
            weekly_realized_pnl=snapshot.weekly_realized_pnl,
            peak_equity=snapshot.peak_equity,
            open_risk_pct=snapshot.open_risk_pct,
            reserved_risk_pct=snapshot.reserved_risk_pct,
            consecutive_losses=snapshot.consecutive_losses,
            trading_mode=snapshot.trading_mode,
            source=snapshot.source,
            as_of=snapshot.as_of,
            payload=snapshot.model_dump(mode="json"),
        )
        session.add(rec)
        await session.flush()
        return snapshot

    return AccountSnapshot.model_validate(row.payload)


async def find_existing_decision(
    session: AsyncSession,
    candidate_id: str,
    profile_id: str,
    now: dt.datetime,
) -> RiskDecision | None:
    """Idempotency check: returns existing unexpired decision for the candidate and profile."""
    row = (
        await session.scalars(
            select(RiskDecisionRecord)
            .where(
                RiskDecisionRecord.candidate_id == candidate_id,
                RiskDecisionRecord.profile_id == profile_id,
                RiskDecisionRecord.expires_at > now,
            )
            .order_by(RiskDecisionRecord.as_of.desc())
            .limit(1)
        )
    ).first()

    if row:
        return RiskDecision.model_validate(row.payload)
    return None


async def persist_risk_decision(session: AsyncSession, decision: RiskDecision) -> RiskDecision:
    record = RiskDecisionRecord(
        id=decision.id,
        candidate_id=decision.candidate_id,
        plan_id=decision.plan_id,
        strategy_id=decision.strategy_id,
        profile_id=decision.profile_id,
        symbol=decision.symbol,
        direction=decision.direction,
        decision=decision.decision,
        requested_risk_pct=decision.requested_risk_pct,
        approved_risk_pct=decision.approved_risk_pct,
        requested_risk_amount=decision.requested_risk_amount,
        approved_risk_amount=decision.approved_risk_amount,
        position_size=decision.position_size,
        entry_lower=decision.entry_lower,
        entry_upper=decision.entry_upper,
        stop_loss=decision.stop_loss,
        stop_distance=decision.stop_distance,
        account_snapshot_id=decision.account_snapshot_id,
        policy_version=decision.policy_version,
        as_of=decision.as_of,
        expires_at=decision.expires_at,
        payload=decision.model_dump(mode="json"),
    )
    session.add(record)
    await session.flush()
    return decision


async def list_recent_decisions(
    session: AsyncSession, limit: int = 50, symbol: str | None = None
) -> list[RiskDecision]:
    stmt = select(RiskDecisionRecord).order_by(RiskDecisionRecord.as_of.desc()).limit(limit)
    if symbol:
        stmt = stmt.where(RiskDecisionRecord.symbol == symbol)
    rows = (await session.scalars(stmt)).all()
    return [RiskDecision.model_validate(r.payload) for r in rows]
