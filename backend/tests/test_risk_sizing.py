"""Phase 5 comprehensive financial math and position sizing edge case tests."""

from decimal import Decimal

import pytest

from app.services.risk.domain import default_gold_spec
from app.services.risk.sizing import calculate_position_size


@pytest.fixture
def spec():
    return default_gold_spec(source="simulated")


def test_normal_long_position_sizing(spec):
    # $10,000 equity, 1% risk = $100
    # Gold entry: 2500.00 - 2502.00, SL: 2495.00
    # Worst entry: 2502.00. Stop distance: 7.00
    # Loss per lot (100 oz): 7.00 * 100 = $700/lot
    # Raw volume: 100 / 700 = 0.142857...
    # Quantized volume: 0.14 lot
    # Actual risk: 0.14 * 700 = $98.00 <= $100.00
    res = calculate_position_size(
        direction="LONG",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        stop_loss=Decimal("2495.00"),
        approved_risk_amount=Decimal("100.00"),
        account_equity=Decimal("10000.00"),
        spec=spec,
    )
    assert res.is_valid is True
    assert res.position_size == Decimal("0.14")
    assert res.actual_risk_amount == Decimal("98.00")
    assert res.actual_risk_amount <= Decimal("100.00")
    assert res.stop_distance == Decimal("7.00")
    assert res.loss_per_lot == Decimal("700.00")
    assert res.error_th is None


def test_normal_short_position_sizing(spec):
    # $10,000 equity, 1% risk = $100
    # Gold entry: 2500.00 - 2502.00, SL: 2506.00
    # Worst entry for short: 2500.00. Stop distance: 6.00
    # Loss per lot: 6.00 * 100 = $600/lot
    # Raw volume: 100 / 600 = 0.1666...
    # Quantized volume: 0.16 lot
    # Actual risk: 0.16 * 600 = $96.00 <= $100.00
    res = calculate_position_size(
        direction="SHORT",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        stop_loss=Decimal("2506.00"),
        approved_risk_amount=Decimal("100.00"),
        account_equity=Decimal("10000.00"),
        spec=spec,
    )
    assert res.is_valid is True
    assert res.position_size == Decimal("0.16")
    assert res.actual_risk_amount == Decimal("96.00")
    assert res.actual_risk_amount <= Decimal("100.00")
    assert res.stop_distance == Decimal("6.00")


def test_zero_stop_distance(spec):
    res = calculate_position_size(
        direction="LONG",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2500.00"),
        stop_loss=Decimal("2500.00"),
        approved_risk_amount=Decimal("100.00"),
        account_equity=Decimal("10000.00"),
        spec=spec,
    )
    assert res.is_valid is False
    assert "Stop Loss ต้องอยู่ต่ำกว่า" in res.error_th


def test_wrong_side_stop_loss_long(spec):
    res = calculate_position_size(
        direction="LONG",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        stop_loss=Decimal("2505.00"),  # SL above entry for LONG
        approved_risk_amount=Decimal("100.00"),
        account_equity=Decimal("10000.00"),
        spec=spec,
    )
    assert res.is_valid is False
    assert "Stop Loss ต้องอยู่ต่ำกว่าโซน Entry" in res.error_th


def test_wrong_side_stop_loss_short(spec):
    res = calculate_position_size(
        direction="SHORT",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2502.00"),
        stop_loss=Decimal("2495.00"),  # SL below entry for SHORT
        approved_risk_amount=Decimal("100.00"),
        account_equity=Decimal("10000.00"),
        spec=spec,
    )
    assert res.is_valid is False
    assert "Stop Loss ต้องอยู่สูงกว่าโซน Entry" in res.error_th


def test_huge_stop_distance_below_min_volume(spec):
    # Massive stop distance: 200 points ($20,000/lot). Risk: $50
    # Raw volume: 50 / 20000 = 0.0025 lot -> rounds down to 0.00 lot (< min 0.01)
    res = calculate_position_size(
        direction="LONG",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2500.00"),
        stop_loss=Decimal("2300.00"),
        approved_risk_amount=Decimal("50.00"),
        account_equity=Decimal("10000.00"),
        spec=spec,
    )
    assert res.is_valid is False
    assert "ต่ำกว่าขั้นต่ำ" in res.error_th


def test_tiny_stop_distance_capped_at_max_volume(spec):
    # Stop distance: 0.05 points ($5.00/lot). Risk: $1,000
    # Raw volume: 1000 / 5 = 200 lots -> capped at max_volume = 10.00 lots
    res = calculate_position_size(
        direction="LONG",
        entry_lower=Decimal("2500.00"),
        entry_upper=Decimal("2500.00"),
        stop_loss=Decimal("2499.95"),
        approved_risk_amount=Decimal("1000.00"),
        account_equity=Decimal("10000.00"),
        spec=spec,
    )
    assert res.is_valid is True
    assert res.position_size == spec.volume_max
    assert res.actual_risk_amount <= Decimal("1000.00")


def test_volume_step_quantization_never_rounds_up(spec):
    # Check that across a spectrum of stop distances, actual risk is NEVER > approved risk
    equity = Decimal("10000.00")
    approved_risk = Decimal("100.00")

    for dist_cents in range(50, 3000, 17):  # 0.50 to 30.00 points
        dist = Decimal(dist_cents) / Decimal("100")
        res = calculate_position_size(
            direction="LONG",
            entry_lower=Decimal("2500.00"),
            entry_upper=Decimal("2500.00"),
            stop_loss=Decimal("2500.00") - dist,
            approved_risk_amount=approved_risk,
            account_equity=equity,
            spec=spec,
        )
        if res.is_valid:
            assert res.actual_risk_amount <= approved_risk, f"Exceeded risk at dist={dist}"
            assert res.position_size % spec.volume_step == Decimal("0")


def test_zero_or_negative_inputs(spec):
    assert not calculate_position_size(
        "LONG", Decimal("0"), Decimal("2500"), Decimal("2490"), Decimal("100"), Decimal("10000"), spec
    ).is_valid
    assert not calculate_position_size(
        "LONG", Decimal("2500"), Decimal("2500"), Decimal("0"), Decimal("100"), Decimal("10000"), spec
    ).is_valid
    assert not calculate_position_size(
        "LONG", Decimal("2500"), Decimal("2500"), Decimal("2490"), Decimal("0"), Decimal("10000"), spec
    ).is_valid
    assert not calculate_position_size(
        "LONG", Decimal("2500"), Decimal("2500"), Decimal("2490"), Decimal("100"), Decimal("0"), spec
    ).is_valid
    assert not calculate_position_size(
        "LONG", Decimal("2510"), Decimal("2500"), Decimal("2490"), Decimal("100"), Decimal("10000"), spec
    ).is_valid
