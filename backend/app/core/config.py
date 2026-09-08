"""Application settings — ทุกค่ามาจาก Environment Variables (ห้าม hardcode: G-06)."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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
    rate_limit_auth_per_minute: int = 10
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

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    # Test override (unit tests run on SQLite via this URL)
    database_url_override: str | None = Field(default=None, repr=False)

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
