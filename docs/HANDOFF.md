# Rolling Agent Handoff — AIGoldTrader

## Session Result
- Date: 2026-09-28.
- Branch: `main`.
- Starting HEAD/origin-main: `885258738aecbb594213dc1f9d20457de3c4830d`.
- Starting worktree: clean.
- Activity: D2C governance/architecture/no-lookahead/Risk-state boundary review only.
- Governance result: **PLAN APPROVED WITH CONDITIONS**.
- Exactly one next implementation unit is authorized: D2C stateless verified pure-Risk replay integration.
- D2C was not implemented in this session and remains not yet verified.
- D1, D2A, D2B1, and D2B2 remain **CLOSED**; D3–D7 remain **NOT AUTHORIZED**.
- Backtesting Engine remains **NOT COMPLETE**.
- No production code, tests, database, migration, dependency, runtime, frontend, or trading configuration changed.

## Verified Foundations and Architecture
- D2A supplies canonical causal replay, hard `coverage.usable_end`, deterministic Strategy/optional TradePlan
  events, stable ordering, private input reconstruction, and separate complete-input/causal-output identities.
- D2B1 supplies immutable pure inputs/results, deterministic `evaluate_pure_risk()`, sizing, explicit authority,
  and semantic identity. D2B2 retains all live locks, persistence, idempotency, and reservations.
- D2C must privately canonicalize with `make_replay_inputs()`, invoke `replay()`, then call
  `evaluate_pure_risk()` directly. It must not import or call the D2B2 live adapter or engine.
- Every D2A event yields one D2C event: `EVALUATED` when a TradePlan exists or
  `NOT_EVALUATED_NO_PLAN` without a fabricated plan or Risk decision.
- Pure APPROVED/REDUCED/BLOCKED results are analysis evidence only. No reservation, fill, position, trade, PnL,
  equity, metric, persistence, API, or UI is authorized.

## Stateless Baseline
- Each plan is evaluated independently; no event consumes another event's capacity.
- Balance/equity/peak equity/free margin equal D1 `initial_balance`; daily/weekly/floating PnL, exposure,
  reservations, positions, and consecutive losses are zero. Account/state/observation time equals event T.
- Account and snapshot IDs are deterministic. Use existing `source="CONFIGURED_TEST"` with
  `trading_mode="BACKTEST"`, explicitly labeled non-live configured scenario evidence.
- Portfolio open/reserved/symbol/directional risk and counts are zero; integrity is `OK`.
- Kill Switch is isolated `INACTIVE` with `BACKTEST_NO_EXTERNAL_KILL_SWITCH` provenance.
- Data health is isolated `HEALTHY` with `BACKTEST_CAUSAL_DATA_ADMISSION` provenance.
- Candidate status comes from the D2A event; transition count is explicitly zero because no causal ledger exists.

## Risk Configuration and Symbol Authority
- Add a frozen separate `RiskReplayConfig`; do not alter D1 `BacktestRunConfig`.
- It contains the complete offline `RiskPolicy`, exact caller-requested risk, and full XAUUSD symbol-spec
  assumption. Policy version must equal manifest provenance and every policy field is fingerprinted.
- Requested risk defaults to `None`, is finite/non-negative/bounded, and passes unchanged to the pure core. None
  and explicit zero keep verified normalization while remaining different audit identities.
- Symbol economics are a `BACKTEST_ASSUMPTION`, never historical broker truth. At T, the projected pure spec uses
  `observed_at=T` only to mean scenario-effective at T, with deterministic identity and no broker server.

## Historical News and Quote Authority
- With news Risk enabled, every strategy requires complete causal non-fixture historical news: matching vintage
  source, requested-period coverage, available calendar, and `news_mode="LIVE"`.
- Missing/unavailable/fixture news fails admission closed; it is never normalized to CALM. With news Risk disabled,
  Risk replay may proceed without news while D1/D2A Strategy-news rules remain unchanged.
- Reuse `news.engine.latest_known()` for point-in-time revisions; the pure core owns Risk news-window rules.
- Select the greatest-timestamp quote whose timestamp and `observed_at` are both at or before T.
- No quote becomes pure `UNAVAILABLE`; stale quotes remain available for pure freshness evaluation. Candles never
  supply fabricated bid/ask/spread.

## Identity and Failure Contract
- Configuration identity binds integration version, full policy, requested risk, spec, baseline/safety state, and
  causal projection semantics. Risk input identity binds D2A replay input identity plus that configuration.
- Evaluated-event input identity additionally binds canonical pure input, quote `observed_at`, source D2A event,
  and version. Event identity binds disposition and exact pure semantic fingerprint when evaluated.
- Output identity binds cutoff, D2A causal replay fingerprint, counters, and ordered D2C events. Future-only
  source suffix may change complete input identity but must not alter earlier causal output identity.
- Stable integration failures cover input, configuration, news, spec, causality, resource, and pure-policy
  evaluation errors. An ordinary pure Risk BLOCKED result is valid output, not a run failure.

## Next Activity and Safety
- Implement only backtest-local D2C contracts, fingerprints, adapter/orchestrator, and focused tests; a small
  backtesting package export is allowed. D2A and D2B production semantics must remain unchanged.
- Test D2A linkage, pure parity, same-T authority, causal news/quotes, baselines, requested risk, identity,
  ordering, prefix/future invariance, mutation attacks, bounds, determinism, and architecture isolation.
- Run D2A and D2B1 regressions. D2C closure requires a fresh independent GPT-5.6 Sol / High verification gate.
- After D2C implementation, stop; do not begin D3. D3–D7, fills, lifecycle, PnL/equity/metrics, persistence/API/UI,
  Model Routing, Paper Trading, OMS, broker execution, and Live Trading remain not authorized.
- Preserve `TRADING_MODE=PAPER`, `LIVE_AUTO_TRADING=false`, broker execution NONE, advisory-only AI, and the
  authority order Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.
