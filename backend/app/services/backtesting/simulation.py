"""D3 deterministic fill simulation over D2A candles + D2C risk evidence."""

import datetime as dt
from decimal import Decimal

from app.services.backtesting.fingerprint import semantic_fingerprint
from app.services.backtesting.replay import make_replay_inputs, replay
from app.services.backtesting.replay_domain import ReplayInputs
from app.services.backtesting.risk_replay import replay_risk
from app.services.backtesting.risk_replay_domain import RiskEvaluationStatus, RiskReplayConfig
from app.services.backtesting.simulation_domain import (
    EquityPoint,
    ExitReason,
    SimulatedTrade,
    SimulationResult,
    TradeStatus,
)
from app.services.market_data.domain import SECONDS, Candle


def _close_time(candle: Candle) -> dt.datetime:
    return candle.open_time + dt.timedelta(seconds=SECONDS[candle.timeframe])


def simulate(inputs: ReplayInputs, config: RiskReplayConfig, *, stop_at: dt.datetime | None = None) -> SimulationResult:
    """Simulate fills sequentially (max 1 concurrent simulated position).

    A plan created at T can only fill on a primary candle whose open_time >= T
    (that candle was not yet consumed at T because T is its close predecessor:
    candidates are created at candle close, so the next candle opens at T).
    Exits are evaluated only on candles strictly after the fill candle.
    """
    canonical = make_replay_inputs(
        manifest=inputs.manifest,
        candles=inputs.candles,
        news_events=inputs.news_events,
        quotes=inputs.quotes,
        strategy_config=inputs.strategy_config,
        analysis_config=inputs.analysis_config,
        news_config=inputs.news_config,
        tick_size=inputs.tick_size,
        news_source=inputs.news_source,
        news_mode=inputs.news_mode,
        calendar_available=inputs.calendar_available,
    )
    source = replay(canonical, stop_at=stop_at)
    risk = replay_risk(inputs, config, stop_at=stop_at)
    risk_by_event = {e.replay_strategy_event_fingerprint: e for e in risk.events}

    primary_tf = canonical.manifest.config.timeframe
    candles = tuple(c for c in canonical.candles.get(primary_tf, ()) if _close_time(c) <= (stop_at or source.cutoff))
    costs = canonical.manifest.config.costs
    contract_size = config.symbol_specification.contract_size

    balance = canonical.manifest.config.initial_balance
    peak = balance
    trades: list[SimulatedTrade] = []
    equity: list[EquityPoint] = []
    open_until: dt.datetime | None = None

    for event in source.events:
        risk_event = risk_by_event.get(event.event_fingerprint)
        plan = event.trade_plan
        base = {
            "trade_id": "bt_trade_" + semantic_fingerprint({"event": event.event_fingerprint})[:24],
            "candidate_id": event.candidate_id,
            "plan_id": plan.id if plan else None,
            "strategy_id": event.strategy_id,
            "profile_id": event.profile_id,
            "direction": plan.direction if plan else None,
            "planned_at": event.as_of,
        }
        if plan is None or risk_event is None or risk_event.risk_evaluation_status != RiskEvaluationStatus.EVALUATED:
            trades.append(SimulatedTrade(**base, status=TradeStatus.NO_PLAN))
            continue
        pure = risk_event.pure_risk_result
        if pure is None or pure.decision == "BLOCKED" or pure.position_size <= 0:
            trades.append(
                SimulatedTrade(
                    **base,
                    status=TradeStatus.RISK_BLOCKED,
                    approved_risk_amount=pure.approved_risk_amount if pure else Decimal("0"),
                )
            )
            continue
        if open_until is not None and event.as_of < open_until:
            trades.append(
                SimulatedTrade(
                    **base,
                    status=TradeStatus.NOT_FILLED_CONCURRENT,
                    position_size=pure.position_size,
                    approved_risk_amount=pure.approved_risk_amount,
                )
            )
            continue

        lots = pure.position_size
        adverse = costs.spread_price + costs.slippage_price_per_side
        is_long = plan.direction == "LONG"
        entry_price = (plan.entry_upper + adverse) if is_long else (plan.entry_lower - adverse)
        stop = plan.stop_loss
        target = plan.targets[0].price

        fill_idx = None
        for idx, candle in enumerate(candles):
            if candle.open_time < event.as_of:
                continue
            if candle.open_time >= plan.expires_at:
                break
            if candle.low <= plan.entry_upper and candle.high >= plan.entry_lower:
                fill_idx = idx
                break
        if fill_idx is None:
            trades.append(
                SimulatedTrade(
                    **base,
                    status=TradeStatus.EXPIRED_UNFILLED,
                    position_size=lots,
                    approved_risk_amount=pure.approved_risk_amount,
                )
            )
            continue

        fill_candle = candles[fill_idx]
        exit_price = None
        exit_reason = ExitReason.END_OF_RUN
        exit_idx = len(candles) - 1
        ambiguous = False
        for idx in range(fill_idx + 1, len(candles)):
            candle = candles[idx]
            hit_stop = candle.low <= stop if is_long else candle.high >= stop
            hit_target = candle.high >= target if is_long else candle.low <= target
            if hit_stop and hit_target:
                ambiguous = True
                hit_target = False  # worst case: SL first
            if hit_stop:
                gap_price = candle.open if (candle.open < stop if is_long else candle.open > stop) else stop
                exit_price = (
                    (gap_price - costs.slippage_price_per_side)
                    if is_long
                    else (gap_price + costs.slippage_price_per_side)
                )
                exit_reason = ExitReason.STOP_LOSS
                exit_idx = idx
                break
            if hit_target:
                exit_price = target  # no favorable improvement beyond configured target
                exit_reason = ExitReason.TAKE_PROFIT
                exit_idx = idx
                break
        if exit_price is None:
            last = candles[-1]
            exit_price = (
                (last.close - costs.slippage_price_per_side)
                if is_long
                else (last.close + costs.slippage_price_per_side)
            )
            exit_idx = len(candles) - 1

        diff = (exit_price - entry_price) if is_long else (entry_price - exit_price)
        gross = diff * contract_size * lots
        commission = costs.commission_usd_per_lot_per_side * lots * Decimal("2")
        net = gross - commission
        balance += net
        peak = max(peak, balance)
        drawdown = peak - balance
        exit_at = _close_time(candles[exit_idx])
        open_until = exit_at
        equity.append(
            EquityPoint(
                at=exit_at,
                balance=balance,
                equity=balance,
                drawdown=drawdown,
                drawdown_pct=(drawdown / peak * Decimal("100")) if peak > 0 else Decimal("0"),
            )
        )
        trades.append(
            SimulatedTrade(
                **base,
                status=TradeStatus.FILLED_CLOSED,
                exit_reason=exit_reason,
                ambiguous_sl_tp=ambiguous,
                entry_at=fill_candle.open_time,
                exit_at=exit_at,
                entry_price=entry_price,
                exit_price=exit_price,
                position_size=lots,
                approved_risk_amount=pure.approved_risk_amount,
                gross_pnl=gross,
                commission=commission,
                net_pnl=net,
                r_multiple=(net / pure.approved_risk_amount) if pure.approved_risk_amount > 0 else None,
            )
        )

    payload = {"risk": risk.risk_replay_fingerprint, "trades": [t.model_dump(mode="python") for t in trades]}
    return SimulationResult(
        risk_replay_fingerprint=risk.risk_replay_fingerprint,
        simulation_fingerprint=semantic_fingerprint(payload),
        initial_balance=canonical.manifest.config.initial_balance,
        final_balance=balance,
        trades=tuple(trades),
        equity_points=tuple(equity),
        max_concurrent_positions=1,
    )
