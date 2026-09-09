## Later user authorization — 2026-09-09

The user explicitly authorized provisional Phase 2 before final Sol High re-review.
Phase 1.1's final independent review is still pending. Phase 2 implementation is now complete and
awaits combined Phase 1.1 + Phase 2 review; see phase-2-gate.md.
The NO-GO/DO NOT START Phase 2 statements in the preserved report below record the earlier
authorization and are superseded only by this explicit user exception. Phase 3 must not start.

---

# Phase 1.1 corrective cycle — PASS (2026-09-09)

## Status and review history

**Corrective engineering verification: PASS. Independent Sol High Re-review: PENDING.**
**Phase 2: NO-GO / DO NOT START. TASK-021+: NOT STARTED.**

Audit trail: initial Phase 1.1 implementation claimed PASS (71 backend / 17 frontend tests);
Independent Review returned **FAIL** with HARD-R01, HARD-R02 and HARD-R03; the gate and
TASK-H001/H002/H003 were reopened before this corrective cycle. All three findings were
reproduced, corrected and verified below. This report does not represent independent acceptance.
The complete initial report remains below as a historical, superseded claim.

Scope: only HARD-R01/R02/R03, focused regression tests and corrective evidence.
Existing uncommitted Phase 1/P1.1 work is preserved. No staging, commit or push.
Plan: hardening 3/3, total 23/107; original numbered tasks remain 104.

## HARD-R01 — trusted-proxy launch boundary

Root cause: base docker-compose.yml omitted --no-proxy-headers. Uvicorn rewrote the transport
peer before the independently accepted application resolver could enforce TRUST_PROXY=false.
Before correction, the base command's real native listener allowed four rotating-forwarded-header
attempts with a limit of three: 401, 401, 401, 401.

Minimal fix: add --no-proxy-headers to the base Compose command. The application resolver is
byte-for-byte unchanged. Audit covered README, native/development docs, base/dev Compose,
Dockerfile, scripts and test/harness launch calls. The loop-only Config test now explicitly sets
proxy_headers=False. The new harness reads actual source commands and never injects a proxy flag.

Files changed this cycle: docker-compose.yml; backend/tests/test_hardening.py;
backend/tests/test_native_dev.py; backend/tests/integration/test_postgres.py;
new backend/tests/integration/launch_support.py.

| Launch surface | Source command | Proxy headers disabled | TRUST_PROXY=false safe | Result |
|---|---|---|---|---|
| README.md | uvicorn app.main:app --no-proxy-headers --reload --port 8000 --loop app.core.event_loop:new_event_loop | Yes | Yes | PASS: real native transport test |
| docs/18-devops.md | uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8000 --reload --loop app.core.event_loop:new_event_loop | Yes | Yes | PASS: real native transport test |
| docker-compose.yml | uvicorn app.main:app --no-proxy-headers --host 0.0.0.0 --port 8000 | Yes | Yes | PASS: real native transport test |
| docker-compose.dev.yml | uvicorn app.main:app --no-proxy-headers --host 0.0.0.0 --port 8000 --reload | Yes | Yes | PASS: real native transport test |
| backend/Dockerfile | uvicorn app.main:app --no-proxy-headers --host 0.0.0.0 --port 8000 | Yes | Yes | PASS: real native transport test |

Runtime verification uses each source command's actual proxy options, even with
FORWARDED_ALLOW_IPS="*". Host/port and Windows event loop are adapted; --reload supervisor is
removed for an owned single-process test. Thus the matrix verifies server transport behavior,
not full container orchestration or the reload supervisor. Docker/container execution: **NOT RUN**
(Docker unavailable; optional). WSL is not required. No extra executable launcher was found in scripts.

Five launch tests rotate XFF, X-Real-IP, Forwarded and accounts from one peer:
401, 401, 401, **429**; audit records retain the direct peer. Two additional live base-Compose tests
verify TRUST_PROXY=true: trusted immediate peers resolve valid chains; untrusted peers ignore them;
malformed chains fall back to the transport peer. Existing wildcard/configuration and resolver tests pass.
Result: **HARD-R01 PASS**.

## HARD-R02 — token semantics and atomic rejection

