"""API router aggregation — รวมทุก router ที่นี่ (docs/05)."""

from fastapi import APIRouter

from app.api import auth, health

api_router = APIRouter(prefix="/api")
api_router.include_router(auth.router)
api_router.include_router(health.router)
