import datetime as dt
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ForbiddenError, NotFoundError, ValidationError
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

logger = logging.getLogger(__name__)


async def get_active_policy(session: AsyncSession) -> RiskPolicy:
    rows = (
        await session.scalars(
            select(RiskPolicyRecord)
            .where(RiskPolicyRecord.is_active == True)  # noqa: E712
            .order_by(RiskPolicyRecord.created_at.desc())
        )
    ).all()

    if not rows:
        raise NotFoundError("No active authoritative risk policy provisioned")
    if len(rows) > 1:
        raise ValidationError(f"Multiple ({len(rows)}) active risk policies found; authority violated")

    return RiskPolicy.model_validate(rows[0].payload)


async def activate_policy(
    session: AsyncSession, policy: RiskPolicy, activated_by: str = "admin"
) -> RiskPolicy:
    """Atomically deactivates existing active policies and activates the new policy under lock."""
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text
        await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('risk_policy_activation'))"))

    now = dt.datetime.now(dt.UTC)
    from sqlalchemy import update
    await session.execute(
        update(RiskPolicyRecord).where(RiskPolicyRecord.is_active == True).values(is_active=False)  # noqa: E712
    )

    record = await session.get(RiskPolicyRecord, f"pol_{policy.version}")
    if record is not None:
        record.is_active = True
        record.payload = policy.model_dump(mode="json")
    else:
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


async def save_policy(session: AsyncSession, policy: RiskPolicy) -> RiskPolicy:
    return await activate_policy(session, policy)


async def get_authoritative_symbol_spec(
    session: AsyncSession,
    symbol: str = "XAUUSD",
    source: str = "simulated",
    provider: Any = None,
    now: dt.datetime | None = None,
    max_age_seconds: int = 86400,
) -> SymbolSpecification:
    """Fetches latest symbol specification from DB or live provider; fails closed if unavailable or stale."""
    at = now or dt.datetime.now(dt.UTC)
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

    if row is not None:
        observed_at = row.observed_at if row.observed_at.tzinfo else row.observed_at.replace(tzinfo=dt.UTC)
        age = (at - observed_at).total_seconds()
        if age <= max_age_seconds:
            return SymbolSpecification.model_validate(row.payload)

    # If provider is supplied and can fetch live spec, refresh and persist
    if provider is not None and hasattr(provider, "get_symbol_spec"):
        try:
            live_spec = provider.get_symbol_spec(symbol)
            if live_spec is not None:
                record = SymbolSpecificationRecord(
                    id=live_spec.id,
                    symbol=live_spec.symbol,
                    source=live_spec.source,
                    tick_size=live_spec.tick_size,
                    tick_value=live_spec.tick_value,
                    contract_size=live_spec.contract_size,
                    volume_min=live_spec.volume_min,
                    volume_max=live_spec.volume_max,
                    volume_step=live_spec.volume_step,
                    digits=live_spec.digits,
                    observed_at=live_spec.observed_at,
                    payload=live_spec.model_dump(mode="json"),
                )
                session.add(record)
                await session.flush()
                return live_spec
        except (SQLAlchemyError, Exception) as exc:
            logger.debug("Live provider symbol spec refresh skipped: %s", exc)

    # Simulated fallback only for simulated replay source
    if source == "simulated":
        return default_gold_spec(source="simulated", observed_at=at)

    raise NotFoundError(
        f"Authoritative symbol specification for '{symbol}' from source '{source}' is missing or stale"
    )


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
    Enforces User -> Account -> AccountSnapshot.
    No in-memory snapshot fabrication; missing account or snapshot fails closed (404/403).
    """
    # 1. Look up authoritative Account record
    acc_row = None
    try:
        parsed_uuid = uuid.UUID(account_id)
        acc_row = await session.scalar(select(Account).where(Account.id == parsed_uuid))
    except (ValueError, TypeError):
        acc_row = await session.scalar(select(Account).where(Account.name == account_id))

    if acc_row is None:
        raise NotFoundError(f"Account '{account_id}' not found")

    # 2. Authorization check
    if not is_admin and user_id != "system":
        if str(acc_row.user_id) != str(user_id):
            raise ForbiddenError("User is not authorized to access this account")

    # 3. Look up authoritative AccountSnapshot record
    row = (
        await session.scalars(
            select(AccountSnapshotRecord)
            .where(
                (AccountSnapshotRecord.account_id == account_id)
                | (AccountSnapshotRecord.account_id == str(acc_row.id))
                | (AccountSnapshotRecord.account_id == acc_row.name)
            )
            .order_by(AccountSnapshotRecord.as_of.desc())
            .limit(1)
        )
    ).first()

    if row is None:
        raise NotFoundError(f"No authoritative snapshot provisioned for account '{account_id}'")

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
    existing = await session.get(RiskDecisionRecord, decision.id)
    if existing is not None:
        return decision

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
    try:
        async with session.begin_nested():
            session.add(record)
            await session.flush()
    except IntegrityError as exc:
        logger.debug("Concurrent persist unique collision recovered cleanly: %s", exc)
        existing = await session.get(RiskDecisionRecord, decision.id)
        if existing is not None:
            return RiskDecision.model_validate(existing.payload)
        stmt = (
            select(RiskDecisionRecord)
            .where(
                RiskDecisionRecord.candidate_id == decision.candidate_id,
                RiskDecisionRecord.profile_id == decision.profile_id,
                RiskDecisionRecord.dependency_fingerprint == decision.dependency_fingerprint,
            )
            .order_by(RiskDecisionRecord.as_of.desc())
            .limit(1)
        )
        row = (await session.scalars(stmt)).first()
        if row is not None:
            return RiskDecision.model_validate(row.payload)
    return decision


async def list_recent_decisions(
    session: AsyncSession, limit: int = 50, symbol: str | None = None
) -> list[RiskDecision]:
    stmt = select(RiskDecisionRecord).order_by(RiskDecisionRecord.as_of.desc()).limit(limit)
    if symbol:
        stmt = stmt.where(RiskDecisionRecord.symbol == symbol)
    rows = (await session.scalars(stmt)).all()
    return [RiskDecision.model_validate(r.payload) for r in rows]
