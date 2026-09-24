# Current Active Batch — AIGoldTrader

## Batch Identifier
**Batch D — Deterministic Backtesting Core**

## Governance Decision
**PLAN REQUIRES SPLIT.** Batch D is authorized only as the gated program below.

**Current gate: D2A — REMEDIATED, PENDING INDEPENDENT RE-VERIFICATION.**

The D2 governance review determined that D2 is too broad to implement safely as one unit. It is split into
D2A causal replay, D2B shared pure Risk policy, and D2C replay/Risk integration. D2A targeted remediation is
complete but not closed; only its independent GPT-5.6 Sol / High re-verification is authorized now.
D2B, D2C, and D3–D7 remain **NOT AUTHORIZED** and require separate governance advancement after the
preceding unit is implemented, independently verified, documented, and closed. Do not automatically progress.

## Current State
- Batch B: **CLOSED**.
- Batch C: **CLOSED**.
- External AI: **HARDENING**; deterministic fixture mode remains the default.
- Backtesting: **CAUSAL REPLAY FOUNDATION REMEDIATED; PENDING INDEPENDENT VERIFICATION; RISK/FILL ENGINE NOT IMPLEMENTED**.
- D2A causal replay is remediated and locally verified, pending independent re-verification; this does not make
  the Backtesting Engine complete.
- The `/backtesting` page currently renders Strategy Lab historical evaluation snapshots only.
  Those snapshots are not a backtest engine and must not be described as one.

## Objective
Create a deterministic, reproducible, single-symbol historical simulation engine for XAUUSD
that reuses existing causal Market Data, Market Structure, STRAT01–STRAT06, TradePlan, and Risk
policy semantics. The engine must produce auditable candidate, risk, simulated-trade, equity, and
metric results without an external LLM and without any live trading side effect.

## Non-Negotiable Architecture
```
authoritative historical candles/news vintages
  -> chronological closed-event replay clock
  -> existing causal analysis/market structure
  -> existing Strategy Engine and TradePlan geometry
  -> side-effect-free shared Risk policy evaluation
  -> isolated deterministic execution simulator
  -> candidate/risk ledger + simulated trade ledger
  -> equity curve + canonical metrics
```

Do not create backtesting-only copies of STRAT01–STRAT06 or market-structure rules.

The existing live `RiskEngine.evaluate_candidate()` path is not safe to call from a backtest:
it acquires account locks and reads/writes live Kill Switch, data-health, decision, and reservation
state. Batch D must extract or introduce a side-effect-free shared risk-policy decision seam while
preserving current live Risk behavior and tests. Historical adapters may supply only isolated
simulation account, exposure, Kill Switch, quote/cost, and point-in-time news state.

## No-Lookahead Authority Model
- The replay clock `T` is an aware UTC timestamp advanced monotonically by closed market events.
- At `T`, a candle is visible only when `open_time + timeframe_duration <= T`.
- Higher-timeframe bars remain unavailable until their own close; partial bars cannot be treated as closed.
- Swings, structure events, zones, sessions, and patterns are visible only when `confirmed_at <= T`.
- Later invalidation or outcome state is visible only after its causal `ended_at`/event time.
- News values and revisions are visible only when `available_at <= T`; later revisions are excluded.
- Quotes/observations must have both market timestamp and observation availability at or before `T`.
- Strategy context, candidate, TradePlan, risk decision, and simulated account snapshot use the same `T`.
- A plan created from the close at `T` cannot fill from that candle's already-consumed range; the earliest
  eligible trigger is the next chronological event after `T`.
- Wall-clock time, future data, completed-run outcomes, and external AI are never inputs to core replay.

Prefix-invariance is the acceptance oracle: replaying a full dataset with cutoff `T` must produce the
same state and decisions as replaying only the causal prefix available through `T`.

