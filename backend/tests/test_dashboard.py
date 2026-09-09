import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from starlette.requests import Request

from app.api import dashboard


@pytest.mark.parametrize("failed", ["market", "news", "analysis", "strategy", "database"])
async def test_independent_failure_keeps_registry_and_other_cards(monkeypatch, failed):
    names = {
        "market": "started",
        "news": "news_card",
        "analysis": "analysis_card",
        "strategy": "strategy_current",
        "database": "database_card",
    }
    for key, name in names.items():
        monkeypatch.setattr(dashboard, name, AsyncMock(return_value="postgresql" if key == "database" else None))
    monkeypatch.setattr(dashboard, names[failed], AsyncMock(side_effect=RuntimeError("private connection string")))
    result = await dashboard.assemble(SimpleNamespace())
    assert len(result.strategies) == 6 and result.current_plan is None
    assert "private connection" not in result.model_dump_json()
    assert not result.live_auto_trading and result.risk_engine == "NOT_IMPLEMENTED"
    if failed != "database":
        assert next(h for h in result.health if h.module == "database").state == "HEALTHY"


async def test_summary_singleflight_and_cache_not_refetched_per_browser(monkeypatch):
    for name in ("started", "news_card", "analysis_card", "strategy_current", "database_card"):
        monkeypatch.setattr(dashboard, name, AsyncMock(return_value=None))
    value = await dashboard.assemble(SimpleNamespace())
    build = AsyncMock(return_value=value)
    monkeypatch.setattr(dashboard, "assemble", build)
    app = SimpleNamespace(state=SimpleNamespace())
    request = Request({"type": "http", "app": app})
    results = await asyncio.gather(*(dashboard.summary(request) for _ in range(5)))
    assert build.await_count == 1
    assert len({r.generated_at for r in results}) == 1
    assert all(r.served_at >= r.generated_at for r in results)
