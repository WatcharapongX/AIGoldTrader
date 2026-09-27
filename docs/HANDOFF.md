# Rolling Agent Handoff — AIGoldTrader

## Session Result
- Date: 2026-09-27.
- Branch: `main`.
- Starting SHA: `0f6253811739366e8f34b3afeb90f22b276e208c`.
- Gate: Batch D2B Shared Pure Risk Policy Core governance authorization.
- Reviewer/runtime: GPT-5.6 Sol / High.
- Decision: **PLAN REQUIRES SPLIT**.
- D2B1: **AUTHORIZED FOR IMPLEMENTATION**.
- D2B2, D2C, and D3–D7: **NOT AUTHORIZED**.
- D1 and D2A remain **CLOSED**; Batch D remains **OPEN**.

## Source Finding
- `RiskEngine.evaluate_candidate()` mixes deterministic policy with live infrastructure.
- Pure behavior includes quote/news/account/lifecycle/spec gates, cooldown, exposure capacity,
  position sizing, reason/provenance construction, and semantic fingerprint inputs.
- Live behavior includes PostgreSQL locks, Kill Switch persistence/read, data-health counters,
  reservation reads/writes, cached-decision reconciliation, idempotency, and transactions.
- `PortfolioRiskManager.check_budget_capacity()` mixes locked reservation queries with pure math.
- `KillSwitchManager.evaluate_automatic_triggers()` mixes deterministic breach facts with DB mutation.
- `calculate_position_size()` is already deterministic pure Decimal math and is reusable unchanged.
- `is_cooldown_active()` is pure but currently located in the infrastructure-coupled portfolio module.

## D2B1 Authorized Unit
- Name: Pure Risk Contracts and Deterministic Policy Core.
- Add frozen, `extra="forbid"`, Decimal-safe, aware-UTC input/result contracts.
- Add explicit `as_of`; no wall-clock fallback or hidden lookup.
- Add explicit candidate, TradePlan, account, policy, spec, quote/news, lifecycle, Kill Switch,
  data-health, requested-risk, and portfolio exposure inputs.
- Add deterministic APPROVED/REDUCED/BLOCKED evaluation and pure capacity math.
- Add typed stable reason codes with existing Thai display text preserved.
- Add automatic daily-loss/drawdown/instantaneous data-safety trigger facts without mutation.
- Add a complete versioned pure semantic payload/fingerprint.
- Reuse current position sizing unchanged.
- Capture current live behavior as the immutable characterization/parity oracle.
- The live `RiskEngine.evaluate_candidate()` must not delegate to the new core in D2B1.

## Safety Boundaries
- Kill Switch input states are ACTIVE, INACTIVE, and UNKNOWN.
- ACTIVE blocks; UNKNOWN fails closed; only INACTIVE continues.
- Pure code never calls `check`, `get_state`, `activate`, or automatic mutation APIs.
- Daily-loss/drawdown facts are pure; live Kill Switch mutation remains D2B2 orchestration.
- Persistent provider/source data-health counters remain live DB state.
- Pure input receives already-derived health state; UNKNOWN is explicit and fail-closed.
- Duplicate active reservations become an explicit integrity anomaly input and block.
- DB reservation rows remain the live source of reserved risk; snapshot reserved risk is not double-counted.
- Positive unattributed open risk remains fail-closed.

## Portfolio, Sizing, and Identity
- Exposure input contains open/reserved, symbol, directional, active-reservation, and open-position state.
- Capacity order preserves cooldown, integrity, unattributed risk, concurrency, account, symbol,
  direction, per-trade cap/reduction, then approved amount.
- Sizing preserves worst-case entry, downward volume-step quantization, min/max volume,
  geometry validation, and actual risk not exceeding approved risk.
- Evaluation-intent identity may be reused unchanged only under parity fixtures.
- Current dependency fingerprint requires extraction to cover detailed portfolio/integrity/data-health state.
- DB row order, live-only IDs, random UUIDs, and wall time must not enter pure identity.
- `RiskDecision` and decision/reservation persistence identity remain live-wrapper responsibilities.

## Required D2B1 Tests
- Pure policy unit and full decision-matrix tests.
- Portfolio-capacity and duplicate-integrity parity.
- Kill Switch ACTIVE/UNKNOWN/INACTIVE matrix.
- News unavailable/blackout/pre-reduction/post-spread matrix.
- Quote, account, and spec freshness matrices using explicit `as_of`.
- Candidate terminal and TradePlan expiry cases.
- Sizing parity and fail-closed geometry/volume cases.
- Fingerprint sensitivity, invariance, and repeat determinism.
- Architecture isolation proving no SQLAlchemy/models/repository/Kill Switch/provider/MT5/network/filesystem/wall clock.
- Existing Risk regression remains the oracle; expected behavior may not be rewritten to fit refactoring.

## Capability and Trading Safety
- Backtesting causal replay remains implemented and verified; the Backtesting Engine remains incomplete.
- No Risk replay integration, fills, lifecycle, PnL, equity, metrics, persistence, API, or UI is authorized.
- `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` remain unchanged.
- Broker execution remains `NONE`; AI remains advisory-only.
- Authority remains Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.

## Next Gate
- Implement D2B1 only with GPT-5.6 Sol / High.
- Then run an independent GPT-5.6 Sol / High verification in a fresh session.
- D2B1 completion does not authorize D2B2 or D2C.
- Do not begin Model Routing, Paper Trading, OMS, broker execution, or live trading.
