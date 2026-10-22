# UAT Readiness Checklist (PAPER-only)

Sign-off requires every box checked on the exact commit SHA being promoted.

## Safety
- [ ] `TRADING_MODE=PAPER`, `LIVE_AUTO_TRADING=false` verified in target env
- [ ] Startup rejects `TRADING_MODE=LIVE` / `LIVE_AUTO_TRADING=true` (fail-closed test)
- [ ] No `order_send` in codebase (architecture tests green)
- [ ] Kill Switch activate/clear exercised in `/risk` with reason audit

## Quality gates
- [ ] GitHub CI green (backend, frontend, security jobs) on promotion SHA
- [ ] Independent verification PASS recorded for the active Batch D gate
- [ ] Coverage artifact reviewed; no regression vs previous promotion
- [ ] PostgreSQL integration suite executed (not skipped) against disposable DB

## Data & recovery
- [ ] Backup produced by `scripts/backup-postgres.ps1` and SHA-256 verified
- [ ] Restore drill completed on disposable DB within RTO 4h (RPO 24h)
- [ ] `alembic check` clean (models == migration head) on restored DB

## Observability & ops
- [ ] `/healthz`, `/readyz`, `/metrics` reachable; alert routed to operator
- [ ] Structured logs shipped/retained per operator policy
- [ ] Secrets injected via env/secret manager; none in repo or images
- [ ] DB/Redis ports not published publicly (loopback or private network only)

## Explicitly out of scope for UAT sign-off
Paper execution, OMS, broker routing, and live trading require a separate
governance authorization and are NOT approved by this checklist.
