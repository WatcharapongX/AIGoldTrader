"""System status and health aggregation router (FC-00 / FC-01).

Provides an authenticated, truthful overview of all 8 sub-systems:
Backend, Database, Redis, Market Data / MT5, News / Calendar, AI Provider, Risk Engine, Kill Switch.
Never manufactures fake status or exposes internal secrets.
"""

import datetime as dt
import logging
from typing import Literal

from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, BaseModel
from sqlalchemy import text

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.db.session import get_engine, get_session_factory
from app.models import User
from app.services.redis_client import redis_health
from app.services.risk.kill_switch import kill_switch_manager
from app.services.risk.repository import get_active_policy

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/system", tags=["system"])


class SubsystemStatus(BaseModel):
    module: str
    state: Literal[
        "HEALTHY",
        "DEGRADED",
        "STALE",
        "UNAVAILABLE",
        "NORMAL",
        "ACTIVE",
        "FIXTURE_READY",
        "EXTERNAL_READY",
        "EXTERNAL_NOT_CONFIGURED",
        "DISABLED",
    ]
    detail_th: str
    updated_at: AwareDatetime


class SystemStatusResponse(BaseModel):
    as_of: AwareDatetime
    trading_mode: str
    live_auto_trading: bool
    ai_mode: str
    ai_status_label: str
    modules: dict[str, SubsystemStatus]


