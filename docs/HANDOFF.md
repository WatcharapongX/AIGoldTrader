# Rolling Agent Handoff — AIGoldTrader

## Session Result (2026-11-23 UAT deploy)
- `main` tip is `2c85669` (merge of PR #41 — UAT sign-off record). Tag `uat-2026-11-23` remains pinned at `397e955` (merge of PR #40; CI green backend/frontend/security).
- Sign-off: `docs/UAT_CHECKLIST.md` on `main` records owner approval for tag `uat-2026-11-23` @ `397e955`.
- **UAT deploy on this Windows host (`C:\AI Gold Trader`): DONE.** Working tree checked out detached at `uat-2026-11-23` (= `397e955`). PM2 restarted only `aigold-backend` (id1) and `aigold-frontend` (id0). `eform-dev` left untouched.
- Post-deploy smoke: `/healthz` ok with `trading_mode=PAPER`, `live_auto_trading=false`, `env=DEV`; `/readyz` ready (database true, redis disabled); frontend `:3001` HTTP 200.
- Note: `backend/.env` does not set `TRADING_MODE` / `LIVE_AUTO_TRADING` explicitly; app defaults + fail-closed validators enforce PAPER / false (confirmed via `/healthz`). Do not introduce LIVE flags.
- D2C commit `bc6716c` remains off `main` (on `origin/cursor/login-seed-ops-note-4b9d` / related tip). **Do NOT merge.** Independent verification gate still required. D3+ not authorized.
- Dependabot #14 (TypeScript 7) still open / frontend CI failed — leave or close via UI; do not merge.
- Docs HANDOFF refresh lives on branch `cursor/docs-handoff-uat-2026-11-23-a11f` (worktree `C:\AIGold-handoff-uat-2026-11-23`). UAT runtime tree stays on the tag.

## Branch and PR State
| Item | Ref | Status |
|---|---|---|
| Production line | `main` | `2c85669` (PR #41 merged); prefer for new docs/feature work |
| UAT tag | `uat-2026-11-23` | `397e955`; **deployed** on this host; do not move without new sign-off |
| Prior UAT tag | `uat-2026-11-20` | `7acbda6`; superseded |
| This HANDOFF PR branch | `cursor/docs-handoff-uat-2026-11-23-a11f` | open for merge into `main` |
| D2C risk-seam | `bc6716c` | NOT on `main`; gate pending |
| Dependabot open | #14 TypeScript 7.0.2 | frontend FAILED; do not merge |
| PR3 load smoke | `cursor/pr3-load-smoke-script` | PARKED; not authorized |

## Open Decisions and Known Issues
1. **D2C `bc6716c`**: independent verification gate required before any merge/cherry-pick. Touches Risk authority.
2. **#14 TypeScript 7**: major bump; frontend CI fails. Separate validated PR only if pursued later.
3. **Dev-only npm advisories**: deferred; production audit previously 0.
4. **Constraints maintenance**: `backend/constraints.txt` pins do not auto-update.
5. Optional: add explicit `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` to UAT `backend/.env` for operator clarity (defaults already safe).

## Local Clone / UAT Host State
- Runtime checkout: `C:\AI Gold Trader` → detached `uat-2026-11-23` @ `397e955` (PM2 cwd).
- Docs worktree: `C:\AIGold-handoff-uat-2026-11-23` → branch `cursor/docs-handoff-uat-2026-11-23-a11f` tracking `origin/main` tip for this HANDOFF commit only.
- PM2: `aigold-frontend` id0, `aigold-backend` id1, `eform-dev` id2 (do not touch eform).
- Restart pattern used: `pm2 restart aigold-backend aigold-frontend` after tag checkout. Full `setup-startup.ps1` not re-run (avoids registry churn).
- Preserve `stash@{0}` until user confirms drop. Local backup refs keep as before.

## Next Actions
1. Merge this HANDOFF refresh via compare URL (user merges).
2. Keep UAT host on tag `uat-2026-11-23` until next signed tag.
3. Independent verification gate for `bc6716c` before any D2C/Risk merge.
4. Do not start Batch C / D3+. Do not invent a separate production deploy.
5. Close or leave #14 intentionally via GitHub UI.

## Safety Invariants (unchanged)
- `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` must be preserved in every environment.
- AI remains advisory only. No `order_send`, OMS, or live position management.
- Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.

## Independent Verification Gate
- Closed D2C (PR #17, 2026-10-22) remains the last closed Risk/replay gate on `main`.
- No independent gate has run for `bc6716c`. Required before any D3+, any change to D2C/Risk authority, or any new UAT tag that includes that work.
