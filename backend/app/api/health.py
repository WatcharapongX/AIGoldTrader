"""Health / Readiness endpoints (docs/02 §10, FR-SE-04)."""

import logging
import time
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel
from sqlalchemy import text

from app.core.config import get_settings
from app.db.session import get_engine
from app.services.redis_client import redis_health

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])

_started_at = time.monotonic()


class HealthResponse(BaseModel):
    status: Literal["ok"]
    app: str
    env: str
    trading_mode: str
    live_auto_trading: bool
    uptime_seconds: float


class ReadyChecks(BaseModel):
    database: bool
    redis: bool | None


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: ReadyChecks
    redis_enabled: bool


@router.get("/healthz", response_model=HealthResponse)
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


@router.get("/readyz", response_model=ReadyResponse, responses={503: {"model": ReadyResponse}})
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
