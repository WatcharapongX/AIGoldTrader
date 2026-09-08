# Phase 1 gate — PASS (2026-09-08)

## PHASE / TASK / STATUS

**Phase 1 — Project Foundation / TASK-020: PASS — 11/11 tasks.**
Plan total: 20/104. Phase 2 remains unstarted; stop for independent review.
This report replaces the prior missing-PostgreSQL evidence with actual native service and browser results.

## Environment and scope

- Windows native PostgreSQL service postgresql-x64-18, PostgreSQL 18.6, accepting connections on local port 5432.
- PostgreSQL was installed by the user before this continuation; no installer download, service modification, authentication-rule change or password reset was performed.
- User authorized a visible hidden-password prompt. The setup helper created distinct new DEV/TEST databases with separate restricted login roles.
- Backend/.env stores project configuration only; the installation/admin password was not saved.
- Original architecture names PostgreSQL 16; this host's gate was tested on 18.6. No PostgreSQL 16 verification is claimed.
- Existing frontend process on port 3000 was preserved. Browser acceptance used a separate production frontend on 3001 and native API on 8000.
- No Docker tests, Redis installation, Phase 2 work, trading feature, commit or push.

## Changes in this continuation

Changed:

- backend/tests/integration/test_postgres.py — reads explicit test configuration from process environment or backend/.env; checks actual schema/index/FK constraints, transactions, password hashing, failed login, refresh/session persistence, audit fields and secret-free logs. Runs auth/audit both before rollback and after re-apply.
- frontend/src/components/layout/Sidebar.tsx — the Logout button had no click handler. Connected it to the existing auth store; no auth architecture change.
- implementation_plan.md, README.md, docs/17-testing.md, docs/18-devops.md and this report — current setup, reproducible commands and verified gate status.

Created:

- backend/scripts/setup_native_postgres.py — hidden installation-password prompt; new DEV/TEST databases and restricted roles; no existing objects reset/dropped. Generated role passwords use SCRAM verifiers in SQL.
- frontend/tests/e2e/native-login.cjs — real Chromium browser acceptance using the preinstalled Playwright bundle. No browser framework added to package.json.
- Ignored local configuration/evidence: backend/.env and data/local/task020-browser (generated browser test credentials, logs, screenshot, browser-results.json and postgres-evidence.json). These files must remain local.

## Commands and actual results

Run backend commands from backend, frontend commands from frontend.

| Check | Executed command / evidence | Result |
|---|---|---|
| Native PostgreSQL listening | PostgreSQL 18 pg_isready | PASS |
| Actual DEV connection | psycopg SELECT current_database/current_user; restricted role check | PASS |
| DEV migration | python -m alembic upgrade head | PASS — 0001_initial |
| PostgreSQL integration | python -m pytest -m integration --show-capture=no --tb=short -rs | PASS — 1 passed, 35 deselected |
| Migration up | Real Alembic upgrade head in a new isolated test schema | PASS |
| Schema | Six foundation tables + revision, primary keys, unique indexes and foreign keys queried in PostgreSQL | PASS |
| Transactions/constraints | Actual insert/rollback, duplicate email rejection, missing-user session FK rejection | PASS |
| Rollback | Real Alembic downgrade base; no application tables/revision row remain | PASS |
| Re-migration | Real Alembic upgrade head; revision 0001_initial and auth/audit work again | PASS |
| Final test state | Newly owned test schemas removed; zero phase1_gate_* schemas remain | PASS |
| Backend lint | python -m ruff check . | PASS |
| Backend typecheck | python -m mypy app scripts | PASS — 31 files |
| Backend syntax/import | python -m compileall -q app alembic scripts; native startup/tests | PASS |
| Backend full regression | python -m pytest --show-capture=no --tb=short | PASS — 36 passed, no skips |
| Backend build | python -m pip wheel . --no-deps --wheel-dir dist | PASS |
| Frontend build | npm.cmd run build | PASS — 20 generated static pages |
| Frontend typecheck | npm.cmd run typecheck | PASS |
| Frontend lint | npm.cmd run lint | PASS |
| Frontend unit tests | npm.cmd test | PASS — 6 passed |
| Native API /healthz | Actual HTTP query; PAPER, live_auto_trading=false | PASS |
| Native API /readyz | Actual HTTP query; database=true, redis=null | PASS |
| Browser gate | node tests/e2e/native-login.cjs, configured as in docs/17-testing.md | PASS |
| Log scan | Compared generated DB/browser passwords, connection URLs, signing key and token patterns against actual test-server logs | PASS — no matches |

