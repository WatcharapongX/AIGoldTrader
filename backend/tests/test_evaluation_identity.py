"""SOL-P1-001: IDs, projections and persistence must agree on actual dependencies."""

import datetime as dt
from decimal import Decimal as D
from functools import lru_cache

import pytest

from app.services.news.domain import NewsResponse
from app.services.strategy.domain import EVALUATION_VERSION, StrategyResponse, fingerprint
from app.services.strategy.engine import EvaluationCache, evaluate, profiles
from app.services.strategy.identity import projections
from tests.test_strategy import ANALYSIS, CONFIG, context, qualified_context

SCENARIOS = (
    "healthy",
    "unavailable",
    "unknown",
    "nfp_upcoming",
    "cpi_upcoming",
    "forecast",
    "actual",
    "macro",
    "regime",
    "provider_health",
    "provider_conflict",
)


@lru_cache(maxsize=8)
def base(strategy_id):
    return qualified_context(strategy_id)


def traders(ctx, *strategies):
    return tuple(
        profiles(CONFIG, ctx.config_id)[1].model_copy(update={"id": "profile-" + s, "allowed_strategies": (s,)})
        for s in strategies
    )


def news_change(ctx, scenario):
    n = ctx.news.model_dump()
    if scenario in ("unavailable", "provider_health"):
        n.update(calendar_state="CALENDAR_UNAVAILABLE", data_quality="UNAVAILABLE")
    elif scenario == "unknown":
        n.update(news_regime="UNKNOWN", macro_bias="UNKNOWN")
    elif scenario in ("nfp_upcoming", "cpi_upcoming"):
        n.update(news_regime="PRE_NEWS", release_status="PRE_NEWS")
        for e in n["events"]:
            e.update(
                actual=None, released_at=None, status="SCHEDULED", scheduled_at=ctx.as_of + dt.timedelta(minutes=5)
            )
            if scenario == "cpi_upcoming":
                e.update(event_code="CPI_MOM", event_name="CPI m/m")
    elif scenario == "forecast":
        n["events"][0]["forecast"] = D(999)
    elif scenario == "actual":
        n["events"][0]["actual"] = D(888)
    elif scenario == "macro":
        n["macro_bias"] = "CONFLICTING"
    elif scenario == "regime":
        n["news_regime"] = "NEWS_LOCK"
    elif scenario == "provider_conflict":
        n.update(data_quality="CONFLICT")
        n["events"][0]["field_conflicts"] = ("forecast",)
    # Healthy is another semantically distinct known news revision too.
    n["fingerprint"] = fingerprint([scenario, n])
    news = ctx.news.model_validate(n)
    changed = ctx.model_copy(update={"news_json": news.model_dump_json(), "news_fingerprint": news.fingerprint})
    return changed.model_copy(update={"id": fingerprint(changed.model_dump(exclude={"id"}))})


@pytest.mark.parametrize("strategy", ["STRAT01", "STRAT02", "STRAT03", "STRAT04"])
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_general_identity_and_full_persisted_projection_invariant(strategy, scenario):
    ctx = base(strategy)
    p = traders(ctx, strategy)
    cache = EvaluationCache()
    a = evaluate(ctx, CONFIG, p, cache)
    size = len(cache.values)
    b = evaluate(news_change(ctx, scenario), CONFIG, p, cache)
    assert a.context.id != b.context.id
    assert a.context.market_context_id == b.context.market_context_id
    assert a.id == b.id and a.component_ids == b.component_ids
    assert a.candidates == b.candidates and a.candidates[0].status == "READY"
    assert len(cache.values) == size
    assert projections(a) == projections(b)
    leaf = projections(a)[0]
    assert leaf.context.id == ctx.market_context_id
    assert leaf.context.news_json is None and leaf.context.news_fingerprint is None
    assert leaf.candidates[0].plan == a.candidates[0].plan


@pytest.mark.parametrize("strategy", ["STRAT05", "STRAT06"])
@pytest.mark.parametrize("scenario", ["forecast", "actual", "regime", "provider_health", "provider_conflict"])
def test_news_dependency_sensitive(strategy, scenario):
    ctx = base(strategy)
    p = traders(ctx, strategy)
    a = evaluate(ctx, CONFIG, p)
    b = evaluate(news_change(ctx, scenario), CONFIG, p)
    assert a.id != b.id and a.component_ids != b.component_ids
    assert projections(a)[0].id != projections(b)[0].id
    assert projections(b)[0].context.news == b.context.news
    assert b.candidates[0].news_provenance.context_fingerprint == b.context.news_fingerprint


@pytest.mark.parametrize("separate_traders", [False, True])
def test_mixed_request_keeps_general_leaf_and_revises_news_leaf(separate_traders):
    ctx = base("STRAT01")
    p = traders(ctx, "STRAT01", "STRAT05")
    if not separate_traders:
        p = (p[0].model_copy(update={"allowed_strategies": ("STRAT01", "STRAT05")}),)
    a = evaluate(ctx, CONFIG, p)
    b = evaluate(news_change(ctx, "forecast"), CONFIG, p)
    leaves_a = {v.candidates[0].strategy_id: v for v in projections(a)}
    leaves_b = {v.candidates[0].strategy_id: v for v in projections(b)}
    assert a.id != b.id
    assert leaves_a["STRAT01"] == leaves_b["STRAT01"]
    assert leaves_a["STRAT05"].id != leaves_b["STRAT05"].id
    assert len({v.id for v in projections(a)}) == 2


