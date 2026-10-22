# Security Policy

## Safety invariants (non-negotiable)

- `TRADING_MODE=PAPER` only. `TRADING_MODE=LIVE` and `LIVE_AUTO_TRADING=true` are
  rejected at startup (fail-closed, `backend/app/core/config.py`).
- No broker execution exists in this codebase (`order_send` is absent and is
  guarded by architecture tests). AI is advisory only.
- Authority: Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human.

## Reporting a vulnerability

Report privately to the repository owner. Do not open a public issue for
exploitable findings. Include reproduction steps and affected commit SHA.

## Operations runbook (summary)

- Secrets: only via environment / secret manager. `SECRET_KEY` >= 32 bytes,
  never committed. Rotate JWT secret by deploying a new `SECRET_KEY` (all
  sessions invalidate; users re-login).
- Backups: run `scripts/backup-postgres.ps1` on a schedule; verify the
  `.sha256` sidecar. Restore drill (quarterly, disposable DB only):
  `pg_restore --clean --no-owner -d <disposable_db> <backup>.dump`, then run
  `alembic check` and the readiness endpoint against the restored copy.
  Targets: RPO 24h (daily backup), RTO 4h (documented manual restore).
- Incident response: activate the Kill Switch from `/risk`, preserve logs
  (structured JSON with correlation IDs), rotate affected credentials,
  and record the incident in `docs/HANDOFF.md`.
- Dependency hygiene: Dependabot + CI (`pip-audit`, gitleaks) must be green
  before release. Never merge a Dependabot major bump without CI passing.
