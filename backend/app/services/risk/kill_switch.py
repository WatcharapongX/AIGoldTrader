"""Phase 5 server-side deterministic Kill Switch manager.

Kill Switch state dominates all risk decisions; if active, all risk approvals are BLOCKED.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import NamedTuple, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import DataHealthRecord, KillSwitchRecord
from app.services.risk.domain import (
    POLICY_VERSION,
    AccountSnapshot,
    KillSwitchState,
    KillSwitchStatus,
    KillSwitchTrigger,
    RiskPolicy,
)


class KillSwitchCheck(NamedTuple):
    is_active: bool
    state: KillSwitchState | None
    blocked_reason_th: str | None


def _to_utc(val: dt.datetime | None) -> dt.datetime | None:
    if val is None:
        return None
    return val if val.tzinfo is not None else val.replace(tzinfo=dt.UTC)


class KillSwitchManager:
    def __init__(self):
        self._cached_state: KillSwitchState | None = None
        self._consecutive_data_health_failures: int = 0

    async def get_state(self, session: AsyncSession) -> KillSwitchState:
        """Fetch latest kill switch state from DB; fallback to UNKNOWN (fail-closed) if empty (SOL-P5-P1-009)."""
        from sqlalchemy import func

        row = (
            await session.scalars(
                select(KillSwitchRecord)
                .order_by(
                    func.coalesce(KillSwitchRecord.cleared_at, KillSwitchRecord.activated_at).desc(),
                    KillSwitchRecord.activated_at.desc(),
                )
                .limit(1)
            )
        ).first()

        if row is None:
            now = dt.datetime.now(dt.UTC)
            return KillSwitchState(
                id="ks_unknown",
                state="UNKNOWN",
                trigger_type="AUTOMATIC_SYSTEM_HEALTH",
                reason_th="ไม่สามารถตรวจสอบสถานะ Kill Switch ได้ (ฐานข้อมูลยังไม่มีข้อมูลสถานะ)",
                activated_at=now,
                activated_by="system",
                cleared_at=None,
                cleared_by=None,
                policy_version=POLICY_VERSION,
            )

        return KillSwitchState(
            id=row.id,
            state=cast(KillSwitchStatus, row.state),
            trigger_type=cast(KillSwitchTrigger, row.trigger_type),
            reason_th=row.reason_th,
            activated_at=_to_utc(row.activated_at) or dt.datetime.now(dt.UTC),
            activated_by=row.activated_by,
            cleared_at=_to_utc(row.cleared_at),
            cleared_by=row.cleared_by,
            policy_version=row.policy_version,
        )

    async def check(self, session: AsyncSession) -> KillSwitchCheck:
        state = await self.get_state(session)
        if state.state == "ACTIVE":
            return KillSwitchCheck(
                is_active=True,
                state=state,
                blocked_reason_th=f"ไม่อนุมัติเนื่องจาก Kill Switch ทำงาน ({state.reason_th})",
            )
        if state.state == "UNKNOWN":
            return KillSwitchCheck(
                is_active=True,
                state=state,
                blocked_reason_th="ไม่อนุมัติเนื่องจากไม่สามารถยืนยันสถานะ Kill Switch ได้ (Fail-closed)",
            )
        return KillSwitchCheck(
            is_active=False,
            state=state,
            blocked_reason_th=None,
        )

    async def activate(
        self,
        session: AsyncSession,
        trigger_type: KillSwitchTrigger,
        reason_th: str,
        activated_by: str,
        policy_version: str = POLICY_VERSION,
    ) -> KillSwitchState:
        # Serialized execution across workers
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('kill_switch_action'))"))

        now = dt.datetime.now(dt.UTC)
        current = await self.get_state(session)
        if current.state == "ACTIVE":
            # Already active; idempotent return
            return current

        effective_now = now
        if current.state != "UNKNOWN" and current.activated_at and effective_now <= current.activated_at:
            effective_now = current.activated_at + dt.timedelta(microseconds=1)
        if current.cleared_at and effective_now <= current.cleared_at:
            effective_now = current.cleared_at + dt.timedelta(microseconds=1)

        record_id = f"ks_{uuid.uuid4().hex[:24]}"
        payload = {
            "id": record_id,
            "state": "ACTIVE",
            "trigger_type": trigger_type,
            "reason_th": reason_th,
            "activated_at": effective_now.isoformat(),
            "activated_by": activated_by,
            "cleared_at": None,
            "cleared_by": None,
            "policy_version": policy_version,
        }
        db_record = KillSwitchRecord(
            id=record_id,
            state="ACTIVE",
            trigger_type=trigger_type,
            reason_th=reason_th,
            activated_at=effective_now,
            activated_by=activated_by,
            cleared_at=None,
            cleared_by=None,
            policy_version=policy_version,
            payload=payload,
        )
        session.add(db_record)
        await session.flush()

        state = KillSwitchState(
            id=record_id,
            state="ACTIVE",
            trigger_type=trigger_type,
            reason_th=reason_th,
            activated_at=effective_now,
            activated_by=activated_by,
            cleared_at=None,
            cleared_by=None,
            policy_version=policy_version,
        )
        self._cached_state = state
        return state

    async def clear(
        self,
        session: AsyncSession,
        cleared_by: str,
        reason_th: str = "ผู้ดูแลระบบยกเลิกสถานะ Kill Switch",
    ) -> KillSwitchState:
        # Serialized execution across workers
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(text("SELECT pg_advisory_xact_lock(hashtext('kill_switch_action'))"))

        now = dt.datetime.now(dt.UTC)
        current = await self.get_state(session)
        if current.state == "INACTIVE":
            return current

        effective_now = now
        if current.state != "UNKNOWN" and current.activated_at and effective_now <= current.activated_at:
            effective_now = current.activated_at + dt.timedelta(microseconds=1)
        if current.cleared_at and effective_now <= current.cleared_at:
            effective_now = current.cleared_at + dt.timedelta(microseconds=1)

        record_id = f"ks_{uuid.uuid4().hex[:24]}"
        payload = {
            "id": record_id,
            "state": "INACTIVE",
            "trigger_type": current.trigger_type,
            "reason_th": reason_th,
            "activated_at": effective_now.isoformat(),
            "activated_by": current.activated_by,
            "cleared_at": effective_now.isoformat(),
            "cleared_by": cleared_by,
            "policy_version": current.policy_version,
        }
        db_record = KillSwitchRecord(
            id=record_id,
            state="INACTIVE",
            trigger_type=current.trigger_type,
            reason_th=reason_th,
            activated_at=effective_now,
            activated_by=current.activated_by,
            cleared_at=effective_now,
            cleared_by=cleared_by,
            policy_version=current.policy_version,
            payload=payload,
        )
        session.add(db_record)
        await session.flush()

        state = KillSwitchState(
            id=record_id,
            state="INACTIVE",
            trigger_type=current.trigger_type,
            reason_th=reason_th,
            activated_at=current.activated_at,
            activated_by=current.activated_by,
            cleared_at=effective_now,
            cleared_by=cleared_by,
            policy_version=current.policy_version,
        )
        self._cached_state = state
        return state

    async def evaluate_automatic_triggers(
        self,
        session: AsyncSession,
        account: AccountSnapshot,
        policy: RiskPolicy,
        quote_stale: bool = False,
        quote_stale_reason: str = "",
    ) -> KillSwitchState | None:
        """Evaluates automatic safety triggers (daily loss limit, drawdown limit, data health).
        If triggered, activates and persists the Kill Switch state immediately (SOL-P5-P1-013, 014, 015).
        """
        # Daily loss trigger
        if account.daily_realized_pnl < Decimal("0") and account.equity > Decimal("0"):
            daily_loss_pct = abs(account.daily_realized_pnl) / account.equity * Decimal("100")
            if daily_loss_pct >= policy.daily_loss_limit_pct:
                return await self.activate(
                    session=session,
                    trigger_type="AUTOMATIC_DAILY_LOSS",
                    reason_th=(
                        f"ผลขาดทุนรายวันสะสม ({daily_loss_pct:.2f}%) "
                        f"เกินเพดานความปลอดภัย ({policy.daily_loss_limit_pct:.2f}%)"
                    ),
                    activated_by="system_risk_engine",
                    policy_version=policy.version,
                )

        # Drawdown trigger
        if account.peak_equity > Decimal("0") and account.equity < account.peak_equity:
            drawdown_pct = (account.peak_equity - account.equity) / account.peak_equity * Decimal("100")
            if drawdown_pct >= policy.max_drawdown_pct:
                return await self.activate(
                    session=session,
                    trigger_type="AUTOMATIC_DRAWDOWN",
                    reason_th=(
                        f"ระดับ Drawdown ({drawdown_pct:.2f}%) เกินเพดานความปลอดภัยสูงสุด ({policy.max_drawdown_pct:.2f}%)"
                    ),
                    activated_by="system_risk_engine",
                    policy_version=policy.version,
                )

        # Data health trigger with cross-process persistent tracking (SOL-P5-P2-038)
        now_utc = dt.datetime.now(dt.UTC)
        threshold = getattr(policy, "data_health_consecutive_failures", 3)
        stmt = select(DataHealthRecord).where(DataHealthRecord.id == "dh_default")
        if session.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        dh_row = (await session.scalars(stmt)).first()
        if dh_row is None:
            dh_row = DataHealthRecord(
                id="dh_default",
                provider="default",
                source="market_data",
                consecutive_failures=0,
                updated_at=now_utc,
                payload={},
            )
            session.add(dh_row)
            await session.flush()

        if quote_stale:
            dh_row.consecutive_failures += 1
            dh_row.last_failure_at = now_utc
            dh_row.updated_at = now_utc
            self._consecutive_data_health_failures = dh_row.consecutive_failures
            await session.flush()
            if dh_row.consecutive_failures >= threshold:
                return await self.activate(
                    session=session,
                    trigger_type="AUTOMATIC_DATA_HEALTH",
                    reason_th=(
                        f"ข้อมูลราคาผิดปกติหรือไม่สดใหม่ต่อเนื่อง {dh_row.consecutive_failures} ครั้ง: {quote_stale_reason}"
                    ),
                    activated_by="system_data_health",
                    policy_version=policy.version,
                )
        else:
            if dh_row.consecutive_failures > 0:
                dh_row.consecutive_failures = 0
                dh_row.last_healthy_at = now_utc
                dh_row.updated_at = now_utc
                await session.flush()
            self._consecutive_data_health_failures = 0

        return None


kill_switch_manager = KillSwitchManager()
