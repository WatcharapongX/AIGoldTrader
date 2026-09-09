# Phase 4 strategy and trade-plan engine

> Current targeted integration (2026-09-09): Forex Factory weekly JSON is the configured
> primary schedule/Forecast/Previous source for STRAT05–06. STRAT01–04 have market-only
> safety, candidate identities and cache dependencies. See [current acceptance report](forex-factory-news-strategies.md).
> Provider-selection and shared news-blocking statements below describe the earlier baseline.
> Final semantic versions: strategy-1.2.1 / news-1.2.0. Phase 5 remains NOT STARTED.

Status: IMPLEMENTATION COMPLETE — PENDING COMBINED SOL HIGH INDEPENDENT REVIEW PHASE 3.5+4. Authorization: latest Phase 4 request permits work after the safe-partial Phase 3.5 gate; historical review gates remain recorded.
Runtime prerequisite verified against PostgreSQL / IUX Demo: news API equals pure historical computation; future cutoffs rejected; operational clocks excluded. Economic source remains FIXTURE and must block readiness in actual market mode.

## Bounded implementation plan
- TASK-039: immutable, versioned shared market context; key levels, DST sessions, indicators and deterministic patterns; registry.
- TASK-040: SMC liquidity reversal with explicit sweep/reclaim/structure/zone sequence.
- TASK-041: established trend pullback with structural confirmation.
- TASK-042: close-confirmed breakout/retest with displacement.
- TASK-043: confirmed range mean reversion, excluding strong trends.
- TASK-044: post-news momentum/reversal; RUN_TREND is a context/profile mapping only. No trailing or management.
- TASK-045: single/multiple strategy and trader profiles; adaptive mode reserved. Same context revision for every profile.
- TASK-046: candidates, structural plan geometry, immutable evaluations and lifecycle; migration 0006, authenticated API, generated contracts, Thai UI and chart overlays.
- TASK-047: causal/golden/rolling validation, PostgreSQL migration/idempotency, regression, actual IUX/browser checks, final gate.

## Boundaries and conventions
Analysis and suggestions only. PAPER and LIVE_AUTO_TRADING=false. No orders, lots, account-risk allocation, execution, position management, AI selection or Phase 5 work.
Snapshot absence means NOT_INCLUDED_UNKNOWN, never invalidation. Frozen evidence remains attached to historical candidates. Revisions create new identities and explicit supersession; expiry is tied to market cutoffs.
Deterministic as_of and content fingerprints are distinct from generated_at/served_at. Closed canonical candles only; no future pivots, news vintages or completed session extrema.
Strategies receive isolated read-only views of one serialized context; provider/SQL access belongs exclusively to the context service.
MACD uses SMA-seeded EMA(12,26), signal EMA(9); Stochastic %K(14), %D(3), flat range yields unavailable. Configuration is versioned.
Sessions use IANA timezones and UTC instants. Incomplete or running sessions are provisional. Structural targets are never manufactured to meet RR.
Real-mode fixture or unavailable news blocks readiness. Fixture replay can exercise goldens but must be labelled as test data.
W1 may use partial history if the profile minimum is met; no synthetic history extension.

## Final gate
Stop before Phase 5. Combined Sol High independent review of Phase 3.5 + 4 is required. No Git mutation/commit/push in this phase.


## Implemented architecture and provenance
Earlier baseline engine version: strategy-1.0.1. Version 1.0.1 distinguishes unavailable spread/volatility from elevated values in Thai explanations. Earlier DEV acceptance revisions remain immutable with their original version; they are not rewritten.
The service reads nine canonical timeframes in one PostgreSQL REPEATABLE READ transaction, ending at a closed M1 minute cutoff. An application lock serializes this native single-instance evaluator. Market/news collection remains owned by the existing services.
The context freezes canonical candles and Phase 3 snapshots as canonical JSON strings, plus typed immutable tuples for derived objects. Each access to upstream objects deserializes a separate copy: strategy code cannot mutate another profile's view. The stored strategy_config_json and analysis_config_json allow replay with the exact configuration.
Context identities include bounded input windows, upstream snapshots, news vintages/fingerprint, source, tick size and configuration. Evaluation/candidate identities also include profiles and playbook versions. Generated/served clocks are normalized to UTC at the API boundary and do not enter identity.
The service recomputes on closed-minute REST refresh and explicit refresh; identical content is idempotent in storage. It is analysis-on-request, not an unattended scheduler. Querying historical cutoffs cannot modify future snapshots. No new WebSocket authentication scheme is introduced.