def test_clocks_do_not_change_identity_even_with_news():
    from app.services.strategy.context import build_context

    ctx = base("STRAT05")
    n = ctx.news

    def build(clock):
        response = NewsResponse(**n.model_dump(), generated_at=clock, served_at=clock, cache_age_seconds=0)
        return build_context(
            candles={},
            symbol=ctx.symbol,
            source=ctx.source,
            at=ctx.as_of,
            news=response,
            tick_size=ctx.tick_size,
            config=CONFIG,
            analysis_config=ANALYSIS,
            replay=True,
        )

    a = build(ctx.as_of)
    b = build(ctx.as_of + dt.timedelta(minutes=1))
    assert a == b
    assert evaluate(a, CONFIG, traders(a, "STRAT05")).id == evaluate(b, CONFIG, traders(b, "STRAT05")).id


def test_market_profile_version_and_config_dependencies():
    a = context(count=60)
    b = context(count=60, at=a.as_of + dt.timedelta(days=7))
    assert evaluate(a, CONFIG).id != evaluate(b, CONFIG).id
    p = traders(a, "STRAT01")
    changed = (p[0].model_copy(update={"id": "another-profile"}),)
    assert evaluate(a, CONFIG, p).id != evaluate(a, CONFIG, changed).id
    from app.services.strategy.identity import component_id

    definition = evaluate(a, CONFIG, p).strategies[0]
    assert component_id(a, p[0], definition) != component_id(
        a, p[0], definition.model_copy(update={"version": "future"})
    )
    config = CONFIG.model_copy(update={"minimum_rr": D(2)})
    with pytest.raises(ValueError, match="configuration/context"):
        evaluate(a, config, p)
    c = context(count=60, config=config)
    assert evaluate(a, CONFIG).id != evaluate(c, config).id


def test_api_serializes_request_components_and_projected_history():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api import strategy as api
    from app.api.deps import get_current_user

    ctx = base("STRAT01")
    p = traders(ctx, "STRAT01", "STRAT05")
    values = [evaluate(ctx, CONFIG, p), evaluate(news_change(ctx, "actual"), CONFIG, p)]
    app = FastAPI()
    app.include_router(api.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: object()
    from unittest.mock import patch

    async def current(request, value):
        return StrategyResponse(evaluation=values.pop(0), generated_at=ctx.as_of, served_at=ctx.as_of, stale=False)

    with patch.object(api, "current", current), TestClient(app) as client:
        a = client.get("/api/strategy/context")
        b = client.get("/api/trade-plan/current")
    assert a.status_code == b.status_code == 200
    ea, eb = (StrategyResponse.model_validate(r.json()).evaluation for r in (a, b))
    for strategy in ("STRAT01", "STRAT05"):
        ca = next(c for c in ea.candidates if c.strategy_id == strategy)
        cb = next(c for c in eb.candidates if c.strategy_id == strategy)
        assert (ea.component_ids[ca.id] == eb.component_ids[cb.id]) == (strategy == "STRAT01")
        if strategy == "STRAT01":
            assert ca.id == cb.id and ca.plan == cb.plan
    leaf = projections(ea)[0]
    response = StrategyResponse(evaluation=leaf, generated_at=ctx.as_of, served_at=ctx.as_of, stale=True)
    assert StrategyResponse.model_validate_json(response.model_dump_json()).evaluation == leaf
    assert leaf.identity_version == EVALUATION_VERSION


@pytest.mark.asyncio
async def test_sqlite_mixed_persistence_idempotent(db_session):
    from sqlalchemy import func, select

    from app.models.strategy import CandidateTransitionRecord, StrategyEvaluationRecord, TradeCandidateRecord
    from app.services.strategy.repository import persist

    session, _ = db_session
    ctx = base("STRAT01")
    p = traders(ctx, "STRAT01", "STRAT05")
    a = evaluate(ctx, CONFIG, p)
    b = evaluate(news_change(ctx, "forecast"), CONFIG, p)
    first = await persist(session, a)
    await session.commit()
    assert await persist(session, a) == first
    second = await persist(session, b)
    await session.commit()
    assert await persist(session, b) == second
    assert await session.scalar(select(func.count()).select_from(StrategyEvaluationRecord)) == 3
    assert await session.scalar(select(func.count()).select_from(TradeCandidateRecord)) == 3
    assert await session.scalar(select(func.count()).select_from(CandidateTransitionRecord)) == 1
    for v in projections(b):
        row = await session.get(TradeCandidateRecord, v.candidates[0].id)
        assert row.evaluation_id == v.id


def test_empty_request_projection_and_tampered_component_rejected():
    ctx = base("STRAT01")
    p = tuple(t.model_copy(update={"enabled": False}) for t in traders(ctx, "STRAT01"))
    a = evaluate(ctx, CONFIG, p)
    b = evaluate(news_change(ctx, "forecast"), CONFIG, p)
    assert a.id == b.id
    assert projections(a) == projections(b)
    assert projections(a)[0].scope == "EMPTY"
    assert projections(a)[0].context.news_json is None
    real = evaluate(ctx, CONFIG, traders(ctx, "STRAT01"))
    with pytest.raises(ValueError, match="Evaluation identity conflict"):
        projections(real.model_copy(update={"component_ids": {real.candidates[0].id: "wrong"}}))