Root cause: the frontend checked broad field types and permissive date parsing, while the backend
schema allowed arbitrary token strings/type. The review payload (empty tokens, Basic, expiry "1")
was reproduced as accepted, with two storage entries and a cookie written.

Backend contract: strict nonempty token strings without whitespace; required exact lowercase literal
"bearer"; required timezone-aware datetime with a strict RFC3339 shape in OpenAPI.
The response model rejects malformed calendar/time values and numeric/naive date input.
Future-at-acceptance is enforced by the frontend because it depends on the receiving client's clock.
This decision and the canonical contract are documented in docs/05-api-design.md.

Frontend validation: strict calendar, clock and timezone parsing, expiry strictly greater than the
acceptance time, and token semantics all run before persistence. It does not rely on Date.parse().
Fractional seconds accept the backend's 1–6 digits; millisecond conversion is conservative.
ApiContractError propagates through refresh/recovery without token/cookie writes; authentication
remains false after invalid recovery. Ordinary failed/expired-session handling remains intact.
No token-storage architecture redesign was made.

Files: backend/app/api/auth.py; frontend/src/lib/contracts.ts; frontend/src/lib/api.ts;
frontend/src/stores/auth.ts; generated frontend/src/types/api.generated.ts and
frontend/tests/fixtures/api-contract.json; backend/tests/test_hardening.py;
new frontend/tests/corrective-token.test.cjs; docs/05-api-design.md.
Generated outputs came from the existing exporter; the generator itself is unchanged.

Negative coverage: 22 malformed cases each traverse actual login, refresh and session recovery,
including empty/whitespace tokens, Basic/Bearer/arbitrary type, malformed/missing objects/fields,
numeric-like expiry, invalid dates, expired/current timestamps. Storage and cookie snapshots
remain unchanged and authenticated state is false. Backend negative cases and OpenAPI assertions
also pass. Fixed-clock boundary/calendar/offset tests and valid login/refresh/recovery tests pass.

Real Chromium additionally intercepted only a test-context login response with the exact malformed
review payload: rejection shown, login page retained, storage/cookie unchanged, runtime errors zero.
The separate real PostgreSQL browser login/refresh flow passes with genuine backend responses.
Result: **HARD-R02 PASS**.

## HARD-R03 — request correlation lifecycle

Root cause: BaseHTTPMiddleware reset the ContextVar before Uvicorn emitted access logging during
http.response.start. Reproduction showed the response ID present but uvicorn.access correlation "-".

Fix: a small pure ASGI CorrelationMiddleware holds request-scoped context through response send,
body and background completion; sets the canonical response header; resets only in finally after
the ASGI lifecycle. Existing safe error handling is reused. No global mutable request ID or logging
stack replacement. Exceptions before response start receive a correlated controlled 500.
After headers have already been sent, exceptions are safely logged and re-raised rather than
attempting a second response. The live exception probe covers the pre-header JSON response path.

Files: backend/app/core/correlation.py, backend/app/main.py and live PostgreSQL integration tests.

Live verification: valid ID, invalid 65-character ID, controlled exception and 12 concurrent labeled
requests preserve response/audit/application/access correlation without cross-contamination.
The error log shares the exception request's canonical ID. In the separate native browser run,
all 18 access records have non-"-" IDs. Real successful login with an invalid supplied ID and the
browser login each match response, persisted audit, application log and access log.

Result: **HARD-R03 PASS**.

## Final regression results

| Check | Result |
|---|---|
| Backend Ruff | PASS |
| Backend mypy app scripts | PASS, 33 source files |
| Backend compileall app/alembic/scripts/tests | PASS |
| Backend wheel build | PASS |
| Full backend pytest | **93 passed, 0 skipped**, 3 pre-existing warnings |
| PostgreSQL integration subset included above | **12 passed** (includes 8 live launch/correlation tests) |
| Native Windows / Redis-disabled / auth / audit / proxy / limiter / logging tests | PASS within full suite |
| Alembic check against real PostgreSQL | PASS: No new upgrade operations detected |
| Generated API contract freshness | PASS |
| Frontend lint / typecheck | PASS |
| Frontend production build | PASS, 20 static pages |
| Full frontend tests | **41 passed, 0 skipped** |
| Existing real Chromium auth smoke | PASS, browser errors 0 / failed assets 0 |
| Malformed-token Chromium harness | PASS, no persistence / runtime errors 0 |

