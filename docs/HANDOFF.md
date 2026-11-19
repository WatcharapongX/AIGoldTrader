# Rolling Agent Handoff — AIGoldTrader

## Session Result (2026-11-19)
- Chose **Environment & Promotion Policy A**: `main` is the only long-lived branch; UAT is an environment pinned to a tag `uat-YYYY-MM-DD` (or SHA) on `main`. No `uat` branch. See `docs/CURRENT_STATE.md`.
- `docs/UAT_CHECKLIST.md` updated with the promotion artifact rule (pinned tag on `main`).
- Local `main` reconciled with `origin/main`: the previous local-only commits (squash-duplicates of #17/#18 plus `load-smoke.py`) were removed from the new `main` history and preserved in backup refs (see Local Clone State).
- `scripts/load-smoke.py` (commit `4f2eed1`, D7 perf) moved out of `main` to `cursor/pr3-load-smoke-script`. D7 is NOT AUTHORIZED; the script is not part of `main`.
- No application/trading source changed. No broker, OMS, live execution, or `order_send` added.

## Branch and PR State
| Item | Branch / Ref | Status |
|---|---|---|
| Production line | `main` | Tip is the docs-policy commit on top of `origin/main` (`fe324c8`). |
| PR3 (load smoke) | `cursor/pr3-load-smoke-script` | Pushed; commit `17c47b6` (cherry-pick of `4f2eed1`). PR not opened yet. |
| #17 D2C forged-event guard | `cursor/pr1-d2c-forged-event-guard` | `origin/main` contains commit titled `(#17)`; verify merge state on GitHub. |
| #18 D6 runs panel | `cursor/pr2-d6-backtest-runs-panel` | `origin/main` contains commit titled `(#18)`; verify merge state on GitHub. |
| Login seed ops note | `cursor/login-seed-ops-note-4b9d` | Remote-only; not reviewed in this session. |
| Dependabot branches | `dependabot/*` | Open on GitHub; not reviewed in this session. |

## Local Clone State (Windows dev server)
- Backup refs (local only, not pushed):
  - `refs/backup/main-pre-reconcile-2026-11-19` -> `4bea348` (old local `main` before reconcile)
  - `refs/backup/main-pre-clean-2026-11-19` -> old local `main` tip before the clean rebuild (includes merge `6b0f661` and removal `4eaa752`)
- Do not delete these backup refs until the content is confirmed on GitHub.

## Independent Test Evidence
- Last independently verified evidence is from D2C closure (`bc6716c`): 350 focused tests passed, Ruff clean, adversarial matrix passed.
- This session ran no new test suite (docs-only change plus one script removal).

## Next Actions
1. Open PR for `cursor/pr3-load-smoke-script` only when D7 is authorized; otherwise keep as a parked branch.
2. Verify on GitHub that #17 and #18 are merged, then reconcile `docs/CURRENT_STATE.md`, `docs/CURRENT_BATCH.md`, and `docs/SYSTEM_CAPABILITIES.yaml` to mark D2C CLOSED on `main` (only after the merge is confirmed).
3. Confirm GitHub CI is green on the new `main` tip before any UAT promotion.
4. Set up the UAT server: fresh clone from `origin/main`, checkout the pinned tag only, and create its own `.env` (keep `TRADING_MODE=PAPER`, `LIVE_AUTO_TRADING=false`). Do not copy the dev `.env`.
5. Create the first UAT tag only after the UAT checklist is signed off on that SHA.

## Safety Invariants (unchanged)
- `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` must be preserved in every environment.
- AI remains advisory only. No `order_send`, OMS, or live position management.
- Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.

## Independent Verification Gate
- Not required for this session (docs and git-hygiene changes only).
- Required again before D7 work or any reopening of D2C.
