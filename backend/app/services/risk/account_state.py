"""Phase 5 Authoritative Paper Account State Service.

Maintains authoritative balance, equity, free_margin, and loss metrics without fabricating trading PnL.
Uses persistent PaperAccountStateRecord as the canonical economic source of truth.
AccountSnapshot represents an immutable observation/audit of that state.
Free margin is strictly preserved; state_version increments only on economic state change.
Freshness separates state_updated_at from observation time (no timestamp laundering).
"""

import datetime as dt
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.risk import AccountSnapshotRecord, PaperAccountStateRecord
from app.services.risk.account_resolver import resolve_canonical_account
from app.services.risk.domain import AccountSnapshot


def _to_utc(val: dt.datetime | None) -> dt.datetime | None:
    if val is None:
        return None
    return val if val.tzinfo is not None else val.replace(tzinfo=dt.UTC)


class PaperAccountStateService:
    @staticmethod
    async def get_or_create_paper_state(
        session: AsyncSession,
        account_id: str = "default_paper_account",
        now: dt.datetime | None = None,
    ) -> PaperAccountStateRecord:
        """Retrieves or creates canonical PaperAccountStateRecord."""
        effective_now = now or dt.datetime.now(dt.UTC)

        # 1. Look up authoritative Account via safe canonical resolver (AUD-P1-004, BATCHA-P1-002)
        acc_row, canonical_id = await resolve_canonical_account(session, account_ref=account_id)

        # Acquire advisory lock on account bootstrap to prevent first-row creation race (AUD-P1-004)
        if session.get_bind().dialect.name == "postgresql":
            from sqlalchemy import text

            await session.execute(
                text("SELECT pg_advisory_xact_lock(hashtext(:lock_key))"),
                {"lock_key": f"paper_account_init_{canonical_id}"},
            )

        # 2. Query PaperAccountStateRecord under row lock if available
        state_row = await session.scalar(
            select(PaperAccountStateRecord)
            .where(
                (PaperAccountStateRecord.account_id == canonical_id)
                | (PaperAccountStateRecord.account_id == account_id)
                | (PaperAccountStateRecord.account_id == acc_row.name)
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if state_row is not None:
            if state_row.account_id != canonical_id:
                state_row.account_id = canonical_id
            return state_row

        # 3. Check for newest existing AccountSnapshotRecord to bootstrap state
        latest_snap = (
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

        start_bal = Decimal(str(acc_row.starting_balance)) if acc_row.starting_balance else Decimal("10000.00")
        bal = Decimal(str(latest_snap.balance)) if latest_snap is not None else start_bal
        eq = Decimal(str(latest_snap.equity)) if latest_snap is not None else bal
        fm = (
            Decimal(str(latest_snap.free_margin))
            if latest_snap is not None and latest_snap.free_margin is not None
            else eq
        )
        peq = Decimal(str(latest_snap.peak_equity)) if latest_snap is not None else max(bal, eq)
        dpnl = Decimal(str(latest_snap.daily_realized_pnl)) if latest_snap is not None else Decimal("0.00")
        wpnl = Decimal(str(latest_snap.weekly_realized_pnl)) if latest_snap is not None else Decimal("0.00")
        orp = Decimal(str(latest_snap.open_risk_pct)) if latest_snap is not None else Decimal("0.0000")
        rrp = Decimal(str(latest_snap.reserved_risk_pct)) if latest_snap is not None else Decimal("0.0000")
        cl = latest_snap.consecutive_losses if latest_snap is not None else 0
        state_ver = 1
        fl_pnl = Decimal("0.00")
        pos_count = 0
        cd_until = None
        last_loss = None
        state_updated = _to_utc(latest_snap.as_of) if latest_snap is not None else effective_now

        if latest_snap is not None and latest_snap.payload:
            payload = latest_snap.payload
            if payload.get("state_version"):
                state_ver = int(payload["state_version"])
            if payload.get("floating_pnl") is not None:
                fl_pnl = Decimal(str(payload["floating_pnl"]))
            if payload.get("open_positions_count") is not None:
                pos_count = int(payload["open_positions_count"])
            if payload.get("cooldown_until"):
                cd_until = dt.datetime.fromisoformat(payload["cooldown_until"])
            if payload.get("last_loss_at"):
                last_loss = dt.datetime.fromisoformat(payload["last_loss_at"])

        # 4. Atomic insert to eliminate concurrent initial-row creation race
        is_postgres = session.get_bind().dialect.name == "postgresql"
        values_dict = {
            "account_id": canonical_id,
            "state_version": state_ver,
            "balance": bal,
            "equity": eq,
            "free_margin": fm,
            "daily_realized_pnl": dpnl,
            "weekly_realized_pnl": wpnl,
            "floating_pnl": fl_pnl,
            "peak_equity": peq,
            "open_risk_pct": orp,
            "reserved_risk_pct": rrp,
            "open_positions_count": pos_count,
            "consecutive_losses": cl,
            "last_loss_at": last_loss,
            "cooldown_until": cd_until,
            "state_updated_at": state_updated,
            "last_observed_at": effective_now,
            "payload": {},
        }
        if is_postgres:
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            pg_stmt = (
                pg_insert(PaperAccountStateRecord)
                .values(**values_dict)
                .on_conflict_do_nothing(index_elements=["account_id"])
            )
            await session.execute(pg_stmt)
        else:
            from sqlalchemy.dialects.sqlite import insert as sqlite_insert

            sqlite_stmt = (
                sqlite_insert(PaperAccountStateRecord)
                .values(**values_dict)
                .on_conflict_do_nothing(index_elements=["account_id"])
            )
            await session.execute(sqlite_stmt)

        state_row = await session.scalar(
            select(PaperAccountStateRecord)
            .where(
                (PaperAccountStateRecord.account_id == canonical_id)
                | (PaperAccountStateRecord.account_id == account_id)
                | (PaperAccountStateRecord.account_id == acc_row.name)
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if state_row is not None and state_row.account_id != canonical_id:
            state_row.account_id = canonical_id
        return state_row

    @staticmethod
    async def update_paper_account_state(
        session: AsyncSession,
        account_id: str,
        balance: Decimal | None = None,
        equity: Decimal | None = None,
        free_margin: Decimal | None = None,
        daily_realized_pnl: Decimal | None = None,
        weekly_realized_pnl: Decimal | None = None,
        floating_pnl: Decimal | None = None,
        open_risk_pct: Decimal | None = None,
        reserved_risk_pct: Decimal | None = None,
        open_positions_count: int | None = None,
        consecutive_losses: int | None = None,
        last_loss_at: dt.datetime | None = None,
        cooldown_until: dt.datetime | None = None,
        now: dt.datetime | None = None,
    ) -> PaperAccountStateRecord:
        """Updates economic fields. Increments state_version and updates state_updated_at

        ONLY when safety-relevant economics actually change (SOL-P5-P1-030).
        Serializes updates under row lock to prevent concurrency races.
        """
        effective_now = now or dt.datetime.now(dt.UTC)

        # 1. Resolve canonical ID via safe resolver (AUD-P1-004, BATCHA-P1-002)
        acc_row, canonical_id = await resolve_canonical_account(session, account_ref=account_id)

        # 2. Acquire row lock before comparing/updating state
        state = await session.scalar(
            select(PaperAccountStateRecord)
            .where(
                (PaperAccountStateRecord.account_id == canonical_id)
                | (PaperAccountStateRecord.account_id == account_id)
                | (PaperAccountStateRecord.account_id == (acc_row.name if acc_row else account_id))
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if state is None:
            state = await PaperAccountStateService.get_or_create_paper_state(session, account_id, effective_now)
        elif acc_row is not None and state.account_id != canonical_id:
            state.account_id = canonical_id

        has_economic_change = False

        if balance is not None and balance != state.balance:
            state.balance = balance
            has_economic_change = True
        if equity is not None and equity != state.equity:
            state.equity = equity
            state.peak_equity = max(state.peak_equity, equity)
            has_economic_change = True
        if free_margin is not None and free_margin != state.free_margin:
            state.free_margin = free_margin
            has_economic_change = True
        if daily_realized_pnl is not None and daily_realized_pnl != state.daily_realized_pnl:
            state.daily_realized_pnl = daily_realized_pnl
            has_economic_change = True
        if weekly_realized_pnl is not None and weekly_realized_pnl != state.weekly_realized_pnl:
            state.weekly_realized_pnl = weekly_realized_pnl
            has_economic_change = True
        if floating_pnl is not None and floating_pnl != state.floating_pnl:
            state.floating_pnl = floating_pnl
            has_economic_change = True
        if open_risk_pct is not None and open_risk_pct != state.open_risk_pct:
            state.open_risk_pct = open_risk_pct
            has_economic_change = True
        if reserved_risk_pct is not None and reserved_risk_pct != state.reserved_risk_pct:
            state.reserved_risk_pct = reserved_risk_pct
            has_economic_change = True
        if open_positions_count is not None and open_positions_count != state.open_positions_count:
            state.open_positions_count = open_positions_count
            has_economic_change = True
        if consecutive_losses is not None and consecutive_losses != state.consecutive_losses:
            state.consecutive_losses = consecutive_losses
            has_economic_change = True
        if last_loss_at is not None and last_loss_at != state.last_loss_at:
            state.last_loss_at = _to_utc(last_loss_at)
            has_economic_change = True
        if cooldown_until is not None and cooldown_until != state.cooldown_until:
            state.cooldown_until = _to_utc(cooldown_until)
            has_economic_change = True

        if has_economic_change:
            state.state_version += 1
            state.state_updated_at = effective_now

        state.last_observed_at = effective_now
        await session.flush()
        return state

    @staticmethod
    async def refresh_paper_account_snapshot(
        session: AsyncSession,
        account_id: str = "default_paper_account",
        force: bool = False,
        now: dt.datetime | None = None,
        max_observation_age_seconds: int = 0,
    ) -> AccountSnapshot:
        """Produces authoritative AccountSnapshot observing current PaperAccountState.

        Strictly preserves free_margin (never resets to equity).
        Maintains authentic economic timestamp (state_updated_at) without freshness laundering.
        Sets as_of = observation_time (authoritative observation freshness timestamp).
        Generates unique observation ID to prevent PK collision on repeated observations.
        """
        if max_observation_age_seconds < 0:
            raise ValueError("max_observation_age_seconds must be non-negative")

        observation_time = now or dt.datetime.now(dt.UTC)
        state = await PaperAccountStateService.get_or_create_paper_state(session, account_id, observation_time)
        canonical_id = str(state.account_id)

        # Update last_observed_at on observation
        state.last_observed_at = observation_time

        state_updated_at = _to_utc(state.state_updated_at) or observation_time
        account_slug = canonical_id[:8]

        # Reuse is controlled by the caller's authority contract (normally RiskPolicy),
        # never by a hidden service-level safety TTL.
        latest_row = (
            await session.scalars(
                select(AccountSnapshotRecord)
                .where(
                    (AccountSnapshotRecord.account_id == canonical_id)
                    | (AccountSnapshotRecord.account_id == account_id)
                )
                .order_by(AccountSnapshotRecord.as_of.desc())
                .limit(1)
            )
        ).first()

        if not force and latest_row is not None:
            latest_as_of = _to_utc(latest_row.as_of) or observation_time
            payload = latest_row.payload or {}
            if payload.get("state_version") == state.state_version:
                age_sec = (observation_time - latest_as_of).total_seconds()
                if age_sec <= max_observation_age_seconds:
                    res_snap = AccountSnapshot.model_validate(latest_row.payload)
                    if res_snap.account_id != canonical_id:
                        res_snap = res_snap.model_copy(update={"account_id": canonical_id})
                    return res_snap

        # Unique observation ID ensuring no collision on forced observation or multiple observations
        snap_id = f"snap_paper_{account_slug}_{uuid.uuid4().hex[:16]}"

        snapshot = AccountSnapshot(
            id=snap_id,
            account_id=canonical_id,
            balance=Decimal(str(state.balance)),
            equity=Decimal(str(state.equity)),
            free_margin=Decimal(str(state.free_margin)),
            daily_realized_pnl=Decimal(str(state.daily_realized_pnl)),
            weekly_realized_pnl=Decimal(str(state.weekly_realized_pnl)),
            floating_pnl=Decimal(str(state.floating_pnl)),
            peak_equity=Decimal(str(state.peak_equity)),
            open_risk_pct=Decimal(str(state.open_risk_pct)),
            reserved_risk_pct=Decimal(str(state.reserved_risk_pct)),
            consecutive_losses=state.consecutive_losses,
            last_loss_at=_to_utc(state.last_loss_at),
            cooldown_until=_to_utc(state.cooldown_until),
            open_positions_count=state.open_positions_count,
            state_version=state.state_version,
            state_updated_at=state_updated_at,
            observed_at=observation_time,
            trading_mode="PAPER",
            source="PAPER_ACCOUNT_STATE",
            as_of=observation_time,
        )

        record = AccountSnapshotRecord(
            id=snapshot.id,
            account_id=canonical_id,
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
