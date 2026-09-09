# 18 — Development operations

Phase 1, updated 2026-09-08. Native Windows is the primary local development path.
Docker, Docker Desktop, WSL, TimescaleDB and Redis services are not prerequisites for Phase 1.

## Native Windows prerequisites

- Python 3.12+ and Node.js/npm (use npm.cmd in PowerShell).
- PostgreSQL native Windows service for persisted login, audit and database integration.
- Configure your own database, restricted application role and connection settings; no database is created or erased automatically.
- Current host: Python/Node available; native PostgreSQL 18.6 service is running and separate DEV/TEST databases are configured. The complete Phase 1 gate passed on this version.

## Existing configured host

The user authorized project database provisioning through scripts/setup_native_postgres.py.
Backend/.env already contains separate DEV/TEST URLs, explicit test opt-in and a generated signing key.
Do not overwrite it or re-run initial provisioning on this configured host.
The installation/admin password is not stored. The generated browser verification account is kept in the
ignored data/local/task020-browser/credentials.json file; do not commit or share it.

On another unconfigured native host, after installing the backend dependencies, the optional helper can be run
from backend using:

~~~powershell
.\.venv\Scripts\python.exe scripts/setup_native_postgres.py
~~~

It prompts for the existing PostgreSQL installation password without echoing it, creates new randomly named
DEV/TEST databases and restricted roles, and writes backend/.env. It refuses to overwrite an existing .env.
It does not install PostgreSQL, modify services/authentication rules, reset existing passwords or drop existing data.

## Backend setup

Run from the repository root. Preserve any existing .env rather than overwriting it.

~~~powershell
Set-Location backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
if (-not (Test-Path .env)) { Copy-Item ..\.env.example .env }
~~~

Edit backend/.env locally:

- SECRET_KEY: a private random value of at least 32 bytes. Empty/example keys are rejected at API startup.
- DATABASE_URL: postgresql+psycopg://USER:ENCODED_PASSWORD@HOST:PORT/DATABASE.
  Replace every placeholder, include the port and percent-encode special characters in the password.
  Plain postgresql:// is normalized to the installed psycopg driver.
- REDIS_ENABLED=false, TRADING_MODE=PAPER, LIVE_AUTO_TRADING=false.
- Optional legacy POSTGRES_* fields require all five values. Do not uncomment blank fields.
  DATABASE_URL_OVERRIDE is reserved for isolated unit tests; do not put it in development configuration.

Settings reads .env in the process working directory. Backend commands below run from backend.
A root .env is for optional Compose only. Never copy backend secrets into frontend environment files.

When your native PostgreSQL service and configured application database are ready:

~~~powershell
Get-Service *postgres*
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.db.seed
.\.venv\Scripts\python.exe -m uvicorn app.main:app --no-proxy-headers --host 127.0.0.1 --port 8000 --reload --loop app.core.event_loop:new_event_loop
~~~

Use the hidden password prompt for seeding; avoid --admin-password because command lines can be observed.
Seeding an existing user does not reset its password. The existing bootstrap also seeds XAUUSD metadata.

