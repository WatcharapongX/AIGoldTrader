# Canonical Current Operational State — AIGoldTrader

- **Last Verified Date**: 2026-09-23
- **Authoritative Branch**: `main`
- **Current Milestone**: Batch D governance authorized as a split deterministic-backtesting program.
- **Current Active Gate**: D1 — Domain Contracts, Reproducibility, and Isolation Boundary.
- **Next Authorized Activity**: Implement D1 only within `docs/CURRENT_BATCH.md`.
- **Prohibited Progression**: D2–D7 remain unapproved until the preceding gate is independently closed.

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

### Planned / Authorized, Not Implemented
- **Deterministic Backtesting Core**: Batch D is authorized only as a split program. D1 is the sole active
  implementation scope. No replay runner, execution simulator, persisted run, API, or results UI exists yet.
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

The approved staged data flow is:

`historical data -> UTC replay -> structure -> strategy/TradePlan -> isolated Risk policy -> simulated execution -> ledgers -> metrics`

---

## 4. Current Governance
- Batch B: **CLOSED**.
- Batch C: **CLOSED**.
- Batch D: **AUTHORIZED AS A SPLIT PROGRAM; D1 ACTIVE ONLY**.
- Backtesting: **PLANNED / AUTHORIZED, NOT IMPLEMENTED**.
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
