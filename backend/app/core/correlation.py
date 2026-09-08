"""Correlation ID propagation — ทุก request/job/order ต้องมี correlation_id."""

import contextvars
import uuid

_correlation_id: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str:
    return _correlation_id.get()
