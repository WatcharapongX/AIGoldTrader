"""Redis integration — cache / pub-sub helper / health (TASK-015).

Redis ไม่ใช่ source of truth (ADR-003) — ระบบหลักต้อง degrade ได้เมื่อ Redis ล่ม.
"""

import asyncio
import inspect
import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

import redis.asyncio as aioredis
from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if not get_settings().redis_enabled:
        raise RuntimeError("Redis is disabled; set REDIS_ENABLED=true to use the Redis adapter")
    if _client is None:
        settings = get_settings()
        _client = aioredis.from_url(
            settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
        )
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
    _client = None


async def redis_health() -> bool | None:
    """None when disabled; otherwise PING success/failure, without raising."""
    if not get_settings().redis_enabled:
        return None
    try:
        client = get_redis()
        ping_res = client.ping()
        if inspect.isawaitable(ping_res):
            ping_res = await ping_res
        return bool(ping_res)
    except Exception:  # noqa: BLE001 — readiness probe ต้องไม่พังเมื่อ Redis ล่ม
        logger.warning("redis health check failed", exc_info=True)
        return False


async def cache_get_json(key: str) -> str | None:
    if not get_settings().redis_enabled:
        return None
    try:
        return await get_redis().get(key)
    except Exception:  # noqa: BLE001 — cache miss บน Redis failure (degrade, ไม่ raise)
        logger.warning("cache_get failed for %s", key, exc_info=True)
        return None


async def cache_set_json(key: str, value: str, ttl_seconds: int = 30) -> bool:
    if not get_settings().redis_enabled:
        return False
    try:
        await get_redis().set(key, value, ex=ttl_seconds)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("cache_set failed for %s", key, exc_info=True)
        return False


# ---------------------------------------------------------------------------
# Pub/Sub helpers — Phase 2+ (market data broadcast, event dispatch)
# ---------------------------------------------------------------------------


async def publish(channel: str, data: dict[str, Any]) -> bool:
    """Publish a JSON message to a Redis channel.

    Returns True on success, False on failure or disabled (no delivery claimed).
    """
    if not get_settings().redis_enabled:
        return False
    try:
        payload = json.dumps(data, default=str)
        await get_redis().publish(channel, payload)
        return True
    except Exception:  # noqa: BLE001
        logger.warning("publish failed on channel %s", channel, exc_info=True)
        return False


class PubSubManager:
    """Manage multiple Redis pub/sub subscriptions.

    Usage::

        manager = PubSubManager()
        await manager.subscribe("market:ticks:XAUUSD", handle_tick)
        await manager.start()   # runs in background task
        ...
        await manager.stop()
    """

    def __init__(self) -> None:
        self._pubsub = get_redis().pubsub()
        self._handlers: dict[str, Callable[[dict[str, Any]], Coroutine[Any, Any, None]]] = {}
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def subscribe(
        self,
        channel: str,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
    ) -> None:
        """Register an async handler for *channel*."""
        self._handlers[channel] = handler
        await self._pubsub.subscribe(channel)
        logger.info("subscribed to Redis channel %s", channel)

    async def unsubscribe(self, channel: str) -> None:
        """Remove subscription for *channel*."""
        self._handlers.pop(channel, None)
        await self._pubsub.unsubscribe(channel)
        logger.info("unsubscribed from Redis channel %s", channel)

    async def start(self) -> None:
        """Start listening in a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._listen(), name="pubsub-listener")

    async def stop(self) -> None:
        """Stop the listener and clean up."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        await self._pubsub.unsubscribe()
        await self._pubsub.aclose()
        logger.info("PubSubManager stopped")

    async def _listen(self) -> None:
        """Internal loop — reads messages and dispatches to handlers."""
        try:
            async for message in self._pubsub.listen():
                if not self._running:
                    break
                if message["type"] != "message":
                    continue
                channel: str = message["channel"]
                handler = self._handlers.get(channel)
                if handler is None:
                    continue
                try:
                    data = json.loads(message["data"])
                    await handler(data)
                except json.JSONDecodeError:
                    logger.warning("non-JSON message on %s: %s", channel, message["data"])
                except Exception:  # noqa: BLE001
                    logger.exception("handler error on channel %s", channel)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("PubSubManager listener crashed")

