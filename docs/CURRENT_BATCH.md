# Current Active Batch — AIGoldTrader

## Batch Identifier
**Batch C1 — External Boundary Closure**

## Status
**AUTHORIZED FOR IMPLEMENTATION**

## Primary Objective
Implement the approved external-provider trust-boundary hardening without changing AI authority or trading capability.

## Authorized Scope
- **C-P2-001**: Public/internal provider error separation.
- **C-ADR-005**: External-mode static startup validation.
- **C-P3-003**: Role-specific provider payload minimization.
- **C-P3-006**: Explicit external-provider redirect policy.
- Focused deterministic C1 security and regression tests.

## Implementation Runtime
**GPT-5.6 Sol / Medium**

## Required Next Gate After Implementation
**C1 Independent Security Verification — GPT-5.6 Sol / High**

## Architecture and Safety Constraints
- Preserve the FastAPI modular monolith, exactly six canonical analytical agents, Meta Controller, and ProviderDescriptor abstraction.
- Preserve worker-local credential resolution, disposable provider workers, fixture-provider default, and existing timeout, retry, and concurrency containment.
- AI remains advisory-only. Kill Switch pre-flight and Risk Engine authority remain above Strategy Engine and AI Advisory.
- `TRADING_MODE=PAPER` remains enforced and `LIVE_AUTO_TRADING=false` remains enforced.
- Broker execution, OMS, position management, paper execution, and the Backtesting Engine remain absent.

## Authorization Boundary
**C2 IS NOT AUTHORIZED.**

**C3 IS NOT AUTHORIZED.**

**Batch C remains open.**

## Strictly Out of Scope
- C2 aggregate runtime budget, AnalysisBudget, or seven-call aggregate token, cost, or deadline controls.
- C3 observability or contract-hardening implementation.
- Role-based model routing, new AI agents, Hermes, MCP, TradingView, or additional agent frameworks.
- Live trading, broker execution, OMS, position management, paper execution, or Backtesting Engine implementation.
- Redis, Kafka, Celery, Kubernetes, microservices, Vector DB, or ML pipelines.
