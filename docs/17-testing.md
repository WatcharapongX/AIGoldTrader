# 17 — Testing

Phase 1, updated 2026-09-08. Evidence: [phase-1-gate.md](phase-1-gate.md).
All default checks run on native Windows without Docker, WSL, PostgreSQL or Redis services.

## Database-independent checks

From backend:

~~~powershell
.\.venv\Scripts\python.exe -m compileall -q app alembic
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy app
.\.venv\Scripts\python.exe -m pytest -m "not integration"
.\.venv\Scripts\python.exe -m pip wheel . --no-deps --wheel-dir dist
~~~

From frontend:

~~~powershell
npm.cmd run build
npm.cmd run typecheck
npm.cmd run lint
npm.cmd test
~~~

Backend unit/API tests use isolated SQLite and fakeredis; they do not prove PostgreSQL/Redis service integration.
Coverage includes JWT login/rotation/logout, audit masking/persistence, validation errors,
Alembic up/down/up on temporary SQLite, PostgreSQL offline DDL with escaped passwords,
DATABASE_URL/legacy configuration, missing config, disabled Redis with no connection attempts,
database failure readiness and native Windows loop selection.
Frontend's six tests use Node's test runner and mocked browser/fetch state; they are not component/browser E2E tests.

## Explicit PostgreSQL integration

Use a disposable test database on a native PostgreSQL service. Set TEST_DATABASE_URL privately in the test
process environment or ignored backend/.env, with the same URL format as DATABASE_URL. Process environment takes precedence. The suite never selects the application
DATABASE_URL as its test target. Set TEST_DATABASE_DISPOSABLE=true only for a dedicated test database.

~~~powershell
$env:TEST_DATABASE_DISPOSABLE = "true"
# TEST_DATABASE_URL must already be configured privately in this process.
.\.venv\Scripts\python.exe -m pytest -m integration -rs
~~~

The test creates a unique phase1_gate_<uuid> schema, restricts migration search_path to it,
runs upgrade → downgrade → upgrade, verifies six tables, seeds a test user and exercises real
PostgreSQL-backed API login/me/refresh/logout plus the LOGIN audit record.
It drops only that schema in a finally block; no existing schemas or application tables are dropped.
A forced process termination can leave an isolated test schema for manual review.
These are API integration tests; a browser login still needs separate evidence.

No TEST_DATABASE_URL in either supported configuration source: **NOT RUN — BLOCKED BY LOCAL POSTGRESQL** (pytest reports a skip).
Missing disposable-target opt-in: **NOT RUN**.
Configured but unreachable/broken target: **FAIL**, not an automatic pass or fallback to SQLite.
Plain pytest runs unit/API tests and shows the integration skip explicitly.

## Phase 1 acceptance checks (passed on native PostgreSQL 18.6)

With native PostgreSQL configured:

1. Run the isolated integration test above.
2. Run migration/seed against your development DB, start API and frontend via [18-devops.md](18-devops.md).
3. Log in through the browser; verify dashboard, assets, reload/session recovery and logout.
4. Verify the actual LOGIN audit record and record the evidence before checking TASK-020.

A real Redis service and Compose smoke are optional for the native Phase 1 gate.
Do not report HTTP-only checks, SQLite, fakeredis, skipped tests or offline DDL as real database/browser integration.

## Browser regression

The existing bundled Playwright/Chromium runtime is used; no frontend dependency was added.
From frontend, set the following process variables to your installed runtime and ignored verification data:

~~~powershell
$env:PLAYWRIGHT_MODULE = 'C:\Users\watch\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\node_modules\playwright'
$env:E2E_BASE_URL = 'http://localhost:3001'
$env:E2E_CREDENTIALS_PATH = 'C:\AI Gold Trader\data\local\task020-browser\credentials.json'
$env:E2E_OUTPUT_DIR = 'C:\AI Gold Trader\data\local\task020-browser'
node tests/e2e/native-login.cjs
~~~

Start the native API on 8000 with CORS permitting the frontend origin, and the built frontend on the selected
port before executing the browser script. The production verification used standalone output with its static/public
assets copied into the standalone directory. An existing frontend on 3000 was preserved.
The script uses the real UI controls and backend; it does not mock login or invoke the auth store to bypass the UI.
It covers wrong password, authenticated shell, reload, server token refresh, logout and protected-route recovery.
Gate result: PASS, zero browser runtime errors and failed asset responses.

Final backend command python -m pytest --show-capture=no --tb=short: 36 passed, no skips.
Final frontend unit suite: 6 passed. Full evidence: [phase-1-gate.md](phase-1-gate.md).
