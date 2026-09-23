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

    # Auth & Cookie Security (Batch B2, AUD-P2-002)
    auth_cookie_name: str | None = None
    auth_cookie_secure: bool | None = None
    auth_trusted_origins: str = ""

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

    # Phase 6.2 AI Provider Configuration (Safe local default: fixture, G-06: no hardcoded credentials)
    ai_provider_mode: Literal["fixture", "external"] = "fixture"
    ai_provider_type: Literal["fixture", "openai_compatible"] = "fixture"
    ai_provider_api_key: str = Field(default="", repr=False)
    ai_provider_base_url: str = "https://api.openai.com/v1"
    ai_model_mapping: dict[str, str] = Field(
        default_factory=lambda: {
            "fast-advisory": "gpt-4o-mini",
            "reasoning-advisory": "gpt-4o",
            "deep-analysis": "gpt-4o",
        }
    )
    ai_max_concurrent_provider_calls: int = Field(default=6, ge=1, le=32)
    ai_provider_queue_timeout_seconds: float = Field(default=15.0, gt=0.0, le=60.0)
    # C2 request-scoped ceiling. Defaults fund 7 logical calls (six agents +
    # Meta), each with the default one permitted retry, while remaining finite.
    ai_analysis_max_provider_attempts: int = Field(default=14, ge=1, le=256)
    ai_analysis_max_prompt_tokens: int = Field(default=114_688, ge=1, le=16_000_000)
    ai_analysis_max_completion_tokens: int = Field(default=14_336, ge=1, le=2_000_000)
    ai_analysis_max_total_tokens: int = Field(default=129_024, ge=1, le=18_000_000)
    ai_analysis_max_measured_bytes: int = Field(default=560_000, ge=1, le=64_000_000)
    ai_analysis_deadline_seconds: float = Field(default=30.0, ge=0.01, le=300.0)

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
        if self.ai_provider_mode == "external" and self.ai_provider_type == "fixture":
            raise ValueError(
                "Invalid configuration: ai_provider_mode='external' cannot use ai_provider_type='fixture'"
            )
        if self.ai_provider_mode == "fixture" and self.ai_provider_type != "fixture":
            raise ValueError(
                "Invalid configuration: ai_provider_mode='fixture' requires ai_provider_type='fixture'"
            )
        if self.ai_provider_mode == "external":
            from app.services.ai.provider import ModelBinding, validate_provider_base_url

            api_key = self.ai_provider_api_key.strip()
            if not api_key:
                raise ValueError("External AI provider requires non-empty ai_provider_api_key")
            if not self.ai_model_mapping:
                raise ValueError("External AI provider requires non-empty ai_model_mapping")
            for alias, model in self.ai_model_mapping.items():
                ModelBinding(alias=alias, model=model)
            validate_provider_base_url(self.ai_provider_base_url, active_secret=api_key)
        return self

    @field_validator("ai_provider_base_url")
    @classmethod
    def _validate_ai_provider_base_url(cls, v: str) -> str:
        from app.services.ai.provider import validate_provider_base_url

        return validate_provider_base_url(v)

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
        if not all(
            (self.postgres_host, self.postgres_port, self.postgres_db, self.postgres_user, self.postgres_password)
        ):
            raise ValueError("Set DATABASE_URL or all POSTGRES_* connection settings")
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    @property
    def effective_auth_cookie_name(self) -> str:
        if self.auth_cookie_name:
            return self.auth_cookie_name
        return "__Host-aigold_refresh" if self.app_env in {"PROD", "UAT"} else "aigold_refresh_dev"

    @property
    def effective_auth_cookie_secure(self) -> bool:
        if self.auth_cookie_secure is not None:
            return self.auth_cookie_secure
        return self.app_env in {"PROD", "UAT"}

    @staticmethod
    def _normalize_single_origin(raw: str) -> str | None:
        from urllib.parse import urlsplit

        s = raw.strip()
        if not s or s == "*":
            return s
        parts = urlsplit(s)
        if not parts.scheme or not parts.netloc:
            return s.rstrip("/")
        # Reconstruct scheme://netloc strictly (strips paths, queries, fragments, trailing slashes)
        netloc = parts.netloc.lower()
        return f"{parts.scheme.lower()}://{netloc}"

    @property
    def auth_trusted_origin_list(self) -> list[str]:
        raw_list = [o.strip() for o in self.auth_trusted_origins.split(",") if o.strip()]
        if not raw_list:
            raw_list = self.cors_origin_list
        normalized: list[str] = []
        for origin in raw_list:
            norm = self._normalize_single_origin(origin)
            if norm and norm not in normalized:
                normalized.append(norm)
        return normalized

    def validate_runtime_secrets(self) -> None:
        if len(self.secret_key.encode()) < 32 or self.secret_key.startswith("change-me"):
            raise ValueError("Set SECRET_KEY to a private random value of at least 32 bytes")

        cookie_name = self.effective_auth_cookie_name
        cookie_secure = self.effective_auth_cookie_secure
        trusted_origins = self.auth_trusted_origin_list

        if self.app_env in {"PROD", "UAT"}:
            if not cookie_secure:
                raise ValueError("PROD/UAT requires secure refresh cookie (auth_cookie_secure=True)")
            if not cookie_name.startswith("__Host-"):
                raise ValueError("PROD/UAT requires __Host- prefix for refresh cookie name")
            if not trusted_origins:
                raise ValueError("PROD/UAT requires explicit non-empty trusted origins")
            for origin in trusted_origins:
                if origin == "*" or "*" in origin:
                    raise ValueError("Wildcard origins are strictly forbidden for auth trusted origins")
                if not origin.startswith("https://"):
                    raise ValueError(f"PROD/UAT trusted origins must use HTTPS: {origin}")
        else:
            if not cookie_secure and cookie_name.startswith("__Host-"):
                raise ValueError("Insecure cookie cannot use __Host- prefix")

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def ai_provider_api_key_configured(self) -> bool:
        """Safe internal readiness flag; the credential value never leaves the server."""
        return bool(self.ai_provider_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def configure_ai_provider_runtime(settings: Settings) -> None:
    """Wire application Settings to runtime AI Provider executor and limits."""
    from app.services.ai.execution import provider_executor

    provider_executor.configure_concurrency(
        max_concurrent=settings.ai_max_concurrent_provider_calls,
        queue_timeout_seconds=settings.ai_provider_queue_timeout_seconds,
    )