Final commands, run with the project virtual environment from backend:

    python -m ruff check .
    python -m mypy app scripts
    python -m compileall -q app alembic scripts tests
    python -m scripts.export_api_contract --check
    python -m pytest --show-capture=no --tb=short
    python -m pip wheel . --no-deps --wheel-dir dist
    python -m alembic check

Frontend: npm run build, npm run typecheck, npm run lint, npm test.
The existing frontend/tests/e2e/native-login.cjs ran against owned native backend and Next standalone
processes with real DEV PostgreSQL credentials supplied from ignored local configuration.

Browser smoke covers protected redirect, wrong password, valid login/dashboard, reload/session
recovery, refresh, logout, protection after logout, console/runtime errors and assets.
Early harness setup needed UTF-8 file reads and a corrected test-helper import location; those were
fixed before the successful final full regression. No outstanding test failure is omitted.

## Security, database and native verification

- Forwarded-header spoofing: BLOCKED at the supported source launch boundaries.
- Semantic-invalid token payload: REJECTED / NOT PERSISTED across all consuming paths.
- Correlation overflow and log injection: SAFE; access correlation PRESENT; concurrency PASS.
- Sensitive DB parameters: NOT EXPOSED by regression checks. Final native logs and modified/untracked
  source were scanned against actual local secrets, URL/password variants and logs for JWTs; no matches
  were found. Scans report only outcomes, never secret values.
- Migration 0001_initial and 0002_phase1_schema_alignment SHA-256 fingerprints match the pre-edit
  baseline exactly. No new migration or database architecture change.
- Real database remains at 0002; Alembic reports no drift. Existing integration fresh/rollback/
  re-upgrade coverage passes. All 12 pre-existing audit row fingerprints were preserved.
- Dedicated TEST database used isolated newly owned schemas; zero residual test schemas.
  Native smoke sessions logged out; zero unrevoked smoke-user sessions.
- Native Windows Python/FastAPI + Node/Next.js + PostgreSQL 18.6: PASS. Health/readiness are healthy,
  database true, Redis disabled/optional. Owned smoke processes were stopped; PostgreSQL service
  remains running. Docker optional and not installed; WSL not needed.
- TRADING_MODE=PAPER, LIVE_AUTO_TRADING=false. Broker execution path NONE, new Phase 2 code NONE.

## Git state and scope preservation

Branch main; HEAD 857e764bea47279af7986a449d80505b74820432 unchanged.
No staged changes; no commit or push. Git diff --check passes.
The following state includes preserved earlier P1/P1.1 work, not only this corrective cycle.

### Tracked modified files (29)

- .env.example
- README.md
- backend/Dockerfile
- backend/app/api/auth.py
- backend/app/api/health.py
- backend/app/core/config.py
- backend/app/core/correlation.py
- backend/app/core/logging.py
- backend/app/core/rate_limit.py
- backend/app/db/session.py
- backend/app/main.py
- backend/app/models/refresh_session.py
- backend/app/services/audit.py
- backend/tests/conftest.py
- backend/tests/integration/test_postgres.py
- backend/tests/test_native_dev.py
- docker-compose.dev.yml
- docker-compose.yml
- docs/02-system-architecture.md
- docs/04-database-design.md
- docs/05-api-design.md
- docs/17-testing.md
- docs/18-devops.md
- docs/phase-1-gate.md
- frontend/src/lib/api.ts
- frontend/src/stores/auth.ts
- frontend/src/types/index.ts
- frontend/tests/auth.test.cjs
- implementation_plan.md

### Untracked files (11)

- backend/alembic/versions/0002_phase1_schema_alignment.py
- backend/app/core/client_ip.py
- backend/scripts/export_api_contract.py
- backend/tests/integration/launch_support.py
- backend/tests/test_hardening.py
- docs/phase-1.1-gate.md
- frontend/src/lib/contracts.ts
- frontend/src/types/api.generated.ts
- frontend/tests/contracts.test.cjs
- frontend/tests/corrective-token.test.cjs
- frontend/tests/fixtures/api-contract.json

