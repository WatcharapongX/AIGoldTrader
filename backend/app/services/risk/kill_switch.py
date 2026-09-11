"""Phase 5 server-side deterministic Kill Switch manager.

Kill Switch state dominates all risk decisions; if active, all risk approvals are BLOCKED.
"""

import datetime as dt
import uuid
from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import KillSwitchRecord
from app.services.risk.domain import POLICY_VERSION, KillSwitchState, KillSwitchTrigger


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

    async def get_state(self, session: AsyncSession) -> KillSwitchState:
        """Fetch latest kill switch state from DB; fallback to default INACTIVE if empty."""
        row = (
            await session.scalars(
                select(KillSwitchRecord)
                .order_by(KillSwitchRecord.activated_at.desc())
                .limit(1)
            )
        ).first()

        if row is None:
            now = dt.datetime.now(dt.UTC)
            return KillSwitchState(
                id=f"ks_{uuid.uuid4().hex[:16]}",
                state="INACTIVE",
                trigger_type="MANUAL",
                reason_th="ระบบปกติ Kill Switch ไม่ได้ทำงาน",
                activated_at=now,
                activated_by="system",
                cleared_at=now,
                cleared_by="system",
                policy_version=POLICY_VERSION,
            )

        return KillSwitchState(
            id=row.id,
            state=row.state,
            trigger_type=row.trigger_type,
            reason_th=row.reason_th,
            activated_at=_to_utc(row.activated_at),
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
        now = dt.datetime.now(dt.UTC)
        current = await self.get_state(session)
        if current.state == "ACTIVE":
            # Already active; idempotent return
            return current

        record_id = f"ks_{uuid.uuid4().hex[:24]}"
        payload = {
            "id": record_id,
            "state": "ACTIVE",
            "trigger_type": trigger_type,
            "reason_th": reason_th,
            "activated_at": now.isoformat(),
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
            activated_at=now,
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
            activated_at=now,
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
        now = dt.datetime.now(dt.UTC)
        current = await self.get_state(session)
        if current.state == "INACTIVE":
            return current

        record_id = f"ks_{uuid.uuid4().hex[:24]}"
        payload = {
            "id": record_id,
            "state": "INACTIVE",
            "trigger_type": current.trigger_type,
            "reason_th": reason_th,
            "activated_at": now.isoformat(),
            "activated_by": current.activated_by,
            "cleared_at": now.isoformat(),
            "cleared_by": cleared_by,
            "policy_version": current.policy_version,
        }
        db_record = KillSwitchRecord(
            id=record_id,
            state="INACTIVE",
            trigger_type=current.trigger_type,
            reason_th=reason_th,
            activated_at=now,
            activated_by=current.activated_by,
            cleared_at=now,
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
            cleared_at=now,
            cleared_by=cleared_by,
            policy_version=current.policy_version,
        )
        self._cached_state = state
        return state


kill_switch_manager = KillSwitchManager()
