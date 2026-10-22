"""D4 canonical metrics derived only from immutable simulated trade evidence."""

from decimal import Decimal

from app.services.backtesting.simulation_domain import BacktestMetrics, SimulationResult, TradeStatus


def compute_metrics(result: SimulationResult) -> BacktestMetrics:
    closed = [t for t in result.trades if t.status == TradeStatus.FILLED_CLOSED]
    wins = [t for t in closed if t.net_pnl > 0]
    losses = [t for t in closed if t.net_pnl < 0]
    breakeven = [t for t in closed if t.net_pnl == 0]
    gross_profit = sum((t.net_pnl for t in wins), Decimal("0"))
    gross_loss = sum((-t.net_pnl for t in losses), Decimal("0"))
    net = sum((t.net_pnl for t in closed), Decimal("0"))
    total = len(closed)

    def avg(values):
        return (sum(values, Decimal("0")) / Decimal(len(values))) if values else None

    max_dd = max((p.drawdown for p in result.equity_points), default=Decimal("0"))
    max_dd_pct = max((p.drawdown_pct for p in result.equity_points), default=Decimal("0"))

    best_w = cur_w = best_l = cur_l = 0
    for trade in closed:
        if trade.net_pnl > 0:
            cur_w, cur_l = cur_w + 1, 0
        elif trade.net_pnl < 0:
            cur_l, cur_w = cur_l + 1, 0
        else:
            cur_w = cur_l = 0
        best_w, best_l = max(best_w, cur_w), max(best_l, cur_l)

    by_strategy: dict[str, int] = {}
    for trade in closed:
        by_strategy[trade.strategy_id] = by_strategy.get(trade.strategy_id, 0) + 1

    initial = result.initial_balance
    return BacktestMetrics(
        total_trades=total,
        wins=len(wins),
        losses=len(losses),
        breakeven=len(breakeven),
        win_rate=(Decimal(len(wins)) / Decimal(total) * Decimal("100")) if total else None,
        loss_rate=(Decimal(len(losses)) / Decimal(total) * Decimal("100")) if total else None,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        net_profit=net,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
        average_win=avg([t.net_pnl for t in wins]),
        average_loss=avg([-t.net_pnl for t in losses]),
        average_r=avg([t.r_multiple for t in closed if t.r_multiple is not None]),
        expectancy=avg([t.net_pnl for t in closed]),
        max_drawdown=max_dd,
        max_drawdown_pct=max_dd_pct,
        return_pct=(net / initial * Decimal("100")) if initial > 0 else Decimal("0"),
        consecutive_wins=best_w,
        consecutive_losses=best_l,
        long_trades=sum(1 for t in closed if t.direction == "LONG"),
        short_trades=sum(1 for t in closed if t.direction == "SHORT"),
        by_strategy=by_strategy,
    )
