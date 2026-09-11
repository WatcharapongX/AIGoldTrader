"""Phase 5 deterministic position sizing and financial math.

All math uses Decimal. Volume is always quantized down to prevent exceeding approved risk.
"""

from decimal import Decimal
from typing import NamedTuple

from app.services.risk.domain import Direction, SymbolSpecification


class SizingResult(NamedTuple):
    is_valid: bool
    position_size: Decimal
    actual_risk_amount: Decimal
    actual_risk_pct: Decimal
    stop_distance: Decimal
    loss_per_lot: Decimal
    error_th: str | None


def calculate_position_size(
    direction: Direction,
    entry_lower: Decimal,
    entry_upper: Decimal,
    stop_loss: Decimal,
    approved_risk_amount: Decimal,
    account_equity: Decimal,
    spec: SymbolSpecification,
) -> SizingResult:
    """Calculate quantized position size using conservative stop distance and strict round-down.

    For LONG: worst-case entry fill is entry_upper (furthest from stop).
    For SHORT: worst-case entry fill is entry_lower (furthest from stop).
    To be maximally conservative against risk, we evaluate stop distance from the worst-case entry.
    """
    zero = Decimal("0")
    if account_equity <= zero or approved_risk_amount <= zero:
        return SizingResult(
            is_valid=False,
            position_size=zero,
            actual_risk_amount=zero,
            actual_risk_pct=zero,
            stop_distance=zero,
            loss_per_lot=zero,
            error_th="วงเงินความเสี่ยงหรือยอดเงินในบัญชีต้องมากกว่า 0",
        )

    if (
        spec.tick_size <= zero
        or spec.tick_value <= zero
        or spec.contract_size <= zero
        or spec.volume_step <= zero
        or spec.volume_min <= zero
        or spec.volume_max <= zero
    ):
        return SizingResult(
            is_valid=False,
            position_size=zero,
            actual_risk_amount=zero,
            actual_risk_pct=zero,
            stop_distance=zero,
            loss_per_lot=zero,
            error_th="ข้อมูลสเปกสัญลักษณ์ (Symbol Specification) ไม่ถูกต้อง",
        )

    if entry_lower <= zero or entry_upper <= zero or stop_loss <= zero:
        return SizingResult(
            is_valid=False,
            position_size=zero,
            actual_risk_amount=zero,
            actual_risk_pct=zero,
            stop_distance=zero,
            loss_per_lot=zero,
            error_th="ราคา Entry หรือ Stop Loss ต้องมากกว่า 0",
        )

    if entry_lower > entry_upper:
        return SizingResult(
            is_valid=False,
            position_size=zero,
            actual_risk_amount=zero,
            actual_risk_pct=zero,
            stop_distance=zero,
            loss_per_lot=zero,
            error_th="ช่วงราคา Entry ไม่ถูกต้อง (lower > upper)",
        )

    if direction == "LONG":
        if stop_loss >= entry_lower:
            return SizingResult(
                is_valid=False,
                position_size=zero,
                actual_risk_amount=zero,
                actual_risk_pct=zero,
                stop_distance=zero,
                loss_per_lot=zero,
                error_th="ระดับ Stop Loss ต้องอยู่ต่ำกว่าโซน Entry สำหรับคำสั่ง LONG",
            )
        # Worst-case entry fill for risk calculation is entry_upper
        worst_entry = entry_upper
        stop_distance = worst_entry - stop_loss
    elif direction == "SHORT":
        if stop_loss <= entry_upper:
            return SizingResult(
                is_valid=False,
                position_size=zero,
                actual_risk_amount=zero,
                actual_risk_pct=zero,
                stop_distance=zero,
                loss_per_lot=zero,
                error_th="ระดับ Stop Loss ต้องอยู่สูงกว่าโซน Entry สำหรับคำสั่ง SHORT",
            )
        # Worst-case entry fill for risk calculation is entry_lower
        worst_entry = entry_lower
        stop_distance = stop_loss - worst_entry
    else:
        return SizingResult(
            is_valid=False,
            position_size=zero,
            actual_risk_amount=zero,
            actual_risk_pct=zero,
            stop_distance=zero,
            loss_per_lot=zero,
            error_th=f"ทิศทางคำสั่ง {direction} ไม่รองรับ",
        )

    if stop_distance <= zero:
        return SizingResult(
            is_valid=False,
            position_size=zero,
            actual_risk_amount=zero,
            actual_risk_pct=zero,
            stop_distance=zero,
            loss_per_lot=zero,
            error_th="ระยะ Stop Loss ต้องมากกว่า 0",
        )

    # Loss per 1.0 standard lot for this stop distance
    # For XAUUSD: ticks = stop_distance / tick_size; loss = ticks * tick_value
    loss_per_lot = (stop_distance / spec.tick_size) * spec.tick_value

    if loss_per_lot <= zero:
        return SizingResult(
            is_valid=False,
            position_size=zero,
            actual_risk_amount=zero,
            actual_risk_pct=zero,
            stop_distance=stop_distance,
            loss_per_lot=zero,
            error_th="มูลค่าความเสียหายต่อ Lot ต้องมากกว่า 0",
        )

    raw_volume = approved_risk_amount / loss_per_lot

    # Always quantize down to volume_step to NEVER exceed approved risk
    steps = int(raw_volume / spec.volume_step)
    quantized_volume = Decimal(steps) * spec.volume_step

    if quantized_volume < spec.volume_min:
        return SizingResult(
            is_valid=False,
            position_size=zero,
            actual_risk_amount=zero,
            actual_risk_pct=zero,
            stop_distance=stop_distance,
            loss_per_lot=loss_per_lot,
            error_th=(
                f"ขนาด Lot ที่คำนวณได้ ({quantized_volume}) ต่ำกว่าขั้นต่ำ ({spec.volume_min}) "
                f"เมื่อจำกัดความเสี่ยงที่ ${approved_risk_amount:.2f}"
            ),
        )

    if quantized_volume > spec.volume_max:
        quantized_volume = spec.volume_max

    actual_risk_amount = (quantized_volume * loss_per_lot).quantize(Decimal("0.01"))
    actual_risk_pct = ((actual_risk_amount / account_equity) * Decimal("100")).quantize(Decimal("0.0001"))

    # Fail closed assertion: actual risk must never exceed approved risk
    if actual_risk_amount > approved_risk_amount + Decimal("0.0001"):
        return SizingResult(
            is_valid=False,
            position_size=zero,
            actual_risk_amount=zero,
            actual_risk_pct=zero,
            stop_distance=stop_distance,
            loss_per_lot=loss_per_lot,
            error_th="ความเสี่ยงจากการคำนวณ Lot สูงกว่าที่ได้รับอนุมัติ (Quantization Safety Violation)",
        )

    return SizingResult(
        is_valid=True,
        position_size=quantized_volume,
        actual_risk_amount=actual_risk_amount,
        actual_risk_pct=actual_risk_pct,
        stop_distance=stop_distance,
        loss_per_lot=loss_per_lot,
        error_th=None,
    )
