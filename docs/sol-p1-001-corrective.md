# SOL-P1-001 — Corrective identity and persistence verification

Date: 2026-09-10 (Asia/Bangkok). Finding: **FIXED — PENDING SOL RE-REVIEW**.
This is implementation verification, not independent SOL approval.

## STATUS

Implementation verification PASS. This report is included in the authorized milestone;
the final delivery records the resulting commit SHA, push result and clean-worktree check.
Phase 5 remains prohibited.

## ROOT CAUSE REPRODUCTION

| Original check | Before | After |
|---|---|---|
| CANDIDATES_EQUAL | true | true |
| CANDIDATE_IDS_EQUAL | true | true |
| CACHE_SIZE_STABLE | true | true |
| EVALUATION_IDS_EQUAL | **false** | **true** |
| MARKET_CONTEXT_IDS_EQUAL | true | true |
| FULL_CONTEXT_IDS_EQUAL | false | false |
| Complete persisted projections/hashes equal | not guaranteed | true |

Root Cause Confirmed: YES. The aggregate evaluation hash used the full context ID,
although STRAT01–04 candidate/cache identities already used market_context_id.
Changing the hash alone would retain a different news-bearing payload under the same
immutable primary key. The correction changes both semantic identity and stored representation.

## IMPLEMENTATION

Identity Design: evaluation-2.0.0, separately versioned from unchanged strategy-1.2.1.
Each profile/strategy component hashes its profile, definition and existing dependency_id.
A REQUEST ID composes these component IDs. Current API responses retain the full presentation
context and candidate-to-component mapping; REQUEST envelopes are never persisted.

Dependency Projection: STRAT01–04 use the market projection, with news_json/news_fingerprint
null and context.id equal to market_context_id. STRAT05–06 retain full canonical news inputs.
An empty request has an explicit EMPTY projection. News transport clocks are stripped before
building context identities, including direct NewsResponse callers.

Persistence Representation: one STRATEGY row for each enabled profile/strategy component,
containing only its profile, definition and candidate. Irrelevant presentation news cannot
alter its immutable JSON. A general-only REQUEST ID can stay stable while its transient
presentation news changes; consumers needing immutable identity use component_ids/history.

Immutable Payload Safety: compare the entire stored payload and its digest on duplicate writes.
Check candidate payload and canonical ownership too. Reject mismatches transactionally.
Candidate Relationship: evaluation_id points to its canonical component row. Lifecycle predecessor
selection is isolated by profile/strategy/source/symbol and cutoff.

Legacy Compatibility: old aggregate JSON parses with LEGACY / legacy-aggregate-v1 defaults.
If an identical candidate already belongs to a verifiable legacy snapshot, explicitly adopt
only its FK into the new canonical component, with an audit log of public IDs. Preserve its
ID/payload, the old aggregate JSON/hash and all previous transitions. Do not generate a
lifecycle transition for this representation change. Unknown formats and canonical conflicts
fail. PostgreSQL tests verify legacy adoption, rollback, reconnect and no orphan candidates.

Migration Required: **NO**. Existing JSONB tables and FK are sufficient. Alembic head remains
0006_strategy; DEV drift check and isolated TEST migration preservation pass. No SQL migration
or bulk rewrite was executed by this corrective batch.

Files Changed (corrective scope, relative to the captured dirty baseline):
- Backend: strategy/context.py, domain.py, engine.py, repository.py; new identity.py.
- Tests: test_strategy.py, integration/test_strategy_postgres.py; new test_evaluation_identity.py
  and integration/test_evaluation_identity_postgres.py.
- Frontend: strategy/contracts.ts, StrategyWorkspace.tsx, generated strategy schema/types,
  strategy tests and fixtures; new strategy-projection.json fixture.
- Documentation: this report, strategy engine guide, implementation plan, root/docs indexes.
  Three Markdown hard-break whitespace warnings in the existing FF report were normalized for the staged diff gate; its findings are unchanged.

The one publication milestone also includes the already completed pre-Phase-5 baseline
(Phase 1.1, market data/structure, economic context, Phase 4 strategies and Dashboard).
Starting HEAD contains only Phase 1, so publishing the correction alone would omit its
required code, contracts, migration history and tests. Baseline code outside the corrective
file list is unchanged from the start of this task. Historical gate documents retain their
original no-Git and phase-stop statements; the latest user authorization supersedes them
only for this milestone.

## STRAT01–04 IDENTITY

| Strategy | News-only Evaluation ID | Candidate ID | Cache | Full output / plan / evidence / stored payload |
|---|---|---|---|---|
| STRAT01 | stable | stable | stable | stable |
| STRAT02 | stable | stable | stable | stable |
| STRAT03 | stable | stable | stable | stable |
| STRAT04 | stable | stable | stable | stable |

Overall: PASS, 44 combinations (4 strategies x 11 scenarios).
Scenarios: healthy, unavailable, unknown, upcoming NFP, upcoming CPI, forecast, Actual,
macro bias, news regime, provider health and provider conflict.
All fixture general candidates remain READY with identical complete output and projections.

## STRAT05–06

STRAT05: news-sensitive evaluation/component IDs PASS; exact news provenance PASS;
existing closed-market confirmation and release requirements preserved.
STRAT06: news-sensitive evaluation/component IDs PASS; exact news provenance PASS;
existing sweep/reclaim/structure confirmation requirements preserved.
Forecast/Actual/regime/provider-health/provider-conflict changes exercise both strategies.
Live weekly FF data has no numeric Actual: both remain non-READY without a fabricated plan.

## MULTI-STRATEGY

