"""Phase 5 Risk Engine domain contracts. All financial calculations use safe Decimal precision."""

import datetime as dt
import hashlib
import json
from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

VERSION = "risk-1.0.0"
POLICY_VERSION = "risk-policy-1.0.0"

Decision = Literal["APPROVED", "REDUCED", "BLOCKED"]
Direction = Literal["LONG", "SHORT"]
KillSwitchTrigger = Literal[
    "MANUAL",
    "AUTOMATIC_DAILY_LOSS",
    "AUTOMATIC_DRAWDOWN",
    "AUTOMATIC_DATA_HEALTH",
    "AUTOMATIC_SYSTEM_HEALTH",
]
KillSwitchStatus = Literal["ACTIVE", "INACTIVE", "UNKNOWN"]
ReservationStatus = Literal["ACTIVE", "RELEASED", "EXPIRED"]


def fingerprint(value: object) -> str:
    def encode(item: object) -> object:
        if isinstance(item, BaseModel):
            return item.model_dump(mode="json")
        if isinstance(item, (dt.datetime, dt.date)):
            return item.isoformat()
        if isinstance(item, Decimal):
            return format(item, "f")
        raise TypeError(type(item).__name__)

    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=encode, ensure_ascii=False).encode()
    ).hexdigest()


class RiskPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = POLICY_VERSION
    max_risk_per_trade_pct: Decimal = Field(default=Decimal("1.0"), gt=0, le=Decimal("5.0"))
    min_risk_per_trade_pct: Decimal = Field(default=Decimal("0.1"), gt=0, le=Decimal("1.0"))
    max_account_risk_pct: Decimal = Field(default=Decimal("3.0"), gt=0, le=Decimal("10.0"))
    max_symbol_risk_pct: Decimal = Field(default=Decimal("2.0"), gt=0, le=Decimal("10.0"))
    max_directional_risk_pct: Decimal = Field(default=Decimal("2.0"), gt=0, le=Decimal("10.0"))
    max_concurrent_trades: int = Field(default=3, ge=1, le=10)
    daily_loss_limit_pct: Decimal = Field(default=Decimal("3.0"), gt=0, le=Decimal("10.0"))
    weekly_loss_limit_pct: Decimal = Field(default=Decimal("6.0"), gt=0, le=Decimal("20.0"))
    max_drawdown_pct: Decimal = Field(default=Decimal("10.0"), gt=0, le=Decimal("30.0"))
    cooldown_consecutive_losses: int = Field(default=3, ge=1, le=10)
    cooldown_period_minutes: int = Field(default=60, ge=5, le=1440)
    max_spread_multiplier: Decimal = Field(default=Decimal("2.0"), gt=1, le=10)
    max_spread_absolute: Decimal = Field(default=Decimal("1.50"), gt=0, le=10)
    quote_freshness_seconds: int = Field(default=5, ge=1, le=60)
    account_freshness_seconds: int = Field(default=60, ge=5, le=3600)
    symbol_spec_freshness_seconds: int = Field(default=86400, ge=60, le=604800)
    news_risk_enabled: bool = True
    news_high_impact_blackout_pre_minutes: int = Field(default=5, ge=1, le=60)
    news_high_impact_pre_minutes: int = Field(default=15, ge=1, le=120)
    news_high_impact_post_minutes: int = Field(default=15, ge=1, le=120)
    news_reduction_factor: Decimal = Field(default=Decimal("0.5"), gt=0, lt=1)
    min_volume: Decimal = Field(default=Decimal("0.01"), gt=0)
    max_volume: Decimal = Field(default=Decimal("10.00"), gt=0)
    volume_step: Decimal = Field(default=Decimal("0.01"), gt=0)
    reservation_ttl_seconds: int = Field(default=300, ge=30, le=1800)
    data_health_consecutive_failures: int = Field(default=3, ge=1, le=10)

    @model_validator(mode="after")
    def validate_policy(self):
        if self.min_risk_per_trade_pct > self.max_risk_per_trade_pct:
            raise ValueError("min_risk_per_trade_pct cannot exceed max_risk_per_trade_pct")
        if self.max_risk_per_trade_pct > self.max_account_risk_pct:
            raise ValueError("max_risk_per_trade_pct cannot exceed max_account_risk_pct")
        if self.max_symbol_risk_pct > self.max_account_risk_pct:
            raise ValueError("max_symbol_risk_pct cannot exceed max_account_risk_pct")
        if self.max_directional_risk_pct > self.max_account_risk_pct:
            raise ValueError("max_directional_risk_pct cannot exceed max_account_risk_pct")
        if self.news_high_impact_blackout_pre_minutes > self.news_high_impact_pre_minutes:
            raise ValueError("blackout window must be within pre-news window")
        if self.min_volume > self.max_volume:
            raise ValueError("min_volume cannot exceed max_volume")
        return self


class SymbolSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    symbol: str
    source: str
    tick_size: Decimal = Field(gt=0)
    tick_value: Decimal = Field(gt=0)
    contract_size: Decimal = Field(gt=0)
    volume_min: Decimal = Field(gt=0)
    volume_max: Decimal = Field(gt=0)
    volume_step: Decimal = Field(gt=0)
    digits: int = Field(ge=0, le=5)
    observed_at: AwareDatetime
    broker_server: str | None = None

    @field_validator("observed_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)

    @model_validator(mode="after")
    def validate_spec(self):
        if self.volume_min > self.volume_max:
            raise ValueError("volume_min cannot exceed volume_max")
        if self.volume_step <= 0 or self.volume_step > self.volume_min:
            raise ValueError("volume_step must be positive and not exceed volume_min")
        return self


def default_gold_spec(source: str = "simulated", observed_at: dt.datetime | None = None) -> SymbolSpecification:
    at = observed_at or dt.datetime.now(dt.UTC)
    spec_id = fingerprint({"symbol": "XAUUSD", "source": source, "observed_at": at.isoformat()})[:32]
    return SymbolSpecification(
        id=f"sym_{spec_id}",
        symbol="XAUUSD",
        source=source,
        tick_size=Decimal("0.01"),
        tick_value=Decimal("1.00"),
        contract_size=Decimal("100.00"),
        volume_min=Decimal("0.01"),
        volume_max=Decimal("10.00"),
        volume_step=Decimal("0.01"),
        digits=2,
        observed_at=at,
    )


class AccountSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    account_id: str
    balance: Decimal = Field(ge=0)
    equity: Decimal = Field(ge=0)
    free_margin: Decimal | None = None
    daily_realized_pnl: Decimal = Decimal("0.00")
    weekly_realized_pnl: Decimal = Decimal("0.00")
    floating_pnl: Decimal | None = None
    peak_equity: Decimal = Field(ge=0)
    open_risk_pct: Decimal = Field(default=Decimal("0.0000"), ge=0)
    reserved_risk_pct: Decimal = Field(default=Decimal("0.0000"), ge=0)
    consecutive_losses: int = Field(default=0, ge=0)
    last_loss_at: AwareDatetime | None = None
    cooldown_until: AwareDatetime | None = None
    open_positions_count: int = 0
    state_version: int = 1
    state_updated_at: AwareDatetime | None = None
    observed_at: AwareDatetime | None = None
    trading_mode: Literal["PAPER", "BACKTEST", "SEMI_AUTO", "LIVE"] = "PAPER"
    source: Literal[
        "CONFIGURED_TEST",
        "CONFIGURED_PAPER",
        "PAPER_SNAPSHOT",
        "PAPER_ACCOUNT_STATE",
        "UNAVAILABLE",
        "MT5_DEMO",
        "MT5_REAL",
    ] = "CONFIGURED_TEST"
    as_of: AwareDatetime

    @field_validator("as_of", "state_updated_at", "observed_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None

    @model_validator(mode="after")
    def validate_equity(self):
        if self.peak_equity < self.equity and self.equity > 0:
            object.__setattr__(self, "peak_equity", self.equity)
        return self


class MarketProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: str
    mode: str
    quote_timestamp: AwareDatetime
    quote_bid: Decimal
    quote_ask: Decimal
    quote_spread: Decimal
    is_stale: bool = False


class NewsEventAudit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    event_name: str
    currency: str
    impact: str
    scheduled_at: AwareDatetime
    available_at: AwareDatetime | None = None
    window_state: str = ""
    provider: str = ""
    revision_id: str = ""
    source: str = ""
    revision_version: int | None = None

    @field_validator("scheduled_at", "available_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime | None) -> dt.datetime | None:
        return v.astimezone(dt.UTC) if v is not None else None

    @model_validator(mode="after")
    def sync_aliases(self):
        prov = self.provider or self.source
        src = self.source or self.provider
        rev_id = self.revision_id or (str(self.revision_version) if self.revision_version is not None else "")
        rev_ver = self.revision_version
        if rev_ver is None and self.revision_id:
            try:
                rev_ver = int(self.revision_id)
            except ValueError:
                pass
        object.__setattr__(self, "provider", prov)
        object.__setattr__(self, "source", src)
        object.__setattr__(self, "revision_id", rev_id)
        object.__setattr__(self, "revision_version", rev_ver)
        return self


class NewsRiskProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    news_state: str
    in_blackout: bool
    in_pre_news_window: bool
    in_post_news_window: bool
    event_ids: tuple[str, ...] = ()
    description_th: str = ""
    events: tuple[NewsEventAudit, ...] = ()
    provider: str = ""
    revision_id: str = ""
    source: str = ""
    revision_version: int | None = None

    @model_validator(mode="after")
    def sync_aliases(self):
        prov = self.provider or self.source
        src = self.source or self.provider
        rev_id = self.revision_id or (str(self.revision_version) if self.revision_version is not None else "")
        rev_ver = self.revision_version
        if rev_ver is None and self.revision_id:
            try:
                rev_ver = int(self.revision_id)
            except ValueError:
                pass
        object.__setattr__(self, "provider", prov)
        object.__setattr__(self, "source", src)
        object.__setattr__(self, "revision_id", rev_id)
        object.__setattr__(self, "revision_version", rev_ver)
        return self


class RiskDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    evaluation_intent_id: str = ""
    candidate_id: str
    plan_id: str
    strategy_id: str
    strategy_version: str
    profile_id: str
    symbol: str
    direction: Direction
    decision: Decision
    requested_risk_pct: Decimal = Field(ge=0)
    approved_risk_pct: Decimal = Field(ge=0)
    requested_risk_amount: Decimal = Field(ge=0)
    approved_risk_amount: Decimal = Field(ge=0)
    position_size: Decimal = Field(ge=0)
    entry_lower: Decimal = Field(gt=0)
    entry_upper: Decimal = Field(gt=0)
    stop_loss: Decimal = Field(gt=0)
    stop_distance: Decimal = Field(ge=0)
    portfolio_exposure_before: Decimal = Field(ge=0)
    portfolio_exposure_after: Decimal = Field(ge=0)
    account_id: str = ""
    account_snapshot_id: str
    symbol_specification_id: str
    policy_version: str
    reasons_th: tuple[str, ...] = ()
    warnings_th: tuple[str, ...] = ()
    blocked_reasons_th: tuple[str, ...] = ()
    as_of: AwareDatetime
    expires_at: AwareDatetime
    dependency_fingerprint: str = ""
    trade_plan_fingerprint: str = ""
    market_provenance: MarketProvenance | None = None
    news_provenance: NewsRiskProvenance | None = None
    execution_blocked: Literal["NO_EXECUTION_ANALYSIS_ONLY"] = "NO_EXECUTION_ANALYSIS_ONLY"

    @field_validator("as_of", "expires_at")
    @classmethod
    def utc_clock(cls, v: dt.datetime) -> dt.datetime:
        return v.astimezone(dt.UTC)


class RiskReservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    decision_id: str
    account_id: str
    candidate_id: str | None = None
    profile_id: str
    symbol: str
    direction: Direction
    risk_pct: Decimal = Field(gt=0)
    risk_amount: Decimal = Field(gt=0)
    position_size: Decimal = Field(gt=0)
    status: ReservationStatus = "ACTIVE"
    reserved_at: AwareDatetime
    reserved_until: AwareDatetime
    released_at: AwareDatetime | None = None
    release_reason: str | None = None


class KillSwitchState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    state: KillSwitchStatus
    trigger_type: KillSwitchTrigger
    reason_th: str
    activated_at: AwareDatetime
    activated_by: str
    cleared_at: AwareDatetime | None = None
    cleared_by: str | None = None
    policy_version: str = POLICY_VERSION


class PortfolioRiskSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str
    account_source: str = "CONFIGURED_PAPER"
    as_of: AwareDatetime
    open_risk_pct: Decimal = Field(ge=0)
    reserved_risk_pct: Decimal = Field(ge=0)
    total_risk_pct: Decimal = Field(ge=0)
    max_account_risk_pct: Decimal = Field(ge=0)
    available_risk_pct: Decimal = Field(ge=0)
    symbol_risk_pct: dict[str, Decimal] = Field(default_factory=dict)
    directional_risk_pct: dict[Direction, Decimal] = Field(default_factory=dict)
    active_reservations: tuple[RiskReservation, ...] = ()
    active_reservations_count: int = 0
    kill_switch_active: bool = False
    kill_switch_state: KillSwitchState | None = None
    daily_loss_pct: Decimal = Field(ge=0)
    weekly_loss_pct: Decimal = Field(ge=0)
    drawdown_pct: Decimal = Field(ge=0)
    in_cooldown: bool = False
    cooldown_until: AwareDatetime | None = None


class RiskEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    profile_id: str
    account_id: str = "default_paper_account"
    requested_risk_pct: Decimal | None = None
    as_of: AwareDatetime | None = None
