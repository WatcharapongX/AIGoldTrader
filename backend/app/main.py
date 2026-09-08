"""FastAPI application factory (docs/02 §2, TASK-011/013/019)."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import api_router
from app.api.health import router as health_router
from app.core.config import get_settings
from app.core.correlation import get_correlation_id, new_correlation_id, set_correlation_id
from app.core.errors import AppError
from app.core.logging import setup_logging
from app.db.session import dispose_engine
from app.services.redis_client import close_redis

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    settings.validate_runtime_secrets()
    setup_logging(settings.log_level, settings.log_format)
    # Guard: ห้าม runtime config ที่ฝืน Guardrails (INV-08)
    if settings.trading_mode == "LIVE" and not settings.live_auto_trading:
        logger.warning("TRADING_MODE=LIVE but LIVE_AUTO_TRADING=false — order paths remain blocked")
    logger.info(
        "startup",
        extra={"app": settings.app_name, "env": settings.app_env, "trading_mode": settings.trading_mode},
    )
    try:
        yield
    finally:
        await close_redis()
        await dispose_engine()
        logger.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AI Trading Platform API",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.debug else None,
        redoc_url=None,
    )

    # CORS allow-list (FR-SE-01)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID", "Idempotency-Key"],
    )

    @app.middleware("http")
    async def correlation_middleware(request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID") or new_correlation_id()
        set_correlation_id(correlation_id)
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.to_payload())

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": [
                        {"type": error["type"], "loc": error["loc"], "msg": error["msg"]}
                        for error in exc.errors()
                    ]},
                    "correlation_id": get_correlation_id(),
                }
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL",
                    "message": "Internal server error",
                    "details": {},
                    "correlation_id": get_correlation_id(),
                }
            },
        )

    app.include_router(api_router)
    app.include_router(health_router, include_in_schema=False)
    return app


app = create_app()
