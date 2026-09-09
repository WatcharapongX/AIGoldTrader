# PRE-REVIEW COMPLETION BATCH / PHASE 3.5R + 4.1

Date: 2026-09-09. Evidence: data/local/pre-review (local, ignored; no credentials in this report).

## OVERALL STATUS

**PARTIAL** — Phase3.5R connects real keyless data but does not meet the original
full-calendar coverage/revision/latency gate. Phase4.1 implemented and browser
acceptance passed; final independent review pending. No Phase5 work.

## PHASE 3.5R — REAL PROVIDER

| Item | Observed result |
|---|---|
| Provider / type | Xoomar, documented public HTTPS JSON, no HTML scraping |
| Source / mode | xoomar_calendar / LIVE (UI: REAL) |
| Credentials | No account/API key required or created |
| Runtime connection | Connected; health DEGRADED because coverage LIMITED |
| Events received | 4 USD events; 1 actual, 3 upcoming |
| Values | NFP actual 162 thousand / previous 21 thousand; forecasts absent |
| Upcoming | CPI September11, FOMC September16 UTC, NFP October2 |
| Provider timestamp | Snapshot updatedAt, separate from event knowledge |
| Receipt / sync | Explicit received_at and last_sync_at, current health endpoint |
| Polling | One backend worker / 300 seconds; no browser-to-provider calls |
| Retry / rate limit | Exponential backoff and bounded Retry-After handling; mock429 tested |
| Revision | Append-only observed vintages; identical snapshots/restarts deduplicate |
| Timezone | UTC canonical; explicit offsets and Asia/Bangkok display; winter/summer tests |
| Migration | None needed; current/head 0006_strategy, no schema drift |
| Result | PARTIAL, never presented as FULL COMPLETE |

