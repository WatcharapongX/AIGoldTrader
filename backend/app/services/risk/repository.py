import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError
from app.models.account import Account
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


async def get_authoritative_symbol_spec(
    session: AsyncSession,
    symbol: str = "XAUUSD",
    source: str = "simulated",
    now: dt.datetime | None = None,
) -> SymbolSpecification:
    """Fetches latest symbol specification from DB, or returns authoritative default spec without DB mutation."""
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
        return default_gold_spec(source=source, observed_at=now)

    return SymbolSpecification.model_validate(row.payload)


async def get_or_create_symbol_spec(
    session: AsyncSession, symbol: str = "XAUUSD", source: str = "simulated"
) -> SymbolSpecification:
    return await get_authoritative_symbol_spec(session, symbol=symbol, source=source)


async def get_authoritative_account_snapshot(
    session: AsyncSession,
    account_id: str = "default_paper_account",
    user_id: str = "system",
    is_admin: bool = False,
    now: dt.datetime | None = None,
) -> AccountSnapshot:
    """Fetches authoritative snapshot for an authorized account.
    Fails closed (404/403) on arbitrary non-existent or unauthorized accounts (SOL-P5-P1-003, SOL-P5-P1-004).
    Pure read operation: never mutates DB on GET.
    """
    at = now or dt.datetime.now(dt.UTC)

    # 1. Account existence and authorization check
    if account_id != "default_paper_account":
        # Check if account exists in accounts table
        acc_row = None
        try:
            parsed_uuid = uuid.UUID(account_id)
            acc_row = await session.scalar(select(Account).where(Account.id == parsed_uuid))
        except (ValueError, TypeError):
            acc_row = await session.scalar(select(Account).where(Account.name == account_id))

        if acc_row is not None:
            # Check ownership
            if not is_admin and user_id != "system" and str(acc_row.user_id) != str(user_id):
                raise ForbiddenError("User is not authorized to access this account")
        else:
            # Check if any snapshot exists for this account_id
            existing_snap = await session.scalar(
                select(AccountSnapshotRecord).where(AccountSnapshotRecord.account_id == account_id).limit(1)
            )
            if existing_snap is None:
                raise NotFoundError(f"Account '{account_id}' not found")

    # 2. Fetch latest snapshot from DB
    row = (
        await session.scalars(
            select(AccountSnapshotRecord)
            .where(AccountSnapshotRecord.account_id == account_id)
            .order_by(AccountSnapshotRecord.as_of.desc())
            .limit(1)
        )
    ).first()

    if row is None:
        # Default in-memory baseline for default_paper_account without mutating DB
        return AccountSnapshot(
            id=f"snap_{account_id}_{int(at.timestamp())}",
            account_id=account_id,
            balance=Decimal("10000.00"),
            equity=Decimal("10000.00"),
            free_margin=Decimal("10000.00"),
            daily_realized_pnl=Decimal("0.00"),
            weekly_realized_pnl=Decimal("0.00"),
            peak_equity=Decimal("10000.00"),
            open_risk_pct=Decimal("0.0000"),
            reserved_risk_pct=Decimal("0.0000"),
            consecutive_losses=0,
            trading_mode="PAPER",
            source="CONFIGURED_PAPER",
            as_of=at,
        )

    return AccountSnapshot.model_validate(row.payload)


async def get_or_create_account_snapshot(
    session: AsyncSession,
    account_id: str = "default_paper_account",
    user_id: str = "system",
    now: dt.datetime | None = None,
) -> AccountSnapshot:
    return await get_authoritative_account_snapshot(
        session=session,
        account_id=account_id,
        user_id=user_id,
        is_admin=True,
        now=now,
    )


async def find_existing_decision(
    session: AsyncSession,
    candidate_id: str,
    profile_id: str,
    dependency_fingerprint: str | None = None,
    now: dt.datetime | None = None,
) -> RiskDecision | None:
    """Idempotency check: returns existing unexpired decision matching
    candidate, profile, and dependency fingerprint.
    """
    stmt = (
        select(RiskDecisionRecord)
        .where(
            RiskDecisionRecord.candidate_id == candidate_id,
            RiskDecisionRecord.profile_id == profile_id,
        )
        .order_by(RiskDecisionRecord.as_of.desc())
    )
    if dependency_fingerprint is not None:
        stmt = stmt.where(RiskDecisionRecord.dependency_fingerprint == dependency_fingerprint)
    if now is not None:
        stmt = stmt.where(RiskDecisionRecord.expires_at > now)

    row = (await session.scalars(stmt.limit(1))).first()
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
        dependency_fingerprint=decision.dependency_fingerprint or "default_fingerprint",
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
