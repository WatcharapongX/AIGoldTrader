"""Explicit transitions preserve frozen evidence; absence never means invalidation."""

import datetime as dt

from app.services.market_data.domain import SECONDS
from app.services.strategy.domain import SetupCandidate, State, StrategyMarketContext, Transition, fingerprint

TERMINAL = {"INVALIDATED", "EXPIRED", "SUPERSEDED"}


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