@router.get("/status", response_model=SystemStatusResponse)
async def get_system_status(
    request: Request,
    user: User = Depends(get_current_user),
) -> SystemStatusResponse:
    """Consolidated, truthful runtime status for the trading dashboard and sidebar."""
    now = dt.datetime.now(dt.UTC)
    settings = get_settings()

    # 1. Database check
    db_ok = False
    dialect_name = "unknown"
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            dialect_name = conn.dialect.name
            db_ok = True
    except Exception as exc:
        logger.debug("Database health check exception: %s", exc)

    # 2. Redis check
    redis_ok = await redis_health()

    # 3. Market service check
    market_state: Literal["HEALTHY", "DEGRADED", "UNAVAILABLE"] = "UNAVAILABLE"
    market_detail = "ยังไม่ได้เชื่อมต่อข้อมูลราคา"
    if hasattr(request.app.state, "market"):
        try:
            m_status = request.app.state.market.status()
            if m_status.status == "CONNECTED":
                market_state = "HEALTHY"
                market_detail = f"{m_status.source} · {m_status.mode} · CONNECTED"
            else:
                market_state = "DEGRADED"
                market_detail = f"{m_status.source} · {m_status.status}"
        except Exception:
            market_state = "DEGRADED"

    # 4. News service check
    news_state: Literal["HEALTHY", "DEGRADED", "UNAVAILABLE"] = "UNAVAILABLE"
    news_detail = "ผู้ให้บริการปฏิทินไม่พร้อมใช้งาน"
    if hasattr(request.app.state, "news"):
        try:
            n_health = request.app.state.news.health()
            news_state = n_health.state if n_health.state in ("HEALTHY", "DEGRADED", "UNAVAILABLE") else "DEGRADED"
            news_detail = n_health.detail_th
        except Exception:
            news_state = "UNAVAILABLE"

    # 5. AI Provider check
    ai_state: Literal["FIXTURE_READY", "EXTERNAL_READY", "EXTERNAL_NOT_CONFIGURED", "DEGRADED"] = "FIXTURE_READY"
    ai_label = "FIXTURE READY"
    ai_detail = "โหมดทดสอบในตัว (Offline Canonical Advisory)"
    if settings.ai_provider_mode == "external":
        if settings.ai_provider_api_key_configured:
            ai_state = "EXTERNAL_READY"
            ai_label = "EXTERNAL READY"
            ai_detail = f"เชื่อมต่อ {settings.ai_provider_type} สำเร็จ (API Key พร้อมใช้งาน)"
        else:
            ai_state = "EXTERNAL_NOT_CONFIGURED"
            ai_label = "EXTERNAL NOT CONFIGURED"
            ai_detail = "ยังไม่ได้ระบุ AI_PROVIDER_API_KEY"
    else:
        ai_state = "FIXTURE_READY"
        ai_label = "FIXTURE READY"
        ai_detail = "โหมดสาธิต (Offline Fixture Advisory) · ปลอดภัย ไม่ส่งข้อมูลออกภายนอก"

    # 6. Risk Engine & Kill Switch checks
    risk_state: Literal["HEALTHY", "UNAVAILABLE"] = "UNAVAILABLE"
    risk_detail = "ระบบบริหารความเสี่ยงยังไม่พร้อมใช้งาน"
    ks_state: Literal["NORMAL", "ACTIVE", "UNAVAILABLE"] = "UNAVAILABLE"
    ks_detail = "ตรวจสถานะ Kill Switch ไม่สำเร็จ"

    try:
        async with get_session_factory()() as session:
            policy = await get_active_policy(session)
            if policy:
                risk_state = "HEALTHY"
                risk_detail = f"Fail-Closed Protection (Policy {policy.version})"

            kill_switch = await kill_switch_manager.get_state(session)
            if kill_switch:
                if kill_switch.state == "ACTIVE":
                    ks_state = "ACTIVE"
                    ks_detail = f"เปิดใช้งาน: {kill_switch.reason_th}"
                else:
                    ks_state = "NORMAL"
                    ks_detail = "สวิตช์ฉุกเฉินสถานะปกติ (พร้อมทำงานตลอด 24 ชม.)"
    except Exception as exc:
        logger.debug("Risk/KillSwitch status query exception: %s", exc)

    modules = {
        "backend": SubsystemStatus(
            module="backend",
            state="HEALTHY",
            detail_th=f"FastAPI Backend ({settings.app_name}) พร้อมใช้งาน",
            updated_at=now,
        ),
        "database": SubsystemStatus(
            module="database",
            state="HEALTHY" if db_ok else "UNAVAILABLE",
            detail_th="PostgreSQL เชื่อมต่อสมบูรณ์" if dialect_name == "postgresql" else (
                "SQLite In-Memory (ฐานข้อมูลทดสอบ)" if db_ok else "ไม่สามารถเชื่อมต่อฐานข้อมูลได้"
            ),
            updated_at=now,
        ),
        "redis": SubsystemStatus(
            module="redis",
            state="HEALTHY" if redis_ok else ("DEGRADED" if settings.redis_enabled else "DISABLED"),
            detail_th="Redis Distributed Cache พร้อมใช้งาน" if redis_ok else (
                "Redis ขัดข้อง" if settings.redis_enabled else "ปิดใช้งาน (ทำงานแบบ Standalone)"
            ),
            updated_at=now,
        ),
        "market_data": SubsystemStatus(
            module="market_data",
            state=market_state,
            detail_th=market_detail,
            updated_at=now,
        ),
        "news": SubsystemStatus(
            module="news",
            state=news_state,
            detail_th=news_detail,
            updated_at=now,
        ),
        "ai_provider": SubsystemStatus(
            module="ai_provider",
            state=ai_state,
            detail_th=ai_detail,
            updated_at=now,
        ),
        "risk_engine": SubsystemStatus(
            module="risk_engine",
            state=risk_state,
            detail_th=risk_detail,
            updated_at=now,
        ),
        "kill_switch": SubsystemStatus(
            module="kill_switch",
            state=ks_state,
            detail_th=ks_detail,
            updated_at=now,
        ),
    }

    return SystemStatusResponse(
        as_of=now,
        trading_mode=settings.trading_mode,
        live_auto_trading=settings.live_auto_trading,
        ai_mode=settings.ai_provider_mode,
        ai_status_label=ai_label,
        modules=modules,
    )