Provider docs: [calendar API](https://xoomar.com/markets/api/calendar).
Usage terms: [Xoomar terms](https://xoomar.com/terms).
Implementation and exact limitations: [architecture](10-dashboard-command-center.md).

## REAL NEWS VALIDATION

Example event: Non-Farm Payrolls / August2026, USD, HIGH.
Scheduled: 2026-09-04T12:30:00Z = September4 19:30 Bangkok.
Actual: 162.0000 thousand. Forecast: absent. Previous: 21.0000 thousand.
Provider snapshot: 2026-09-09T13:14:48.279000Z.
Received: 2026-09-09T13:14:44.695267Z.
Canonical first-known available_at: 2026-09-09T13:14:44.695267Z.
Source: xoomar_calendar / LIVE.

Raw API values and schedules matched canonical events. BLS cross-check supports the
published NFP result and CPI schedule:
[BLS employment release](https://www.bls.gov/news.release/archives/empsit_09042026.htm),
[BLS CPI](https://www.bls.gov/cpi/).
CPI September11 12:30UTC appeared as 19:30 Bangkok in the real browser.
Snapshot clock skew of about four seconds was measured; at most ten seconds is
accepted for snapshot metadata only. Future actual and event knowledge checks are strict.

## NEWS SAFETY

- Future actual, timezone-naive data, unknown series, duplicate identities and
  undocumented forecast values are rejected.
- Runtime fixture leakage: none. Unconfigured provider defaults to unavailable.
- Silent fallback: none. Provider outages retain historical data with unhealthy status.
- Stale receipt / 429 / provider500 / redirects / bad data tested with injected responses.
- Real release-time polling across a newly occurring CPI/NFP release: NOT RUN in this
  session. This is not a claim of low-latency or complete news coverage.
- Historical snapshot received today is unavailable to cutoffs before first receipt.
- No inferred cancellation when an event disappears. Provider does not expose complete
  cancellation/delay/revision history; missed intermediate corrections remain unknown.
- Speeches / NFP component feeds / forecasts / broad original catalogue are not supplied
  by this adapter. No missing values or macro components are fabricated.

## NEWS TO PHASE 4

Same NewsMarketContext consumed by existing Phase4 context/evaluate path.
API output equals pure evaluate for the same frozen context; repeated explicit-cutoff
requests preserve evaluation ID and generated time.
Six definitions, seven profiles, 13 candidates. Real LIMITED coverage keeps
calendar_usable_for_trading=false. All observed candidates BLOCKED_CONTEXT; no current plan.
No score override of mandatory news/structure conditions. Core strategy logic unchanged.

## DASHBOARD / PHASE 4.1

Implemented: market Bid/Ask/spread/source/session/regime; H4/H1/M15/M5 structure
and latest events/liquidity; canonical PDH/PDL/PWH/PWL/Asia levels; real news with
missing-value semantics and source/freshness; six strategies; seven profiles;
deterministic current-plan selection or no-trade reasons; module health; safety.

Typed authenticated aggregate endpoint; Pydantic → generated TypeScript/schema →
runtime semantic validation. Bounded shared 30-second cache, isolated module timeouts,
existing internal MarketConnection, cleanup on navigation/reload. No external feed in frontend.

## DASHBOARD TRUTHFULNESS

No fake win rate, profit, equity, performance, risk score or account statistics.
Scores are rule-based candidate scores, not probabilities. Plans are suggestions,
not orders. Missing candidates/quote/news are explicitly unavailable. Stale/error
hides the current plan. Unknown backend WS state is replaced by actual client transport state.

## RESPONSIVE / BROWSER

Dashboard, Trading news and Calendar: PASS at desktop1440, tablet820, mobile390.
Critical console errors: 0. Failed critical assets: 0. Horizontal overflow: 0.
Visible Dashboard bid matched a canonical mt5_demo_iux WebSocket quote.
Navigation/reload observed one active socket, maximum one in measured run.
Calendar detail/revision and missing forecast display: PASS.
Strategy all three modes, 13/6/1 visible candidates, overlays, reload/responsive: PASS.
Phase3 full browser regression: PASS on all9 timeframes; layer toggles, reconnect,
closed-bar refresh, reload and mobile passed. Console errors0 / failed assets0.

## SYSTEM HEALTH

Backend responding; PostgreSQL operational; MT5 connected in DEMO mode.
News connected but DEGRADED/LIMITED; engine deliberately cannot approve news readiness.
Analysis and strategy results available; freshness clocks shown.
WebSocket actual client transport used. Redis remains optional/disabled.
Adaptive RESERVED_DISABLED; broker execution disabled; risk engine not implemented.

## TEST RESULTS

| Category | Result |
|---|---|
| Backend full regression | 371 PASS; 10 live-external tests excluded from this suite |
| PostgreSQL integration | 18 PASS, included in371; isolated disposable test schema |
| Phase3 analysis unit suite | 54 PASS, included in371 |
| Phase3.5 news unit suite | 67 PASS, included in371 |
| Phase3.5R provider unit suite | 19 PASS, included in371 |
| Phase4 strategy unit suite | 66 PASS, included in371 |
| Phase4.1 aggregation unit suite | 6 PASS, included in371 |
| Remaining foundation/market/security | 141 PASS, included in371 |
| Direct real MT5 acceptance | 9 PASS; strict300-bar W1 test excluded and partial separately verified |
| Real nine-TF Phase3 API/batch/stream/prefix | PASS; 45 prefix checks |
| Real Phase4 API/pure/idempotence | PASS; LIVE news context, all13 blocked |
| Real Dashboard/raw provider comparison | PASS; four source events, no fixture |
| Frontend regression | 130 PASS; zero failed/skipped |
| Backend lint / mypy | PASS;66 source files, new modules include body checks |
| Frontend lint / typecheck / build | PASS; production build completed |
| Generated contract drift | PASS |
| Alembic current / heads / check | 0006_strategy; no upgrade operations detected |

Test counts are partitioned; do not add PostgreSQL or unit subsets to371 again.
Existing library deprecation warnings remain (FastAPI/httpx and pytest_asyncio).
An exploratory globally-expanded --check-untyped-defs run reports27 pre-existing
findings in old analysis/market modules; standard project configuration and new
code checks pass. This is not a clean certification of all legacy expanded checks.

## SECURITY / TRADING SAFETY

Server-side fixed public host; no credentials in provider URLs or browser.
Auth required for new endpoints;401 verified. Existing authentication/market transport retained.
Secret audit: NONE found in Git-visible files or runtime logs.
Protected foundation/strategy algorithms/migrations:33 files unchanged against
this batch baseline. Original database rows deleted:0. Users last-login changed
through test authentication; one original session only gained revoked_at.
Active refresh sessions after cleanup:0. Invalid OHLC rows:0.
PAPER; live_auto_trading=false; no MT5 order call, order placement, execution,
position management, PnL, risk engine or LLM introduced.
No broker order execution test was run because execution is forbidden in this scope.

## W1

Requested300 / returned231 / closed230 / PARTIAL.
No fabricated bars. Existing history-aware strategy behavior retained.
Eight other timeframes return300; no claims that W1 is complete.

## GIT STATE

Branch main. HEAD857e764bea47279af7986a449d80505b74820432.
Working tree: 44 modified tracked files / 121 untracked files.
This includes pre-existing work. This batch changed21 existing files and added16.
No unrelated pending changes were discarded.
Staged0. Commit created: NO. Push: NO. No branch/reset/clean/merge/rebase operation.
Existing pending changes from earlier phases were retained.

## KNOWN LIMITATIONS

1. Real calendar coverage and latency are insufficient for FULL Phase3.5R; no consensus.
2. Canonical IDs are local series/reference-period identities, not vendor-issued IDs.
   Ambiguous batches fail closed. No complete historical provider revision stream.
3. Snapshot updatedAt is not an economic release or event revision timestamp.
4. No witnessed new release cycle, long-duration soak or distributed-worker certification.
5. Shared summary cache is single-process; independent modules can have different
   explicit as-of times. Phase4 evaluation itself still uses one immutable context.
6. No live eligible plan existed; READY plan geometry is covered by existing fixture
   and contract tests, not invented in the runtime demonstration.
7. W1 history remains231/300. Existing expanded legacy typing findings/deprecations remain.

## PRE-REVIEW GATE

Phase3.5: READY for review.
Phase3.5R: PARTIAL — working real keyless subset with safety restrictions.
Phase4: READY for review.
Phase4.1: READY for review; final evidence audit PASS.
Overall: PARTIAL, not full real-calendar acceptance.

## SOL HIGH REVIEW

READY FOR COMBINED INDEPENDENT REVIEW of the implemented scope and disclosed
Phase3.5R partial gate. Reviewer must not promote this to complete real-calendar
or live-news trading readiness without a richer verified provider.

## NEXT PHASE

**PHASE5: DO NOT START. MANDATORY STOP.**

## EVIDENCE INDEX

- data/local/pre-review/backend-tests-final.xml —371 backend tests.
- data/local/pre-review/test-counts.json —partition including18 PostgreSQL tests.
- data/local/pre-review/frontend-tests-final.log —130 frontend tests.
- data/local/pre-review/mt5-tests.xml —9 direct real MT5 tests.
- data/local/pre-review/dashboard-api-result.json and raw-provider.json —real provider/API comparison.
- data/local/pre-review/strategy-api-results.json —canonical API/pure/idempotence.
- data/local/pre-review/browser-dashboard/results.json —Dashboard/Trading/Calendar/quote equality.
- data/local/pre-review/browser-strategy/results.json —three modes/responsive.
- data/local/pre-review/browser-analysis/results.json —nine timeframes/overlays/refresh/reconnect.
- data/local/pre-review/final-audit.json —baseline files/database/secrets/Git.
- docs/10-dashboard-command-center.md —provider terms, time/revision semantics and operations.

These are local evidence files, not uploaded or published. Screenshots are in the
corresponding browser evidence directories. Earlier failed attempts remain in
separate evidence directories; final results above supersede startup-race and
fixture-specific browser-selector failures.
