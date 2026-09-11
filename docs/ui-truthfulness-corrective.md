# ASTRA HIGH
# UI TRUTHFULNESS CORRECTIVE BATCH

## STATUS
COMPLETE for the targeted UI corrective batch; ready for independent SOL HIGH re-review. This is not Phase 5 approval. The external MT5 W1 history test remains FAIL (231/300 real bars), disclosed below; no bars were fabricated.

## BASELINE
- Branch: main.
- Original task starting HEAD: c01b53303c9c0a5357274b815266e7899b1f71b9.
- Continuation starting HEAD: 88c676d1caae450325ef76bd83e31b012efa5333.
- During the interruption, commit 88c676d landed and was pushed independently. It already contains the main truthfulness changes and six local startup files. This continuation preserves that commit and leaves those startup files unchanged.
- The final corrective commit completes browser acceptance, the exact public image exception, and the Analysis route using the existing TradingScreen. No backend/domain files changed.

## FINDINGS FIXED
| Finding | Result | Evidence |
| --- | --- | --- |
| UI-P1-001 | FIXED | Canonical quote and M5 candle rendering, unavailable unsupported assets/MA/daily change; semantic source-change tests. |
| UI-P1-002 | FIXED | Strategy Setup / Setup Score from plan.score, /100; no AI confidence/probability claim. |
| UI-P1-003 | FIXED | Removed fabricated portfolio, performance and sentiment metrics/charts. |
| UI-P1-004 | FIXED | API-backed trading/health status; UNKNOWN on failures; AI NOT IMPLEMENTED. |
| UI-P2-005 | FIXED | Decorative Login without static gold quote or unsupported live/AI feature claims. |
| UI-P3-006 | FIXED | Obsolete phase copy removed; Analysis reuses implemented workspace; lint and semantic tests pass. |

## MARKET DATA TRUTHFULNESS
- XAUUSD bid, ask and spread: canonical quote values; source must match the active provider.
- Change: unavailable; fabricated daily change removed.
- OHLC: canonical latest M5 candle with timestamp and CLOSED/FORMING label; unavailable without candles. Not derived from bid/ask.
- MA: unavailable (dash); no frontend approximation.
- Source/freshness: provider, mode, quote timestamp and freshness/connection label. Live Market Data requires fresh real-mode data and confirmed transport/provider state. Simulated data is explicitly labeled. Retained stale data is marked, and stale plans are suppressed.
- EURUSD, DXY, US10Y, BTCUSD: unavailable, with no invented prices or changes.
- Dashboard chart: existing canonical candles rendered with lightweight-charts; no synthetic candles.

## AI SEMANTICS
- AI Trading Signal: replaced with Strategy Setup.
- Setup Score: deterministic backend plan.score /100; absent plan is a dash.
- AI Confidence: removed; explicit text says score is not a probability or AI result.
- Phase 6 dependency: AI remains NOT IMPLEMENTED; no AI implementation introduced.

## PORTFOLIO / PERFORMANCE
- Equity, PnL, Win Rate and Strategy Performance: unavailable; no numerical placeholder or fabricated chart.
- Sentiment: replaced by canonical market structure with a non-sentiment/non-signal explanation.
- Fake Metrics Remaining: NO in the targeted Login/Dashboard surfaces.

## OPERATIONAL STATUS
- Trading Mode: runtime PAPER.
- Auto Trading: runtime OFF.
- Market Data / MT5: mt5_demo_iux, DEMO, real market data; runtime reports PARTIAL HISTORY.
- Database: runtime health/readiness response (HEALTHY in the successful browser run).
- AI: NOT IMPLEMENTED.
- Failed API scenario: trading/auto-trading/backend/database/market state UNKNOWN, no forced HEALTHY or Live Market Data.
- Health polling: bounded 15-second interval, 8-second timeout, abort/cleanup on unmount.

## LOGIN
- Static Quote: removed.
- Real-Time Claim: no unconditional market/AI/risk-engine claim.
- Result: PASS at 1440, 820 and 390 px.
- Illustration repair: proxy permits the exact /images/login-bg.jpg asset. Unknown assets, nested paths under that filename, and Dashboard remain protected by the existing route gate. API token validation is unchanged.

