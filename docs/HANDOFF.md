# Rolling Agent Handoff — AIGoldTrader

## Governance Result
- Date: 2026-09-23.
- Branch at review start: `main`.
- Starting HEAD and origin/main: `e2099bb8d10409231c2a640b096cbbabba9d4ade`.
- Starting worktree: clean.
- Decision: **PLAN REQUIRES SPLIT**.
- Batch D is authorized as a gated deterministic-backtesting program.
- D1 is the only active implementation scope; D2–D7 are not authorized.
- No backend, frontend, test, migration, runtime, or dependency file changed in governance.

## Current State
- Batch B is closed.
- Batch C is closed; external AI remains HARDENING with fixture mode default.
- Backtesting remains not implemented.
- `/backtesting` currently renders Strategy Lab evaluation snapshots only.
- There is no historical fill engine, simulated trade ledger, equity curve, metrics engine, BacktestRun API,
  persistence, cancellation, or backtest-results UI.
- Paper trading, OMS, position management, broker routing, live trading, and model routing remain unauthorized.

## Reusable Architecture
- Market Candle is a strict UTC-aware Decimal contract with OHLC, canonical bucket, source, and closed state.
- Market persistence can query bounded source/symbol/timeframe ranges in ascending order.
- AnalysisEngine is deterministic, closed-candle-only, rejects duplicate/reversed input, and timestamps
  swing/structure/zone availability with `confirmed_at`.
- Strategy `build_context()` filters each timeframe to bars closed by an aware UTC cutoff.
- Existing tests prove future-candle prefix invariance and candle-by-candle strategy equality.
- Strategy contexts/candidates and TradePlans are immutable, versioned, fingerprinted, and evidence-bearing.
- STRAT01–STRAT06 and seven profiles must be reused unchanged.
- Risk policies, sizing, dependency fingerprints, account/directional limits, and APPROVED/REDUCED/BLOCKED
  semantics are reusable domain rules.

## Critical Risk Boundary
- Do not call the existing live `RiskEngine.evaluate_candidate()` directly from Backtesting Core.
- That orchestration acquires PostgreSQL advisory locks and reads/writes live Kill Switch, data health,
  decisions, and reservations.
- D2 must introduce/extract a side-effect-free shared risk-policy seam while preserving the live path.
- Historical evaluation uses only isolated simulation account/exposure/Kill Switch/news/quote-cost state.
- Architecture tests must prove no writes to live account, reservation, candidate, Kill Switch, order,
  position, or broker state and no external-AI dependency.

## Causal Replay Decision
- Replay time is a monotonic aware UTC `T` advanced by closed events.
- A bar is visible only after its timeframe close; higher-timeframe partial bars remain invisible.
- Every structural object, news revision, candidate, plan, and decision must be available by `T`.
- A plan created at candle close cannot fill from that already-consumed candle.
- Full-input-with-cutoff and causal-prefix replay must be identical at each `T`.
- Unexpected gaps, missing warm-up/news vintages, duplicates, reversed times, invalid OHLC, mixed sources,
  and timeframe mismatch fail closed. Prices are never manufactured.

## Execution Decision
- Execution is an isolated historical simulator, not Paper Engine, OMS, or broker execution.
- Spread, slippage, and commission are explicit server-validated deterministic assumptions.
- Same-candle SL+TP uses complete causal lower-timeframe order when available; otherwise SL-first worst-case.
- Gap-through-stop uses the worse available fill; favorable target improvement is not assumed.
- Ambiguity is recorded and remains in headline performance.
- End-of-run open positions close explicitly at the last usable executable price.

## Persistence Decision
- Future minimal tables: backtest_runs, backtest_candidates, backtest_trades, backtest_equity_points.
- Run stores canonical config, versions/fingerprints, coverage/provenance, lifecycle, limits, and metrics JSON.
- Candidate ledger stores plan and risk evidence, including blocked/reduced reasons.
- Trade ledger is immutable simulated evidence; equity points are bounded chart data.
- Do not reuse live execution/risk-reservation tables or add event sourcing/analytics infrastructure.

## Resource Decision
- Maximum requested period: 366 days.
- Maximum primary events: 250,000; maximum total candle inputs: 1,000,000.
- Active runs: 1 per user, 2 system-wide; pending queue: 8.
- Candidate/trade rows: 100,000 each; equity points: 250,000; estimated output: 128 MiB/run.
- Page size maximum: 500. Increases require governance review.

## Active D1 Scope
- Define immutable run/config/lifecycle/result/provenance/coverage contracts.
- Define engine/config/data fingerprints and version fields.
- Encode server-owned resource ceilings and fail-closed validation/error semantics.
- Define simulation/live isolation interfaces and import/write architecture tests.
- Add small hand-calculable fixtures and contract tests only.
- D1 must not add a replay runner, fill simulator, migration, API, UI, background task, or external AI call.

## Planned Gates
- D2: replay, no-lookahead, causal news, and pure Risk seam; not authorized.
- D3: fills, costs, ambiguity, portfolio/trade ledgers; not authorized.
- D4: metrics/equity/period dimensions; not authorized.
- D5: PostgreSQL, bounded in-process jobs/cancellation, authenticated API; not authorized.
- D6: minimal Backtesting UI; not authorized.
- D7: full deterministic/security/regression independent closure; not authorized.
- Each transition requires explicit governance; never auto-progress.

## Safety and Verification
- Preserve `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false`.
- Preserve Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.
- No Redis, Kafka, Celery, Kubernetes, microservices, Vector DB, GPU, or ML pipeline.
- Future implementation runtime: GPT-5.6 Sol / Medium.
- Mandatory independent verification runtime: GPT-5.6 Sol / High.
- The next authorized task is D1 implementation only.