**0002_phase1_schema_alignment.py remains UNTRACKED and unchanged.**
It was already untracked before this corrective cycle. The accepted client_ip.py resolver and
existing exporter also match the pre-edit fingerprints. This cycle changed 15 existing files and
added only launch_support.py and corrective-token.test.cjs; all other pre-existing source files
match the baseline. No user edits were reverted.

## Evidence and remaining gate

Sanitized local evidence is ignored under data/local/hard-corrective/:
reproduction.json (historical before-fix behavior), native-results.json, browser-results.json,
malformed-browser.json, security-evidence.json, final-safety.json, dashboard.png and
malformed-login.png. Historical reproduction-server.log intentionally demonstrates the old "-"
access ID; backend.log is the corrected native run. Evidence and credentials were not staged.

P2-R01 token-storage architecture: **DEFERRED / UNCHANGED**.
P3-001 ordinary failed-login auditing: **DEFERRED / UNCHANGED**.
Single-process limiter: **KNOWN LIMITATION**, unchanged.
Three deprecation warnings: **PRE-EXISTING**, not addressed in this scope.

**Phase 1.1 corrective verification gate: PASS.**
**STOP — pending Independent Sol High Re-review. Phase 2: DO NOT START.**

---

## Historical initial implementation claim (superseded by independent FAIL and corrective report above)

# Phase 1.1 Foundation Hardening — PASS (2026-09-09)

## Status and authorization

Phase 1.1 corrective engineering gate: **PASS**. TASK-H001/H002/H003: 3/3 complete.
Plan total: 23/107 (original 104 tasks plus 3 hardening tasks; no renumbering).
**Independent Sol High Review is pending. Phase 2: DO NOT START.**

The user supplied Phase 1 Independent Re-review: PASS WITH MINOR ISSUES, P1-001 FIXED AND INDEPENDENTLY VERIFIED.
That review granted Phase 2 GO, followed by the user's explicit requirement to complete this targeted hardening
and stop for another review. No TASK-021+, market-data, candle/tick, trading WebSocket, strategy, AI trading
or broker implementation was added. No commit or push; existing uncommitted P1 work was preserved.

## Source-confirmed reproduction before fixes

A newly owned schema in the existing dedicated TEST PostgreSQL database reproduced:

| Finding | Reproduction | Before |
|---|---|---|
| P2-001 | Same peer/account; change XFF over 11 wrong login attempts with a 10/minute limit | All 11 returned 401; bypass confirmed |
| P2-002 | Successful credentials plus a 65-character correlation header on real PostgreSQL | HTTP 500 |
| P2-002 | Render a SQLAlchemy StatementError carrying a fixture sensitive parameter | Parameter exposed by original formatter |
| P2-003 | Compare source MeResponse/TS User and readiness client return type | Missing backend fields required by frontend; readiness typed as health |

Only sanitized reproduction outcomes were saved in ignored data/local/phase1-1/reproduction.json.
Source, prior gate/plan, ORM/migrations, OpenAPI, tests, installed Uvicorn proxy implementation and installed
Next.js TypeScript/data-fetching guidance were inspected before editing.

## P2-001 — rate limiting and trusted proxy

**Root cause:** auth accepted the first client-supplied XFF value without a trust boundary; its limiter key was
IP+email, so either could reset the budget. The dictionary retained arbitrarily many attacker-chosen keys.
Uvicorn could also rewrite request.client before application code.

**Fix:** direct transport peer by default; supported native/Docker launch commands use --no-proxy-headers.
TRUST_PROXY defaults false. Opt-in requires bounded TRUSTED_PROXY_CIDRS; wildcard/default routes are rejected.
Only trusted immediate peers may provide one valid bounded XFF chain; walk right-to-left to the first untrusted
hop. Other forwarded-header forms remain unused. Invalid/ambiguous chains fall back to the peer.

Every login checks independent resolved-client and normalized-account (trim/casefold SHA-256 key) budgets.
Single-process windows use monotonic time and a lock; 60-second expiry, ordered cleanup and bounded deques/keys.
At capacity, reject new identities rather than evict active protections. Defaults: 10/minute and 10,000 keys.
Redis remains optional; no distributed limiter was introduced.

