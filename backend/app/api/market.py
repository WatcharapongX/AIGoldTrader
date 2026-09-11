"""Authenticated market REST and first-frame-authenticated WebSocket, never URL tokens."""

import asyncio
import time
import uuid
from contextlib import suppress

import jwt
from fastapi import APIRouter, Depends, Query, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import AwareDatetime
from pydantic import ValidationError as SchemaError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import ForbiddenError, NotFoundError, RateLimitedError, ValidationError
from app.core.security import decode_token
from app.db.session import get_session, get_session_factory
from app.models import Role, Symbol, User
from app.services.market_data.domain import (
    CandlePage,
    MarketDataStatus,
    MarketMessage,
    Quote,
    SymbolInfo,
    SymbolInput,
    Timeframe,
    WsAuth,
    WsCommand,
)
from app.services.market_data.repository import candles_query
from app.services.market_data.service import MarketService

router = APIRouter()
ws_router = APIRouter()


def service(app) -> MarketService:
    if not hasattr(app.state, "market"):
        app.state.market = MarketService(get_session_factory(), get_settings())
    return app.state.market


async def started(request: Request) -> MarketService:
    current = service(request.app)
    await current.start()
    return current


def info(symbol: Symbol) -> SymbolInfo:
    return SymbolInfo(
        name=symbol.name,
        asset_class=symbol.asset_class,
        digits=symbol.digits,
        contract_size=symbol.contract_size,
        tick_value=symbol.tick_value,
        default_spread=symbol.default_spread,
        session_hours=symbol.session_hours,
        is_active=symbol.is_active,
        source_available=symbol.name == "XAUUSD",
    )


async def find_symbol(session, name):
    symbol = await session.scalar(select(Symbol).where(Symbol.name == name, Symbol.is_active.is_(True)))
    if symbol is None:
        raise NotFoundError("Active symbol not found")
    return symbol


@router.get("/symbols", response_model=list[SymbolInfo])
async def symbols(user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)):
    return [
        info(s)
        for s in (await session.scalars(select(Symbol).where(Symbol.is_active.is_(True)).order_by(Symbol.name))).all()
    ]


