# Current Active Batch — AIGoldTrader

## Batch Identifier
**Batch C — External AI Runtime Safety**

## Completed Sub-Batch
**C1 — External Boundary Closure: CLOSED** following independent security verification.

## Current Status
**Batch C2 — Aggregate Runtime Control: AUTHORIZED FOR IMPLEMENTATION**

## Primary Objective
Implement bounded request-scoped aggregate runtime control for the six-agent + Meta analysis lifecycle.

## Authorized Scope
- Request-scoped `AnalysisBudget` or equivalent.
- Aggregate provider-call budget.
- Aggregate token/byte accounting.
- Aggregate deadline.
- Concurrent reservation and reconciliation.
- Retry integration.
- Meta budget/exhaustion behavior.
- Deterministic C2 tests.

## Implementation Runtime and Required Gate
- **Implementation runtime**: GPT-5.6 Sol / Medium.
- **Required post-implementation gate**: C2 Independent Verification — GPT-5.6 Sol / High.

## Authorization Boundary
**C3 IS NOT AUTHORIZED.**

**Model routing IS NOT AUTHORIZED.**

C2 implementation is authorized only within the scope above.

## Architecture and Safety Constraints
- Preserve the FastAPI modular monolith, exactly six canonical analytical agents, Meta Controller, and ProviderDescriptor abstraction.
- Preserve worker-local credential resolution, disposable provider workers, fixture-provider default, and existing timeout, retry, and concurrency containment.
- AI remains advisory-only. Kill Switch pre-flight and Risk Engine authority remain above Strategy Engine and AI Advisory.
- `TRADING_MODE=PAPER` remains enforced and `LIVE_AUTO_TRADING=false` remains enforced.
- Broker execution, OMS, position management, paper execution, and the Backtesting Engine remain absent.

## Batch Boundary
**Batch C remains open.** C1 is closed; C2 Aggregate Runtime Control implementation is authorized.

## Strictly Out of Scope
- C3 observability or contract-hardening implementation.
- Role-based model routing, new AI agents, Hermes, MCP, TradingView, or additional agent frameworks.
- Live trading, broker execution, OMS, position management, paper execution, or Backtesting Engine implementation.
- Redis, Kafka, Celery, Kubernetes, microservices, Vector DB, or ML pipelines.
