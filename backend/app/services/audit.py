"""Audit Logging Service — จุดเขียน audit_logs เดียวของระบบ (TASK-017, FR-SE-03)."""

import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.correlation import get_correlation_id, normalize_correlation_id
from app.core.masking import mask_payload
from app.models import AuditLog

logger = logging.getLogger(__name__)


async def write_audit(
    session: AsyncSession,
    *,
    action: str,
    entity: str,
    entity_id: str | uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
    before: dict | None = None,
    after: dict | None = None,
    reason: str | None = None,
    source: str = "API",
    ip: str | None = None,
    correlation_id: str | None = None,
) -> AuditLog:
    """บันทึก audit event — mask sensitive fields ก่อนเก็บเสมอ (FR-SE-02)."""
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id else None,
        before=mask_payload(before),
        after=mask_payload(after),
        reason=reason,
        source=source,
        correlation_id=normalize_correlation_id(correlation_id or get_correlation_id()),
        ip=ip,
    )
    session.add(entry)
    await session.flush()
    logger.info("audit", extra={"audit_action": action, "entity": entity, "entity_id": entry.entity_id})
    return entry