## TEST RESULTS
Validation performed 2026-09-11 against the final production frontend and the unchanged backend.
| Check | Result |
| --- | --- |
| Full backend | 504 passed, 10 external MT5 cases deselected; 3 existing dependency warnings |
| PostgreSQL integration | 22 passed, included in the 504; separate disposable test database and isolated test schemas |
| Evaluation identity | 61 unit + 3 PostgreSQL passed |
| Phase 3 analysis | 54 unit + 1 PostgreSQL passed |
| News/calendar | news, Forex Factory, public calendar and their PostgreSQL suites passed |
| Phase 4 strategy | 68 unit + 1 PostgreSQL passed |
| Frontend full suite | 150 passed |
| Semantic UI tests | 12 passed, real React rendering with changing fixtures |
| ESLint | PASS |
| TypeScript | PASS |
| API Contract | PASS (export_api_contract --check) |
| Production build | PASS |
| Browser | PASS: Login, Dashboard, Trading, Analysis x 1440/820/390; API-unavailable scenario PASS |
| Browser console/assets | No critical console errors, no failed critical assets, no horizontal document/main overflow |
| External MT5 read-only | 9 passed; 1 FAIL: W1 has 231/300 real bars |

The initial backend run lacked test database configuration and skipped integration tests. A subsequent full run used the existing separate disposable test database and passed all 22 PostgreSQL tests. The final result above is that completed run. No DEV database was used as the integration test database.

Browser acceptance performs real login backed by PostgreSQL, waits for the dashboard summary and canonical candles, validates the Analysis response, and captures screenshots. A separate intercepted 503/WebSocket-disconnected scenario verifies unavailable semantics. Expected 503 errors belong only to that explicit failure scenario. Screenshots were visually inspected for desktop/mobile Dashboard, mobile Login/Analysis and unavailable state.

A malformed generated Next.js development cache initially blocked typechecking. It was moved into the ignored evidence directory; the production build and typecheck passed. PM2 frontend was restarted on the rebuilt production output. Backend and MT5 were left running.

Local evidence (ignored, not committed): data/local/ui-truthfulness/{backend.txt,backend.xml,frontend-tests.txt,lint.txt,typecheck.txt,build.txt,mt5.txt,browser/results.json,browser/*.png}.
Re-run commands: npm test; npm run lint; npm run typecheck; npm run build in frontend, and python -m scripts.export_api_contract --check in backend. Browser harness: frontend/tests/e2e/ui-truthfulness.cjs, configured through E2E_BASE_URL, E2E_CREDENTIALS_PATH, E2E_OUTPUT_DIR and PLAYWRIGHT_MODULE. Credentials are read from a local file and are not embedded in the harness.

## SOL-P1-001 REGRESSION
- Evaluation Identity: PASS; all backend files hash-identical to the original task baseline.
- STRAT01-04: identity/strategy regressions PASS, logic unchanged.
- STRAT05-06: news/identity/strategy regressions PASS, logic unchanged.
- Result: no regression observed; existing SOL-P1-001 closure preserved.

## TRADING SAFETY
- TRADING_MODE: PAPER.
- LIVE_AUTO_TRADING: false.
- order_send: not invoked or added.
- Broker Execution: not implemented or enabled by this batch.
- Risk Engine: no changes or new implementation.
- Phase 5: not started.

## DEFERRED FINDINGS
- SOL-P2-001: GET persistence — unchanged/deferred.
- SOL-P2-002: analysis timestamp semantics — unchanged/deferred.
- SOL-P2-003: Xoomar GDP — unchanged/deferred.
- SOL-P2-004: JWT localStorage — unchanged/deferred.
- SOL-P2-005: Forex Factory cross-week identity — unchanged/deferred.
- SOL-P3-001: dependency warnings — unchanged/deferred.
- External limitation: MT5 W1 history 231/300; remains visibly PARTIAL, not synthesized.

## GIT RESULT
- Branch: main.
- Starting HEAD: original c01b533; resumed from 88c676d.
- Corrective commit message: fix(ui): remove misleading trading and performance data.
- Commit SHA / final HEAD / push outcome: recorded in the delivery message after normal push to origin/main; this document belongs to that corrective commit.
- Intended staged files: Analysis page, proxy, auth regression tests, browser truthfulness harness, and this report.
- Previously local startup files: already tracked by intervening 88c676d; not modified or newly staged by this continuation.
- Secret scan: PASS across 19 changed files from the original baseline, including known local secret values and credential patterns; no findings. Staged scope is checked separately before commit.
- Modified/untracked/staged after commit: verified in delivery. Ignored evidence and credentials are excluded.

## NEXT GATE
READY FOR SOL HIGH UI TRUTHFULNESS RE-REVIEW: YES.
Re-review must consider the disclosed MT5 history limitation. This batch does not grant approval to begin Phase 5.

## PHASE 5
DO NOT START. Stop after commit/push and wait for independent SOL HIGH re-review.