## Strategy library
STRAT01 requires HTF alignment, observed liquidity sweep/reclaim, CHOCH/MSS, a subsequent live FVG/OB and retest/rejection.
STRAT02 requires established HTF direction, BOS, a trend/pullback regime, live zone retest and LTF structure.
STRAT03 requires a confirmed pivot pattern, close breakout, displacement-backed structure and a subsequent neckline retest. Wick-only breakout is insufficient.
STRAT04 requires RANGING, confirmed dealing-range boundaries, ADX below 25, rejection and CHOCH/MSS. Strong opposite HTF context blocks it.
STRAT05 requires released actual data, nonconflicting directional macro context, directional observed reaction, normal measured spread, known volatility and structure after release, plus structural retest geometry.
STRAT06 requires high-impact released actual, observed sweep/reclaim and CHOCH/MSS, reversal reaction and normal measured spread.
News fixture/unavailable, unavailable spread/volatility, incompatible HTF, restricted news or stale/insufficient context cannot be outscored. Pattern/indicator/news alone cannot generate entry.

## Profiles and timeframe rules
Seven immutable configuration profiles: Strategy Lab (all six playbooks), SMC Specialist, Trend Runner, Liquidity Specialist, Breakout Trader, Range Trader and News Trader. Thirteen isolated evaluations use exactly one context ID.
SCALP: H1/M15/M5/M1. DAY_TRADE: H4/H1/M15/M5. SWING: W1/D1/H4/H1. RUN_TREND: D1/H4/H1/M15. Default minimum is 60 closed bars in each mapped frame. W1 230 closed bars therefore meets this minimum while remaining partial against requested 300.
SINGLE_STRATEGY, MULTI_STRATEGY and MULTI_TRADER are display/comparison modes over these frozen results; no automatic final trade choice. Adaptive is RESERVED_DISABLED. Profile authoring API, per-account editing and execution selection are deferred interfaces, not active features.

## Score and structural geometry
Evidence weights: structure 25, liquidity 20, HTF 15, key level 10, pattern 10, indicator 5, news 10 and valid geometry 5. Each conflict subtracts 15, then the result is clamped to 0–100. A playbook need not use every component. Scores are evidence coverage, never win probabilities. Mandatory conditions remain binding at every score.
Entry comes from a live FVG/OB, confirmed range edge or confirmed pattern neckline. Stop extends beyond the structural anchor using configured ATR buffer, rounded outward to verified tick size.
Targets are known confirmed structural levels in order of distance. The nearest obstruction failing minimum RR rejects the plan; it is never skipped to manufacture RR. Two distinct targets are mandatory; the third is an optional runner reference. RR uses the worst price across the complete entry zone. No lots, account risk, trailing or profit guarantee.

## Lifecycle and bounded retention
Candidate direction and status are separate. NO_TRADE/BLOCKED_CONTEXT are normal outcomes and carry missing conditions/conflicts. Entry-bearing candidates may wait for confirmation. A suggested plan expires after configured trigger bars from its structure confirmation; refreshing does not indefinitely extend the same evidence.
Explicit upstream INVALIDATED/ended_at evidence or a subsequent known close through structural SL can invalidate. Time expiry and newer profile/strategy evaluation produce explicit EXPIRED/SUPERSEDED transitions. Missing IDs alone never invalidate. Superseded originals remain immutable.
Historical /trade-candidates returns original revisions; /trade-candidates/{id}/transitions carries their later lifecycle. Current suggestions come only from /trade-plan/current (same current envelope as /strategy/context). Consumers must honor as_of/expires_at/stale. It is not a position-monitoring API.
Storage: trader_profiles, strategy_evaluations (full reproducible context/evaluation), trade_candidates and candidate_transitions. Unique IDs and profile/config + evaluation/profile/strategy constraints enforce idempotence. Conflicting payloads fail; no silent overwrite. Migration 0006 is additive and refuses destructive downgrade with populated history. Retention/archival of this full JSON evidence must be designed before long unattended deployment; no automatic purge is added.