**Tests:** same peer, changed XFF, changed accounts, same normalized account across peers, trusted/untrusted
multi-hop proxies, IPv6, malformed chains, unsafe configuration, expiry, atomic budgets and capacity.
Native Uvicorn test varied XFF/Forwarded/X-Real-IP plus account under a 3/minute test configuration:
**401, 401, 401, 429**. Persisted limited-login audit IP: **127.0.0.1**, the actual peer.
The owned API was restarted at the normal 10/minute limit before browser regression.

**Result: PASS.** Limitations: per-process state resets on restart; shared NAT and account-wide throttling can
temporarily affect legitimate users. Multi-instance deployments require a future shared design.
A trusted proxy must correctly overwrite/append XFF, and upstream peer rewriting must stay disabled.

## P2-002 — correlation ID and exception logging

**Root cause:** the header was copied unchecked into a VARCHAR(64) audit field. Exception traceback rendering
included SQLAlchemy/driver parameter context.

**Fix:** one helper accepts ASCII [A-Za-z0-9][A-Za-z0-9._-]{0,63}; invalid/missing IDs become UUID hex.
Middleware, audit writes and response/log context use the validated identity; context resets after each request.
Controlled unexpected errors also retain the canonical response header and generic error body.

SQLAlchemy hide_parameters=True; SQL engine logging stays WARNING. Safe exception formatting keeps type,
code locations and safe SQLSTATE without SQL/driver text, raw parameters, request bodies or locals.
HTTP logs retain operation, method, route template and correlation; console retains operation/type/correlation.
Existing ordinary failed-login audit behavior was not extended.

**Tests:** exact 64-character ID retained; overlong, spaces, CR/LF and NUL handled; context reset; normal/error
headers; real PostgreSQL login/audit with valid, overlong and injection IDs; direct audit override validation.
Actual PostgreSQL CAST failure with a random sensitive bound parameter tested in both JSON and console output:
DataError and correlation/context visible; parameter, password and signing key absent.

The first integration harness run inspected hide_parameters on AsyncEngine directly and failed with AttributeError.
Corrected the test to inspect sync_engine; both log-format cases and the final full suite then passed.
No production code workaround was used to suppress the test.

**Result: PASS.** No change to database column lengths or migration 0001/0002.

## P2-003 — frontend/backend response contracts

**Root cause:** TS User required mfa_enabled/last_login_at/created_at absent from /auth/me; readiness reused a
different health shape; generic response.json() as T skipped runtime validation.

**Fix:** backend Pydantic/OpenAPI is authoritative. Added health/readiness response models (including readiness
503 schema), typed the existing role enum, and exported only Phase 1 response models with a small Python script.
No new dependency/toolchain package. Generated TypeScript reflects required/optional/nullable fields; User aliases
MeResponse. TokenPair also includes expires_at and the schema's defaulted token_type.

Transport returns unknown; endpoint parsers validate user/token/health/readiness responses before consumption.
Malformed token responses never reach browser storage. Existing storage/refresh/logout architecture is unchanged.

**Tests:** backend wire/model field checks, exact generated-artifact freshness; frontend OpenAPI-derived fixtures
and missing/wrong required-field mutations, role/status/Redis-nullability checks, actual client parser boundaries,
invalid-token storage rejection, and existing auth/store/client tests.

**Result: PASS.** ReadyResponse is distinct from HealthResponse; existing non-2xx client rejection behavior remains.
Runtime parsers accept additive fields. The scoped generator fails on unsupported schema constructs so extension
requires deliberate review.

## Final executed regression results

| Check | Command / evidence | Result |
|---|---|---|
| Backend lint | python -m ruff check . | PASS |
| Backend typecheck | python -m mypy app scripts | PASS — 33 source files |
| Contract freshness | python -m scripts.export_api_contract --check | PASS |
| Backend full tests | python -m pytest --show-capture=no --tb=short | PASS — **71 passed, 0 skipped**, 3 existing deprecation warnings |
| PostgreSQL integration | Four actual PostgreSQL cases in the final full suite: two original schema/auth cases + JSON/console hardening cases | PASS — **4 tests** |
| Auth/audit/health/Windows/Redis regression | Included in full backend suite plus actual native HTTP/browser checks | PASS |
| Backend build | python -m pip wheel . --no-deps --wheel-dir dist | PASS |
| DEV schema consistency | python -m alembic check | PASS — **No new upgrade operations detected** |
| Frontend build | npm.cmd run build | PASS — 20 generated static pages |
| Frontend typecheck | npm.cmd run typecheck | PASS |
| Frontend lint | npm.cmd run lint | PASS |
| Frontend full tests | npm.cmd test | PASS — **17 passed, 0 skipped** |
| Native Windows | Uvicorn selector loop + Next standalone + PostgreSQL 18.6 | PASS |
| Native security | Real HTTP spoofing / peer audit / overlong header | PASS |
| Native health/readiness | PAPER, live=false, database=true, redis=null, redis_enabled=false | PASS |
| Chromium browser | Existing native-login.cjs, real UI/API/PostgreSQL | PASS |
| Optional Docker runtime / live Redis / PostgreSQL 16 | Outside this native acceptance run | NOT RUN |

