"""Explicit transitions preserve frozen evidence; absence never means invalidation."""

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.strategy import CandidateTransitionRecord, TradeCandidateRecord
from app.services.market_data.domain import SECONDS
from app.services.strategy.domain import SetupCandidate, State, StrategyMarketContext, Transition, fingerprint

TERMINAL = {"INVALIDATED", "EXPIRED", "SUPERSEDED"}


class ResolvedCandidateLifecycle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    current_status: State
    is_terminal: bool
    transition_count: int
    latest_transition: Transition | None = None
    reason_th: str = ""
    candidate: SetupCandidate


async def resolve_candidate_current_lifecycle(
    session: AsyncSession,
    candidate_id: str,
    profile_id: str | None = None,
    for_update: bool = False,
) -> ResolvedCandidateLifecycle:
    """Authoritative projection of candidate lifecycle state.

    Enforces AUD-P1-001:
    - Queries TradeCandidateRecord (optionally under row lock).
    - Queries all CandidateTransitionRecords for candidate_id ordered by as_of ASC, id ASC.
    - Authoritative status is the latest transition's to_status, or base candidate.status if no transitions.
    - Evaluates terminal status: is_terminal = current_status in TERMINAL.
    """
    stmt = select(TradeCandidateRecord).where(TradeCandidateRecord.id == candidate_id)
    if profile_id:
        stmt = stmt.where(TradeCandidateRecord.profile_id == profile_id)
    if for_update:
        stmt = stmt.with_for_update()

    cand_row = (await session.scalars(stmt.limit(1))).first()
    if cand_row is None:
        if profile_id:
            raise NotFoundError("Trade candidate not found for the specified profile")
        raise NotFoundError(f"Trade candidate '{candidate_id}' not found")

    candidate = SetupCandidate.model_validate(cand_row.payload)

    # Query all transitions for this candidate
    trans_stmt = (
        select(CandidateTransitionRecord)
        .where(CandidateTransitionRecord.candidate_id == candidate_id)
        .order_by(CandidateTransitionRecord.as_of.asc(), CandidateTransitionRecord.id.asc())
    )
    trans_rows = (await session.scalars(trans_stmt)).all()

    current_status: State = candidate.status
    latest_trans: Transition | None = None
    reason_th = ""

    if trans_rows:
        latest_row = trans_rows[-1]
        latest_trans = Transition.model_validate(latest_row.payload)
        current_status = latest_trans.to_status
        reason_th = latest_trans.reason_th or ""

    is_term = current_status in TERMINAL

    return ResolvedCandidateLifecycle(
        candidate_id=candidate_id,
        current_status=current_status,
        is_terminal=is_term,
        transition_count=len(trans_rows),
        latest_transition=latest_trans,
        reason_th=reason_th,
        candidate=candidate,
    )


def transition(
    candidate: SetupCandidate,
    context: StrategyMarketContext,
    replacement: SetupCandidate | None = None,
    current_status: State | None = None,
) -> Transition | None:
    old = current_status or candidate.status
    if (
        old in TERMINAL
        or context.as_of < candidate.detected_at
        or context.dependency_id(candidate.strategy_id) == candidate.context_id
    ):
        return None
    state: State | None = None
    reason = ""
    referenced = {source for evidence in candidate.evidence for source in evidence.source_ids}
    for frame in context.frames:
        snapshot = frame.analysis
        invalidated = {
            obj.id
            for obj in snapshot.zones
            if obj.status == "INVALIDATED" and obj.ended_at is not None and obj.ended_at <= context.as_of
        }
        invalidated |= {
            obj.id
            for obj in snapshot.liquidity
            if obj.status == "INVALIDATED" and obj.ended_at is not None and obj.ended_at <= context.as_of
        }
        if referenced & invalidated:
            state, reason = "INVALIDATED", "ข้อมูลต้นทางยืนยันว่าหลักฐานที่อ้างอิงใช้ไม่ได้แล้ว"
        if candidate.plan:
            for bar in frame.candles:
                closed_at = bar.open_time + dt.timedelta(seconds=SECONDS[frame.timeframe])
                if candidate.plan.as_of < closed_at <= context.as_of and (
                    bar.close <= candidate.plan.stop_loss
                    if candidate.direction == "LONG"
                    else bar.close >= candidate.plan.stop_loss
                ):
                    state, reason = "INVALIDATED", "ราคาปิดผ่านจุดหยุดเชิงโครงสร้าง"
    if state is None and context.as_of >= candidate.expires_at:
        state, reason = "EXPIRED", "ครบเวลาหมดอายุตามจำนวนแท่งกรอบยืนยัน"
    if (
        state is None
        and replacement
        and replacement.id != candidate.id
        and (replacement.profile_id == candidate.profile_id and replacement.strategy_id == candidate.strategy_id)
    ):
        state, reason = "SUPERSEDED", "มีการประเมิน revision ใหม่ ผลเดิมและหลักฐานยังคงเก็บไว้"
    if state is None:
        return None
    return Transition(
        id=fingerprint([candidate.id, context.id, old, state]),
        candidate_id=candidate.id,
        context_id=context.id,
        from_status=old,
        to_status=state,
        as_of=context.as_of,
        reason_th=reason,
    )


async def apply_terminal_candidate_transition(
    session: AsyncSession,
    candidate_id: str,
    target_status: State,
    now: dt.datetime,
    reason_th: str = "",
    context_id: str = "manual_or_system",
) -> Transition:
    """Atomically locks candidate, records terminal transition, and revokes active risk reservations.

    Enforces BATCHA-P1-003 and Section 21-25:
    1. Locks target candidate row under SELECT ... FOR UPDATE.
    2. Records CandidateTransitionRecord.
    3. Revokes all active RiskReservations for candidate_id in the same transaction.
    """
    cand_row = await session.scalar(
        select(TradeCandidateRecord).where(TradeCandidateRecord.id == candidate_id).with_for_update()
    )
    if cand_row is None:
        raise NotFoundError(f"Trade candidate '{candidate_id}' not found")

    cand = SetupCandidate.model_validate(cand_row.payload)
    change = Transition(
        id=fingerprint([candidate_id, context_id, cand.status, target_status]),
        candidate_id=candidate_id,
        context_id=context_id,
        from_status=cand.status,
        to_status=target_status,
        as_of=now,
        reason_th=reason_th,
    )

    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    insert_fn: Any = pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert

    await session.execute(
        insert_fn(CandidateTransitionRecord)
        .values(
            id=change.id,
            candidate_id=change.candidate_id,
            as_of=change.as_of,
            payload=change.model_dump(mode="json"),
        )
        .on_conflict_do_nothing()
    )

    if target_status in TERMINAL:
        from app.services.risk.portfolio import portfolio_manager

        await portfolio_manager.release_candidate_reservations(
            session=session,
            candidate_id=candidate_id,
            now=now,
            reason=reason_th or f"Candidate became terminal ({target_status})",
        )

    await session.flush()
    return change
