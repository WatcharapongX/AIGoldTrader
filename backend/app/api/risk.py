"""Phase 5 Risk Engine API surface.

GET endpoints are strictly read-only (no state mutation or reservation).
POST endpoints handle explicit commands (risk evaluation, kill switch activation/clearing).
Execution (orders, Phase 7) is strictly forbidden.
"""

import datetime as dt
import logging

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.api.market import started
from app.api.news import service as news_service
from app.core.errors import ForbiddenError, NotFoundError, ValidationError
from app.db.session import get_session
from app.models import Role, User
from app.models.strategy import TradeCandidateRecord
from app.services.risk.domain import (
    KillSwitchState,
    PortfolioRiskSummary,
    RiskDecision,
    RiskEvaluationRequest,
    RiskPolicy,
)
from app.services.risk.engine import risk_engine
from app.services.risk.kill_switch import kill_switch_manager
from app.services.risk.portfolio import portfolio_manager
from app.services.risk.repository import (
    find_existing_decision,
    get_active_policy,
    get_or_create_account_snapshot,
    get_or_create_symbol_spec,
    list_recent_decisions,
    persist_risk_decision,
)
from app.services.strategy.domain import SetupCandidate

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
    now = body.as_of or dt.datetime.now(dt.UTC)

    # 1. Idempotency fast-path: return existing unexpired decision if already evaluated
    existing = await find_existing_decision(session, body.candidate_id, body.profile_id, now)
    if existing:
        return existing

    # 2. Fetch candidate record
    candidate_row = (
        await session.scalars(
            select(TradeCandidateRecord)
            .where(
                TradeCandidateRecord.id == body.candidate_id,
                TradeCandidateRecord.profile_id == body.profile_id,
            )
            .limit(1)
        )
    ).first()

    if candidate_row is None:
        # Fallback: search by candidate ID only
        candidate_row = (
            await session.scalars(
                select(TradeCandidateRecord)
                .where(TradeCandidateRecord.id == body.candidate_id)
                .limit(1)
            )
        ).first()

    if candidate_row is None:
        raise NotFoundError("Trade candidate not found")

    candidate = SetupCandidate.model_validate(candidate_row.payload)
    if candidate.plan is None:
        raise ValidationError("Trade candidate does not contain a trade plan")

    # 3. Context dependencies
    market = await started(request)
    quote = market.quote

    news = None
    try:
        ns = await news_service(request)
        news = await ns.context(
            events=[],
            as_of=now,
            candles=[],
            structure=None,
            view="current",
            market_source=market.provider.source,
        )
    except Exception as exc:
        logger.warning("Failed to fetch news context for risk evaluation: %s", exc)

    policy = await get_active_policy(session)
    spec = await get_or_create_symbol_spec(session, symbol=candidate.symbol, source=market.provider.source)
    account = await get_or_create_account_snapshot(
        session, account_id=body.account_id, user_id=str(user.id), now=now
    )

    # 4. Evaluate and persist decision
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
    )

    await persist_risk_decision(session, decision)
    await session.commit()
    return decision


@router.get("/decisions", response_model=list[RiskDecision])
async def get_decisions(
    limit: int = Query(50, ge=1, le=200),
    symbol: str | None = Query(None, max_length=20),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Read-only list of recent risk decisions."""
    return await list_recent_decisions(session, limit=limit, symbol=symbol)


@router.get("/decisions/{decision_id}", response_model=RiskDecision)
async def get_decision_by_id(
    decision_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Read-only fetch of a single risk decision."""
    from app.models.risk import RiskDecisionRecord

    row = await session.scalar(select(RiskDecisionRecord).where(RiskDecisionRecord.id == decision_id))
    if row is None:
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
    account = await get_or_create_account_snapshot(session, account_id=account_id, user_id=str(user.id), now=now)
    summary = await portfolio_manager.get_summary(session, account, policy, now)
    ks_state = await kill_switch_manager.get_state(session)

    # Attach kill switch state to summary
    return summary.model_copy(
        update={
            "kill_switch_active": ks_state.state == "ACTIVE",
            "kill_switch_state": ks_state,
        }
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
