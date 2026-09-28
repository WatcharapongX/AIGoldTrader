# Current Active Batch — AIGoldTrader

## Batch Identifier
**Batch D — Deterministic Backtesting Core**

## Governance Decision
**PLAN REQUIRES SPLIT.** Batch D is authorized only as the gated program below.

**Current gate: D2B2 — LIVE RISK WRAPPER MIGRATION AND PARITY CLOSURE — CLOSED FOLLOWING FINAL INDEPENDENT RE-VERIFICATION PASS.**

The D2 governance review determined that D2 is too broad to implement safely as one unit. It is split into
D2A causal replay, D2B shared pure Risk policy, and D2C replay/Risk integration. The D2A deterministic causal
replay foundation passed independent GPT-5.6 Sol / High verification and is closed. D2B governance found that the
pure policy extraction and safety-critical live-wrapper migration must be independently gated. **D2B1 — Pure
Risk Contracts and Deterministic Policy Core** passed final independent re-verification and is closed. D2B2 was
separately authorized, implemented, remediated, and passed the required independent GPT-5.6 Sol / High
re-verification gate. D2B2 is closed. D2C and D3–D7 remain **NOT AUTHORIZED**. Do not automatically progress.

## Current State
- Batch B: **CLOSED**.
- Batch C: **CLOSED**.
- External AI: **HARDENING**; deterministic fixture mode remains the default.
- Backtesting: **CAUSAL REPLAY FOUNDATION IMPLEMENTED AND VERIFIED; RISK/FILL ENGINE NOT IMPLEMENTED**.
- D2A causal replay is implemented, independently verified, and closed; this does not make
  the Backtesting Engine complete.
- D2B1 pure Risk contracts/kernel is independently verified and closed.
- D2B2 live-wrapper migration is independently verified and closed.
- D2B1 requested-risk semantic clarification is **RESOLVED**; the four-layer pure contract below is authoritative.
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
2. **D2A — CLOSED**: pure, single-threaded causal replay foundation through existing
   Analysis, Strategy, and suggestion-only TradePlan evaluation. The implementation scope is limited to:
   - an aware-UTC monotonic replay clock advanced by unique chronological closed primary-timeframe candles;
   - a canonical hard causal ceiling at `coverage.usable_end`, applied after private execution preparation and
     reflected exactly in `ReplayResult.cutoff` without truncating complete historical-source identity;
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
3. **D2B1 — CLOSED / FINAL INDEPENDENT RE-VERIFICATION PASS**: typed immutable pure Risk inputs/results, stable reason codes,
   deterministic policy evaluation, pure portfolio-capacity math, explicit time/safety state, reusable sizing,
   semantic fingerprinting, characterization fixtures, and pure/live parity tests. The existing live
   `RiskEngine.evaluate_candidate()` orchestration must remain the behavioral oracle and must not delegate to the
   new core in D2B1. No database, Kill Switch, reservation, API, replay, or persistence integration is authorized.
4. **D2B2 — CLOSED / FINAL INDEPENDENT RE-VERIFICATION PASS**: the live Risk wrapper delegates deterministic
   policy and sizing to the independently verified D2B1 core while preserving advisory and reservation row locks,
   automatic Kill Switch persistence, persistent data-health tracking, idempotency, existing-decision
   reconciliation, reservation atomicity, transactions, and exact public `RiskDecision` compatibility. Independent
   GPT-5.6 Sol / High re-verification passed; D2C still requires separate governance authorization.
5. **D2C — PLANNED / NOT AUTHORIZED**: integrate D2A candidate/TradePlan output with the verified D2B pure Risk
   seam, deterministic risk-decision event ordering/fingerprinting, and complete replay/Risk parity and isolation
   tests. No fills, trade lifecycle, PnL, or persistence.
6. **D3 — PLANNED / NOT AUTHORIZED**: deterministic fills, costs, ambiguity, isolated portfolio lifecycle,
   candidate/risk/trade in-memory ledgers.
7. **D4 — PLANNED / NOT AUTHORIZED**: canonical metrics, equity/drawdown, and derivable period dimensions.
8. **D5 — PLANNED / NOT AUTHORIZED**: additive PostgreSQL persistence, bounded in-process execution/cancellation,
   authenticated API, ownership and output pagination. No Celery/Redis/Kafka.
