"""Authenticated, allow-listed, read-only configuration status for FC-10.

This module intentionally never serializes ``Settings`` directly. Secret values,
credential-bearing URLs, filesystem paths, and connection topology remain server-side.
"""

import datetime as dt
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, ConfigDict

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.models import Role, User

router = APIRouter(prefix="/configuration", tags=["configuration"])

CredentialState = Literal["CONFIGURED", "MISSING", "NOT_REQUIRED", "NOT_EXPOSED"]


class SafeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TradingConfiguration(SafeModel):
    mode: str
    live_auto_trading: bool
    broker_execution: Literal["NONE"]
    account_provenance: Literal["CONFIGURED_PAPER", "UNAVAILABLE"]


class MarketConfiguration(SafeModel):
    provider: Literal["simulated", "mt5"]
    account_mode: Literal["DEMO", "LIVE"]
    configured_symbol: str | None
    server_timezone: str
    poll_seconds: float
    stale_after_seconds: int
    archive_real_ticks: bool
    terminal: CredentialState
    account_validation: CredentialState
    server_validation: CredentialState
    provenance: Literal["SIMULATED", "DEMO", "LIVE"]


class NewsConfiguration(SafeModel):
    provider: Literal["fixture", "unavailable", "xoomar", "forex_factory"]
    poll_seconds: int
    stale_after_seconds: int
    provenance: Literal["FIXTURE", "LIVE", "UNAVAILABLE"]


class AIConfiguration(SafeModel):
    mode: Literal["fixture", "external"]
    provider_type: Literal["fixture", "openai_compatible"]
    credential: CredentialState
    endpoint: Literal["DEFAULT_PROVIDER", "CUSTOM_ENDPOINT_CONFIGURED"]
    model_mapping: dict[str, str]
    max_concurrent_provider_calls: int
    queue_timeout_seconds: float
    provenance: Literal["FIXTURE", "EXTERNAL"]


class InfrastructureConfiguration(SafeModel):
    environment: str
    redis_enabled: bool


class SessionConfiguration(SafeModel):
    access_token_minutes: int
    refresh_session_days: int


class SafeConfigurationResponse(SafeModel):
    as_of: AwareDatetime
    authority: Literal["SERVER_CONFIGURATION"]
    restart_required: bool
    trading: TradingConfiguration
    market: MarketConfiguration
    news: NewsConfiguration
    ai: AIConfiguration
    infrastructure: InfrastructureConfiguration
    session: SessionConfiguration


def _presence(value: object, *, visible: bool, required: bool = True) -> CredentialState:
    if not required:
        return "NOT_REQUIRED"
    if not visible:
        return "NOT_EXPOSED"
    return "CONFIGURED" if bool(value) else "MISSING"


@router.get("/safe", response_model=SafeConfigurationResponse)
async def safe_configuration(user: User = Depends(get_current_user)) -> SafeConfigurationResponse:
    """Return a deliberately small configuration projection; never a Settings dump."""
    settings = get_settings()
    admin = user.role == Role.ADMIN
    mt5_required = settings.market_data_provider == "mt5"
    news_provenance = (
        "FIXTURE"
        if settings.news_calendar_provider == "fixture"
        else "UNAVAILABLE"
        if settings.news_calendar_provider == "unavailable"
        else "LIVE"
    )
    market_provenance = "SIMULATED" if settings.market_data_provider == "simulated" else settings.mt5_account_mode

    return SafeConfigurationResponse(
        as_of=dt.datetime.now(dt.UTC),
        authority="SERVER_CONFIGURATION",
        restart_required=True,
        trading=TradingConfiguration(
            mode=settings.trading_mode,
            live_auto_trading=settings.live_auto_trading,
            broker_execution="NONE",
            account_provenance="CONFIGURED_PAPER" if settings.trading_mode == "PAPER" else "UNAVAILABLE",
        ),
        market=MarketConfiguration(
            provider=settings.market_data_provider,
            account_mode=settings.mt5_account_mode,
            configured_symbol=settings.mt5_symbol_xauusd or None,
            server_timezone=settings.mt5_server_timezone,
            poll_seconds=settings.mt5_poll_seconds,
            stale_after_seconds=settings.market_stale_seconds,
            archive_real_ticks=settings.market_archive_real_ticks,
            terminal=_presence(settings.mt5_terminal_path, visible=admin, required=mt5_required),
            account_validation=_presence(settings.mt5_expected_login, visible=admin, required=mt5_required),
            server_validation=_presence(settings.mt5_expected_server, visible=admin, required=mt5_required),
            provenance=market_provenance,
        ),
        news=NewsConfiguration(
            provider=settings.news_calendar_provider,
            poll_seconds=(
                settings.news_real_poll_seconds
                if settings.news_calendar_provider in {"xoomar", "forex_factory"}
                else settings.news_config.provider_poll_seconds
            ),
            stale_after_seconds=settings.news_config.provider_stale_seconds,
            provenance=news_provenance,
        ),
        ai=AIConfiguration(
            mode=settings.ai_provider_mode,
            provider_type=settings.ai_provider_type,
            credential=_presence(
                settings.ai_provider_api_key,
                visible=admin,
                required=settings.ai_provider_mode == "external",
            ),
            endpoint=(
                "DEFAULT_PROVIDER"
                if settings.ai_provider_base_url == "https://api.openai.com/v1"
                else "CUSTOM_ENDPOINT_CONFIGURED"
            ),
            model_mapping=settings.ai_model_mapping,
            max_concurrent_provider_calls=settings.ai_max_concurrent_provider_calls,
            queue_timeout_seconds=settings.ai_provider_queue_timeout_seconds,
            provenance="FIXTURE" if settings.ai_provider_mode == "fixture" else "EXTERNAL",
        ),
        infrastructure=InfrastructureConfiguration(
            environment=settings.app_env,
            redis_enabled=settings.redis_enabled,
        ),
        session=SessionConfiguration(
            access_token_minutes=settings.jwt_access_token_expire_minutes,
            refresh_session_days=settings.jwt_refresh_token_expire_days,
        ),
    )
