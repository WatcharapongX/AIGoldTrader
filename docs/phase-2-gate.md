# Phase 2 — Market Data / Trading Screen

## Status

**IMPLEMENTATION COMPLETE — PENDING COMBINED SOL HIGH INDEPENDENT REVIEW.**
Phase 2 is **PROVISIONAL**, not production approved. Phase 3 / TASK-030+: **DO NOT START**.

The user explicitly authorized Phase 2 before final Phase 1.1 independent re-review.
Prior corrective gate history is preserved. Preflight reran the existing foundation: **93 tests passed**.
Only TASK-021–029 were implemented. No stage, commit or push.

## Current mode

| Item | Value |
|---|---|
| Provider | ReplayProvider via MARKET_DATA_PROVIDER=simulated |
| Market-data label | SIMULATED DATA; no real market feed claim |
| Symbol with source | XAUUSD |
| Trading mode | PAPER |
| LIVE_AUTO_TRADING | false |
| Broker execution / automated orders | NONE |
| Native visual app | http://localhost:3001/trading (login required) |
| Native API | http://localhost:8000 |

Native owned processes are left running for the user. An unrelated service on port 3000 was preserved.
The Codex browser opening was queued; the local URL remains directly accessible.
Real browser tests use private ignored local credentials; all smoke sessions were logged out.

## Phase 2 tasks

| Task | Implementation and acceptance | Result |
|---|---|---|
| TASK-021 | Authenticated symbol reads, ADMIN create/update/deactivate, seeded XAUUSD/specs | PASS |
| TASK-022 | Provider abstraction, deterministic ReplayProvider and configuration registry | PASS |
| TASK-023 | Validated ticks, Decimal fields, persistence, quality rejection and bounded publication | PASS |
| TASK-024 | M1 base to M1/M3/M5/M15/M30/H1/H4/D1/W1, replacement-safe OHLCV and rollover | PASS |
| TASK-025 | Candle upserts, real PostgreSQL, from/to/limit and backwards cursor pagination | PASS |
| TASK-026 | /ws/market first-frame auth, subscription/snapshot/update/status/heartbeat/reconnect | PASS |
| TASK-027 | Responsive candlestick Trading page, symbol/timeframe/quote/source/status controls | PASS |
| TASK-028 | Staleness, abnormal-data system_events, provider recovery; no kill-switch business logic | PASS |
| TASK-029 | Build/test/DB/security/native/visual verification and documentation | PASS |

Completed 9/9, pending implementation tasks 0. Plan total 32/107; original task numbering retained.
Native adaptation explicitly recorded in the existing plan: native PostgreSQL tables and LocalMarketBus
satisfy this single-instance DEV milestone. The original mandatory hypertable/Redis wording is
superseded by the user's current native/optional-dependency instructions. Distributed deployment
and TimescaleDB integration are future work, not silently reported as implemented.

## Market data and screen

Historical data initializes 300 candles/timeframe; API accepts limits 1–1000.
Realtime quote and candle updates follow database commit. Prices remain exact Decimal strings
until chart rendering. UTC normalization covers local-timezone PostgreSQL responses.
W1 starts Monday UTC. Engine and golden replay comparisons cover all nine timeframes.

Trading screen displays XAUUSD, Bid, Ask, Spread, last update, source, connection text, historical
and updating candles, price/time scales and crosshair. Analysis is explicitly unavailable until Phase 3.
There are no actionable entry/SL/TP/AI signals or order buttons.

The chart instance is reused across ticks and timeframe changes. Chart data is capped at 1000 candles.
REST calls/sockets/watchdogs/retry timers clean up on unmount. Reconnect uses an authoritative snapshot,
exponential capped delay and at most ten attempts; manual reconnect remains available.
Local bus queues and accepted/reserved connections are bounded. Slow consumers reconnect instead of
silently dropping a candle transition. Provider outages do not turn liveness into a feed-availability check.

## Visual acceptance — actual final production build