9. **D6 — PLANNED / NOT AUTHORIZED**: minimal Backtesting UI consuming authoritative D5 APIs.
10. **D7 — PLANNED / NOT AUTHORIZED**: determinism, no-lookahead, security/resource, migration, API, browser,
   and full regression independent closure gate.

## D2B Governance Decision
**PLAN REQUIRES SPLIT.** The current `RiskEngine.evaluate_candidate()` interleaves deterministic policy with
stateful live authority. Extracting the pure kernel and migrating the live wrapper in one change would couple
policy correctness to PostgreSQL locking, Kill Switch persistence, data-health counters, idempotency, and
reservation reconciliation. D2B is therefore split into D2B1 and D2B2. D2B1 is closed; D2B2 implementation was
separately authorized, implemented, remediated, independently re-verified, and closed.

### Responsibility Classification
**Pure policy** owns deterministic evaluation from explicit immutable inputs: Kill Switch state interpretation;
quote availability/freshness and absolute/post-news spread rules; news unavailable/blackout/pre-news reduction/
post-news monitoring and provenance; account freshness, equity, daily/weekly loss, drawdown and cooldown; candidate
terminal state and TradePlan expiry/status; symbol-spec validity/freshness; requested/min/max risk; open-risk
fail-closed behavior; account/symbol/directional/concurrency capacity math; position sizing; stable reason codes and
Thai text mapping; safety-trigger facts; and semantic payload/fingerprint construction.

**Live orchestration** retains `AsyncSession`, PostgreSQL advisory/row locks, account/policy/spec/news/quote
acquisition, automatic Kill Switch activation and state persistence/read, persistent provider/source data-health
counters, reservation queries/create/release/reconciliation, existing-decision lookup, idempotency cache handling,
decision persistence, transaction behavior, and live account/symbol authority.

**Mixed / extraction required** includes `RiskEngine.evaluate_candidate()`,
`PortfolioRiskManager.check_budget_capacity()`, `PortfolioRiskManager.get_summary()`,
`KillSwitchManager.evaluate_automatic_triggers()`, `_blocked_decision()`, and the current dependency fingerprint.
Their deterministic calculations move to the pure boundary; their DB mutation, live identity, and persistence
effects remain in the live wrapper. `default_gold_spec()` is a live/test convenience only because it defaults to
wall time; the pure core must never invoke it without an explicit `observed_at`.

### D2B1 Pure Input Contract
Add frozen Pydantic contracts with `extra="forbid"`, aware UTC timestamps, and Decimal-safe fields. A
`PureRiskEvaluationInput` must contain:
- explicit `as_of`; `SetupCandidate`; `TradePlanSuggestion`; `AccountSnapshot`; `RiskPolicy`; and
  `SymbolSpecification`;
- explicit quote available/unavailable state and quote data, with no provider fetch;
- normalized point-in-time news state/events/provenance, with no latest-revision or provider lookup;
- explicit Kill Switch state `ACTIVE`, `INACTIVE`, or `UNKNOWN` plus bounded provenance;
- explicit data-health state (`HEALTHY`, `DEGRADED`, `TRIGGERED`, or `UNKNOWN`) and already-derived persistent
  failure facts; the pure layer never owns a counter;
- authoritative candidate lifecycle status and transition count;
- requested risk percentage;
- an immutable portfolio exposure snapshot containing open risk, DB-authoritative reserved risk after exclusion
  of the exact candidate reservation, symbol risk, directional risk, active reservation count, open-position count,
  and an explicit duplicate-reservation/integrity state.

The account fields consumed by policy are balance, equity, peak equity, daily/weekly realized PnL, open risk,
reserved risk as evidence only, consecutive losses, last loss time, cooldown deadline, open-position count,
snapshot identity/version/source, and `as_of`. D2B1 does not evolve any account field.

