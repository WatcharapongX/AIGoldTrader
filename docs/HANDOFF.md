# Rolling Agent Handoff — AIGoldTrader

## Current Governance State

- **Authoritative branch**: `main`.
- **Authoritative pre-C3 governance baseline**: `e6b12325fe41f5c3037ca5447f91c564bdaeb575`.
- **Latest completed gate**: C2 Independent Verification — GPT-5.6 Sol / High — **PASS**.
- **Batch C1 — External Boundary Closure**: **CLOSED**.
- **Batch C2 — Aggregate Runtime Control**: **CLOSED**.
- **Batch C**: **OPEN**.
- **external_ai**: **HARDENING**.
- **Batch C3 — Output Contract & Safe Observability Hardening**: **AUTHORIZED FOR IMPLEMENTATION**.
- **Model routing**: **NOT AUTHORIZED**.
- **Trading execution**: **NOT AUTHORIZED**.

## C2 Verified Runtime Controls

- One request-scoped aggregate budget is created only after Kill Switch, Risk, reservation, stale, no-lookahead, and TradePlan authority gates pass.
- Aggregate ceilings cover provider attempts, prompt/completion/total tokens, measurable bytes, and an absolute monotonic deadline.
- Canonical base reservations and retry allocation are deterministic; retry use cannot starve later base calls.
- Actual worker retries count against the aggregate budget; unknown failed-attempt usage remains conservatively charged.
- Successful `ProviderResult` usage is reconciled truthfully, with safe terminal reservation finalization and no negative counters, oversubscription, or double refund.
- Queue wait is included in the aggregate deadline; remaining time is recomputed after admission and caps worker execution.
- Funded agents remain concurrent; cancellation and worker cleanup are safe, with no orphan worker reproduced in focused evidence.
- Meta receives a fresh reservation after agent reconciliation and safely skips rather than fabricating synthesis or becoming `READY` when aggregate resources are insufficient.

## C2 Verification Evidence

- C2 focused suite: **19 passed**.
- Combined C1+C2 suite: **221 passed**.
- Ruff: **PASS**.
- `git diff --check`: **PASS**.
- The earlier Codex sandbox `WinError 5` was an execution-environment restriction only; normal Windows host worker verification passed.

## C1 Protections Preserved

- **C-P2-001**: **CLOSED** — public provider failures remain normalized and secret-safe.
- **C-ADR-005**: **CLOSED** — external static configuration validates without startup provider network calls.
- **C-P3-003**: **CLOSED** — provider payloads remain role-minimized.
- **C-P3-006**: **CLOSED** — external redirects remain refused.
- ProviderDescriptor isolation, worker-local credential resolution, per-call limits, fixture default, and global provider concurrency remain intact.

## Trading Safety Preserved

- `TRADING_MODE=PAPER` remains unchanged.
- `LIVE_AUTO_TRADING=false` remains unchanged.
- AI remains advisory-only with zero execution authority.
- Authority remains Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.
- Broker execution, OMS, position management, paper execution, and the Backtesting Engine remain absent.

## C3 Authorized Scope

- Bound model-controlled AI output strings and collection cardinality.
- Preserve strict schema validation with AI-local safe degradation.
- Verify compromised model-generated agent summaries remain inert data at the Meta trust boundary; make only the minimum targeted containment change if a verified finding requires it.
- Add bounded, non-secret structured AI-runtime telemetry using existing logging only.
- Add focused telemetry-redaction, adversarial, and output-contract regression tests.

## C3 Implementation Constraints

- Required implementation runtime: **GPT-5.6 Sol / Medium**.
- Required independent post-implementation gate: **GPT-5.6 Sol / High**.
- Preserve C1 provider-boundary protections and C2 aggregate resource controls.
- Preserve exactly six canonical agents plus the Meta Controller; no routing, new agents, providers, or frameworks.
- Do not add observability infrastructure, a telemetry backend, Redis, Kafka, Celery, Kubernetes, or microservices.
- Do not alter trading authority, Risk Engine decisions, Kill Switch state, TradePlan geometry, or execution boundaries.

## Next Authorized Activity

- **Batch C3 Implementation** only.
- Do not implement model routing, backtesting, paper execution, OMS, broker execution, or live trading.