The same Uvicorn command works without --reload. Keep the explicit loop option on Windows.
Migration and seed commands select the compatible loop internally. Psycopg requires a
[Selector event loop on Windows](https://www.psycopg.org/psycopg3/docs/advanced/async.html).
The custom Uvicorn loop option requires 0.36+ and is declared in pyproject.toml;
see [Uvicorn release notes](https://www.uvicorn.org/release-notes/).
Tested here with Uvicorn 0.52.4 and psycopg 3.3.5.

Without PostgreSQL, skip migration/seed and still run the API with a valid SECRET_KEY.
/healthz returns 200; /readyz returns 503 until the database is available. Auth persistence requires PostgreSQL.
Run all database-independent tests as described in [17-testing.md](17-testing.md).

## Frontend in a second PowerShell terminal

~~~powershell
Set-Location "C:\AI Gold Trader\frontend"
npm.cmd ci
npm.cmd run dev
~~~

Open http://localhost:3000/login. The default API URL is http://localhost:8000/api.
For a different address, set NEXT_PUBLIC_API_URL and NEXT_PUBLIC_WS_URL in frontend/.env.local.
Only browser-safe public URLs belong there. Public environment values are baked into the production build.

~~~powershell
Invoke-RestMethod http://localhost:8000/healthz
Invoke-RestMethod http://localhost:8000/readyz
~~~

/api/healthz and /api/readyz remain aliases. Redis disabled is represented by
redis_enabled: false and checks.redis: null, not a successful Redis check.
Enabled Redis reports true/false; database readiness remains mandatory.

## Redis boundary

Phase 1 auth/session/audit use PostgreSQL; rate limiting is already in process.
There are no running distributed workers, shared state or order-lock consumers in this phase.
Redis is therefore deferred by default. Existing cache/publish helpers remain the adapter boundary:
disabled reads return a cache miss; writes/publications return false (no delivery claimed).
Explicit pub/sub subscriptions require enabling Redis. No local substitute is used for a future trading lock.
Re-evaluate distributed requirements when the relevant future phase starts.

## Optional Docker deployment

Keep the existing Compose files as an optional deployment route. Copy the template to root .env
and set SECRET_KEY, POSTGRES_USER, POSTGRES_DB, POSTGRES_PASSWORD.
Compose supplies its service host/port and explicitly enables its Redis adapter.

~~~powershell
docker compose config --quiet
docker compose up --build -d
docker compose exec backend python -m app.db.seed
# Optional development mounts/reload:
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
~~~

Compose-only builds/service smoke checks are optional and do not block native development.
The frontend image copies standalone/static/public assets and runs as a non-root user.
Backend migrations run before its single-replica development server.
Do not run rollback or remove volumes against application data. Use only the isolated integration test for rollback evidence.

## Phase 1.1 configuration and proxy boundary

The native and optional Docker launch commands now explicitly disable Uvicorn proxy-header rewriting with
--no-proxy-headers. This flag is required in both direct and trusted-proxy application modes: the application
must receive the actual transport peer to enforce its own allow-list. Do not combine this resolver with another
ASGI/server middleware that rewrites request.client first.

New defaults in .env.example (existing private backend/.env need not be rewritten):

~~~dotenv
TRUST_PROXY=false
TRUSTED_PROXY_CIDRS=
RATE_LIMIT_AUTH_PER_MINUTE=10
RATE_LIMIT_MAX_KEYS=10000
~~~

For a controlled proxy deployment, set TRUST_PROXY=true and TRUSTED_PROXY_CIDRS to a comma-separated list of
only the actual proxy IPs/networks. Network validation rejects '*' and IPv4/IPv6 default routes. Keep the backend
network restricted to the intended path and configure the proxy to overwrite/append XFF correctly.
Do not enable proxy trust merely because an incoming request contains forwarded headers.

Login limits use independent client and normalized-account budgets, each at the configured per-minute rate.
Entries expire after 60 seconds and are bounded; at capacity new identities receive 429 until capacity expires.
Use one process/instance for this phase's protection; restarting resets local state. Redis remains optional.

SQL parameter hiding and safe exception summaries apply to JSON and console logs. Never enable SQL echo/debug
logging or manually log request bodies/exception strings to troubleshoot authentication. Use correlation ID,
error type, operation, route template and safe stack locations. No private configuration values were printed
or added to source by this hardening work.


## Phase 2 local market feed (2026-09-09)

Apply the new additive migration with python -m alembic upgrade head and verify alembic check.
Set MARKET_DATA_PROVIDER=simulated; retain PAPER, LIVE_AUTO_TRADING=false and Redis optional.
Existing native Uvicorn launch options, including --no-proxy-headers, remain required.
One DEV application instance owns the lazy replay worker; avoid multiple workers on the same dataset.
The native app uses PostgreSQL without requiring TimescaleDB, Docker or WSL. See docs/06-market-data.md.
Stop a running Next standalone process before rebuilding on Windows: it can lock .next/standalone.
Keep tokens and provider credentials out of URLs/logs. Add local frontend origins explicitly to CORS.
