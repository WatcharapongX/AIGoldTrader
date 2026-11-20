# Rolling Agent Handoff — AIGoldTrader

## Session Result (2026-11-20 cleanup)
- `main` tip is `e0ed3d3` (merge of Dependabot #20). Backend, frontend, and security CI are GREEN on that SHA.
- UAT: tag `uat-2026-11-20` points at `7acbda6` (signed SHA, CI green). Sign-off record is on `main` in `docs/UAT_CHECKLIST.md` (PR #38).
- Constraints PR #39 is on `main` (backend `constraints.txt`; CI uses `pip install -e ".[dev]" -c constraints.txt`).
- Dependabot merged to `main` this wave: #1–#13, #15, #19, #20. Do not re-open those.
- Dependabot still open: **#14 TypeScript 7.0.2** — frontend CI FAILED. Do NOT merge. Close via GitHub UI with reason: major TypeScript bump; frontend CI fails; needs separate validated PR.
- D2C commit `bc6716c` remains on `origin/cursor/login-seed-ops-note-4b9d` only. Not in `main`. Tests passed earlier; **independent verification gate still required**. Do NOT merge or cherry-pick.
- GitHub connector `plugin-github-github` is broken (mcp_auth). `gh` CLI unavailable here. Push via `git` works; cannot merge/close PRs via API without auth. Do not extract credentials.
- Leftover Dependabot worktrees removed this session (`C:\pr2-setup-python`, `C:\pr7-setup-node`, `C:\pr10-pytest-asyncio`, `C:\pr12-pytest`). Local tracking branches for those four deleted. `git worktree list` is clean (main checkout only).
- `stash@{0}` preserved: local `docs/UAT_CHECKLIST.md` edits from `cursor/uat-signoff-2026-11-20`. Do not drop until user confirms.

## Branch and PR State
| Item | Ref | Status |
|---|---|---|
| Production line | `main` | `e0ed3d3`; CI GREEN |
| UAT tag | `uat-2026-11-20` | `7acbda6`; do not move without a new sign-off |
| Dependabot open | #14 TypeScript 7.0.2 | frontend FAILED; leave open or close via UI |
| `cursor/login-seed-ops-note-4b9d` | tip includes `bc6716c` | NOT merged; D2C gate pending |
| `stash@{0}` | UAT checklist local edits | Keep until user confirms drop |
| PR3 load smoke | `cursor/pr3-load-smoke-script` | PARKED; not authorized |

## Open Decisions and Known Issues
1. **D2C risk-seam `bc6716c`**: independent verification gate required before any merge. Touches Risk authority. No merge / no cherry-pick until gate passes.
2. **#14 TypeScript 7**: major bump; frontend CI fails. Separate validated PR only if pursued later.
3. **Dev-only npm advisories (9)**: `@typescript-eslint/*`, `typescript-eslint`, `minimatch`, `brace-expansion` (high), `zod` (high). Production audit is 0. Deferred.
4. **Constraints maintenance.** Pins in `backend/constraints.txt` do not auto-update. Bump pins deliberately before relying on newer pip versions in CI.
5. **Rate limiter.** Production API limiter (default 120/min per IP) unchanged. Test-only overrides exist.

## Local Clone State (Windows dev server)
- Repo: `C:\AI Gold Trader`. Prefer `main` at `e0ed3d3` for new work after this docs PR lands.
- Do not commit dirty `docs/UAT_CHECKLIST.md` if present; it must stay aligned with the signed-off record on `main`.
- Local backup refs (keep): `refs/backup/main-pre-reconcile-2026-11-19`, `refs/backup/main-pre-clean-2026-11-19`.
- `backend/.venv` should track CI pins (pydantic / FastAPI via constraints).

## Next Actions
1. Open PR from compare link for this HANDOFF refresh; merge when ready.
2. Close #14 in the GitHub UI (or leave open intentionally) — agent cannot close without auth.
3. Run independent verification gate for `bc6716c` before any D2C / Risk merge.
4. Keep `stash@{0}` until user confirms it is obsolete, then drop.
5. Do not create a new UAT tag without a new sign-off on the then-current `main` SHA.
6. Do not start Batch C / D3+.

## Safety Invariants (unchanged)
- `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` must be preserved in every environment.
- AI remains advisory only. No `order_send`, OMS, or live position management.
- Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.

## Independent Verification Gate
- D2C: independently verified and closed 2026-10-22 (PR #17, 350 tests).
- No independent gate has run for `bc6716c`. One is required before any D3+ work, any change to D2C or Risk authority, and before any further UAT tag.
