"""Phase 5 Risk Engine API surface.

GET endpoints are strictly read-only (no state mutation or reservation).
POST endpoints handle explicit commands (risk evaluation, kill switch activation/clearing).
Execution (orders, Phase 7) is strictly forbidden.
"""

import datetime as dt
import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.market import started
from app.api.news import service as news_service
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.db.session import get_session
from app.models import Role, User
from app.models.account import Account
from app.models.strategy import TradeCandidateRecord
from app.services.news.repository import event_vintages
from app.services.risk.domain import (
    AccountSnapshot,
    KillSwitchState,
    PortfolioRiskSummary,
    RiskDecision,
    RiskEvaluationRequest,
    RiskPolicy,
)
from app.services.risk.account_resolver import resolve_canonical_account
from app.services.risk.engine import risk_engine
from app.services.risk.kill_switch import kill_switch_manager
from app.services.risk.portfolio import portfolio_manager
from app.services.risk.repository import (
    find_existing_decision,
    get_active_policy,
    get_authoritative_account_snapshot,
    get_authoritative_symbol_spec,
    list_recent_decisions,
    persist_risk_decision,
)
from app.services.strategy.domain import SetupCandidate
from app.services.strategy.lifecycle import resolve_candidate_current_lifecycle

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/risk", tags=["risk"])


class KillSwitchActionRequest(BaseModel):
    reason_th: str = Field(min_length=3, max_length=500)


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.ADMIN:
        raise ForbiddenError("Only administrators can manage the Kill Switch")
    return user