## Historical Data and Quality Policy
- Initial symbol scope is exactly `XAUUSD`; use only existing canonical timeframes M1–W1.
- Validate requested period, actual usable period, warm-up period, source, and provenance before RUNNING.
- Reject duplicate, reversed/non-monotonic, misbucketed, mixed-source/timeframe, invalid-OHLC, and stale data.
- Classify scheduled market closures separately from unexpected gaps. Never manufacture missing prices.
- Default policy is fail-closed on any required unexpected gap or insufficient strategy/news warm-up.
- `COMPLETED_WITH_DATA_GAPS` is not authorized. A materially incomplete run is `FAILED` with coverage evidence.
- STRAT05/STRAT06 require causal historical news vintages. If unavailable, the run fails coverage validation;
  fixture news or later-revised values cannot be presented as historical truth.

## Deterministic Execution Policy
- Execution is historical simulation only: no broker API, MT5 `order_send`, Paper Engine, OMS, or live position.
- Entry triggers only after plan creation, when an eligible future event touches the complete entry rule.
- Apply configured spread and slippage adversely and deterministically; commission is explicit and deterministic.
- Cost assumptions are scenario inputs and provenance, never mislabeled as observed market quotes.
- Stops and targets use adjusted executable prices. Gaps through a stop fill at the worse available price.
- Gaps through a target do not receive unobserved favorable price improvement beyond the configured rule.
- If SL and TP are both reachable in one candle, use complete causal lower-timeframe data when available;
  otherwise resolve SL first (worst-case), set an ambiguity flag, and include the trade in headline metrics.
- Expiry and strategy invalidation cancel an unfilled plan at their causal event time.
- An open trade at end of range is closed by an explicit `END_OF_RUN` rule at the last usable executable price.

## Minimal Simulation State
One isolated account context contains initial/current balance, equity, peak equity, realized/unrealized PnL,
open and reserved risk, drawdown, consecutive losses, cooldown, and bounded active simulated positions.
Existing account/symbol/directional/concurrent risk policy semantics remain authoritative. Simulation objects
must use backtest-specific types and identifiers and must never write live account, reservation, candidate,
Kill Switch, order, position, or exposure state.

## Persistence Boundary
PostgreSQL remains authoritative. The approved minimal future entities are:
- `backtest_runs`: owner, lifecycle, canonical request/config JSON, fingerprints/versions, data coverage and
  provenance, resource counters, timestamps, error/cancellation reason, and final metrics JSON.
- `backtest_candidates`: candidate/TradePlan evidence and fingerprints, risk decision APPROVED/REDUCED/BLOCKED,
  reasons, requested/approved risk, and whether entry was reached.
- `backtest_trades`: immutable simulated lifecycle, prices, size/risk, exit reason, gross/cost/net PnL, R,
  ambiguity/provenance, and result status.
- `backtest_equity_points`: bounded UTC equity/drawdown points sufficient for UI charting.

No event sourcing, analytics database, Vector DB, or reuse of live order/position/risk-reservation tables.

## Canonical Metrics
Total trades, wins, losses, breakeven, win/loss rates, gross profit/loss, net profit, profit factor,
average win/loss, average R, expectancy, maximum drawdown and percentage, return percentage,
consecutive wins/losses, long/short results, and strategy breakdown. Day/week/month/session/regime/
strategy/direction dimensions must remain derivable from immutable trade evidence; avoid cosmetic metrics.

## Resource Bounds
Server validation must enforce all bounds. Initial hard ceilings for implementation are:
- requested period: 366 days;
- primary replay events: 250,000; total candle inputs across required frames: 1,000,000;
- active runs: 1 per user and 2 system-wide; bounded pending queue: 8;
- persisted candidates/trades: 100,000 each per run; equity points: 250,000 per run;
- estimated persisted output: 128 MiB per run; list page size: 500.

D1 must encode these as server-owned policy and document rejection semantics. Later reduction is allowed after
profiling; increases require a governance review. Requests must never allocate unbounded memory or output.