STRAT01 + STRAT05: after a news change, STRAT01 component ID/payload remains identical;
STRAT05 component changes and the aggregate REQUEST may change. PASS.
Same-profile multi-strategy and separate-trader modes both pass in pure and PostgreSQL tests.
PostgreSQL also exercises all six strategies across all 11 news revisions.

## PERSISTENCE

Idempotency: PASS across sessions/reconnects; original generated_at retained.
Duplicate Evaluations: no additional general rows on news-only changes; news revisions create
their own rows. Repeating the same dependencies creates no additional rows.
Immutable Collision: conflicting payloads rejected; no hash-only overwrite.
Candidate FK: canonical one-candidate owner verified; no orphan rows.
PostgreSQL: 22 integration tests PASS, including 3 new projection/legacy tests.
Live DEV audit: all 195 original evaluations, 2,526 candidates, 2,513 transitions and
28 profile rows preserved byte-for-byte by row checksum. 91 new canonical rows and candidate
owners verified at the acceptance snapshot. No old rows deleted. Auth smoke updates the
existing user's last_login_at and appends its ordinary session/audit records.
Result: PASS. Existing GET-side persistence remains SOL-P2-001, explicitly deferred.

## NO-LOOKAHEAD

Phase 3: causal pivots/events/zones and prefix regression PASS.
News: point-in-time vintages/release availability and no future data regression PASS.
Strategy: closed candles, confirmation/expiry, no-lookahead regression PASS.
Batch/Incremental: API = batch = incremental on real IUX data, all 9 timeframes;
45 prefix checks PASS. Existing bounded-window semantics unchanged.
Future strategy API cutoff rejected with 422; unauthenticated reads rejected with 401.
Result: PASS within the tested scope.

## TEST RESULTS

| Gate | Result |
|---|---|
| Full backend | 504 PASS; 10 external tests deselected here, run separately |
| PostgreSQL | 22 PASS, real separate TEST database / isolated schemas |
| Phase 3, News, Phase 4 regressions | PASS within full backend |
| New identity suite | 64 PASS (61 unit/API/SQLite + 3 PostgreSQL) |
| General invariance | 44 PASS |
| STRAT05/06 news sensitivity | 10 PASS plus existing news playbook regressions |
| MT5 external | 9 PASS; strict W1 300-bar gate FAIL: only 231/300 real bars |
| Real Phase 3 | 9 timeframes / 45 prefixes PASS; W1 230 closed bars honestly PARTIAL |
| Frontend | 136 PASS |
| Ruff / mypy | PASS / PASS, 68 source files |
| ESLint / TypeScript | PASS / PASS |
| API Contract / DEV Alembic drift | PASS / PASS, no new upgrade operations |
| Production build | PASS |
| Browser Dashboard / Strategy | PASS at 1440 / 820 / 390; no console/asset errors |
| Browser Analysis | PASS, timeframes/toggles/reload/reconnect/closed-bar refresh/mobile |
| Real news cross-check | 7 events agree raw FF / Calendar / Dashboard / News / Strategy |

The first native idempotency sample ran while market history was still filling: stored
contexts show changed frames, key levels, market_context_id and news.market_as_of at the same
cutoff. After inputs stabilized, duplicate native requests had identical IDs/generated_at
and matched pure evaluation exactly. No identity assertion or application safeguard was relaxed.
The copied FF harness initially lacked its raw input artifact; fetching the official weekly
feed resolved that harness setup issue before the successful cross-check.

Known external limits remain **SAFE PARTIAL**: W1 history is incomplete; FF weekly feed provides
Forecast/Previous but no numeric Actual in this sample (81 raw events, 7 mapped USD events).
The strict W1 test is reported as FAIL, not skipped or relabeled as PASS. No synthetic bars,
fake news Actual or fabricated trade plan was introduced.

## DEFERRED SOL FINDINGS

SOL-P2-001: DEFERRED — GET-side persistence.
SOL-P2-002: DEFERRED — Dashboard timestamp presentation.
SOL-P2-003: DEFERRED — Xoomar GDP mapping.
SOL-P2-004: DEFERRED — token storage architecture.
SOL-P2-005: DEFERRED — Forex Factory cross-week identities.
SOL-P3-001: DEFERRED.
No additional corrective scope was started.

## TRADING SAFETY

TRADING_MODE: PAPER. LIVE_AUTO_TRADING: false.
MT5 order_send: no application calls. Broker Execution: not implemented.
Paper Orders: not implemented. Risk Engine: not implemented.
Position sizing / kill switch / position management: not implemented.
Phase 5: NOT STARTED. Existing navigation placeholders are not implementations.

## GIT RESULT

Branch: main. Starting HEAD: 857e764bea47279af7986a449d80505b74820432.
Starting worktree: 44 modified, 125 untracked, 0 staged files.
Authorized commit message: fix(phase-4): make strategy evaluation identity dependency-aware
Remote: https://github.com/WatcharapongX/AIGoldTrader.git
Exact allow-listed file manifest only; no git add ., force push, reset, clean, merge or rebase.
Known local credential and credential-pattern scans pass; environment secrets, runtime captures,
private credentials, logs, caches and generated build artifacts are excluded.
Final HEAD / commit SHA / push result / final file counts are recorded in the final delivery
and local ignored git-result.json, because a commit cannot embed its own final hash.

## SOL RE-REVIEW GATE

READY FOR SOL HIGH RE-REVIEW: YES, following successful publication.
SOL-P1-001: **FIXED — PENDING SOL RE-REVIEW**.
No independent approval is claimed; external data limitations and deferred findings remain.

## PHASE 5

**DO NOT START.** Stop after the authorized milestone commit/push and wait for SOL HIGH RE-REVIEW.
