"""Canonical pure SHA-256 identities for Batch D1 semantic contracts.

Decimal values use numeric-equivalence canonicalization: trailing fractional
zeroes are not semantic, so ``Decimal("10000.00")`` serializes as ``"10000"``.
"""

import datetime as dt
import hashlib
import json
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel

from app.services.market_data.domain import SECONDS, Candle, Timeframe
from app.services.news.domain import EconomicEvent, ObservedQuote


def canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("Non-finite Decimal is not canonical")
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in ("-0", "") else rendered


def canonical_datetime(value: dt.datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Naive datetime is not canonical")
    return value.astimezone(dt.UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return canonical_value(value.model_dump(mode="python"))
    if isinstance(value, Enum):
        return canonical_value(value.value)
    if isinstance(value, Decimal):
        return canonical_decimal(value)
    if isinstance(value, dt.datetime):
        return canonical_datetime(value)
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("Canonical mappings require string keys")
        return {key: canonical_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [canonical_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        raise TypeError("Float is not allowed in authoritative canonical data")
    raise TypeError(f"Unsupported canonical type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(canonical_value(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def semantic_fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def historical_data_fingerprint(
    *,
    symbol: str,
    source: str,
    candles: dict[Timeframe, tuple[Candle, ...]],
    news_events: tuple[EconomicEvent, ...] = (),
    quotes: tuple[ObservedQuote, ...] = (),
    news_source: str = "historical_unavailable",
    news_mode: str = "UNAVAILABLE",
    calendar_available: bool = False,
) -> str:
    """Bind a manifest to canonical semantic historical source content."""
    candle_sets = [
        {
            "timeframe": timeframe,
            "candles": tuple(sorted(values, key=lambda item: item.open_time)),
        }
        for timeframe, values in sorted(candles.items(), key=lambda item: SECONDS[item[0]])
    ]
    ordered_news = tuple(sorted(news_events, key=canonical_json))
    ordered_quotes = tuple(sorted(quotes, key=canonical_json))
    return semantic_fingerprint(
        {
            "kind": "historical-data-snapshot",
            "symbol": symbol,
            "source": source,
            "candles": candle_sets,
            "news_events": ordered_news,
            "quotes": ordered_quotes,
            "news_source": news_source,
            "news_mode": news_mode,
            "calendar_available": calendar_available,
        }
    )


def config_fingerprint(config: BaseModel) -> str:
    return semantic_fingerprint({"kind": "backtest-config", "value": config})


def resource_policy_fingerprint(policy: BaseModel) -> str:
    return semantic_fingerprint({"kind": "backtest-resource-policy", "value": policy})


def coverage_fingerprint(coverage: BaseModel) -> str:
    return semantic_fingerprint({"kind": "backtest-coverage", "value": coverage})


def data_provenance_fingerprint(provenance: BaseModel) -> str:
    return semantic_fingerprint({"kind": "backtest-provenance", "value": provenance})


def run_input_fingerprint(manifest: BaseModel) -> str:
    return semantic_fingerprint({"kind": "backtest-run-manifest", "value": manifest})


def replay_configuration_fingerprint(
    *,
    strategy_config: BaseModel,
    analysis_config: BaseModel,
    news_config: BaseModel,
    tick_size: Decimal | None,
    replay_engine_version: str,
) -> str:
    """Identity of every D2A configuration value consumed by replay."""
    return semantic_fingerprint(
        {
            "kind": "backtest-replay-configuration",
            "replay_engine_version": replay_engine_version,
            "strategy_config": strategy_config,
            "analysis_config": analysis_config,
            "news_config": news_config,
            "tick_size": tick_size,
        }
    )


def replay_input_fingerprint(*, manifest: BaseModel, configuration_fingerprint: str) -> str:
    """Complete executable D2A identity without conflating causal output."""
    return semantic_fingerprint(
        {
            "kind": "backtest-replay-input",
            "manifest_fingerprint": run_input_fingerprint(manifest),
            "configuration_fingerprint": configuration_fingerprint,
        }
    )