@router.post("/evaluate", response_model=RiskDecision)
async def evaluate_risk(
    request: Request,
    body: RiskEvaluationRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Command to evaluate a trade candidate/plan and create an atomic risk reservation."""
    # AUD-P1-002: VIEWER role cannot invoke state-changing risk evaluation
    if user.role == Role.VIEWER:
        raise ForbiddenError("VIEWER role cannot execute risk evaluation")

    settings = get_settings()
    # In PAPER mode, caller as_of is strictly ignored in favor of server UTC clock (SOL-P5-P1-007)
    if settings.trading_mode == "PAPER":
        now = dt.datetime.now(dt.UTC)
    else:
        now = body.as_of or dt.datetime.now(dt.UTC)

    # Validate requested_risk_pct if provided
    if body.requested_risk_pct is not None:
        if body.requested_risk_pct <= Decimal("0") or not body.requested_risk_pct.is_finite():
            raise ValidationError("Requested risk percentage must be a positive finite number")

    # 0. Authorize user for account and resolve canonical UUID (AUD-P1-004)
    acc_row, canonical_account_id = await resolve_canonical_account(
        session=session,
        account_ref=body.account_id,
        user=user,
        is_admin=(user.role == Role.ADMIN),
    )

    # Transaction-level advisory lock on canonical account to serialize concurrent evaluations (SOL-P5-P1-031, AUD-P1-004)
    if session.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text

        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
            {"lock_key": f"risk_account_{canonical_account_id}"},
        )

    # 1. Fetch candidate record and resolve authoritative lifecycle state (AUD-P1-001)
    lifecycle = await resolve_candidate_current_lifecycle(
        session=session,
        candidate_id=body.candidate_id,
        profile_id=body.profile_id,
        for_update=True,
    )
    candidate = lifecycle.candidate
    if candidate.plan is None:
        raise ValidationError("Trade candidate does not contain a trade plan")

    # 2. Context dependencies
    market = await started(request)
    quote = market.quote

    news = None
    news_unavailable = False
    try:
        ns = await news_service(request)
        events = await event_vintages(session, ns.provider.source, now)
        events = [e for e in events if now - dt.timedelta(days=7) <= e.scheduled_at <= now + dt.timedelta(days=7)]
        news = await ns.context(
            events=events,
            as_of=now,
            candles=[],
            structure=None,
            view="current",
            market_source=market.provider.source,
        )
    except Exception as exc:
        logger.warning("Failed to fetch news context for risk evaluation: %s", exc)
        news_unavailable = True

    policy = await get_active_policy(session)
    spec = await get_authoritative_symbol_spec(
        session,
        symbol=candidate.symbol,
        source=market.provider.source,
        provider=market.provider,
        now=now,
        max_age_seconds=policy.symbol_spec_freshness_seconds,
    )
    if settings.trading_mode == "PAPER" and (
        body.account_id == "default_paper_account" or canonical_account_id == str(acc_row.id)
    ):
        from app.services.risk.account_state import PaperAccountStateService

        try:
            await PaperAccountStateService.refresh_paper_account_snapshot(
                session,
                account_id=canonical_account_id,
                now=now,
                max_observation_age_seconds=policy.account_freshness_seconds,
            )
        except Exception as exc:
            logger.debug("Paper account snapshot refresh skipped: %s", exc)

    account = await get_authoritative_account_snapshot(
        session=session,
        account_id=canonical_account_id,
        user_id=str(user.id),
        is_admin=(user.role == Role.ADMIN),
        now=now,
    )

    if news_unavailable and policy.news_risk_enabled:
        news = None  # engine fails closed when news is None while policy.news_risk_enabled is True

    # 3. Evaluate candidate (handles KillSwitch, automatic triggers,
    # idempotency cache with fingerprint, sizing, and atomic reservation)
    decision = await risk_engine.evaluate_candidate(
        session=session,
        candidate=candidate,
        plan=candidate.plan,
        account=account,
        policy=policy,
        spec=spec,
        quote=quote,
        news_context=news,
        requested_risk_pct=body.requested_risk_pct,
        as_of=now,
        candidate_lifecycle_status=lifecycle.current_status,
        candidate_transition_count=lifecycle.transition_count,
    )

    from sqlalchemy.exc import IntegrityError

    try:
        await persist_risk_decision(session, decision)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        # Recover canonical committed decision from concurrent worker race (SOL-P5-NEW-P1-018)
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy import text

            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"risk_account_{canonical_account_id}"},
            )
        existing = await find_existing_decision(
            session=session,
            candidate_id=candidate.id,
            profile_id=candidate.profile_id,
            dependency_fingerprint=decision.dependency_fingerprint,
            now=now,
        )
        if existing is not None:
            if existing.decision == "BLOCKED":
                await portfolio_manager.release_candidate_reservations(
                    session=session,
                    account_id=account.account_id,
                    candidate_id=candidate.id,
                    now=now,
                    reason=(
                        existing.blocked_reasons_th[0]
                        if existing.blocked_reasons_th
                        else "Recovered blocked decision reconciliation"
                    ),
                )
            else:
                await portfolio_manager.create_reservation(
                    session=session,
                    decision_id=existing.id,
                    account_id=account.account_id,
                    candidate_id=candidate.id,
                    profile_id=existing.profile_id,
                    symbol=existing.symbol,
                    direction=existing.direction,
                    risk_pct=existing.approved_risk_pct,
                    risk_amount=existing.approved_risk_amount,
                    position_size=existing.position_size,
                    policy=policy,
                    now=now,
                    reserved_until_cap=existing.expires_at,
                )
            await session.commit()
            return existing
        raise

    return decision


@router.get("/decisions", response_model=list[RiskDecision])
async def get_decisions(
    limit: int = Query(50, ge=1, le=200),
    symbol: str | None = Query(None, max_length=20),
    account_id: str | None = Query(None, max_length=64),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Read-only list of recent risk decisions with tenant isolation."""
    account_ids = None
    if user.role != Role.ADMIN:
        owned_rows = (await session.scalars(select(Account.id).where(Account.user_id == user.id))).all()
        owned_ids = [str(a) for a in owned_rows]
        if not owned_ids:
            return []
        if account_id is not None:
            _, req_canonical = await resolve_canonical_account(session, account_id, user)
            if req_canonical not in owned_ids:
                return []
            account_ids = [req_canonical]
        else:
            account_ids = owned_ids
    elif account_id is not None:
        _, req_canonical = await resolve_canonical_account(session, account_id, user, is_admin=True)
        account_ids = [req_canonical]

    return await list_recent_decisions(session, limit=limit, symbol=symbol, account_ids=account_ids)


@router.get("/decisions/{decision_id}", response_model=RiskDecision)
async def get_decision_by_id(
    decision_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Read-only fetch of a single risk decision with tenant isolation."""
    from app.models.risk import RiskDecisionRecord

    row = await session.scalar(select(RiskDecisionRecord).where(RiskDecisionRecord.id == decision_id))
    if row is None:
        raise NotFoundError("Risk decision not found")

    if user.role != Role.ADMIN:
        owned_rows = (await session.scalars(select(Account.id).where(Account.user_id == user.id))).all()
        owned_ids = {str(a) for a in owned_rows}
        if str(row.account_id) not in owned_ids:
            raise NotFoundError("Risk decision not found")

    return RiskDecision.model_validate(row.payload)


@router.get("/portfolio", response_model=PortfolioRiskSummary)
async def get_portfolio_risk(
    account_id: str = Query("default_paper_account", max_length=64),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Read-only portfolio risk exposure and active reservations."""
    now = dt.datetime.now(dt.UTC)
    policy = await get_active_policy(session)
    account = await get_authoritative_account_snapshot(
        session=session,
        account_id=account_id,
        user_id=str(user.id),
        is_admin=(user.role == Role.ADMIN),
        now=now,
    )
    summary = await portfolio_manager.get_summary(session, account, policy, now)
    ks_state = await kill_switch_manager.get_state(session)

    # Attach kill switch state to summary
    return summary.model_copy(
        update={
            "kill_switch_active": ks_state.state == "ACTIVE",
            "kill_switch_state": ks_state,
        }
    )


@router.get("/account", response_model=AccountSnapshot)
async def get_account_snapshot(
    account_id: str = Query("default_paper_account", max_length=64),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Read-only authoritative account snapshot (balance, equity, margin, drawdown)."""
    now = dt.datetime.now(dt.UTC)
    policy = await get_active_policy(session)
    settings = get_settings()
    if settings.trading_mode == "PAPER" and account_id == "default_paper_account":
        from app.services.risk.account_state import PaperAccountStateService

        try:
            await PaperAccountStateService.refresh_paper_account_snapshot(
                session,
                account_id=account_id,
                now=now,
                max_observation_age_seconds=policy.account_freshness_seconds,
            )
        except Exception as exc:
            logger.debug("Paper account snapshot refresh skipped: %s", exc)

    return await get_authoritative_account_snapshot(
        session=session,
        account_id=account_id,
        user_id=str(user.id),
        is_admin=(user.role == Role.ADMIN),
        now=now,
    )


@router.get("/policy", response_model=RiskPolicy)
async def get_policy(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Read-only current active risk policy."""
    return await get_active_policy(session)


@router.get("/kill-switch", response_model=KillSwitchState)
async def get_kill_switch_state(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Read-only current kill switch status."""
    return await kill_switch_manager.get_state(session)


@router.post("/kill-switch/activate", response_model=KillSwitchState)
async def activate_kill_switch(
    body: KillSwitchActionRequest,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Administrative command to manually activate the Kill Switch."""
    state = await kill_switch_manager.activate(
        session=session,
        trigger_type="MANUAL",
        reason_th=body.reason_th,
        activated_by=f"admin_{user.id}",
    )
    await session.commit()
    return state


@router.post("/kill-switch/clear", response_model=KillSwitchState)
async def clear_kill_switch(
    body: KillSwitchActionRequest,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Administrative command to manually clear the Kill Switch."""
    state = await kill_switch_manager.clear(
        session=session,
        cleared_by=f"admin_{user.id}",
        reason_th=body.reason_th,
    )
    await session.commit()
    return state
