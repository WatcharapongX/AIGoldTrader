"""D3 fills/state/ledgers and D4 canonical metrics."""

import datetime as dt
from decimal import Decimal as D

import pytest

from app.services.backtesting.metrics import compute_metrics
from app.services.backtesting.simulation import simulate
from app.services.backtesting.simulation_domain import (
    EquityPoint,
    SimulatedTrade,
    SimulationResult,
    TradeStatus,
)
from app.services.strategy.domain import Evidence, Target, TradePlanSuggestion
from app.services.strategy.engine import REGISTRY
from tests.test_backtesting_d2a import START, inputs
from tests.test_backtesting_d2c import config, fresh_quotes

UTC = dt.UTC


@pytest.fixture
def plan_strategy(monkeypatch):
    original = REGISTRY["STRAT01"].evaluate

    def evaluate(context, profile, strategy_config):
        candidate = original(context, profile, strategy_config)
        plan = TradePlanSuggestion(
            id="fixture_plan_" + candidate.id,
            candidate_id=candidate.id,
            symbol="XAUUSD",
            direction="LONG",
            entry_type="LIMIT_ZONE",
            entry_lower=D("2000"),
            entry_upper=D("2002"),
            entry_source_id="test_entry",
            stop_loss=D("1995"),
            stop_source_id="test_stop",
            invalidation_th="test-only structural invalidation",
            targets=(
                Target(name="TP1", price=D("2010"), source_id="test_target_1", rr=D("1.1")),
                Target(name="TP2", price=D("2020"), source_id="test_target_2", rr=D("2.5")),
            ),
            score=85,
            evidence=(Evidence(code="TEST", description_th="explicit test-only suggestion"),),
            warnings_th=(),
            news_state="CALM",
            status="SUGGESTION_ONLY",
            as_of=context.as_of,
            context_id=candidate.context_id,
            expires_at=context.as_of + dt.timedelta(hours=1),
        )
        return candidate.model_copy(
            update={"direction": "LONG", "status": "READY", "confirmed_at": context.as_of, "plan": plan}
        )

    monkeypatch.setattr(REGISTRY["STRAT01"], "evaluate", evaluate)


def test_simulation_is_deterministic_and_never_fills_on_creation_candle(plan_strategy):
    source = inputs(quotes=fresh_quotes())
    first = simulate(source, config(), stop_at=START + dt.timedelta(minutes=30))
    second = simulate(source, config(), stop_at=START + dt.timedelta(minutes=30))
    assert first == second
    assert first.simulation_fingerprint == second.simulation_fingerprint
    filled = [t for t in first.trades if t.status == TradeStatus.FILLED_CLOSED]
    assert filled
    for trade in filled:
        assert trade.entry_at is not None and trade.entry_at >= trade.planned_at
        assert trade.exit_at is not None and trade.exit_at > trade.entry_at
        # Hand-checkable cost model: net = gross - 2 sides commission.
        assert trade.net_pnl == trade.gross_pnl - trade.commission
    assert first.final_balance == first.initial_balance + sum((t.net_pnl for t in filled), D("0"))
    assert len(first.equity_points) == len(filled)


def test_no_plan_events_are_explicit_ledger_records():
    result = simulate(inputs(), config(), stop_at=START + dt.timedelta(minutes=10))
    assert result.trades
    assert all(t.status == TradeStatus.NO_PLAN for t in result.trades)
    metrics = compute_metrics(result)
    assert metrics.total_trades == 0
    assert metrics.win_rate is None and metrics.profit_factor is None


def _trade(net, *, r="1", direction="LONG", strategy="STRAT01", at=START):
    return SimulatedTrade(
        trade_id=f"t{net}{r}{direction}",
        candidate_id="c1",
        plan_id="p1",
        strategy_id=strategy,
        profile_id="research",
        direction=direction,
        status=TradeStatus.FILLED_CLOSED,
        planned_at=at,
        entry_at=at,
        exit_at=at + dt.timedelta(minutes=5),
        entry_price=D("2000"),
        exit_price=D("2010"),
        position_size=D("1"),
        approved_risk_amount=D("100"),
        gross_pnl=net,
        commission=D("0"),
        net_pnl=net,
        r_multiple=D(r),
    )


def test_metrics_hand_calculated_fixture():
    trades = (_trade(D("100"), r="1"), _trade(D("-50"), r="-0.5", direction="SHORT"), _trade(D("0"), r="0"))
    result = SimulationResult(
        risk_replay_fingerprint="a" * 64,
        simulation_fingerprint="b" * 64,
        initial_balance=D("10000"),
        final_balance=D("10050"),
        trades=trades,
        equity_points=(
            EquityPoint(at=START, balance=D("10100"), equity=D("10100"), drawdown=D("0"), drawdown_pct=D("0")),
            EquityPoint(
                at=START + dt.timedelta(minutes=5),
                balance=D("10050"),
                equity=D("10050"),
                drawdown=D("50"),
                drawdown_pct=D("0.4950495049504950495049504950"),
            ),
        ),
    )
    metrics = compute_metrics(result)
    assert (metrics.total_trades, metrics.wins, metrics.losses, metrics.breakeven) == (3, 1, 1, 1)
    assert metrics.gross_profit == D("100") and metrics.gross_loss == D("50")
    assert metrics.net_profit == D("50") and metrics.profit_factor == D("2")
    assert metrics.win_rate == D("33.33333333333333333333333333") or metrics.win_rate == D(100) / D(3)
    assert metrics.average_win == D("100") and metrics.average_loss == D("50")
    assert metrics.expectancy == D(50) / D(3)
    assert metrics.max_drawdown == D("50")
    assert metrics.return_pct == D("0.5")
    assert metrics.long_trades == 2 and metrics.short_trades == 1
    assert metrics.by_strategy == {"STRAT01": 3}
