"""Health / Readiness endpoints (docs/02 §10, FR-SE-04)."""

import logging
import time

from fastapi import APIRouter, Response
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine
from app.services.redis_client import redis_health

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

_started_at = time.monotonic()


@router.get("/healthz")
async def healthz() -> dict:
    """Process-level health — ตอบเสมอเมื่อ process ยังทำงาน."""
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "trading_mode": settings.trading_mode,
        "live_auto_trading": settings.live_auto_trading,
        "uptime_seconds": round(time.monotonic() - _started_at, 1),
    }


@router.get("/readyz")
async def readyz(response: Response) -> dict:
    """Readiness — DB ต้องพร้อมเสมอ, Redis ล่ม = degraded (ยัง ready แต่รายงาน)."""
    db_ok = False
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception:  # noqa: BLE001 — readiness ต้องรายงาน ไม่ใช่ raise
        # Connection errors can contain credentials/DSNs; do not log the exception.
        logger.warning("readiness: database check failed")

    redis_ok = await redis_health()

    if not db_ok:
        response.status_code = 503
    return {
        "status": "ready" if db_ok else "not_ready",
        "checks": {"database": db_ok, "redis": redis_ok},
        "redis_enabled": get_settings().redis_enabled,
    }
