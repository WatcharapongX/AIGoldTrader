"""Phase 5 Authoritative Paper Account State Service.

Maintains authoritative balance, equity, and loss metrics without fabricating trading PnL.
Emits snapshot with source PAPER_ACCOUNT_STATE.
All GET endpoints remain 100% read-only.
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.models.account import Account
from app.models.risk import AccountSnapshotRecord
from app.services.risk.domain import AccountSnapshot


class PaperAccountStateService:
    @staticmethod
    async def refresh_paper_account_snapshot(
        session: AsyncSession,
        account_id: str = "default_paper_account",
        force: bool = False,
        now: dt.datetime | None = None,
    ) -> AccountSnapshot:
        as_of = now or dt.datetime.now(dt.UTC)

        # 1. Look up authoritative Account
        try:
            parsed_uuid = uuid.UUID(account_id)
            acc_row = await session.scalar(select(Account).where(Account.id == parsed_uuid))
        except (ValueError, TypeError):
            acc_row = await session.scalar(select(Account).where(Account.name == account_id))

        if acc_row is None:
            raise NotFoundError(f"Account '{account_id}' not found")

        # 2. Get newest existing snapshot if any
        latest_row = (
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

        balance = Decimal(str(acc_row.starting_balance))
        equity = balance
        peak_equity = balance
        daily_pnl = Decimal("0.00")
        weekly_pnl = Decimal("0.00")
        consecutive_losses = 0
        cooldown_until = None
        open_risk_pct = Decimal("0.0000")
        reserved_risk_pct = Decimal("0.0000")

        if latest_row is not None:
            balance = Decimal(str(latest_row.balance))
            equity = Decimal(str(latest_row.equity))
            peak_equity = Decimal(str(latest_row.peak_equity))
            daily_pnl = Decimal(str(latest_row.daily_realized_pnl))
            weekly_pnl = Decimal(str(latest_row.weekly_realized_pnl))
            consecutive_losses = latest_row.consecutive_losses
            if "cooldown_until" in latest_row.payload and latest_row.payload["cooldown_until"]:
                cooldown_until = dt.datetime.fromisoformat(latest_row.payload["cooldown_until"])

        snap_id = f"snap_paper_{as_of.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
        snapshot = AccountSnapshot(
            id=snap_id,
            account_id=account_id,
            balance=balance,
            equity=equity,
            free_margin=equity,
            daily_realized_pnl=daily_pnl,
            weekly_realized_pnl=weekly_pnl,
            floating_pnl=Decimal("0.00"),
            peak_equity=max(peak_equity, equity),
            open_risk_pct=open_risk_pct,
            reserved_risk_pct=reserved_risk_pct,
            consecutive_losses=consecutive_losses,
            cooldown_until=cooldown_until,
            open_positions_count=0,
            trading_mode="PAPER",
            source="PAPER_ACCOUNT_STATE",
            as_of=as_of,
        )

        record = AccountSnapshotRecord(
            id=snapshot.id,
            account_id=account_id,
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
        session.add(record)
        await session.flush()
        return snapshot