### D2B1 Pure Output Contract
Add a frozen `PureRiskResult` containing decision (`APPROVED`, `REDUCED`, or `BLOCKED`), requested/target/approved
risk percentages and amounts, position size, stop distance and loss-per-lot evidence, portfolio exposure before/
after, typed bounded reason/warning/block codes with existing Thai display text, market/news provenance, automatic
safety-trigger facts, and a versioned canonical semantic payload/fingerprint. It must contain no random ID, DB row,
reservation ID, session, or persistence-only field. `RiskDecision` remains a live-wrapper output in D2B2.

### D2B1 Requested-Risk Semantic Clarification — RESOLVED
The pure contract has four distinct layers:
1. `caller_requested_risk_pct: Decimal | None` is the exact caller-provided audit value, including explicit zero.
2. `normalized_requested_risk_pct` preserves current live compatibility: `None` and `Decimal("0")` normalize to
   `policy.max_risk_per_trade_pct`; any other non-zero Decimal remains unchanged. D2B1 must not newly reject zero.
3. `target_risk_pct` is the effective target after deterministic pre-cap modifiers such as pre-news reduction,
   but before per-trade and portfolio capacity approval.
4. `approved_risk_pct` is the final capacity-approved value; every BLOCKED result has `Decimal("0")` approved.

`PureRiskResult` must preserve all four truthful layers even when BLOCKED. It must expose
`normalized_requested_risk_amount`, `target_risk_amount`, and `approved_risk_amount`, calculated from account equity
with existing Decimal behavior. If a generic `requested_risk_amount` is retained, it means the normalized-request
amount, never the legacy BLOCKED projection.

The original live `_blocked_decision()` projection of `RiskDecision.requested_risk_pct` and
`requested_risk_amount` to the policy maximum is a legacy live-wrapper/public-persistence projection, not pure
semantic truth. D2B1 did not change that live behavior or implement an adapter. The D2B2 compatibility adapter maps
APPROVED/REDUCED requested risk from the normalized value and preserves the policy-maximum projection for BLOCKED
decisions unless separate governance authorizes a public change.

Pure/live parity therefore compares decision, approved risk/amount, sizing, exposure, ordered reasons/warnings/
blocks, provenance, and trigger facts. It intentionally does not compare
`PureRiskResult.caller_requested_risk_pct` with BLOCKED `RiskDecision.requested_risk_pct`.

The additive pure audit fingerprint must include the exact caller value, normalized value, and target value.
`None` and explicit `Decimal("0")` normalize to the same policy target but remain distinct audit inputs and must
produce different pure fingerprints. Existing live evaluation-intent and dependency fingerprint functions remain
unchanged in D2B1.

Negative requested risk is not redesigned by this clarification. D2B1 must characterize `Decimal("-0.1")` against
the live oracle before finalization and preserve the observable result/reason semantics. If behavior is internally
inconsistent, uncontrolled, or cannot be represented safely, stop with **D2B1 NEGATIVE-RISK PARITY AMBIGUITY**.
Mandatory requested-risk tests cover `None`, zero, positive below/equal/above the per-trade maximum, normal and
pre-news paths, and early/capacity/sizing BLOCKED paths, asserting caller, normalized, target, approved, and decision
separately. BLOCKED cases include Kill Switch, news blackout, quote unavailable, account stale, daily loss,
portfolio full, and sizing failure.

### Time and Safety Authority
- Every pure temporal comparison uses explicit `as_of`: account age is `as_of - account.as_of`, quote age is
  `as_of - quote.timestamp`, and spec age is `as_of - spec.observed_at`.
- The pure module must contain no `datetime.now()`, `utcnow()`, wall-clock fallback, random UUID, mutable cache,
  thread-dependent state, or hidden singleton lookup.
- `ACTIVE` Kill Switch blocks; `UNKNOWN` fails closed and blocks; only `INACTIVE` allows later rules.
- Pure code derives daily-loss, drawdown, and instantaneous quote/data-safety trigger facts but never activates the
  Kill Switch. The D2B2 live wrapper consumes the same pure facts, updates persistent data health, performs any
  required activation, re-reads the resulting Kill Switch state, and then invokes final policy evaluation.
- Persistent consecutive data-health tracking remains live orchestration keyed by provider/source. An unavailable
  derived health state is explicit and fail-closed; D2B1 must not recreate DB tracking.

