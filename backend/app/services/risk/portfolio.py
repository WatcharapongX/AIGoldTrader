"""Phase 5 Portfolio Risk Manager and Concurrency Reservation.

Ensures aggregate risk across multiple trader profiles and concurrent requests never exceeds policy.
"""

import datetime as dt
import uuid
from decimal import Decimal
from typing import NamedTuple

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import RiskReservationRecord
from app.services.risk.domain import (
    AccountSnapshot,
    Direction,
    PortfolioRiskSummary,
    RiskPolicy,
    RiskReservation,
)


class ReservationBudgetCheck(NamedTuple):
    allowed: bool
    approved_risk_pct: Decimal
    approved_risk_amount: Decimal
    portfolio_exposure_before: Decimal
    portfolio_exposure_after: Decimal
    reason_th: str | None
    is_reduced: bool


class PortfolioRiskManager:
    async def get_active_reservations(
        self, session: AsyncSession, account_id: str, now: dt.datetime, for_update: bool = False
    ) -> list[RiskReservationRecord]:
        """Fetch all active unexpired risk reservations for the account with optional row-lock."""
        stmt = (
            select(RiskReservationRecord)
            .where(
                RiskReservationRecord.account_id == account_id,
                RiskReservationRecord.status == "ACTIVE",
                RiskReservationRecord.reserved_until > now,
            )
        )
        if for_update and session.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update()

        rows = (await session.scalars(stmt)).all()
        return list(rows)

    async def get_summary(
        self,
        session: AsyncSession,
        account: AccountSnapshot,
        policy: RiskPolicy,
        now: dt.datetime | None = None,
    ) -> PortfolioRiskSummary:
        as_of = now or dt.datetime.now(dt.UTC)
        reservations = await self.get_active_reservations(session, account.account_id, as_of)

        reserved_risk_pct = sum((Decimal(str(r.risk_pct)) for r in reservations), Decimal("0"))
        open_risk_pct = account.open_risk_pct
        total_risk_pct = (open_risk_pct + reserved_risk_pct).quantize(Decimal("0.0001"))

        # Symbol breakdown
        symbol_risk: dict[str, Decimal] = {}
        directional_risk: dict[Direction, Decimal] = {"LONG": Decimal("0"), "SHORT": Decimal("0")}

        for r in reservations:
            s = r.symbol
            pct = Decimal(str(r.risk_pct))
            symbol_risk[s] = symbol_risk.get(s, Decimal("0")) + pct
            d = r.direction
            if d in directional_risk:
                directional_risk[d] = directional_risk[d] + pct

        available = max(Decimal("0"), policy.max_account_risk_pct - total_risk_pct)

        # Loss metrics
        daily_loss_pct = Decimal("0")
        if account.daily_realized_pnl < Decimal("0") and account.equity > Decimal("0"):
            daily_loss_pct = (
                abs(account.daily_realized_pnl) / account.equity * Decimal("100")
            ).quantize(Decimal("0.01"))

        weekly_loss_pct = Decimal("0")
        if account.weekly_realized_pnl < Decimal("0") and account.equity > Decimal("0"):
            weekly_loss_pct = (
                abs(account.weekly_realized_pnl) / account.equity * Decimal("100")
            ).quantize(Decimal("0.01"))

        drawdown_pct = Decimal("0")
        if account.peak_equity > Decimal("0") and account.equity < account.peak_equity:
            drawdown_pct = (
                (account.peak_equity - account.equity) / account.peak_equity * Decimal("100")
            ).quantize(Decimal("0.01"))

        in_cooldown = account.consecutive_losses >= policy.cooldown_consecutive_losses

        active_res = tuple(
            RiskReservation(
                id=r.id,
                decision_id=r.decision_id,
                account_id=r.account_id,
                profile_id=r.profile_id,
                symbol=r.symbol,
                direction=r.direction,  # type: ignore
                risk_pct=Decimal(str(r.risk_pct)),
                risk_amount=Decimal(str(r.risk_amount)),
                position_size=Decimal(str(r.position_size)),
                status="ACTIVE",
                reserved_at=r.reserved_at,
                reserved_until=r.reserved_until,
            )
            for r in reservations
        )

        return PortfolioRiskSummary(
            account_id=account.account_id,
            as_of=as_of,
            open_risk_pct=open_risk_pct,
            reserved_risk_pct=reserved_risk_pct,
            total_risk_pct=total_risk_pct,
            max_account_risk_pct=policy.max_account_risk_pct,
            available_risk_pct=available,
            symbol_risk_pct=symbol_risk,
            directional_risk_pct=directional_risk,
            active_reservations=active_res,
            active_reservations_count=len(active_res),
            kill_switch_active=False,
            kill_switch_state=None,
            daily_loss_pct=daily_loss_pct,
            weekly_loss_pct=weekly_loss_pct,
            drawdown_pct=drawdown_pct,
            in_cooldown=in_cooldown,
        )

    async def check_budget_and_reserve(
        self,
        session: AsyncSession,
        account: AccountSnapshot,
        policy: RiskPolicy,
        symbol: str,
        direction: Direction,
        requested_risk_pct: Decimal,
        profile_id: str,
        decision_id: str,
        position_size: Decimal,
        now: dt.datetime,
    ) -> ReservationBudgetCheck:
        """Atomically checks active portfolio risk budget under lock and records a reservation if approved."""
        # Transaction-level advisory lock per account prevents race conditions on empty/low tables
        if session.get_bind().dialect.name == "postgresql":
            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"risk_account_{account.account_id}"},
            )

        # Row-level lock active reservations for this account to prevent concurrency races
        active_rows = await self.get_active_reservations(session, account.account_id, now, for_update=True)

        current_reserved = sum((Decimal(str(r.risk_pct)) for r in active_rows), Decimal("0"))
        current_total = account.open_risk_pct + account.reserved_risk_pct + current_reserved

        # Concurrent trade count check
        if len(active_rows) >= policy.max_concurrent_trades:
            return ReservationBudgetCheck(
                allowed=False,
                approved_risk_pct=Decimal("0"),
                approved_risk_amount=Decimal("0"),
                portfolio_exposure_before=current_total,
                portfolio_exposure_after=current_total,
                reason_th=f"จำนวนคำสั่งที่รอการดำเนินการเต็มโควตา ({policy.max_concurrent_trades} รายการ)",
                is_reduced=False,
            )

        # Check account capacity
        available_account = policy.max_account_risk_pct - current_total
        if available_account < policy.min_risk_per_trade_pct:
            return ReservationBudgetCheck(
                allowed=False,
                approved_risk_pct=Decimal("0"),
                approved_risk_amount=Decimal("0"),
                portfolio_exposure_before=current_total,
                portfolio_exposure_after=current_total,
                reason_th=(
                    f"พอร์ตโฟลิโอมีความเสี่ยงรวม {current_total:.2f}% เต็มเพดานสูงสุด {policy.max_account_risk_pct:.2f}%"
                ),
                is_reduced=False,
            )

        # Check symbol capacity
        symbol_risk = sum((Decimal(str(r.risk_pct)) for r in active_rows if r.symbol == symbol), Decimal("0"))
        available_symbol = policy.max_symbol_risk_pct - symbol_risk
        if available_symbol < policy.min_risk_per_trade_pct:
            return ReservationBudgetCheck(
                allowed=False,
                approved_risk_pct=Decimal("0"),
                approved_risk_amount=Decimal("0"),
                portfolio_exposure_before=current_total,
                portfolio_exposure_after=current_total,
                reason_th=(
                    f"ความเสี่ยงสะสมใน {symbol} ({symbol_risk:.2f}%) เต็มเพดานสัญลักษณ์ {policy.max_symbol_risk_pct:.2f}%"
                ),
                is_reduced=False,
            )

        # Check directional capacity (LONG vs SHORT do NOT cancel out)
        dir_risk = sum((Decimal(str(r.risk_pct)) for r in active_rows if r.direction == direction), Decimal("0"))
        available_direction = policy.max_directional_risk_pct - dir_risk
        if available_direction < policy.min_risk_per_trade_pct:
            return ReservationBudgetCheck(
                allowed=False,
                approved_risk_pct=Decimal("0"),
                approved_risk_amount=Decimal("0"),
                portfolio_exposure_before=current_total,
                portfolio_exposure_after=current_total,
                reason_th=(
                    f"ความเสี่ยงฝั่ง {direction} ({dir_risk:.2f}%) เต็มเพดานทิศทาง {policy.max_directional_risk_pct:.2f}%"
                ),
                is_reduced=False,
            )

        # Determine approved risk
        target_risk = min(requested_risk_pct, policy.max_risk_per_trade_pct)
        bottleneck = min(available_account, available_symbol, available_direction)

        if bottleneck < target_risk:
            # Can we reduce risk?
            if bottleneck >= policy.min_risk_per_trade_pct:
                approved_pct = bottleneck.quantize(Decimal("0.0001"))
                is_reduced = True
                reduction_reason = (
                    f"ปรับลดความเสี่ยงเหลือ {approved_pct:.2f}% เนื่องจากข้อจำกัดเพดานความเสี่ยงคงเหลือในพอร์ต"
                )
            else:
                return ReservationBudgetCheck(
                    allowed=False,
                    approved_risk_pct=Decimal("0"),
                    approved_risk_amount=Decimal("0"),
                    portfolio_exposure_before=current_total,
                    portfolio_exposure_after=current_total,
                    reason_th="วงเงินความเสี่ยงที่เหลืออยู่ไม่เพียงพอสำหรับขนาดความเสี่ยงขั้นต่ำ",
                    is_reduced=False,
                )
        else:
            approved_pct = target_risk.quantize(Decimal("0.0001"))
            is_reduced = approved_pct < requested_risk_pct
            reduction_reason = (
                f"ปรับลดความเสี่ยงตามเพดานต่อคำสั่ง {policy.max_risk_per_trade_pct:.2f}%" if is_reduced else None
            )

        approved_amount = (approved_pct / Decimal("100") * account.equity).quantize(Decimal("0.01"))
        portfolio_after = current_total + approved_pct

        # Save reservation record to lock this budget
        reservation_id = f"res_{uuid.uuid4().hex[:24]}"
        reserved_until = now + dt.timedelta(seconds=policy.reservation_ttl_seconds)

        record = RiskReservationRecord(
            id=reservation_id,
            decision_id=decision_id,
            account_id=account.account_id,
            profile_id=profile_id,
            symbol=symbol,
            direction=direction,
            risk_pct=approved_pct,
            risk_amount=approved_amount,
            position_size=position_size,
            status="ACTIVE",
            reserved_at=now,
            reserved_until=reserved_until,
        )
        session.add(record)
        await session.flush()

        return ReservationBudgetCheck(
            allowed=True,
            approved_risk_pct=approved_pct,
            approved_risk_amount=approved_amount,
            portfolio_exposure_before=current_total,
            portfolio_exposure_after=portfolio_after,
            reason_th=reduction_reason,
            is_reduced=is_reduced,
        )


portfolio_manager = PortfolioRiskManager()
