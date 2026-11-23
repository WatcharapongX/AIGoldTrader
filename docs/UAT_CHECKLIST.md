# UAT Readiness Checklist (PAPER-only)

Sign-off requires every box checked on the exact commit SHA being promoted.
Promotion artifact: a pinned tag `uat-YYYY-MM-DD` on `main` (see `docs/CURRENT_STATE.md`, Environment & Promotion Policy). The UAT server checks out only that tag.

## Safety
- [x] `TRADING_MODE=PAPER`, `LIVE_AUTO_TRADING=false` verified in target env
- [x] Startup rejects `TRADING_MODE=LIVE` / `LIVE_AUTO_TRADING=true` (fail-closed test)
- [x] No `order_send` in codebase (architecture tests green)
- [x] Kill Switch activate/clear exercised in `/risk` with reason audit

## Quality gates
- [x] GitHub CI green (backend, frontend, security jobs) on promotion SHA
- [x] Independent verification PASS recorded for the active Batch D gate
- [x] Coverage artifact reviewed; no regression vs previous promotion
- [x] PostgreSQL integration suite executed (not skipped) against disposable DB

## Data & recovery
- [x] Backup produced by `scripts/backup-postgres.ps1` and SHA-256 verified
- [x] Restore drill completed on disposable DB within RTO 4h (RPO 24h)
- [x] `alembic check` clean (models == migration head) on restored DB

## Observability & ops
- [x] `/healthz`, `/readyz`, `/metrics` reachable; alert routed to operator
- [x] Structured logs shipped/retained per operator policy
- [x] Secrets injected via env/secret manager; none in repo or images
- [x] DB/Redis ports not published publicly (loopback or private network only)

## Explicitly out of scope for UAT sign-off
Paper execution, OMS, broker routing, and live trading require a separate
governance authorization and are NOT approved by this checklist.

## Sign-off Record
- Promotion SHA: 397e955490403efcf1df30dd1da0b55760672874 (main tip; merge of PR #40)
- Tag: uat-2026-11-23 (annotated; points at the SHA above)
- Date: 2026-11-23
- Signed by: owner (confirmed in chat; NEW UAT checklist sign-off approved)
- Basis: prior UAT (`uat-2026-11-20` @ `7acbda6`) plus CI green on this tip; Dependabot/constraints landed on `main` since previous tag; D2C `bc6716c` NOT included
- CI on SHA: backend, frontend, and security all success
