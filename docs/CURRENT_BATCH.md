# Current Active Batch — AIGoldTrader

## Batch Identifier
**Batch C — External AI Runtime Safety**

## Completed Sub-Batches
**C1 — External Boundary Closure: CLOSED** following independent security verification.

**C2 — Aggregate Runtime Control: CLOSED** following independent verification.

## Current Status
**Batch C3 — Output Contract & Safe Observability Hardening**

**Status: AUTHORIZED FOR IMPLEMENTATION**

## Next Permitted Task
Implement C3 only.

## Authorization Boundary
Primary objective: bound model-controlled analytical outputs, harden Meta handling of model-generated summaries, add non-secret structured runtime telemetry, and close focused adversarial contract-test gaps.

### Authorized Scope
- Model-controlled field length bounds and collection cardinality bounds.
- Schema validation and safe degradation behavior.
- Compromised-summary / Meta trust-boundary tests and the minimum containment required by a verified finding.
- Safe structured AI-runtime logging and telemetry redaction tests.
- Focused C3 adversarial and regression tests.

### Required Implementation and Verification
- **Implementation runtime**: GPT-5.6 Sol / Medium.
- **Required independent gate**: GPT-5.6 Sol / High.

**Model routing IS NOT AUTHORIZED.**

**Trading execution IS NOT AUTHORIZED.**

Batch C remains **OPEN**. C3 is authorized for implementation but is not yet implemented or verified.

## Architecture and Safety Constraints
- Preserve the FastAPI modular monolith, exactly six canonical analytical agents, Meta Controller, and ProviderDescriptor abstraction.
- Preserve worker-local credential resolution, disposable provider workers, fixture-provider default, and existing timeout, retry, and concurrency containment.
- AI remains advisory-only. Kill Switch pre-flight and Risk Engine authority remain above Strategy Engine and AI Advisory.
- `TRADING_MODE=PAPER` remains enforced and `LIVE_AUTO_TRADING=false` remains enforced.
- Broker execution, OMS, position management, paper execution, and the Backtesting Engine remain absent.

## Batch Boundary
**Batch C remains open.** C1 and C2 are closed. C3 is authorized for implementation and requires an independent post-implementation gate before closure.

## Strictly Out of Scope
- Role-based model routing, new AI agents, Hermes, MCP, TradingView, or additional agent frameworks.
- Live trading, broker execution, OMS, position management, paper execution, or Backtesting Engine implementation.
- Redis, Kafka, Celery, Kubernetes, microservices, Vector DB, or ML pipelines.
