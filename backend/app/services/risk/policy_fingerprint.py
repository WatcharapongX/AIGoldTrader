"""Canonical versioned fingerprint for pure Risk evaluation inputs."""

import datetime as dt
import enum
import hashlib
import json
from decimal import Decimal
from typing import Any

from pydantic import BaseModel

from app.services.risk.policy_domain import PURE_RISK_CORE_VERSION, PureRiskEvaluationInput


def _canonical_decimal(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _canonical(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical(value.model_dump(mode="python"))
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, Decimal):
        return _canonical_decimal(value)
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.UTC).isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def build_pure_risk_semantic_payload(
    evaluation_input: PureRiskEvaluationInput,
    normalized_requested_risk_pct: Decimal,
    target_risk_pct: Decimal,
) -> str:
    canonical = _canonical(
        {
            "core_version": PURE_RISK_CORE_VERSION,
            "input": evaluation_input,
            "normalized_requested_risk_pct": normalized_requested_risk_pct,
            "target_risk_pct": target_risk_pct,
        }
    )
    return json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compute_pure_risk_fingerprint(
    evaluation_input: PureRiskEvaluationInput,
    normalized_requested_risk_pct: Decimal,
    target_risk_pct: Decimal,
) -> tuple[str, str]:
    payload = build_pure_risk_semantic_payload(
        evaluation_input,
        normalized_requested_risk_pct,
        target_risk_pct,
    )
    return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()
