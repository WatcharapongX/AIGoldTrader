import pytest

from app.services.risk.kill_switch import kill_switch_manager


@pytest.mark.asyncio
async def test_kill_switch_lifecycle_and_idempotency(db_session):
    session, _ = db_session

    # 1. Initial state is INACTIVE
    init_state = await kill_switch_manager.get_state(session)
    assert init_state.state == "INACTIVE"

    # 2. Activate Kill Switch
    active_state = await kill_switch_manager.activate(
        session=session,
        trigger_type="MANUAL",
        reason_th="ทดสอบการเปิดสวิตช์ฉุกเฉิน",
        activated_by="operator_01",
    )
    assert active_state.state == "ACTIVE"
    assert active_state.trigger_type == "MANUAL"
    assert active_state.activated_by == "operator_01"
    assert active_state.cleared_at is None

    # Check via check()
    check = await kill_switch_manager.check(session)
    assert check.is_active is True
    assert "ทดสอบการเปิดสวิตช์ฉุกเฉิน" in check.blocked_reason_th

    # Repeated activation is idempotent
    active_again = await kill_switch_manager.activate(
        session=session,
        trigger_type="MANUAL",
        reason_th="เปิดซ้ำ",
        activated_by="operator_02",
    )
    assert active_again.id == active_state.id
    assert active_again.activated_by == "operator_01"

    # 3. Clear Kill Switch
    cleared_state = await kill_switch_manager.clear(
        session=session,
        cleared_by="operator_01",
        reason_th="เคลียร์สถานะฉุกเฉินเพื่อกลับสู่สภาวะปกติ",
    )
    assert cleared_state.state == "INACTIVE"
    assert cleared_state.cleared_at is not None
    assert cleared_state.cleared_by == "operator_01"

    # Check via check()
    check_cleared = await kill_switch_manager.check(session)
    assert check_cleared.is_active is False
    assert check_cleared.blocked_reason_th is None
