"""Application settings — ทุกค่ามาจาก Environment Variables (ห้าม hardcode: G-06)."""

from decimal import Decimal
from functools import lru_cache
from ipaddress import ip_network
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError

from app.services.analysis.domain import AnalysisConfig
from app.services.news.domain import NewsConfig
from app.services.risk.domain import RiskPolicy
from app.services.strategy.domain import StrategyConfig


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    strategy_config: StrategyConfig = Field(default_factory=StrategyConfig)
    risk_policy: RiskPolicy = Field(default_factory=RiskPolicy)

    news_calendar_provider: Literal["fixture", "unavailable", "xoomar", "forex_factory"] = "unavailable"
    news_real_poll_seconds: int = Field(default=300, ge=60, le=3600)
    news_config: NewsConfig = Field(default_factory=NewsConfig)

    # App
    app_name: str = "ai-trading-platform"
    app_env: str = "DEV"
    debug: bool = True

    # Trading safety (docs/01 G-01, G-03)
    trading_mode: str = "PAPER"
    live_auto_trading: bool = False

    # Security
    secret_key: str = Field(default="", repr=False)
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    cors_origins: str = "http://localhost:3000"
    rate_limit_auth_per_minute: int = Field(default=10, ge=1, le=1000)
    rate_limit_max_keys: int = Field(default=10000, ge=2, le=100000)
    trust_proxy: bool = False
    trusted_proxy_cidrs: str = ""
    rate_limit_api_per_minute: int = 120

    # Database
    database_connection_url: str | None = Field(default=None, validation_alias="DATABASE_URL", repr=False)
    # Compatibility with the existing optional Compose deployment.
    postgres_host: str | None = None
    postgres_port: int | None = None
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = Field(default=None, repr=False)

    # Redis — optional in Phase 1; no distributed state consumers yet.
    redis_enabled: bool = False
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0

    # Phase 2 native single-instance market data; provider credentials never enter the browser.
    market_data_provider: Literal["simulated", "mt5"] = "simulated"
    market_stale_seconds: int = Field(default=5, ge=2, le=300)
    market_max_jump_ratio: Decimal = Field(default=Decimal("0.05"), gt=0, le=1)
    market_max_spread: Decimal = Field(default=Decimal("10"), gt=0)

    # Read-only MT5 IPC uses an already authenticated terminal session.
    mt5_terminal_path: str = Field(default="", repr=False)
    mt5_symbol_xauusd: str = Field(default="", max_length=64)
    mt5_feed_id: str = Field(default="", pattern=r"^[a-z0-9_]{0,16}$")
    mt5_expected_server: str = Field(default="", repr=False)
    mt5_expected_login: int | None = Field(default=None, repr=False)
    mt5_account_mode: Literal["DEMO", "LIVE"] = "DEMO"
    mt5_server_timezone: str = "UTC"
    mt5_future_tolerance_seconds: int = Field(default=2, ge=0, le=10)
    mt5_poll_seconds: float = Field(default=1, ge=1, le=10)
    mt5_timeout_ms: int = Field(default=10000, ge=1000, le=30000)
    # Real tick archival is explicitly disabled until an operator retention policy exists.
    market_archive_real_ticks: bool = False

    # Phase 3 deterministic parameters; optional ANALYSIS_CONFIG JSON, no credentials.
    analysis_config: AnalysisConfig = Field(default_factory=AnalysisConfig)

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Test override (unit tests run on SQLite via this URL)
    database_url_override: str | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_proxy_boundary(self):
        networks = [value.strip() for value in self.trusted_proxy_cidrs.split(",") if value.strip()]
        if self.trust_proxy and not networks:
            raise ValueError("TRUST_PROXY requires explicit TRUSTED_PROXY_CIDRS")
        try:
            if any(ip_network(value, strict=False).prefixlen == 0 for value in networks):
                raise ValueError("Unrestricted proxy trust is forbidden")
        except ValueError:
            raise ValueError("TRUSTED_PROXY_CIDRS must contain bounded IP networks") from None
        return self

    @field_validator("trading_mode")
    @classmethod
    def _validate_trading_mode(cls, v: str) -> str:
        allowed = {"BACKTEST", "PAPER", "SEMI_AUTO", "LIVE"}
        if v not in allowed:
            msg = f"TRADING_MODE must be one of {sorted(allowed)}, got {v!r}"
            raise ValueError(msg)
        return v

    @field_validator("cors_origins")
    @classmethod
    def _split_origins(cls, v: str) -> str:
        # keep raw string; accessor below splits
        return v

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        if self.database_connection_url:
            try:
                url = make_url(self.database_connection_url)
                if url.drivername not in {"postgresql", "postgresql+psycopg"}:
                    raise ValueError("Unsupported database driver")
                if not all((url.host, url.port, url.database, url.username, url.password)):
                    raise ValueError("Incomplete database connection")
            except (ArgumentError, ValueError, TypeError):
                raise ValueError("DATABASE_URL must be a complete PostgreSQL URL with an explicit port") from None
            return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
        if not all((self.postgres_host, self.postgres_port, self.postgres_db,
                    self.postgres_user, self.postgres_password)):
            raise ValueError("Set DATABASE_URL or all POSTGRES_* connection settings")
        return URL.create(
            "postgresql+psycopg", username=self.postgres_user, password=self.postgres_password,
            host=self.postgres_host, port=self.postgres_port, database=self.postgres_db,
        ).render_as_string(hide_password=False)

    def validate_runtime_secrets(self) -> None:
        if len(self.secret_key.encode()) < 32 or self.secret_key.startswith("change-me"):
            raise ValueError("Set SECRET_KEY to a private random value of at least 32 bytes")

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
