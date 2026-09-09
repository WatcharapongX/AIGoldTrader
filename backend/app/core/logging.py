"""Structured JSON logging + correlation id filter (docs/02 §10)."""

import json
import logging
import sys
import traceback
from pathlib import Path

from app.core.correlation import get_correlation_id

_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "module", "msecs", "message", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info",
    "thread", "threadName", "taskName",
}


def safe_exception(exc: BaseException) -> dict:
    """Keep type/code/stack locations, never driver text, SQL, parameters or locals."""
    details = {
        "error_type": type(exc).__name__,
        "stack": [
            {"file": Path(frame.filename).name, "line": frame.lineno, "function": frame.name}
            for frame in traceback.extract_tb(exc.__traceback__)
        ],
    }
    sqlstate = getattr(getattr(exc, "orig", None), "sqlstate", None)
    if isinstance(sqlstate, str) and len(sqlstate) == 5 and sqlstate.isalnum():
        details["sqlstate"] = sqlstate
    return details


class SafeFormatter(logging.Formatter):
    def formatException(self, ei) -> str:
        return json.dumps(safe_exception(ei[1]), ensure_ascii=False)


class CorrelationFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = get_correlation_id()  # type: ignore[attr-defined]
        return True


class JsonFormatter(SafeFormatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key != "correlation_id" and not key.startswith("_"):
                payload[key] = value
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str = "INFO", log_format: str = "json") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationFilter())
    if log_format == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            SafeFormatter("%(asctime)s %(levelname)s [%(correlation_id)s] %(name)s %(message)s")
        )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # SQL echo/debug rows can contain sensitive values even with parameter hiding.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    for noisy in ("uvicorn.access", "uvicorn.error", "uvicorn"):
        logging.getLogger(noisy).handlers = []
        logging.getLogger(noisy).propagate = True
