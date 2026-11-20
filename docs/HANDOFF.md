# Rolling Agent Handoff — AIGoldTrader

## Session Result (2026-11-20)
- `main` tip is `77b33a6` (merge of PR #28). It includes: migration head 0017 test expectations (PR #27, `0d82f15`), rate-limit test isolation (`23348b8`), AI budget-code assertions (`235d97f`), fixture provider reads flat `strategy_direction` (`41202a4`, fixture mode only), and UTF-8 pin in `test_native_dev.py`.
- Backend CI on `main` at `77b33a6` is still **FAILED**. Frontend and security are green. The job log is not reachable without auth, so the exact failing test is not confirmed. The most likely cause is the timing flake in `tests/test_forex_factory.py::test_slow_calendar_does_not_pause_market_quote_collection`, which failed in the local full-suite run. A fix is on its own branch (below).
- D2C reconciled to **CLOSED** in `CURRENT_STATE.md`, `CURRENT_BATCH.md`, and `SYSTEM_CAPABILITIES.yaml`. Evidence: PR #17 merged (`84203b4`) with independent re-verification PASS on 2026-10-22 (350 tests); PR #18 merged (`fe324c8`).
- D3–D7 remain NOT AUTHORIZED in the docs. See Open Decisions.
- No broker, OMS, live execution, or `order_send` was added. `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` are unchanged.

## Branch and PR State
| Item | Ref | Status |
|---|---|---|
| Production line | `main` | `77b33a6`; CI backend red (frontend, security green) |
| Forex test timing fix | `cursor/fix-forex-calendar-test-timing-2026-11-20` | `459820f`; PR to open |
| Docs: D2C closure + this handoff | `cursor/docs-d2c-handoff-2026-11-20` | PR to open |
| PR #17 D2C forged-event guard | `cursor/pr1-d2c-forged-event-guard` | merged `84203b4` |
| PR #18 D6 runs panel | `cursor/pr2-d6-backtest-runs-panel` | merged `fe324c8` |
| PR #21 env policy docs | `cursor/docs-env-policy-2026-11-19` | merged `f0f0ba7` |
| PR #22–#28 CI and test fixes | various `cursor/*` | merged (#28 = `77b33a6`) |
| PR3 load smoke | `cursor/pr3-load-smoke-script` (`17c47b6`) | PARKED; D7 NOT AUTHORIZED |
| Login seed ops note | `cursor/login-seed-ops-note-4b9d` | remote-only; not reviewed |
| Dependabot | `dependabot/*` | open on GitHub; not reviewed |

## Verification Evidence
- Local `ruff check app tests`: PASS.
- Local full `pytest tests` before the forex fix: 1 failure (the forex flake). It passes when run alone and passed 3/3 consecutive runs after the fix.
- Not verified: a green Linux CI run on `main` after `77b33a6`. Local runs are Windows with PostgreSQL 18; CI is Ubuntu with PostgreSQL 16.
- Frontend lint, typecheck, and tests were NOT run locally (see Local Clone State).

## Open Decisions (owner)
1. **D3–D7 conflict.** `docs/CURRENT_BATCH.md` line 9 states the owner authorized continuation to D3–D7 on 2026-10-22. `docs/CURRENT_STATE.md` states D3–D7 are NOT AUTHORIZED, and PR #17 says D3–D7 authorization is unchanged. Docs stay at NOT AUTHORIZED until the owner decides which is correct.
2. **Rate limiter.** The production API limiter (`rate_limit_api_per_minute`, default 120/min per IP) was NOT changed. Only test-scoped overrides were added.
3. **Fixture direction change.** `41202a4` changes default fixture-mode output: a SHORT trade-thesis input now yields SHORT (previously always LONG). Advisory only; no execution path affected.

## Local Clone State (Windows dev server)
- Repo: `C:\AI Gold Trader`. Local `main` is fast-forwarded to `origin/main` (`77b33a6`).
- Backup refs (local only, not pushed; keep until confirmed on GitHub):
  - `refs/backup/main-pre-reconcile-2026-11-19` -> `4bea348`
  - `refs/backup/main-pre-clean-2026-11-19`
- `frontend/node_modules` is broken locally (`eslint` not recognized; earlier `hermes-parser` error). A reinstall needs the pm2-managed frontend server on port 3001 (`next start -p 3001`, `C:\AI Gold Trader\frontend`) stopped first. Do not kill it without owner approval. A `next dev` process from another project (`C:\E-Form\next-eform`, port 3000) is also running and must not be touched.

## Next Actions
1. Open the PR for `cursor/fix-forex-calendar-test-timing-2026-11-20`; confirm backend CI is green on its head.
2. Open the PR for `cursor/docs-d2c-handoff-2026-11-20`; merge after review.
3. Confirm backend CI on `main` is green after both merges (check-runs API for the new head SHA).
4. Only after CI on `main` is green AND the UAT checklist is signed off on that SHA: create the first tag `uat-YYYY-MM-DD` on `main`.
5. UAT server: fresh clone of `origin/main`, checkout the pinned tag only, own `.env` with `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false`. Do not copy the dev `.env`.
6. Owner: resolve the D3–D7 conflict (Open Decision 1).
7. Owner: approve stopping the frontend pm2 service so `node_modules` can be rebuilt, then run frontend lint, typecheck, and tests locally.
8. Optional: review Dependabot PRs and `cursor/login-seed-ops-note-4b9d`; clean up merged remote branches.

## Safety Invariants (unchanged)
- `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` must be preserved in every environment.
- AI remains advisory only. No `order_send`, OMS, or live position management.
- Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.

## Independent Verification Gate
- D2C: independently verified and closed 2026-10-22 (PR #17, 350 tests, Ruff clean).
- This session ran no new independent gate. One is required before any D3+ work, before any change to D2C or Risk authority, and before the first UAT tag.