### Portfolio and Sizing Boundary
The live wrapper builds the exposure snapshot from locked reservation rows. Duplicate active reservations are
represented as an explicit integrity anomaly and deterministically block. DB reservation rows remain the sole live
source of reserved risk; `AccountSnapshot.reserved_risk_pct` is not additively double-counted. Existing behavior
that blocks any positive unattributed `account.open_risk_pct` is preserved. Pure capacity order is cooldown,
integrity anomaly, unattributed open risk, concurrent count, account capacity, symbol capacity, directional
capacity, per-trade cap/reduction, then approved amount. `calculate_position_size()` is already deterministic
Decimal math and must be reused unchanged, including worst-case entry, downward step quantization, volume bounds,
geometry validation, and `actual_risk <= approved_risk` fail-closed behavior.

### Policy Ordering and Identity
Preserve existing observable rule/reason order: automatic trigger facts and post-trigger Kill Switch dominance;
news; candidate terminal state; account freshness/equity/daily loss/weekly loss/drawdown/cooldown; symbol-spec
validity/freshness; unattributed open risk; quote availability/freshness/spread; TradePlan status/expiry; portfolio
capacity; sizing; final resolution. Characterization fixtures must capture the exact current ordering before the
live wrapper is migrated.

`compute_evaluation_intent_identity()` is pure and may be reused subject to unchanged fixtures.
`compute_risk_dependency_fingerprint()` is pure in execution but requires extraction to a versioned semantic
payload because it currently includes live Kill Switch identity fields and only aggregate portfolio exposure.
The new pure fingerprint must cover every explicit policy dependency, including detailed capacity/integrity and
data-health state, while excluding DB row order and live-only IDs. Decision ID derivation, cache lookup, reservation
identity, and persisted `RiskDecision` identity remain live-wrapper responsibilities.

### Authorized D2B1 Implementation Scope
- Add the infrastructure-free pure contracts, stable reason-code layer, policy evaluator, safety-trigger facts,
  pure capacity calculation, and semantic fingerprint under `app.services.risk`.
- Reuse `calculate_position_size()` unchanged. Extract/rehome `is_cooldown_active()` only if the result remains
  byte/semantics equivalent and the existing import remains compatible.
- Capture current live behavior as immutable characterization fixtures before asserting pure parity.
- Add pure unit, portfolio-capacity, Kill Switch, news, freshness, lifecycle, sizing, fingerprint-determinism,
  repeat-determinism, and architecture-isolation tests.
- Add parity tests for the required APPROVED/REDUCED/BLOCKED matrix. Existing expected live behavior is the oracle;
  expected outputs must not be edited merely to accommodate the refactor.
- The pure module must have zero imports/calls to SQLAlchemy, `AsyncSession`, models, `risk.repository`,
  `risk.kill_switch`, reservation records, provider APIs, MetaTrader5, network, filesystem writes, or wall clocks.
- Do not make `RiskEngine.evaluate_candidate()` delegate to the new core in D2B1. That migration is D2B2.

### D2B1 Acceptance and Gate
The matrix must include normal approval; per-trade, portfolio and news reduction; news blackout/unavailable and
post-news spread blocks; quote unavailable/stale/excessive spread; account stale/equity zero/daily loss/weekly loss/
drawdown/cooldown; stale spec; terminal candidate states; expired plan; account/symbol/directional/concurrent caps;
unattributed open risk; duplicate reservation anomaly; below-minimum size; and invalid sizing geometry. Explicit
Kill Switch cases are ACTIVE, UNKNOWN, and INACTIVE. Same input must yield the same result and fingerprint.

D2B1 completion required all existing Risk tests plus the new pure/parity/isolation suites to pass and an
independent GPT-5.6 Sol / High verification gate. Those requirements are satisfied. D2B1 completion does not
authorize D2B2 or D2C.

### D2B1 Final Independent Re-Verification and Closure Status
- D2B1-IV-P2-001: **CLOSED**. Symbol specification authority is linked
  to the candidate symbol by normal contract validation.
