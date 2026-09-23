# Rolling Agent Handoff — AIGoldTrader

## Session Result
- Date: 2026-09-23.
- Branch: `main`.
- Starting HEAD and origin/main: `777d5564a033e6c98d8158eeca5a3722cdeef262`.
- Starting worktree: clean.
- Runtime selected by operator: GPT-5.6 Sol / Medium.
- Batch D remains an open split program.
- D1 is implemented and pending independent verification.
- D2–D7 remain not authorized.

## D1 Production Delta
- Added `backend/app/services/backtesting/__init__.py` for explicit D1 version exports.
- Added `backend/app/services/backtesting/domain.py` for frozen configuration, lifecycle, coverage,
  gap, news-vintage, provenance, manifest, and run-envelope contracts.
- Added `backend/app/services/backtesting/fingerprint.py` for pure canonical JSON and SHA-256 identities.
- Added `backend/app/services/backtesting/policy.py` for exact server-owned resource ceilings and
  stable bounded rejection codes.
- Added `backend/app/services/backtesting/isolation.py` for the declarative simulation/live boundary.
- No existing Market Data, Strategy, Risk, AI, persistence, API, or frontend source was changed.

## Contract Decisions
- Symbol scope is exactly XAUUSD and canonical Market Data `Timeframe` is reused.
- Strategy IDs are STRAT01–STRAT06; profile IDs are the seven existing canonical profiles.
- Requested start/end are aware, normalized to UTC, increasing, and bounded to 366 days.
- Initial balance and all cost assumptions are finite Decimal values.
- Costs explicitly model spread price, slippage price per side, and USD commission per lot per side.
- Contracts use Pydantic `extra="forbid"`, `frozen=True`, and immutable tuples.
- Lifecycle is limited to CREATED, RUNNING, COMPLETED, FAILED, and CANCELLED.
- Backtest identities use the `bt_` namespace and never reuse live reservation/order/position identity.

## Resource Authority
- Maximum period: 366 days.
- Maximum primary replay events: 250,000.
- Maximum total candle inputs: 1,000,000.
- Active runs: 1 per user and 2 system-wide; pending queue: 8.
- Maximum candidates/trades: 100,000 each per run.
- Maximum equity points: 250,000; estimated output: 128 MiB; page size: 500.
- These values are server-owned Literal contracts and cannot be overridden by run configuration.
- Pure declared-counter validation returns stable `ResourceRejectionCode` values.

## Coverage and Reproducibility
- Coverage distinguishes requested, warm-up, usable, and per-timeframe ranges.
- Gaps are typed as scheduled/expected or unexpected with bounded codes.
- SUFFICIENT coverage rejects event shortfalls, unexpected gaps, and required missing news vintages.
- STRAT05/STRAT06 manifests require causal historical news-vintage availability.
- Executable manifests reject INSUFFICIENT or INVALID coverage.
- Canonical serialization sorts keys, preserves sequence order, normalizes aware datetimes to UTC,
  emits enums by value, and never converts Decimal through float.
- Decimal numeric equivalence is intentional: insignificant trailing fractional zeroes are removed.
- Fingerprint layers cover configuration, resource policy, coverage, provenance, and run input.
- Run/database/correlation identities and wall-clock creation metadata are outside semantic input identity.

## Isolation and Scope
- D1 imports no live RiskEngine, Risk repository, Kill Switch, AI, broker/MT5, database, API,
  Strategy persistence/lifecycle, or SQLAlchemy model module.
- D1 performs no Session/AsyncSession/commit/flush/execute/order_send call.
- No replay, candle iteration, prefix runner, Risk policy seam, fills, trade ledger, portfolio lifecycle,
  PnL, metrics, equity curve, persistence, migration, API, UI, or background job was added.
- `TRADING_MODE=PAPER`, `LIVE_AUTO_TRADING=false`, and the authority hierarchy remain unchanged.

## Verification Evidence
- D1 focused and architecture tests: 48 passed, 0 failed/errors.
- Targeted existing Market/Strategy/Risk regression: 117 passed, 0 failed/errors.
- Ruff on all new Python and test files: passed.
- Existing dependency deprecation warnings were informational and unchanged.
- Final `git diff --check` and D1-only scope review passed; commit, push, and clean-worktree evidence is
  reported in the session result.

## Next Authorized Activity
- D1 independent verification only.
- Required runtime: GPT-5.6 Sol / High.
- Do not authorize or implement D2.
- Do not implement replay, Risk seam, fills, metrics, persistence/API/UI, Model Routing,
  Paper Trading, OMS, broker execution, or live trading.
