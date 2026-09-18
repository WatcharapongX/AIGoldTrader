"""Export the small Phase 1 response contract from authoritative backend OpenAPI.

Run from backend: python -m scripts.export_api_contract [--check]
No external generator/dependency; unsupported schema constructs fail explicitly.
"""

import argparse
import json
from pathlib import Path

from app.api.dashboard import DashboardSummary
from app.main import create_app
from app.services.analysis.domain import AnalysisResponse, AnalysisSnapshot, MultiTimeframeContext
from app.services.market_data.domain import (
    Candle,
    CandlePage,
    MarketDataStatus,
    MarketMessage,
    Quote,
    SymbolInfo,
    Timeframe,
    WsAuth,
    WsCommand,
)
from app.services.news.domain import CalendarPage, EventDetail, NewsResponse
from app.services.news.public_calendar import ProviderHealth
from app.services.strategy.domain import StrategyResponse, Transition

ROOT = Path(__file__).resolve().parents[2]
MODELS = ("MeResponse", "AccessTokenResponse", "HealthResponse", "ReadyResponse", "ReadyChecks", "Role")
ENDPOINTS = ("/api/auth/me", "/api/auth/login", "/api/auth/refresh", "/api/healthz", "/api/readyz")


def contract() -> dict:
    schema = create_app().openapi()
    return {
        "schemas": {name: schema["components"]["schemas"][name] for name in MODELS},
        "responses": {
            path: {method: operation["responses"] for method, operation in schema["paths"][path].items()}
            for path in ENDPOINTS
        },
    }


def ts_type(schema: dict) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[1]
    if "anyOf" in schema:
        return " | ".join(ts_type(item) for item in schema["anyOf"])
    if "enum" in schema:
        return " | ".join(json.dumps(value) for value in schema["enum"])
    if "const" in schema:
        return json.dumps(schema["const"])
    if schema.get("type") == "array":
        return f"Array<{ts_type(schema['items'])}>"
    if schema.get("type") == "object" and isinstance(schema.get("additionalProperties"), dict):
        return f"Record<string, {ts_type(schema['additionalProperties'])}>"
    kinds = {"string": "string", "number": "number", "integer": "number", "boolean": "boolean", "null": "null"}
    if schema.get("type") in kinds:
        return kinds[schema["type"]]
    raise ValueError("Unsupported response schema; update the scoped contract exporter deliberately")


def typescript(data: dict) -> str:
    lines = ["// Generated from backend OpenAPI by scripts.export_api_contract. Do not hand-edit.", ""]
    for name, schema in data["schemas"].items():
        if schema.get("type") != "object":
            lines.extend([f"export type {name} = {ts_type(schema)};", ""])
            continue
        lines.append(f"export interface {name} {{")
        for field, value in schema["properties"].items():
            optional = "" if field in schema.get("required", []) else "?"
            lines.append(f"  {field}{optional}: {ts_type(value)};")
        lines.extend(["}", ""])
    return "\n".join(lines)


def artifacts() -> dict[Path, str]:
    data = contract()
    market_schemas = {}
    for model in (Candle, CandlePage, MarketDataStatus, MarketMessage, Quote, SymbolInfo, WsAuth, WsCommand):
        schema = model.model_json_schema(mode="serialization", ref_template="#/schemas/{model}")
        market_schemas.update(schema.pop("$defs", {}))
        market_schemas[model.__name__] = schema
    market = {"schemas": market_schemas, "timeframes": [tf.value for tf in Timeframe]}
    analysis_schemas = {}
    for model in (AnalysisSnapshot, AnalysisResponse, MultiTimeframeContext):
        schema = model.model_json_schema(mode="serialization", ref_template="#/schemas/{model}")
        analysis_schemas.update(schema.pop("$defs", {}))
        analysis_schemas[model.__name__] = schema
    analysis = {"schemas": analysis_schemas}
    news_schemas = {}
    for model in (CalendarPage, EventDetail, NewsResponse, ProviderHealth):
        schema = model.model_json_schema(mode="serialization", ref_template="#/schemas/{model}")
        news_schemas.update(schema.pop("$defs", {}))
        news_schemas[model.__name__] = schema
    news = {"schemas": news_schemas}
    strategy_schemas = {}
    for model in (StrategyResponse, Transition):
        schema = model.model_json_schema(mode="serialization", ref_template="#/schemas/{model}")
        strategy_schemas.update(schema.pop("$defs", {}))
        strategy_schemas[model.__name__] = schema
    strategy = {"schemas": strategy_schemas}
    schema = DashboardSummary.model_json_schema(mode="serialization", ref_template="#/schemas/{model}")
    dashboard_schemas = schema.pop("$defs", {})
    dashboard_schemas["DashboardSummary"] = schema
    dashboard = {"schemas": dashboard_schemas}
    return {
        ROOT / "frontend/src/types/dashboard.generated.ts": typescript(dashboard),
        ROOT / "frontend/src/features/dashboard/dashboard-contract.generated.json": json.dumps(dashboard, indent=2)
        + chr(10),
        ROOT / "frontend/src/types/strategy.generated.ts": typescript(strategy),
        ROOT / "frontend/src/features/strategy/strategy-contract.generated.json": json.dumps(strategy, indent=2)
        + chr(10),
        ROOT / "frontend/src/types/news.generated.ts": typescript(news),
        ROOT / "frontend/src/features/news/news-contract.generated.json": json.dumps(news, indent=2) + chr(10),
        ROOT / "frontend/src/types/analysis.generated.ts": typescript(analysis),
        ROOT / "frontend/src/features/analysis/analysis-contract.generated.json": (
            json.dumps(analysis, indent=2) + chr(10)
        ),
        ROOT / "frontend/src/types/market.generated.ts": typescript(market),
        ROOT / "frontend/src/features/chart/market-contract.generated.json": json.dumps(market, indent=2) + chr(10),
        ROOT / "frontend/src/types/api.generated.ts": typescript(data),
        ROOT / "frontend/tests/fixtures/api-contract.json": json.dumps(data, indent=2) + "\n",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path, content in artifacts().items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                raise SystemExit("API contract drift: run python -m scripts.export_api_contract and review changes")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    print("API contract: PASS")


if __name__ == "__main__":
    main()