Browser: protected-route redirect, wrong password, successful authenticated dashboard, reload, server refresh,
logout/session clear and protected-route recovery all passed. Runtime errors 0, failed assets 0.
Screenshot inspected; the existing PAPER dashboard shell rendered correctly.

## Database regression and security verification

- Migration 0001 unchanged against Git baseline; migration 0002 unchanged against pre-hardening fingerprint.
  Prior P1 session-model and database-design edits were preserved unchanged.
- Real TEST fresh/up/down/re-upgrade/negative drift tests still pass; DEV stays at 0002_phase1_schema_alignment.
- No DEV schema migration/reset was performed this round. All eight preexisting DEV audit record fingerprints
  remained identical; browser LOGIN persisted as JSONB with the matching canonical correlation.
- No unrevoked refresh sessions remain after browser logout; zero phase1_gate_* TEST schemas remain.
- Source and native log scans found no real password, signing key, credential URL or JWT exposure.
  PostgreSQL parameter-leak checks use random test data and assert safe diagnostics in both logging formats.
- TRADING_MODE=PAPER; LIVE_AUTO_TRADING=false; broker execution path NONE; Phase 2 code NONE.
- Temporary verification servers stopped by verified PID/command line; native PostgreSQL service preserved.
  Ignored backend/.env and browser credentials were not rewritten.

Ignored evidence: data/local/phase1-1/reproduction.json, baseline.json, native-security.json,
browser-results.json, audit-before.json, data-security-results.json, dashboard.png and server logs.
No secrets from local evidence belong in commits or reports.

## Files changed in this hardening round

- .env.example; README.md; backend/Dockerfile; docker-compose.dev.yml — explicit proxy/limit defaults and safe launch flags.
- backend/app/api/auth.py; backend/app/core/config.py; backend/app/core/rate_limit.py — trusted identity and bounded budgets.
- backend/app/core/correlation.py; backend/app/core/logging.py; backend/app/db/session.py;
  backend/app/main.py; backend/app/services/audit.py — validated context and safe failure diagnostics.
- backend/app/api/health.py — authoritative health/readiness response models.
- backend/tests/conftest.py; backend/tests/integration/test_postgres.py — test-state isolation and real DB regression.
- frontend/src/lib/api.ts; frontend/src/types/index.ts; frontend/tests/auth.test.cjs — endpoint validation/types and fixtures.
- docs/02-system-architecture.md; docs/05-api-design.md; docs/17-testing.md; docs/18-devops.md —
  targeted security, contract, test and configuration documentation.
- docs/phase-1-gate.md; implementation_plan.md — independent acceptance evidence and hardening task/gate status.

## Files created in this hardening round

- backend/app/core/client_ip.py
- backend/scripts/export_api_contract.py
- backend/tests/test_hardening.py
- frontend/src/lib/contracts.ts
- frontend/src/types/api.generated.ts
- frontend/tests/contracts.test.cjs
- frontend/tests/fixtures/api-contract.json
- docs/phase-1.1-gate.md

The untracked 0002 migration already existed before this round; it is not a new hardening change.
No dependency versions, auth store, UI components, token storage architecture or future trading modules changed.

## Deferred findings and stop point

- P2-R01 — Browser Token Storage Architecture: **DEFERRED**.
- P3-001 — Ordinary Failed Login Audit Coverage: **DEFERRED**.

**Phase 1.1 gate: PASS. Independent Sol High Review: PENDING. Phase 2: DO NOT START.**
No commit, push, history rewrite or user-work discard.
