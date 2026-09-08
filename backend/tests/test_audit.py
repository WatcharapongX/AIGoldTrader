"""Audit + masking — TASK-017 / TASK-019 DoD evidence."""

from sqlalchemy import select

from app.core.masking import mask_payload
from app.models import AuditLog
from app.services import audit


def test_mask_payload_masks_sensitive_keys() -> None:
    payload = {
        "username": "admin",
        "password": "super-secret",
        "nested": {"api_key": "sk-123", "token": "abc", "note": "ok"},
        "list": [{"secret_value": "x", "plain": "y"}],
    }
    masked = mask_payload(payload)
    assert masked["username"] == "admin"
    assert masked["password"] == "***MASKED***"
    assert masked["nested"]["api_key"] == "***MASKED***"
    assert masked["nested"]["note"] == "ok"
    assert masked["list"][0]["secret_value"] == "***MASKED***"
    # original ไม่ถูกแก้
    assert payload["password"] == "super-secret"


async def test_audit_write_masks_credentials(db_session) -> None:
    session, _ = db_session
    await audit.write_audit(
        session,
        action="TEST_ACTION",
        entity="test",
        after={"name": "X", "password": "plain-secret"},
    )
    await session.commit()

    result = await session.execute(select(AuditLog).where(AuditLog.action == "TEST_ACTION"))
    entry = result.scalars().one()
    assert entry.after["password"] == "***MASKED***"
    assert entry.after["name"] == "X"
    assert entry.correlation_id  # มี correlation id เสมอ (FR-SE-03)
