"""Small, non-authoritative allowlisted AI runtime events."""

import json
import logging
import math
import re
from typing import Literal

logger = logging.getLogger(__name__)

EventName = Literal[
    "ai_agent_completed", "ai_agent_degraded", "ai_meta_completed", "ai_meta_degraded", "ai_meta_skipped"
]
FailureCode = Literal[
    "ANALYSIS_DEADLINE_EXHAUSTED", "ANALYSIS_BUDGET_EXHAUSTED",
    "PROVIDER_AUTH_FAILED", "PROVIDER_RATE_LIMITED", "PROVIDER_TIMEOUT",
    "PROVIDER_NETWORK_ERROR", "PROVIDER_CAPACITY_EXHAUSTED",
    "PROVIDER_REQUEST_REJECTED", "PROVIDER_SCHEMA_INVALID",
    "PROVIDER_BUDGET_EXCEEDED", "PROVIDER_WORKER_FAILURE", "PROVIDER_INTERNAL_ERROR",
]
_EVENTS = {"ai_agent_completed", "ai_agent_degraded", "ai_meta_completed", "ai_meta_degraded", "ai_meta_skipped"}
_CODES = set(FailureCode.__args__)
_IDENTIFIER = re.compile(r"[a-z0-9][a-z0-9_-]{0,63}\Z")


def emit_ai_event(
    event_name: EventName,
    *,
    agent_id: str,
    provider_id: str | None = None,
    failure_code: FailureCode | None = None,
    attempt_count: int | None = None,
    duration_ms: float | None = None,
) -> None:
    """Emit only known metadata. Invalid telemetry never affects an AI decision."""
    try:
        if event_name not in _EVENTS or not isinstance(agent_id, str) or not _IDENTIFIER.fullmatch(agent_id):
            return
        data: dict[str, str | int | float] = {"event_name": event_name, "agent_id": agent_id}
        if provider_id is not None:
            if not isinstance(provider_id, str) or not _IDENTIFIER.fullmatch(provider_id):
                return
            data["provider_id"] = provider_id
        if failure_code is not None:
            if failure_code not in _CODES:
                return
            data["failure_code"] = failure_code
        if attempt_count is not None:
            if type(attempt_count) is not int or not 0 <= attempt_count <= 100:
                return
            data["attempt_count"] = attempt_count
        if duration_ms is not None:
            if (type(duration_ms) not in (int, float) or not math.isfinite(duration_ms)
                    or not 0 <= duration_ms <= 120_000):
                return
            data["duration_ms"] = duration_ms
        logger.info("ai_runtime %s", json.dumps(data, separators=(",", ":")))
    except Exception:
        # Logging is never part of AI, Risk, or Kill Switch authority.
        return
