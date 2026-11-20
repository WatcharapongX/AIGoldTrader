# Rolling Agent Handoff — AIGoldTrader

## Session Result (2026-11-20)
- `main` tip is `1f7218f` (merge of PR #31). It includes: migration head 0017 test expectations (PR #27), rate-limit test isolation (`23348b8`), AI budget-code assertions (`235d97f`), the forex calendar test timing fix (PR #29, `459820f`), and D2C/D3–D7 docs (PRs #30, #31).
- **Correction:** the fixture direction fix (`41202a4`) and the UTF-8 pin in `test_native_dev.py` were pushed AFTER PR #28 merged, so they are NOT on `main`. They are re-applied as `839aa3c` on `cursor/fix-fixture-direction-and-encoding-2026-11-20`.
- Backend CI on `1f7218f` **FAILED** (frontend and security passed). Local full-suite run on `1f7218f` reproduced exactly two deterministic failures, both fixed by `839aa3c`:
  - `tests/test_ai_corrective_round2.py::test_canonical_json_pipeline_fixture_direction_and_synthetic_refs`
  - `tests/test_native_dev.py::test_postgresql_offline_migration_handles_percent_encoded_password`
- Full-suite run on `839aa3c` (local): one further failure, `tests/integration/test_market_live.py::test_live_market_database_websocket_stale_and_recovery` (`assert 2 > 2` at line 106: the first websocket update's sequence equals the snapshot's). It PASSES when run alone. Not yet diagnosed; see Open Decisions.
- D2C closed in `CURRENT_STATE.md`, `CURRENT_BATCH.md`, `SYSTEM_CAPABILITIES.yaml`. Evidence: PR #17 merged (`84203b4`) with independent re-verification PASS on 2026-10-22 (350 tests); PR #18 merged (`fe324c8`).
- D3–D7 NOT AUTHORIZED (owner decision 2026-11-20). `CURRENT_BATCH.md` line 9 corrected to match.
- Frontend `node_modules` reinstalled with `npm ci`. Lint, typecheck, 290 unit tests, and production build PASS locally. The pm2 service `aigold-frontend` was stopped for the reinstall and restarted; `http://localhost:3001/` returns 200.
- No broker, OMS, live execution, or `order_send` was added. `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` are unchanged.

## Branch and PR State
| Item | Ref | Status |
|---|---|---|
| Production line | `main` | `1f7218f`; backend CI RED (two deterministic failures, fixed on `839aa3c`) |
| Fixture direction + UTF-8 pin | `cursor/fix-fixture-direction-and-encoding-2026-11-20` | `839aa3c` (+ HANDOFF commit); PR to open |
| PR #17 D2C forged-event guard | `cursor/pr1-d2c-forged-event-guard` | merged `84203b4` |
| PR #18 D6 runs panel | `cursor/pr2-d6-backtest-runs-panel` | merged `fe324c8` |
| PR #21 env policy docs | `cursor/docs-env-policy-2026-11-19` | merged `f0f0ba7` |
| PR #22–#31 CI, test, and docs fixes | various `cursor/*` | merged |
| `cursor/fix-ai-corrective-test-expectations-2026-11-19` | `41202a4` | NOT merged; its commit is re-applied as `839aa3c` |
| PR3 load smoke | `cursor/pr3-load-smoke-script` (`17c47b6`) | PARKED; D7 NOT AUTHORIZED |
| Login seed ops note | `cursor/login-seed-ops-note-4b9d` | remote-only; not reviewed |
| Dependabot | `dependabot/*` (e.g. PR #20, python 3.12 → 3.15) | open; not reviewed |

## Verification Evidence
- Local `ruff check app tests`: PASS (on `839aa3c`).
- Local full `pytest tests` on `839aa3c`: one failure (`test_market_live` websocket race); passes alone.
- Frontend (local, 2026-11-20): `npm run lint` PASS, `npm run typecheck` PASS, `npm test` 290/290 PASS, `npm run build` PASS.
- Not verified: a green Ubuntu/PostgreSQL 16 CI run. Local runs are Windows with PostgreSQL 18.
- CI job logs are not reachable by the agent (GitHub API returns 403 for `actions/jobs/{id}/logs`); failing tests are inferred from local reproduction.

## Open Decisions and Known Issues
1. **`test_market_live` websocket race.** Failing assertion: `assert update.sequence > snapshot.sequence` (line 106). Options: (a) investigate the market-data websocket sequencing in `app/` for a real ordering race; (b) make the test loop until an update with a higher sequence arrives. Not decided.
2. **Frontend npm audit.** `npm ci` reported 12 vulnerabilities (7 moderate, 4 high, 1 critical). Not triaged; needs a separate PR.
3. **Rate limiter.** The production API limiter (`rate_limit_api_per_minute`, default 120/min per IP) was NOT changed. Only test-scoped overrides were added.
4. **Fixture direction change.** `839aa3c` changes default fixture-mode output: a SHORT trade-thesis input now yields SHORT (previously always LONG). Advisory only; no execution path affected.
5. **Unrelated pm2 processes.** `aigold-backend` (pm2 id 1) and `eform-dev` (pm2 id 2, from `C:\E-Form\next-eform`) were not touched.

## Local Clone State (Windows dev server)
- Repo: `C:\AI Gold Trader`. Working branch: `cursor/fix-fixture-direction-and-encoding-2026-11-20` until merged.
- Backup refs (local only, not pushed; keep until confirmed on GitHub):
  - `refs/backup/main-pre-reconcile-2026-11-19` -> `4bea348`
  - `refs/backup/main-pre-clean-2026-11-19`

## Next Actions
1. Merge the PR for `cursor/fix-fixture-direction-and-encoding-2026-11-20`.
2. Resolve Open Decision 1 (`test_market_live` race) before expecting a green backend CI run.
3. Confirm backend CI on `main` is green after the merges (check-runs API for the new head SHA).
4. Only after CI on `main` is green AND the UAT checklist is signed off on that SHA: create the first tag `uat-YYYY-MM-DD` on `main`.
5. UAT server: fresh clone of `origin/main`, checkout the pinned tag only, own `.env` with `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false`. Do not copy the dev `.env`.
6. Triage the frontend npm audit (Open Decision 2) in a separate PR.
7. Optional: review Dependabot PRs and `cursor/login-seed-ops-note-4b9d`; clean up merged remote branches.

## Safety Invariants (unchanged)
- `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` must be preserved in every environment.
- AI remains advisory only. No `order_send`, OMS, or live position management.
- Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.

## Independent Verification Gate
- D2C: independently verified and closed 2026-10-22 (PR #17, 350 tests, Ruff clean).
- This session ran no new independent gate. One is required before any D3+ work, before any change to D2C or Risk authority, and before the first UAT tag.