## Planned API Boundary (Not Yet Authorized for Implementation)
- `POST /api/backtests`
- `GET /api/backtests/{id}` (includes lifecycle and canonical metrics)
- `GET /api/backtests/{id}/trades`
- `GET /api/backtests/{id}/equity`
- `POST /api/backtests/{id}/cancel`

Use existing authentication, ownership, Pydantic validation, error envelopes, correlation IDs, and pagination.
No Risk bypass control is exposed. Cancellation is cooperative and may transition only RUNNING/CREATED to
CANCELLED; partial output can remain diagnostic but cannot be labeled authoritative COMPLETED.

## Planned Minimal UI (Not Yet Authorized for Implementation)
The existing route may later receive a configuration panel (date range, XAUUSD, timeframe, strategy, profile,
initial balance, spread, slippage, commission), lifecycle/status, KPI summary, equity/drawdown chart, paginated
trade list, and strategy/direction filters. Backend truth and provenance badges come first; no broader redesign.

## Gated Sub-Batches
1. **D1 — CLOSED**: foundational immutable domain contracts, reproducibility controls,
   coverage/provenance authority, resource policy, lifecycle semantics, and the simulation/live isolation
   boundary passed independent verification. No runner, migration, API, UI, background task, or simulated
   fill implementation exists.
2. **D2A — REMEDIATED / PENDING INDEPENDENT RE-VERIFICATION**: pure, single-threaded causal replay foundation through existing
   Analysis, Strategy, and suggestion-only TradePlan evaluation. The implementation scope is limited to:
   - an aware-UTC monotonic replay clock advanced by unique chronological closed primary-timeframe candles;
   - canonical input validation and D1 admission limits before unbounded materialization;
   - exact governed interior-bucket reconciliation against canonical scheduled-closure gap evidence, without a
     hardcoded market calendar or fabricated prices;
   - authoritative execution-entry reconstruction into a private canonical snapshot, including historical-source
     fingerprint rebinding even when the convenience factory is bypassed or its returned object is later mutated;
   - a complete D2A replay-input fingerprint over the D1 manifest identity and exact StrategyConfig,
     AnalysisConfig, NewsConfig, tick-size, and replay-engine semantics, kept separate from causal output identity;
   - causal M1–W1 projection by each timeframe's own close, point-in-time news revision projection by
     `available_at`, and quote visibility only when both `timestamp <= T` and `observed_at <= T`;
   - fixed-origin warm-up feeding with no reportable candidate/TradePlan output before `requested_start`;
   - reuse of `AnalysisEngine`/`analyze`, `build_context(..., replay=True)`, `strategy.engine.evaluate`,
     STRAT01–STRAT06, profiles, and existing TradePlan geometry without backtest-specific strategy copies;
   - deterministic in-memory context/candidate/TradePlan replay events ordered by
     `(as_of, profile_id, strategy_id, candidate_id)` with bounded stable failure codes;
   - prefix-recomputation as the reference correctness oracle; incremental optimization is allowed only when
     proven semantically equivalent, and checkpoint/caching optimization is not authorized in D2A;
   - a server-owned replay-engine version replacing the D1 placeholder only when the D2A implementation exists,
     included in existing provenance and run-input fingerprint authority;
   - focused prefix-invariance, future-mutation, higher-timeframe close, news-revision, quote-observation,
     repeat-determinism, resource-bound, and isolation tests.
3. **D2B — PLANNED / NOT AUTHORIZED**: extract a typed, immutable, side-effect-free shared Risk policy core.
   It must preserve live policy ordering and behavior; accept explicit account, policy, symbol spec, quote/news,
   portfolio exposure, lifecycle, isolated Kill Switch state, and replay `T`; reuse deterministic sizing and safe
   fingerprint components; and leave database locks, live automatic Kill Switch mutation/read, idempotency,
   repository access, and reservation release/create in the live wrapper. Independent Sol/High parity review is
   required before D2C.