- D2B1-IV-P2-002: **CLOSED**. `evaluate_pure_risk()` reconstructs and
  validates a private canonical snapshot before evaluation and fingerprints that exact snapshot.
- D2B1-IV-P2-003: **CLOSED**. Pure arithmetic and unchanged sizing run
  under a fresh server-owned Decimal context; Decimal fingerprint rendering is ambient-context independent.
- D2B1-IV-P3-001: **CLOSED**. BLOCKED warning projection matches the
  live oracle while caller, normalized, and target risk truth remain intact.
- Final independent evidence: pure 76 passed; parity 38 passed; architecture 2 passed; combined D2B1 116 passed;
  unchanged live Risk regressions 7/41/9/1/1/4 passed; 53 temporary independent probes passed; Ruff and diff
  check PASS; no reproducible P0/P1/P2/P3 finding remained within D2B1 scope.

### D2B2 Final Independent Re-Verification and Closure Status
- `RiskEngine.evaluate_candidate()` now acquires the account advisory lock, derives safety-trigger facts through
  the pure core, persists automatic Kill Switch/data-health state, re-reads authoritative state, row-locks active
  reservations, performs final pure evaluation, then owns cache/reconciliation/reservation/public mapping effects.
- The live adapter translates quote/news/Kill Switch inputs and constructs locked portfolio evidence. It excludes
  exactly one same-candidate retry reservation; duplicate active rows remain visible and fail closed.
- BLOCKED public `RiskDecision` values preserve the legacy policy-maximum requested-risk projection while the pure
  result retains exact caller, normalized, target, and approved semantic layers.
- Local evidence: pure 76 passed; parity/delegation 41 passed; architecture 2 passed; combined targeted Risk suite
  182 passed; five PostgreSQL concurrency/idempotency/lifecycle gates passed with a workspace-local base temp;
  Ruff and `git diff --check` passed.
- The initial independent gate found one P2 exact-parity defect: BLOCKED approved-risk and position zero values
  lost their legacy Decimal scales in serialized public output. The live compatibility adapter now restores
  `0.0000`, `0.00`, and `0.0000`, with an exact JSON regression test.
- Final independent evidence: HEAD-oracle complete public decision parity 5/5 passed; targeted Risk matrix 182/182
  passed; real PostgreSQL Risk concurrency/idempotency/lifecycle suite 8/8 passed with no skips; Ruff and
  `git diff --check` passed; no P0/P1/P2/P3 finding remains.
- D2B2 is **CLOSED**. D2C remains not authorized.

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
- Governance result: **PLAN REQUIRES SPLIT**; D2A passed independent GPT-5.6 Sol / High verification and is **CLOSED**.
- Governance result: **PLAN REQUIRES SPLIT** for D2B.
- Next permitted activity is **D2C governance review/authorization only**. D2C implementation and D3–D7 are
  **NOT AUTHORIZED**.

## D2A Final Closure Status
- NEW-D2A-RV-001: **CLOSED**.
- V-D2A-14-RV-01: **CLOSED**.
- NEW-D2A-RV-002: **CLOSED**.
- V-D2A-14 roll-up: **CLOSED**.
- NEW-D2A-RV-003: **CLOSED**.
- V-D2A-06: **CLOSED**.
- V-D2A-10: **CLOSED**.
- V-D2A-12/13: **CLOSED**.
- V-D2A-29: **CLOSED**.
- V-D2A-36: **CLOSED**.
- Final independent gate: **D2A Usable-Period Independent Re-Verification — PASS**.
- Final evidence: D2A focused 57 passed; D2A architecture 2 passed; D2A combined 59 passed; D1 80 passed;
  Market Data 33 passed; Analysis 54 passed; News 67 passed; Strategy 68 passed; independent temporary
  usable-period/adversarial probes PASS; Ruff PASS; `git diff --check` PASS.
- No reproducible P0/P1/P2/P3 finding remains within D2A scope.
- D2B1 final independent re-verification: **PASS; CLOSED**.
- D2B2 final independent re-verification: **PASS; CLOSED**.
- D2C governance review/authorization alone is permitted next. D2C implementation and D3–D7 remain not authorized;
  do not begin the next sub-batch automatically.
