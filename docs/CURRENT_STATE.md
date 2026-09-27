# Canonical Current Operational State — AIGoldTrader

- **Last Verified Date**: 2026-09-27
- **Authoritative Branch**: `main`
- **Current Milestone**: Batch D remains OPEN; D1 and D2A are CLOSED.
- **Current Active Gate**: D2B1 Pure Risk Contracts and Deterministic Policy Core — AUTHORIZED FOR IMPLEMENTATION.
- **Next Permitted Activity**: D2B1 implementation only, using GPT-5.6 Sol / High.
- **Prohibited Progression**: D2B2 live-wrapper migration, D2C, and D3–D7 remain NOT AUTHORIZED.

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
- **D2A Causal Replay Foundation**: implemented and independently verified by GPT-5.6 Sol / High. It provides
  deterministic aware-UTC replay, canonical primary-event close semantics, a fixed causal warm-up origin, and a
  hard causal ceiling at exact `coverage.usable_end`; no event after that ceiling is eligible. It preserves M1–W1
  causal close visibility, point-in-time news revisions, quote timestamp plus `observed_at` causality, prefix and
  future-source-mutation invariance, causal historical-state reconstruction, exact scheduled-closure gap
  reconciliation, and fail-closed undeclared interior-gap handling. Inputs are bounded and bound to a private
  canonical replay snapshot with complete configuration/input identity. Selected-strategy evaluation preserves
  canonical Strategy candidate and TradePlan parity, deterministic event ordering, output fingerprints, and
  repeat-run determinism without DB, Risk, AI, broker/MT5, network, or filesystem-write dependencies.
- **Backtesting Engine**: NOT COMPLETE. No Risk replay integration, fill simulation, trade lifecycle, PnL,
  equity curve, metrics engine, persistence, Backtesting API, or results UI exists.
- **D2B governance**: PLAN REQUIRES SPLIT. D2B1 is authorized to add an infrastructure-free pure Risk input/result
  contract and deterministic policy kernel with characterization, parity, determinism, and isolation tests.
  The existing live `RiskEngine.evaluate_candidate()` remains the behavioral oracle and must not delegate to the
  new core during D2B1. D2B2 live-wrapper migration and D2C replay/Risk integration are NOT AUTHORIZED.
- **D2A identity model**: `historical_data_fingerprint` identifies the complete historical source snapshot;
  `run_input_fingerprint` identifies the governed D1 manifest; `replay_input_fingerprint` identifies that manifest
  plus complete D2A replay configuration; `replay_fingerprint` identifies causal output through the effective
  cutoff; and `stop_at` is an output-prefix selector only.
- **D2A usable-period authority**: `requested_cutoff` is `stop_at` when provided, otherwise
  `manifest.config.end`; the effective cutoff is the minimum of requested cutoff, `manifest.config.end`, and
  `manifest.coverage.usable_end`. An event exactly at `usable_end` may be eligible, an event after it is not, and
  a non-aligned `usable_end` is never rounded forward.
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
through existing Analysis, Strategy, and suggestion-only TradePlan output. D2B is further split: D2B1 extracts
and proves the pure Risk contracts/kernel, while D2B2 will later migrate the live wrapper and close parity.
D2C will later integrate replay with the verified seam. This prevents replay
causality work from being coupled to a safety-critical live Risk refactor.

The approved staged data flow is:

`historical data -> UTC replay -> structure -> strategy/TradePlan -> isolated Risk policy -> simulated execution -> ledgers -> metrics`

---

## 4. Current Governance
- Batch B: **CLOSED**.
- Batch C: **CLOSED**.
- Batch D: **OPEN; D1 and D2A CLOSED**.
- D1: **CLOSED**.
- D2A: **CLOSED** following PASS at the GPT-5.6 Sol / High D2A Usable-Period Independent Re-Verification gate.
- NEW-D2A-RV-001, V-D2A-14-RV-01, NEW-D2A-RV-002, V-D2A-14, NEW-D2A-RV-003, V-D2A-06,
  V-D2A-10, V-D2A-12/13, V-D2A-29, and V-D2A-36 are **CLOSED**.
- D2B governance: **PLAN REQUIRES SPLIT**.
- D2B1 Pure Risk Contracts and Deterministic Policy Core: **AUTHORIZED FOR IMPLEMENTATION**.
- D2B2 Live Risk Wrapper Migration and Parity Closure: **NOT AUTHORIZED**.
- D2C and D3–D7: **NOT AUTHORIZED**.
- Backtesting: **CAUSAL REPLAY FOUNDATION IMPLEMENTED AND VERIFIED; RISK/FILL ENGINE NOT IMPLEMENTED**.
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
