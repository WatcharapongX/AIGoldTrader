"""API router aggregation — รวมทุก router ที่นี่ (docs/05)."""

from fastapi import APIRouter

from app.api import ai, analysis, auth, configuration, dashboard, health, market, news, risk, strategy, system

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(health.router)

api_router.include_router(market.router)

api_router.include_router(analysis.router)

api_router.include_router(news.router)

api_router.include_router(strategy.router)

api_router.include_router(dashboard.router)

api_router.include_router(risk.router)

api_router.include_router(ai.router)

api_router.include_router(system.router)

api_router.include_router(configuration.router)