| Check | Result |
|---|---|
| Login / Dashboard / Trading navigation | PASS |
| XAUUSD / Bid / Ask / Spread / SIMULATED DATA visible | PASS |
| Candlestick chart and >=300 historical candles | PASS |
| Observe actual quote/timestamp/candle updates | PASS |
| Timeframe switching | 9/9 PASS |
| Chart canvas survives timeframe changes | PASS |
| Disconnect/reconnect and fresh snapshot | PASS |
| Reload / session recovery | PASS |
| Desktop 1440px / tablet 820px / mobile 390px | PASS, no horizontal overflow |
| Browser console/runtime errors | 0 |
| Failed critical assets | 0 |
| Token in WS URL | NONE |
| Logout and protection | PASS |

Existing native-login.cjs additionally passed wrong-password rejection, genuine backend refresh and
post-logout route protection. Both browser harnesses ran on the final frontend build against real
native PostgreSQL. Desktop and mobile screenshots were visually inspected.

Evidence (ignored local files):
data/local/phase2/market-browser-results.json; trading-desktop.png; trading-tablet.png;
trading-mobile.png; native-auth/browser-results.json; native-results.json; final-safety.json.

## Backend tests

| Check | Result |
|---|---|
| Ruff | PASS |
| mypy app scripts | PASS, 41 source files |
| compileall app/alembic/scripts/tests | PASS |
| Wheel build | PASS |
| Full backend tests | **127 passed, 0 skipped** |
| Real PostgreSQL integration (included above) | **13 passed** |
| Market unit/contract/persistence/auth tests (included above) | **33 passed** |
| Live market DB/WS test (included above) | **1 passed** |
| Existing HARD-R01/R02/R03 regressions | PASS in full suite |
| Alembic check | PASS: No new upgrade operations detected |

The live market integration test was strengthened after the full run to pause only a test provider,
leaving monitoring active. Its focused rerun PASS also verifies persisted MARKET_STALE events.
It validates all histories, selected WS updates, timeframe changes, heartbeat, stale status with healthy
liveness, provider resumption and fresh reconnect snapshots. The test-only pause routes are not part of
the application. Three pre-existing deprecation warnings remain unchanged.

Backend commands: python -m ruff check .; python -m mypy app scripts;
python -m compileall -q app alembic scripts tests; python -m scripts.export_api_contract --check;
python -m pytest --show-capture=no --tb=short;
python -m pip wheel . --no-deps --wheel-dir dist; python -m alembic check.

## Frontend tests

| Check | Result |
|---|---|
| Canonical auth + market/WS contract freshness | PASS |
| Lint | PASS |
| Typecheck | PASS |
| Full frontend tests | **61 passed, 0 skipped** |
| Market schema/semantic/reconnect tests (included above) | **20 passed** |
| Production build | PASS, 20 static pages |
| Actual Trading UI / canvas lifecycle / responsive smoke | PASS |

Commands: npm run lint, npm run typecheck, npm test, npm run build.
The test VM initially needed a full async turn before inspecting its mock WebSocket; the test now
cleans timers even on failure. ESLint findings were resolved. The first final rebuild encountered
Windows EBUSY because our standalone server held its directory; stopping only that owned process
allowed the final build/typecheck to PASS, then the final server and browser suites were rerun.

The first Trading browser run found a real integration mismatch: local PostgreSQL timezone +07:00
versus the strict UTC frontend contract. The backend now normalizes aware fields to UTC Z, with an
added unit test and live REST assertion. The subsequent final visual gate passed. The failed
intermediate attempts are not reported as successful final results.

## Database and native Windows

Migration 0003_phase2_market_data adds ticks/candles and symbols.default_spread.
0001_initial and 0002_phase1_schema_alignment hashes exactly match the pre-Phase-2 baseline.
ORM/migration/actual PostgreSQL agree; SQLite and isolated PostgreSQL fresh/down/up gates pass.

Before/after checks found no missing original rows. All 17 original audit rows and 11 original
sessions retain their fingerprints. The existing smoke user's row changes through the unchanged
authentication service's last_login_at/updated_at behavior. No account/symbol/audit data was discarded.
All smoke sessions are revoked; no isolated TEST schemas remain.

