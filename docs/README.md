# Documentation Index & Architecture Map — AIGoldTrader

> **Note on System State**: This document is an **Index & Reading Guide**. For current authoritative operational status, active milestones, and capability readiness, always refer to [`docs/CURRENT_STATE.md`](file:///c:/AI%20Gold%20Trader/docs/CURRENT_STATE.md) and [`docs/SYSTEM_CAPABILITIES.yaml`](file:///c:/AI%20Gold%20Trader/docs/SYSTEM_CAPABILITIES.yaml).

---

## 1. AI Agent Operating Tier (Startup & Working Context)

| Document | Purpose | Authority | Type | When an AI Agent Should Read It |
|---|---|---|---|---|
| [`/AGENTS.md`](file:///c:/AI%20Gold%20Trader/AGENTS.md) | Global working rules, context policy, safety invariants, loop prevention | Operational Authority | Current | **ALWAYS** at start of every session |
| [`docs/CURRENT_STATE.md`](file:///c:/AI%20Gold%20Trader/docs/CURRENT_STATE.md) | Canonical operational milestone, verified capabilities, active safety state | Canonical State Authority | Current | **ALWAYS** at start of every session |
| [`docs/CURRENT_BATCH.md`](file:///c:/AI%20Gold%20Trader/docs/CURRENT_BATCH.md) | Active batch scope, target deliverables, strict out-of-scope bounds | Task Scope Authority | Current | **ALWAYS** at start of every session |
| [`docs/SYSTEM_CAPABILITIES.yaml`](file:///c:/AI%20Gold%20Trader/docs/SYSTEM_CAPABILITIES.yaml) | Machine-readable capability registry for automated verification | Machine Registry | Current | When validating capability claims |
| [`docs/HANDOFF.md`](file:///c:/AI%20Gold%20Trader/docs/HANDOFF.md) | Rolling summary of recent activity, test status, next steps | Operational Handoff | Current | When resuming from a previous agent session |

---

## 2. Technical Domain Specifications (Read Only When Task-Relevant)

| Document | Component / Scope | Implementation Status | When to Read |
|---|---|---|---|
| [`01-requirements.md`](file:///c:/AI%20Gold%20Trader/docs/01-requirements.md) | System requirements, functional/non-functional specs | Baseline Contract | Architectural refactoring |
| [`02-system-architecture.md`](file:///c:/AI%20Gold%20Trader/docs/02-system-architecture.md) | High-level 22-module topology, system flows | Baseline Contract | System boundary or inter-module work |
| [`03-trading-domain.md`](file:///c:/AI%20Gold%20Trader/docs/03-trading-domain.md) | Domain models, enums, state machines, invariants | Baseline Contract | Domain logic, candidate lifecycle |
| [`04-database-design.md`](file:///c:/AI%20Gold%20Trader/docs/04-database-design.md) | Database schema, table relationships, indices | Baseline Contract | Database models, migrations |
| [`05-api-design.md`](file:///c:/AI%20Gold%20Trader/docs/05-api-design.md) | REST endpoints & WebSocket contract specifications | Baseline Contract | API endpoints or WebSocket transports |
| [`06-market-data.md`](file:///c:/AI%20Gold%20Trader/docs/06-market-data.md) | Market data engine, aggregation, provider interfaces | **Implemented** | Market feed or candle aggregation work |
| [`07-market-structure.md`](file:///c:/AI%20Gold%20Trader/docs/07-market-structure.md) | Swing detection, BOS, CHoCH, MSS algorithms | **Implemented** | Structure detection algorithms |
| [`08-smc-ict.md`](file:///c:/AI%20Gold%20Trader/docs/08-smc-ict.md) | Order blocks, Fair Value Gaps, liquidity sweeps | **Implemented** | SMC/ICT analysis or scoring |
| [`09-strategy-engine.md`](file:///c:/AI%20Gold%20Trader/docs/09-strategy-engine.md) | Strategies STRAT01–06, candidate generation | **Implemented** | Strategy evaluation logic |
| [`10-dashboard-command-center.md`](file:///c:/AI%20Gold%20Trader/docs/10-dashboard-command-center.md) | UI architecture, decoupled screens, data provenance | **Implemented** | Frontend screen refactoring or layout |
| [`docs/AI_RULES.md`](file:///c:/AI%20Gold%20Trader/docs/AI_RULES.md) | 6 analytical agents, Meta Controller, model tiers | **Implemented (Advisory)** | Working on AI agents or external providers |
| `11-risk-engine.md` | Risk policy, gross exposure limits, Kill Switch | **Implemented** | Risk Engine or Kill Switch governance |
| `12-order-management.md` | OMS state machine, idempotency ledger | **Not Implemented** | Future OMS phases only (DO NOT START) |
| `13-paper-trading.md` | Execution simulation (spread/slippage/fill) | **Not Implemented** | Future simulation phases only (DO NOT START) |
| `14-backtesting.md` | Walk-forward backtesting simulation engine | **Not Implemented** | Future backtest phases only (DO NOT START) |
| `15-broker-integration.md` | BrokerAdapter, MT5 live order execution | **Not Implemented** | Future broker phases only (DO NOT START) |
| [`17-testing.md`](file:///c:/AI%20Gold%20Trader/docs/17-testing.md) | Testing strategy, unit/integration guidelines | Active Reference | Authoring new test suites |
| [`18-devops.md`](file:///c:/AI%20Gold%20Trader/docs/18-devops.md) | PM2 process supervision, environment configuration | Active Reference | Runtime environment or devops tasks |
| `architecture-decision-records/` | Architecture Decision Records (ADR-001..007) | Accepted | Reviewing foundational design decisions |

---

## 3. Historical Planning, Freeze, and Remediation Evidence (Tier 3 — DO NOT Load by Default)

| Document | Purpose | Nature | Notice for AI Agents |
|---|---|---|---|
| [`../implementation_plan.md`](file:///c:/AI%20Gold%20Trader/implementation_plan.md) | Original multi-phase project roadmap & task logs | Historical Roadmap | Do NOT use for current authorization. See `docs/CURRENT_BATCH.md`. |
| [`docs/FEATURE_FREEZE.md`](file:///c:/AI%20Gold%20Trader/docs/FEATURE_FREEZE.md) | Baseline functional completion freeze record (FC-12) | Freeze Baseline | Read only for freeze verification or regression audits. |
| [`docs/REMEDIATION_STATUS.md`](file:///c:/AI%20Gold%20Trader/docs/REMEDIATION_STATUS.md) | Post-audit remediation record for Batches A through B3.3 | Audit Evidence | Read only during formal security audits or gate verification. |
| `docs/phase-*-gate.md` | Historical Phase Gate completion evidence | Historical Evidence | Reference only; do not re-verify closed gates. |
| `docs/sol-p1-001-corrective.md` | Historical corrective action evidence for SOL-P1-001 | Historical Evidence | Closed audit evidence. |
| `docs/ui-truthfulness-corrective.md` | Historical corrective action evidence for UI provenance | Historical Evidence | Closed audit evidence. |