The PostgreSQL test uses TEST_DATABASE_URL only, with TEST_DATABASE_DISPOSABLE=true.
Its random owned schema isolates migration rollback; application DEV data was never rolled back.
DEV/TEST roles cannot connect to each other's database through PUBLIC privileges.
The existing event-loop implementation was verified against psycopg/PostgreSQL without modification.

## Real browser evidence

Chromium from the preinstalled runtime executed the real application with no API or database mocks:

1. Unauthenticated dashboard navigation redirected to login.
2. An incorrect password produced HTTP 401 and the generic invalid-credentials message.
3. Correct login issued tokens, set the client cookie/storage and displayed the authenticated dashboard.
4. Reload preserved the authenticated session.
5. Replacing the access token with an invalid test value triggered successful server refresh and recovered the session.
6. Clicking the real Logout button produced HTTP 200, cleared cookie/storage and redirected to login.
7. Subsequent dashboard access again redirected to login.
8. Zero browser runtime errors and zero failed application asset responses.

Screenshots and structured results are in ignored data/local/task020-browser.
The built-in browser tool could not initialize because of a Windows sandbox helper error.
The fallback used bundled Playwright/Chromium through a local script; no package installation was needed.

Initial browser harness assertions did not account for the intentional redirect query parameter.
After matching URL pathname, the test exposed the real missing Logout handler.
The three-line production fix was rebuilt and the entire browser flow then passed.

## Persisted browser audit

A direct PostgreSQL query matched the successful browser login using its response correlation ID:

- Action: LOGIN
- Timestamp: 2026-09-08T20:56:12.601326+07:00
- User ID matches the PostgreSQL user and audit entity ID.
- Source: API
- Correlation ID: f4eb5ae8a4034afc9c1123e5fc94eb01
- Audit payload contains email/role, without password/token credentials.
- LOGOUT persisted after this login; zero active refresh sessions remained.
- The user's password is hashed and last_login_at persisted.

The integration suite independently checks the same fields and password verification.
Wrong-password and unknown-user responses are equally generic.
The current Phase 1 code does not persist an ordinary failed-login audit event, and the plan's gate requires
successful LOGIN persistence; no failed-login audit event is claimed.

## Acceptance criteria / Definition of Done

| Required gate criterion | Result |
|---|---|
| Native backend/frontend startup and health | PASS |
| Real PostgreSQL-backed user authentication/JWT | PASS |
| Real persisted LOGIN audit | PASS |
| PostgreSQL migration, rollback and re-apply | PASS |
| Browser authenticated flow and logout | PASS |
| Backend/frontend lint, typecheck, tests and build | PASS |
| Documentation/status reflect executed evidence | PASS |
| No critical failure or unresolved import; existing service/store boundaries reused | PASS |
| PAPER and disabled live trading retained | PASS |

**TASK-020 is complete; Phase 1 gate passes.**

## Known issues / technical debt (not Phase 1 blockers)

- /admin/users remains a documented planned API/source gap. The Phase 1 acceptance list requires login/audit,
  migration/rollback and checks; it does not require user-management CRUD. No admin endpoint work was added.
- Three existing Python dependency/fixture deprecation warnings remain.
- Backend dependency ranges are not a full reproducible lock.
- Access tokens expire normally after logout; refresh sessions are revoked, following existing architecture.
- The foundation dashboard is intentionally a shell; market/trading features belong to later phases.
- The existing login safety copy mentions real-market paper trades before those later features exist.
- Optional deployment paths and PostgreSQL 16 were not verified in this native PostgreSQL 18.6 run.

## Security / trading impact

No real secret was added to tracked/source/example files or printed in the report.
Project secrets and the generated verification account credentials are stored only in ignored local files.
No authentication bypass, privileged server configuration change, existing data deletion or live broker operation occurred.
TRADING_MODE=PAPER and LIVE_AUTO_TRADING=false remain in effect.

## Stop point

Temporary test API/frontend processes were stopped after verification. The user's original frontend process and native PostgreSQL service were preserved. Source-secret scan and plan-count consistency checks passed.

Phase 1 is complete. Independent review is next. Phase 2 was not started.