Native Windows Python/FastAPI + Node/Next.js + PostgreSQL 18.6: PASS.
Health/readiness PASS, DB ready, Redis disabled/optional; Docker and WSL not required.
Actual Docker/container orchestration was not run. One DEV service instance is supported.

## Security regression

| Boundary | Result |
|---|---|
| HARD-R01 actual launch peer/spoofing boundary | PASS, existing launch guards retained |
| HARD-R02 semantic token validation and atomic rejection | PASS, auth code/contracts preserved |
| HARD-R03 live access/audit/response and concurrent correlation | PASS |
| Market HTTP access | Auth required; ADMIN-only mutations |
| Market WS | Allowlisted Origin + JWT first frame, deadline, expiry/active-user checks |
| URL credential exposure | Query parameters rejected on /ws/market |
| Malformed market data | Structural and semantic rejection before rendering |
| Sensitive local secrets/JWTs in native logs and changed source | NONE found |

The accepted resolver, correlation middleware, logging/rate limiter, auth API/service, frontend
token validators/client/store and existing auth generated outputs match the pre-Phase-2 fingerprints.
The long-lived feed task starts with an empty context so it does not retain an initiating request ID.

## Files changed this phase

- .env.example
- README.md
- backend/app/api/__init__.py
- backend/app/core/config.py
- backend/app/main.py
- backend/app/models/__init__.py
- backend/app/models/symbol.py
- backend/scripts/export_api_contract.py
- backend/tests/integration/test_postgres.py
- backend/tests/test_foundation_gate.py
- docs/02-system-architecture.md
- docs/04-database-design.md
- docs/05-api-design.md
- docs/17-testing.md
- docs/18-devops.md
- docs/README.md
- docs/phase-1.1-gate.md
- frontend/package-lock.json
- frontend/package.json
- frontend/src/app/(dashboard)/trading/page.tsx
- frontend/src/app/globals.css
- frontend/src/components/layout/AppShell.tsx
- frontend/src/components/layout/Sidebar.tsx
- frontend/tests/e2e/native-login.cjs
- implementation_plan.md

## Files created this phase

- backend/alembic/versions/0003_phase2_market_data.py
- backend/app/api/market.py
- backend/app/models/market.py
- backend/app/services/market_data/__init__.py
- backend/app/services/market_data/aggregation.py
- backend/app/services/market_data/domain.py
- backend/app/services/market_data/provider.py
- backend/app/services/market_data/repository.py
- backend/app/services/market_data/service.py
- backend/tests/integration/test_market_live.py
- backend/tests/test_market_data.py
- docs/06-market-data.md
- docs/phase-2-gate.md
- frontend/src/features/chart/TradingScreen.tsx
- frontend/src/features/chart/contracts.ts
- frontend/src/features/chart/market-contract.generated.json
- frontend/src/features/chart/transport.ts
- frontend/src/types/market.generated.ts
- frontend/tests/e2e/market-screen.cjs
- frontend/tests/market.test.cjs

## Git state

Branch main; HEAD 857e764bea47279af7986a449d80505b74820432 unchanged.
**No stage, commit or push.** Git diff --check PASS.
Combined working tree includes preserved previous Phase 1/P1.1 changes:
**41 tracked modified files; 31 untracked files.**

0002_phase1_schema_alignment.py remains **UNTRACKED and unchanged**.
0003_phase2_market_data.py is **new and UNTRACKED**.
All newly created Phase 2 files above remain untracked. Earlier untracked files and files edited
during this phase remain visible in the inventory below; no existing work was discarded.

### Tracked modified inventory

