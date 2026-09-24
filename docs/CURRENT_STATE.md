# Canonical Current Operational State — AIGoldTrader

- **Last Verified Date**: 2026-09-24
- **Authoritative Branch**: `main`
- **Current Milestone**: Batch D remains open; D1 is CLOSED and D2 governance requires a split.
- **Current Active Gate**: D2A Causal Replay Foundation — REMEDIATED, PENDING INDEPENDENT RE-VERIFICATION.
- **Next Permitted Activity**: D2A independent verification only (GPT-5.6 Sol / High).
- **Prohibited Progression**: D2B, D2C, and D3–D7 remain unapproved.

---

## 1. Trading Safety & Authority Hierarchy
- **Trading Mode**: `TRADING_MODE=PAPER` (enforced across all configurations)
- **Live Automatic Trading**: `LIVE_AUTO_TRADING=false` (strictly disabled)
- **Broker Execution**: `NONE` (`order_send` absent from codebase)
- **Authority Hierarchy**: Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator
- **AI Authority**: Advisory only; zero order execution authority and no Risk/Kill Switch override.

---

## 2. Capability Status

### Implemented and Verified
1. Market Data: canonical UTC quotes/candles, M1–W1 aggregation, provider abstraction, persistence and streaming.
2. Market Structure: causal closed-candle swing, BOS, CHoCH, MSS, liquidity, OB/FVG, regime and indicators.
3. Strategy Engine: deterministic STRAT01–STRAT06, seven profiles, immutable causal contexts/candidates,
   suggestion-only TradePlan geometry, eight canonical candidate states and point-in-time news handling.
4. Risk Engine: server-authoritative policies, position sizing, gross exposure/reservation controls,
   deterministic dependency fingerprints and fail-closed Kill Switch authority.
5. AI Analysis: six canonical analytical agents and Meta Controller, advisory only.
6. Frontend Command Center: decoupled screens including `/backtesting`.
7. Batch B browser authentication/session security: independently verified and closed.

### Hardening
- External AI provider infrastructure: C1–C3 independently verified; Batch C closed; fixture mode default.

### Foundation Status
- **Deterministic Backtesting D1**: immutable configuration/lifecycle, coverage/provenance, resource-policy,
  canonical fingerprint, and simulation/live isolation contracts are implemented and independently verified.
  D1-IV-001 through D1-IV-006 are closed.
- **D2A Causal Replay Foundation**: remediated and locally verified, pending independent GPT-5.6 Sol / High
  re-verification. It provides pure UTC causal-prefix replay through existing Analysis, News, Strategy, and
  suggestion-only TradePlan output. Its second targeted remediation adds exact interior candle-gap reconciliation,
  execution-entry source rebinding through a private canonical snapshot, and a complete D2A replay-input identity
  over the D1 manifest plus Strategy/Analysis/News/tick-size semantics. The Backtesting Engine is not complete:
  no Risk replay integration, fill simulation, PnL/metrics engine, persistence, API, or results UI exists.
- The current `/backtesting` page renders Strategy Lab historical evaluation snapshots. These are not trades,
  fills, PnL, an equity curve, or a real backtest.

### Not Implemented / Not Authorized
- Paper trading execution, OMS, live position management, broker order routing, and live automatic trading.
- Model routing, walk-forward optimization, Monte Carlo, optimization/tuning, and AI strategy generation.

---

## 3. Batch D Architecture Finding
Existing causal Market Data, Analysis, Strategy, TradePlan, and Risk contracts are reusable. The current live
Risk evaluation orchestration is not directly reusable by historical replay because it acquires database locks
and interacts with live Kill Switch, data-health, decisions, and reservations. Batch D requires a shared,
side-effect-free policy seam and isolated simulation state; no live table or authority state may be mutated.

Governance therefore split D2 into independently gated units. D2A owns only the causal replay foundation
through existing Analysis, Strategy, and suggestion-only TradePlan output. D2B will separately extract and
prove parity of the shared pure Risk policy seam. D2C will later integrate the two. This prevents replay
causality work from being coupled to a safety-critical live Risk refactor.

The approved staged data flow is:

`historical data -> UTC replay -> structure -> strategy/TradePlan -> isolated Risk policy -> simulated execution -> ledgers -> metrics`

---

## 4. Current Governance
- Batch B: **CLOSED**.
- Batch C: **CLOSED**.
- Batch D: **OPEN; D1 CLOSED**.
- D1: **CLOSED**.
- D2A: **REMEDIATED — PENDING INDEPENDENT RE-VERIFICATION**.
- NEW-D2A-RV-001, V-D2A-14-RV-01, and NEW-D2A-RV-002 are remediated locally and pending independent
  re-verification; V-D2A-14 has the same roll-up status.
- D2B, D2C, and D3–D7: **NOT AUTHORIZED**.
- Backtesting: **CAUSAL REPLAY FOUNDATION REMEDIATED; PENDING INDEPENDENT VERIFICATION; RISK/FILL ENGINE NOT IMPLEMENTED**.
- Model Routing: **NOT AUTHORIZED**.
- Paper Trading: **NOT AUTHORIZED**.
- Broker Execution: **NOT AUTHORIZED**.
- Live Trading: **NOT AUTHORIZED**.
- R0-P3-001 lock-timeout API semantics remains open, non-blocking P3, and outside D1.

---

## 5. Authoritative References
- Working rules: `AGENTS.md`
- Active scope and exact boundaries: `docs/CURRENT_BATCH.md`
- Machine-readable registry: `docs/SYSTEM_CAPABILITIES.yaml`
- Documentation index: `docs/README.md`
- Rolling handoff: `docs/HANDOFF.md`
