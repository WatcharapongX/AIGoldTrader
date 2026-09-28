# Canonical Current Operational State — AIGoldTrader

- **Last Verified Date**: 2026-09-28
- **Authoritative Branch**: `main`
- **Current Milestone**: Batch D remains OPEN; D1, D2A, D2B1, and D2B2 are CLOSED.
- **Current Active Gate**: D2C Verified Pure Risk Replay Integration is AUTHORIZED FOR IMPLEMENTATION under the bounded stateless-baseline contract below.
- **Next Permitted Activity**: Implement D2C only, then stop for an independent GPT-5.6 Sol / High verification gate.
- **Prohibited Progression**: D3–D7 remain NOT AUTHORIZED; D2C authorization does not include fills, state evolution, persistence, API, or UI.

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
- **D2B governance**: PLAN REQUIRES SPLIT. D2B1 implemented, remediated, and independently verified an
  infrastructure-free pure Risk input/result contract and deterministic policy kernel with characterization,
  parity, determinism, authority, and isolation tests; D2B1 is CLOSED.
  D2B2 has migrated the live `RiskEngine.evaluate_candidate()` wrapper to that core while retaining stateful
  locks, persistent Kill Switch/data-health authority, idempotency, reservation reconciliation, transaction
  behavior, and the legacy public BLOCKED projection. Independent re-verification found and closed one fixed-scale
  BLOCKED serialization parity defect; D2B2 is CLOSED. The separate D2C governance authorization is recorded
  below.
- **D2B1 requested-risk clarification**: RESOLVED. Pure semantic truth separates the exact
  `caller_requested_risk_pct`, compatibility-normalized request (`None` and zero map to policy maximum),
  post-modifier `target_risk_pct`, and final `approved_risk_pct`. BLOCKED pure results retain caller/normalized/
  target truth with approved risk zero. The current BLOCKED `RiskDecision` policy-maximum requested-risk value is
  a legacy live-wrapper projection and is not modified in D2B1. Negative risk was characterized as a deterministic
  sizing BLOCK with no reservation side effect and is safely represented without a new validation policy.
- **D2B1 verification closure**: D2B1-IV-P2-001, D2B1-IV-P2-002, D2B1-IV-P2-003, and D2B1-IV-P3-001 are
  **CLOSED** following final independent re-verification PASS. The pure execution boundary validates symbol-spec
  authority, reconstructs a private canonical input snapshot, owns deterministic Decimal context, fingerprints
  context-independent Decimal values, and preserves BLOCKED live warning projection while retaining target truth.
- **D2C governance authorization**: **PLAN APPROVED WITH CONDITIONS** as one implementation unit. D2C is a
  separate in-process backtesting layer which privately canonicalizes caller inputs through the existing D2A
  `make_replay_inputs()` boundary, obtains `ReplayStrategyEvent` values from `replay()`, constructs exact-time
  historical/scenario `PureRiskEvaluationInput` values, and calls `evaluate_pure_risk()` directly. It must not
  import or call `risk.live_adapter`, `RiskEngine`, reservations, Kill Switch persistence, SQLAlchemy, or any live
  repository. Every plan-bearing event is evaluated independently against the same non-evolving account and zero-
  exposure baseline. No-plan events remain explicit `NOT_EVALUATED_NO_PLAN` audit records. `APPROVED`, `REDUCED`,
  and `BLOCKED` are evidence only and create no reservation, fill, position, trade, PnL, or state transition.
- **D2C historical authority**: the complete caller-supplied `RiskPolicy` must match
  `manifest.provenance.risk_policy_version` and is bound by content. Symbol economics are an immutable
  `BACKTEST_ASSUMPTION`, projected at event time only as scenario-effective input, never claimed as historical
  broker observation. With news Risk enabled, causal non-fixture historical news coverage is required for every
  strategy. Quotes are selected only when both market timestamp and `observed_at` are at or before event time;
  absence produces `PureQuoteState.UNAVAILABLE` and an ordinary pure Risk BLOCK.
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
through existing Analysis, Strategy, and suggestion-only TradePlan output. D2B is further split: D2B1 extracted
and proved the pure Risk contracts/kernel, while D2B2 migrated and independently verified the live wrapper with
exact public parity. D2C will later integrate replay with the verified seam. This prevents replay
causality work from being coupled to a safety-critical live Risk refactor.

The approved staged data flow is:

`historical data -> UTC replay -> structure -> strategy/TradePlan -> isolated Risk policy -> simulated execution -> ledgers -> metrics`

---

## 4. Current Governance
- Batch B: **CLOSED**.
- Batch C: **CLOSED**.
- Batch D: **OPEN; D1, D2A, D2B1, and D2B2 CLOSED**.
- D1: **CLOSED**.
- D2A: **CLOSED** following PASS at the GPT-5.6 Sol / High D2A Usable-Period Independent Re-Verification gate.
- NEW-D2A-RV-001, V-D2A-14-RV-01, NEW-D2A-RV-002, V-D2A-14, NEW-D2A-RV-003, V-D2A-06,
  V-D2A-10, V-D2A-12/13, V-D2A-29, and V-D2A-36 are **CLOSED**.
- D2B governance: **PLAN REQUIRES SPLIT**.
- D2B1 Pure Risk Contracts and Deterministic Policy Core: **CLOSED — FINAL INDEPENDENT RE-VERIFICATION PASS**.
- D2B1-IV-P2-001, D2B1-IV-P2-002, D2B1-IV-P2-003, D2B1-IV-P3-001:
  **CLOSED**.
- D2B1 requested-risk semantic clarification: **RESOLVED**.
- D2B2 Live Risk Wrapper Migration and Parity Closure: **CLOSED — FINAL INDEPENDENT RE-VERIFICATION PASS**.
- D2C: **AUTHORIZED FOR IMPLEMENTATION — STATELESS VERIFIED PURE RISK REPLAY INTEGRATION ONLY**.
- D3–D7: **NOT AUTHORIZED**.
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