4. **D2C — PLANNED / NOT AUTHORIZED**: integrate D2A candidate/TradePlan output with the verified D2B pure Risk
   seam, deterministic risk-decision event ordering/fingerprinting, and complete replay/Risk parity and isolation
   tests. No fills, trade lifecycle, PnL, or persistence.
5. **D3 — PLANNED / NOT AUTHORIZED**: deterministic fills, costs, ambiguity, isolated portfolio lifecycle,
   candidate/risk/trade in-memory ledgers.
6. **D4 — PLANNED / NOT AUTHORIZED**: canonical metrics, equity/drawdown, and derivable period dimensions.
7. **D5 — PLANNED / NOT AUTHORIZED**: additive PostgreSQL persistence, bounded in-process execution/cancellation,
   authenticated API, ownership and output pagination. No Celery/Redis/Kafka.
8. **D6 — PLANNED / NOT AUTHORIZED**: minimal Backtesting UI consuming authoritative D5 APIs.
9. **D7 — PLANNED / NOT AUTHORIZED**: determinism, no-lookahead, security/resource, migration, API, browser,
   and full regression independent closure gate.

## Required Test Program
- Same code/config/data/request produces byte-equivalent canonical results and fingerprints.
- Prefix/full-input equality at every replay cutoff; future candle/swing/confirmation/news revision/evidence/
  TradePlan/outcome mutations cannot change the prefix result.
- Entry missed/reached, SL, TP, gaps, same-candle SL+TP, expiry, invalidation, blocked/reduced Risk decision,
  missing data, end-of-run close, cancellation, restart/failure, and limit rejection.
- Small hand-calculated fixtures for PnL, costs, R, rates, profit factor, expectancy, drawdown, and return.
- Architecture tests prove zero imports/calls/writes to broker execution, live orders/positions/reservations,
  production candidate lifecycle, global Kill Switch mutation, and external AI from Backtesting Core.
- Preserve all Batch B authentication and Batch C external-AI regression gates.

## Strictly Out of Scope / Not Authorized
- Model routing or any new AI agent/framework; external LLM calls in core replay.
- Walk-forward optimization, Monte Carlo, genetic optimization, parameter tuning, ML/AI strategy discovery.
- Multi-symbol portfolio backtesting in Batch D.
- Paper trading execution, real OMS, live position management, broker adapters, MT5 `order_send`, live trading.
- Redis, Kafka, Celery, Kubernetes, microservices, Vector DB, GPU, or ML pipelines.

## Safety Invariants
- `TRADING_MODE=PAPER` remains enforced and `LIVE_AUTO_TRADING=false` remains enforced.
- Authority remains Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.
- AI remains advisory-only and has zero execution authority.
- Batch B and Batch C protections must not be weakened.

## Required Gates
- D1 is **CLOSED** following independent GPT-5.6 Sol / High re-verification.
- D1-IV-001 through D1-IV-006 are **CLOSED**.
- Governance result: **PLAN REQUIRES SPLIT**; D2A remediation is complete but not closed.
- Next authorized activity is D2A independent GPT-5.6 Sol / High re-verification only.

## D2A Second Targeted Remediation Status
- NEW-D2A-RV-001: **REMEDIATED — PENDING INDEPENDENT RE-VERIFICATION**.
- V-D2A-14-RV-01: **REMEDIATED — PENDING INDEPENDENT RE-VERIFICATION**.
- NEW-D2A-RV-002: **REMEDIATED — PENDING INDEPENDENT RE-VERIFICATION**.
- V-D2A-14 roll-up: **REMEDIATED — PENDING INDEPENDENT RE-VERIFICATION**.
- V-D2A-06: **CLOSED**.
- V-D2A-10: **CLOSED**.
- V-D2A-12/13: **CLOSED**.
- V-D2A-29: **CLOSED**.
- V-D2A-36: **CLOSED**.
- D2B, D2C, and D3–D7 remain not authorized. Do not begin the next sub-batch automatically.
