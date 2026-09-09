"""Bounded closed-window cache; forming ticks never execute the analysis engine."""

import asyncio
import datetime as dt
import hashlib
import logging
import time
from collections import OrderedDict

from app.services.analysis.domain import AnalysisConfig, AnalysisResponse, AnalysisSnapshot
from app.services.analysis.engine import AnalysisInputError, analyze
from app.services.market_data.domain import Candle

logger = logging.getLogger(__name__)


class AnalysisService:
    def __init__(self):
        self.generated: dict[tuple, dt.datetime] = {}
        self.cache: OrderedDict[tuple, AnalysisSnapshot] = OrderedDict()
        self.lock = asyncio.Lock()
        self.calculations = 0
        self.hits = 0

    async def snapshot(self, candles, symbol, timeframe, source, requested=300, config=None):
        config = config or AnalysisConfig()
        if len(candles) > 1000 or len(candles) > requested or not 1 <= requested <= 1000:
            raise AnalysisInputError("Analysis input exceeds bounded window")
        previous = None
        for index, item in enumerate(candles):
            try:
                candle = Candle.model_validate(item.model_dump())
            except (ValueError, TypeError, AttributeError):
                raise AnalysisInputError("Invalid canonical candle") from None
            if (
                (candle.symbol, candle.timeframe, candle.source) != (symbol, timeframe, source)
                or (previous is not None and candle.open_time <= previous)
                or (not candle.is_closed and index != len(candles) - 1)
            ):
                raise AnalysisInputError("Invalid canonical candle sequence")
            previous = candle.open_time
        # Include all closed values so provider corrections invalidate deterministically.
        digest = hashlib.sha256("".join(c.model_dump_json() for c in candles if c.is_closed).encode()).hexdigest()
        key = (symbol, timeframe, source, requested, len(candles), config.model_dump_json(), digest)
        async with self.lock:
            if key in self.cache:
                self.hits += 1
                self.cache.move_to_end(key)
                return self.cache[key].model_copy(deep=True)
            start = time.perf_counter()
            result = await asyncio.to_thread(analyze, candles, symbol, timeframe, source, requested, config)
            self.calculations += 1
            self.cache[key] = result
            self.generated[key] = dt.datetime.now(dt.UTC)
            while len(self.cache) > 32:
                removed, _ = self.cache.popitem(last=False)
                self.generated.pop(removed, None)
            logger.info(
                "analysis_complete symbol=%s timeframe=%s version=%s bars=%d duration_ms=%.2f",
                symbol,
                timeframe,
                result.algorithm_version,
                result.history.closed,
                (time.perf_counter() - start) * 1000,
            )
            return result.model_copy(deep=True)

    async def response(self, candles, symbol, timeframe, source, requested=300, config=None) -> AnalysisResponse:
        value = await self.snapshot(candles, symbol, timeframe, source, requested, config)
        now = dt.datetime.now(dt.UTC)
        # Lookup by full deterministic identity; operational clocks never enter the fingerprint.
        generated = next(
            (
                self.generated[key]
                for key, item in self.cache.items()
                if item.input_id == value.input_id
                and item.config_id == value.config_id
                and item.symbol == symbol
                and item.timeframe == timeframe
                and item.source == source
                and item.history == value.history
            ),
            now,
        )
        return AnalysisResponse(
            **value.model_dump(),
            generated_at=generated,
            served_at=now,
            cache_age_seconds=max(0, (now - generated).total_seconds()),
        )