@router.get("/symbols/{name}", response_model=SymbolInfo)
async def symbol_detail(
    name: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    return info(await find_symbol(session, name))


@router.post("/symbols", response_model=SymbolInfo, status_code=201)
async def symbol_create(
    payload: SymbolInput, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    if user.role != Role.ADMIN:
        raise ForbiddenError("Admin required")
    if await session.scalar(select(Symbol).where(Symbol.name == payload.name)):
        raise ValidationError("Symbol name already exists")
    symbol = Symbol(**payload.model_dump())
    session.add(symbol)
    await session.commit()
    return info(symbol)


@router.put("/symbols/{name}", response_model=SymbolInfo)
async def symbol_update(
    name: str,
    payload: SymbolInput,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if user.role != Role.ADMIN:
        raise ForbiddenError("Admin required")
    if name != payload.name:
        raise ValidationError("Symbol identity cannot be renamed")
    symbol = await find_symbol(session, name)
    for key, value in payload.model_dump().items():
        setattr(symbol, key, value)
    await session.commit()
    return info(symbol)


@router.delete("/symbols/{name}", status_code=204)
async def symbol_delete(
    name: str, user: User = Depends(get_current_user), session: AsyncSession = Depends(get_session)
):
    if user.role != Role.ADMIN:
        raise ForbiddenError("Admin required")
    symbol = await find_symbol(session, name)
    symbol.is_active = False  # Preserve historical foreign keys.
    await session.commit()
    return Response(status_code=204)


@router.get("/market/status", response_model=MarketDataStatus)
async def market_status(request: Request, user: User = Depends(get_current_user)):
    return (await started(request)).status()


@router.get("/market/quote", response_model=Quote | None)
async def market_quote(
    request: Request,
    symbol: str = "XAUUSD",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    await find_symbol(session, symbol)
    current = await started(request)
    if symbol != "XAUUSD":
        raise NotFoundError("No configured source for this symbol")
    if not current.quote:
        return None
    status = current.status().status
    return current.quote.model_copy(update={"status": status if status != "CONNECTING" else "DISCONNECTED"})


@router.get("/market/candles", response_model=CandlePage)
async def market_candles(
    request: Request,
    symbol: str = "XAUUSD",
    timeframe: Timeframe = Timeframe.M5,
    start: AwareDatetime | None = Query(None, alias="from"),
    end: AwareDatetime | None = Query(None, alias="to"),
    limit: int = Query(300, ge=1, le=1000),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    selected = await find_symbol(session, symbol)
    if symbol != "XAUUSD":
        raise NotFoundError("No configured source for this symbol")
    if start and end and start >= end:
        raise ValidationError("from must be before to")
    current = await started(request)
    candles = await candles_query(
        session, selected.id, symbol, timeframe, start, end, limit, source=current.provider.source
    )
    return CandlePage(candles=candles, next_cursor=candles[0].open_time if len(candles) == limit else None)


def message(current, kind, command, candles=None, error=None):
    return MarketMessage(
        type=kind,
        symbol=command.symbol,
        timeframe=command.timeframe,
        sequence=current.sequence,
        quote=current.quote,
        candles=candles or [],
        status=current.status(),
        error=error,
    ).model_dump(mode="json")


@ws_router.websocket("/ws/market")
async def market_socket(ws: WebSocket):
    settings = get_settings()
    if ws.headers.get("origin") not in settings.cors_origin_list or ws.query_params:
        await ws.close(code=1008)
        return
    current = service(ws.app)
    if len(current.bus.queues) >= 128:
        await ws.close(code=1013)
        return
    queue = current.bus.subscribe()  # Reserve a bounded slot even before authentication.
    await ws.accept()
    receiver = consumer = None
    try:
        auth = WsAuth.model_validate_json(await asyncio.wait_for(ws.receive_text(), 5))
        claims = decode_token(auth.token, settings.secret_key, expected_type="access")
        user_id = uuid.UUID(str(claims["sub"]))
        expiry = float(claims["exp"])
        async with current.factory() as session:
            user = await session.get(User, user_id)
            if not user or not user.is_active:
                raise ValueError("Inactive user")
        await current.start()
        command = WsCommand(type="subscribe")
        subscribed = False
        window, messages = time.monotonic(), 0
        auth_checked = time.monotonic()
        receiver = asyncio.create_task(ws.receive_text())
        consumer = asyncio.create_task(queue.get())
        while True:
            if time.monotonic() - auth_checked >= 5:
                async with current.factory() as session:
                    user = await session.get(User, user_id)
                    if not user or not user.is_active:
                        await ws.close(code=4401)
                        return
                auth_checked = time.monotonic()
            if time.time() >= expiry:
                await ws.close(code=4401)
                return
            done, _ = await asyncio.wait({receiver, consumer}, timeout=2, return_when=asyncio.FIRST_COMPLETED)
            if receiver in done:
                raw = receiver.result()
                if len(raw) > 2048:
                    raise ValueError("Oversized command")
                if time.monotonic() - window > 60:
                    window, messages = time.monotonic(), 0
                messages += 1
                if messages > 60:
                    raise RateLimitedError("Command limit exceeded")
                incoming = WsCommand.model_validate_json(raw)
                if incoming.type != "ping":
                    command = incoming
                if incoming.type == "subscribe":
                    async with current.factory() as session:
                        symbol = await find_symbol(session, command.symbol)
                        if symbol.name != "XAUUSD":
                            raise ValueError("Source unavailable")
                        candles = await candles_query(
                            session, symbol.id, symbol.name, command.timeframe, source=current.provider.source
                        )
                    subscribed = True
                    await ws.send_json(message(current, "snapshot", command, candles))
                elif incoming.type == "unsubscribe":
                    subscribed = False
                else:
                    await ws.send_json(message(current, "heartbeat", command))
                receiver = asyncio.create_task(ws.receive_text())
            if consumer in done:
                update = consumer.result()
                if update is None:
                    await ws.close(code=1013)
                    return
                if subscribed:
                    await ws.send_json(
                        message(
                            current,
                            "update",
                            command,
                            [c for c in update if c.symbol == command.symbol and c.timeframe == command.timeframe],
                        )
                    )
                consumer = asyncio.create_task(queue.get())
            if not done:
                async with current.factory() as session:
                    user = await session.get(User, user_id)
                    if not user or not user.is_active:
                        await ws.close(code=4401)
                        return
                await ws.send_json(message(current, "status", command))
    except (WebSocketDisconnect, RuntimeError):
        pass
    except (
        ValueError,
        KeyError,
        TimeoutError,
        SchemaError,
        jwt.PyJWTError,
        ForbiddenError,
        NotFoundError,
        RateLimitedError,
    ):
        with suppress(RuntimeError):
            await ws.close(code=1008)
    finally:
        current.bus.unsubscribe(queue)
        for task in (receiver, consumer):
            if task:
                task.cancel()
                with suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await task