## Context engines and bounded conventions
Canonical Phase 3 swings/liquidity/zones/dealing range are reused; PDH/PDL/PWH/PWL and opens reference observable canonical periods. IANA Asia/Tokyo, Europe/London and America/New_York windows handle DST. Only exact closed M5 session coverage can be CONFIRMED; partial/running ranges stay PROVISIONAL. Missing complete periods/opens remain absent.
Pattern templates cover double/triple top/bottom, H&S/inverse, ascending/descending/symmetrical triangle, bullish/bearish flag and rising/falling wedge. Internal alternating confirmed pivots, ATR tolerance, minimum separation, slope geometry, observed pole for flags, neckline close confirmation, explicit failure/expiry and a bounded 100-bar default are used. These are conservative first-version templates, not exhaustive visual pattern recognition or a durable cross-window pattern ledger.
MACD SMA-seeded EMA 12/26, signal 9; stochastic K14/D3. RSI/ADX/ATR and existing indicators are reused from Phase 3. No synthetic warmup or flat-range stochastic value.

## API, UI and future boundaries
Authenticated GET routes: /strategy/context, /trade-plan/current, /strategies, /trader-profiles, /strategy/evaluations, /trade-candidates and candidate transitions, under /api. No public mutation/execution route. OpenAPI/Pydantic exports generated TypeScript and runtime JSON schema.
Trading provides Thai reasons, no-trade state, profile cards, mode comparisons, evidence, HTF/LTF history, levels, patterns, indicators and optional independent chart overlays for period/session levels, pivots/neckline confirmation and entry/SL/TP. Actual fixture news is explicitly blocked; ready plans exist only in labelled offline acceptance fixtures until trusted news and market conditions satisfy every rule.
Future risk/AI/execution interfaces may consume immutable context/candidate/plan IDs and expiry. None is activated in Phase 4. Phase 5 remains DO NOT START pending COMBINED SOL HIGH INDEPENDENT REVIEW PHASE 3.5+4.


## SOL-P1-001 corrective identity (evaluation-2.0.0)

The latest user authorization permits one pre-Phase-5 milestone commit/push after verification.
Earlier no-Git and phase-stop statements above describe their historical gates.

Evaluation identity now follows each profile/strategy dependency. A transient REQUEST envelope
contains the full presentation context and candidate-to-component IDs. The repository persists
one immutable STRATEGY projection per enabled profile/strategy, never that presentation envelope.
General STRAT01–04 projections use market_context_id and contain null news fields. STRAT05–06
retain the full news context and provenance. A mixed request may change its aggregate ID on a
news revision while its general component IDs, payloads and candidate foreign keys stay unchanged.
A general-only REQUEST ID stays stable even when its irrelevant news decoration changes.

The complete projected payload and stored hash are checked on duplicate writes, along with
candidate payload and ownership. Legacy aggregates are read with explicit LEGACY defaults.
On an exact candidate match, persistence may adopt its legacy evaluation FK into the canonical
projection; candidate IDs/payloads, legacy snapshots/hashes and prior transitions remain intact.
This representation upgrade is logged and does not emit a trading lifecycle transition.
Unverifiable legacy ownership and conflicts with another canonical owner fail transactionally.

No new migration or algorithm change: strategy-1.2.1, news-1.2.0 and migration 0006 remain.
Identity versioning is separate from the trading algorithm. See [corrective verification](sol-p1-001-corrective.md).