- .env.example
- README.md
- backend/Dockerfile
- backend/app/api/__init__.py
- backend/app/api/auth.py
- backend/app/api/health.py
- backend/app/core/config.py
- backend/app/core/correlation.py
- backend/app/core/logging.py
- backend/app/core/rate_limit.py
- backend/app/db/session.py
- backend/app/main.py
- backend/app/models/__init__.py
- backend/app/models/refresh_session.py
- backend/app/models/symbol.py
- backend/app/services/audit.py
- backend/tests/conftest.py
- backend/tests/integration/test_postgres.py
- backend/tests/test_foundation_gate.py
- backend/tests/test_native_dev.py
- docker-compose.dev.yml
- docker-compose.yml
- docs/02-system-architecture.md
- docs/04-database-design.md
- docs/05-api-design.md
- docs/17-testing.md
- docs/18-devops.md
- docs/README.md
- docs/phase-1-gate.md
- frontend/package-lock.json
- frontend/package.json
- frontend/src/app/(dashboard)/trading/page.tsx
- frontend/src/app/globals.css
- frontend/src/components/layout/AppShell.tsx
- frontend/src/components/layout/Sidebar.tsx
- frontend/src/lib/api.ts
- frontend/src/stores/auth.ts
- frontend/src/types/index.ts
- frontend/tests/auth.test.cjs
- frontend/tests/e2e/native-login.cjs
- implementation_plan.md

### Untracked inventory

- backend/alembic/versions/0002_phase1_schema_alignment.py
- backend/alembic/versions/0003_phase2_market_data.py
- backend/app/api/market.py
- backend/app/core/client_ip.py
- backend/app/models/market.py
- backend/app/services/market_data/__init__.py
- backend/app/services/market_data/aggregation.py
- backend/app/services/market_data/domain.py
- backend/app/services/market_data/provider.py
- backend/app/services/market_data/repository.py
- backend/app/services/market_data/service.py
- backend/scripts/export_api_contract.py
- backend/tests/integration/launch_support.py
- backend/tests/integration/test_market_live.py
- backend/tests/test_hardening.py
- backend/tests/test_market_data.py
- docs/06-market-data.md
- docs/phase-1.1-gate.md
- docs/phase-2-gate.md
- frontend/src/features/chart/TradingScreen.tsx
- frontend/src/features/chart/contracts.ts
- frontend/src/features/chart/market-contract.generated.json
- frontend/src/features/chart/transport.ts
- frontend/src/lib/contracts.ts
- frontend/src/types/api.generated.ts
- frontend/src/types/market.generated.ts
- frontend/tests/contracts.test.cjs
- frontend/tests/corrective-token.test.cjs
- frontend/tests/e2e/market-screen.cjs
- frontend/tests/fixtures/api-contract.json
- frontend/tests/market.test.cjs

## Known limitations and deferred work

- Synthetic daily-periodic replay only, XAUUSD source only. Not live prices or historical market evidence.
- Volume is synthetic observation count. No real market session calendar or holiday analysis.
- Single-instance in-process publication/limiting; no distributed worker coordination.
- Native PostgreSQL retention is implemented; TimescaleDB hypertables/distributed Redis are not.
- Out-of-order/duplicate ticks are rejected; no late historical correction engine.
- Existing access JWT/session storage architecture is unchanged. P2-R01: DEFERRED / UNCHANGED.
- Ordinary failed-login audit P3-001: DEFERRED / UNCHANGED.
- Existing deprecation warnings unchanged. No broker, execution, strategy, SMC/ICT, AI or risk business logic.
- Final Phase 1.1 + Phase 2 independent review: **PENDING**.

## Gate and stop condition

**PHASE 2: IMPLEMENTATION COMPLETE — PENDING COMBINED SOL HIGH REVIEW.**
**TRADING_MODE=PAPER; LIVE_AUTO_TRADING=false; broker execution NONE.**
**STOP. PHASE 3 / TASK-030+: DO NOT START.**


## Subsequent authorization — Phase 2.5
On 2026-09-09 the user stated that Phase2 had passed Independent Gate and explicitly
authorized Phase2.5 real market data. This records the user's reported acceptance;
no independent review artifact was supplied in this turn. Earlier provisional/review
history above is preserved. Phase2.5 evidence is in phase-2.5-gate.md. Phase3 remains
DO NOT START, pending Independent Sol High Review of the real-data work.
