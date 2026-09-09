# FOREX FACTORY NEWS STRATEGY INTEGRATION / STRAT05–06 ONLY

**STATUS: SAFE PARTIAL**

**GATE: READY FOR SOL HIGH COMBINED REVIEW**

**PHASE 5: DO NOT START**

ตรวจรับ 9–10 กันยายน 2026 (Asia/Bangkok). Implementation และ strategy separation ผ่านการทดสอบ
แต่ไม่อ้างว่า live numeric post-release setup ผ่านแล้ว: feed จริงที่ตรวจไม่มี Actual

## FOREX FACTORY INTEGRATION

Official [Forex Factory Calendar](https://www.forexfactory.com/calendar) → Weekly Export → JSON.
Stable allowlisted endpoint: https://nfs.faireconomy.media/ff_calendar_thisweek.json

ใช้ URL คงที่โดยไม่พ่วง version/cache-busting query; ไม่ scrape HTML และไม่ใช้ search results เป็น runtime data.
Raw week: **81 events**, USD **23**; supported USD mapped **7**:
High 6, Medium 1; Forecast **7/7**, Previous **7/7**, Actual **0/7**.
Source forex_factory / LIVE; coverage LIMITED (supported USD weekly schedule).
calendar_usable_for_trading means schedule usable; Actual/group/market checks remain separate.

Recorded health: **HEALTHY**; receipt 2026-09-09T17:04:11.179828Z;
last sync 2026-09-09T17:04:11.443782Z. Per-event provider update time is unavailable.
One extra QA fetch received HTTP 429: no bypass or rapid retry; comparison reused the saved raw response.
Worker uses bounded backoff; health can degrade while last-known events remain visible.

Unknown series, holidays, bond auctions and ADP weekly estimates are outside this supported subset.
Monthly ADP has an exact separate mapping. No weekly/monthly alias.

## REAL EVENT CROSS-CHECK

All 7 events matched title, USD currency, text impact, schedule, Forecast, Previous and Actual across
**raw JSON ↔ Calendar API ↔ Dashboard API ↔ NewsStrategyContext**.
Browser checked all 7 rendered forecasts and Calendar CPI Bangkok time/revision detail.

| Event | Impact | UTC | Bangkok | Forecast | Previous | Actual |
|---|---|---|---|---:|---:|---|
| Core PPI m/m | HIGH | 10 Sep 12:30 | 10 Sep 19:30 | 0.3 | 0.2 | null |
| PPI m/m | HIGH | 10 Sep 12:30 | 10 Sep 19:30 | 0.4 | 0.0 | null |
| Unemployment Claims | MEDIUM | 10 Sep 12:30 | 10 Sep 19:30 | 205 | 206 | null |
| Core CPI m/m | HIGH | 11 Sep 12:30 | 11 Sep 19:30 | 0.2 | 0.2 | null |
| Core CPI y/y | HIGH | 11 Sep 12:30 | 11 Sep 19:30 | 2.4 | 2.5 | null |
| CPI m/m | HIGH | 11 Sep 12:30 | 11 Sep 19:30 | 0.4 | 0.1 | null |
| CPI y/y | HIGH | 11 Sep 12:30 | 11 Sep 19:30 | 3.4 | 3.4 | null |

Percentage series remain percentage points; Claims uses thousands.
Evidence in data/local/ff-news: ff-runtime-results.json, ff-runtime-raw.json,
calendar-api.json, dashboard-api.json, news-api.json, ff-strategy-api.json and browser screenshots.

## STRATEGY SEPARATION / GENERAL STRATEGY INVARIANCE

STRAT01–04 playbooks do not read NewsStrategyContext. They use market-only safety:
observed bid/ask spread versus preceding samples, and latest closed-bar range versus preceding ranges.
Calendar polling runs separately from quote collection, so slow HTTP cannot pause market observations.

General candidate IDs, context dependency, upstream IDs, score, direction, status, missing conditions,
evidence and complete entry/SL/TP plan remain identical when only news changes.
General plans have news_state=NOT_APPLICABLE and news_provenance=null.
A bounded 256-entry per-playbook cache keys them by market_context_id.
News-only updates reuse general candidates and do not create lifecycle supersession.
The combined evaluation envelope may receive a new ID without changing general candidates.

The dedicated invariance matrix starts from READY setups for STRAT01–04 and tests:
healthy, unavailable, unknown, upcoming, released, Forecast conflict, Actual conflict.
Assertions compare entire candidate payloads, not only status.
A slow-provider test verifies quote collection continues and only one poll runs at a time.

## STRAT05 / STRAT06

Both explicitly declare NEWS and consume NewsStrategyContext; no provider HTTP occurs in a strategy.
NewsCandidateProvenance stores event identities/vintages, schedule, per-field source, revision,
news fingerprint/version/as_of and Phase 3 input IDs.

- STRAT05: complete numeric Actual/Forecast group, nonconflicting directional macro/reaction,
  measured spread/volatility, post-release structure and structural retest/SL/TP geometry.
- STRAT06: high-impact released group, sweep/reclaim, CHOCH/MSS, observed reversal and market safety.
  Headline or numeric result alone cannot create a plan.
- Missing numeric Actual: WAITING_FOR_ACTUAL in context; candidate remains blocked/waiting with no plan.
- Non-numeric speech: missing Forecast is legitimate; no invented numeric surprise or sentiment.
  Confirmed speech uses observed reaction/structure. Current FF feed has no speech release marker,
  so it may remain WAITING_FOR_RELEASE.
- Healthy/no active event: general strategies evaluate normally; news strategies have no qualifying setup.
- Upcoming event: general output unchanged; news waits for post-release conditions.
- Actual plus Forecast: surprise is computed, then market/structure checks are still required.
- Calendar unavailable or missing Actual: only news strategy readiness is restricted.

News sensitivity tests remove calendar/Actual/group quality, introduce conflict, mute reaction or widen spread;
qualified STRAT05/06 readiness disappears.

## NEWS DATA / GROUPS / REVISIONS

NFP requires headline, unemployment and wages alignment/completeness. FF NFP additionally needs observed revision
information; missing component/revision is PARTIAL, never headline-only readiness.
CPI keeps headline/core MoM/YoY separate; all four required for a complete FF CPI group.
Explicit default 0.25 weights avoid counting one CPI release as four full weighted releases.
Inflation/FOMC macro direction remains contextual unless configured.

High is admitted by default; FF Medium defaults only to JOBLESS_CLAIMS.
Holiday/Non-Economic/Unknown normalize explicitly and do not acquire a fabricated high-impact gate.
Xoomar remains selectable; no automatic cross-provider Actual merge or unverified reconciliation.

Existing JSONB schema reused; no migration. Ingest is append-only, deduplicates unchanged polls across restart,
retains first knowledge and allocates observed revisions for changed values/schedule.
Original Previous is retained for revision delta. Omission is not cancellation; missed revisions are not reconstructed.
Immutable candidate payload collisions fail explicitly.

## NO-LOOKAHEAD / REPLAY

T−30, T−5, T−1, T0, T+1m, T+5m: future Actual/revisions excluded by available_at.
Whole-history and accumulated-known-vintage contexts agree at each cutoff.
Existing Phase 3/4 tests cover future candles, pivot confirmation, BOS/CHOCH/MSS, reaction cutoffs and streaming equality.
Real MT5 API/batch/stream checks pass for all 9 timeframes and 45 causal prefixes.
Offset-aware UTC storage and summer/winter DST normalization tests pass; Dashboard renders Asia/Bangkok.

## DASHBOARD

Dashboard, strategy modes, Calendar filters/revision detail, reload, overlays and WebSocket cleanup pass.
Desktop 1440, tablet 820, mobile 390: no horizontal overflow, console errors or failed assets.
General strategy caution is separate; news unavailability does not globally hide a general plan.
Actual appears missing, never zero or Forecast.
Authenticated strategy API equals pure engine; duplicate requests retain evaluation/generated clock
for 7 profiles, 6 strategies and 13 candidates.

## TEST RESULTS

| Check | Result |
|---|---|
| Full backend | **440 PASS**, 10 external tests deselected here and executed separately |
| PostgreSQL integration/database | **19 PASS**, isolated disposable TEST schemas |
| Dedicated FF/invariance/sensitivity | **67 PASS**, including PostgreSQL FF restart/revision |
| Xoomar / Phase 3 / 3.5 / 4 | PASS within full backend |
| Real Phase 3 API/batch/stream | PASS: 9 TF, 45 prefixes |
| MT5 external | 9 PASS; **strict W1 300-bar test FAIL: broker returns 231, 230 closed** |
| Ruff / mypy | PASS; mypy 67 app source files |
| Frontend tests | **132 PASS** |
| ESLint / TypeScript / production build | PASS |
| Generated contracts --check | PASS |
| Alembic DEV head | 0006_strategy, unchanged |
| Browser Dashboard / Strategy / Analysis / Calendar | PASS |
| git diff --check | PASS |

W1 is the pre-existing broker-history limitation, not a new calculation failure.
The strict test was executed explicitly, not labeled NOT RUN. Phase 3 processes the partial history correctly.

## SECURITY / SAFETY

Fixed HTTPS host/path; no arbitrary fetch URL endpoint or redirects; 10-second HTTP timeout / 15-second worker bound;
1 MB decoded body, 500-row bound, JSON content type and finite-value checks.
429 Retry-After accepts seconds/date with bounded backoff. Sanitized failure logs contain exception type.
No API key needed; no LLM economic interpretation, order/execution or Phase 5 feature.

Audit: **25 protected foundation files unchanged**; secret exposure NONE.
No original DEV users/sessions/accounts/symbols/audit_logs/system_events rows deleted.
Auth test sessions logged out; market/analysis/auth foundations preserved.
PAPER / ANALYSIS_ONLY; no orders, sizing, risk engine, kill switch, adaptive decision or deployment.

## VERSIONS / LIMITATIONS

- Strategy **strategy-1.1.0 → strategy-1.2.1**.
  Final patch version distinguishes completed provenance from immutable intermediate DEV evidence.
- News **news-1.1.0 → news-1.2.0**. Structure stays structure-1.0.0.
- FF has no stable occurrence IDs/reference period. Exact series + ISO week preserves ordinary within-week reschedules;
  duplicates fail closed. Cross-week reschedule linkage is unresolved and is never guessed.
- Weekly snapshots cannot recover intrapoll revisions, cancellation/omission or guarantee Actual latency.
- No live NFP this week: tests use labeled deterministic fixtures. No live numeric post-release Actual proof.
- Known unrelated Xoomar GDP defect **DEFERRED**. FF GDP maps advance/preliminary/final series independently.
- W1 history remains partial; no data fabricated or protected market-data code changed.
- Performance evidence is a local sanity run, not stress/long-duration certification.

## GIT STATE / FINAL GATE

Branch main; HEAD **857e764bea47279af7986a449d80505b74820432**, unchanged; staged files **0**.
Existing uncommitted work preserved. **No add/commit/push/branch/merge/rebase/reset/clean performed.**

**READY FOR SOL HIGH COMBINED REVIEW — SAFE PARTIAL with the external-data limitations above.**

**PHASE 5 DO NOT START.**
