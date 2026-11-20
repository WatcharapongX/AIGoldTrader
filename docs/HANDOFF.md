# Rolling Agent Handoff — AIGoldTrader

## Session Result (2026-11-20)
- `main` tip is `bcc9b67` (merge of PR #35). Backend, frontend, and security CI are GREEN on that SHA.
- Merged to `main` this session:
  - PR #33 / #32: market websocket stale-update fix (`09e80c6`) and forex calendar test determinism (`651a566`). Note: the fixture direction and UTF-8 fixes (`839aa3c`) are on `main` only through these merges; `41202a4` was never on `main` (earlier claim corrected).
  - PR #34 (`047afe3`): regenerated API contract for pydantic 2.14. CI installs latest dependencies, and pydantic 2.14 no longer emits JSON `pattern` for undecorated `Decimal` fields (schema-doc only, no runtime validation change).
  - PR #35 (`9a17642`): `alembic upgrade head` before `alembic check` in CI. The PG service container starts empty.
- Full local backend suite passes on the final tree with CI-matching dependencies (pydantic 2.14.4, FastAPI 0.165.0).

## Branch and PR State
| Item | Ref | Status |
|---|---|---|
| Production line | `main` | `bcc9b67`; CI GREEN |
| Backend regression test + this HANDOFF | `cursor/market-socket-regression-test-2026-11-20` | `f9596bc` + docs commit; PR to open |
| Frontend security bump | `cursor/frontend-next-security-2026-11-20` | `3230da3`; PR to open |
| Dependabot (20 open PRs, #1–#20) | `dependabot/*` | NOT merged; see triage below |
| `cursor/login-seed-ops-note-4b9d` | `c8177d0` | NOT merged; contains unreviewed D2C risk-seam change `bc6716c` |
| PR3 load smoke | `cursor/pr3-load-smoke-script` | PARKED; D7 NOT AUTHORIZED |

## Frontend Security
- `next` 16.3.4 -> 16.4.6. Advisory range was 16.0.0–16.4.4 (includes unauthenticated RCE in Image Optimization and cache leaks).
- Production audit (`npm audit --omit=dev`): 0 vulnerabilities (was 1 critical, 2 high).
- Remaining 9 advisories are dev-only (`@typescript-eslint/*`, `typescript-eslint`, `minimatch`, `brace-expansion` (high), `zod` (high)). Fixes need major-version changes; deferred.
- Verified locally: lint, typecheck, 290 unit tests, production build. `aigold-frontend` (pm2 id 0) restarted; HTTP 200 on port 3001.
- Note: `npm audit fix --omit=dev` prunes dev packages from `node_modules`. Use `npm ci` afterward.

## Dependabot Triage (not merged)
- Safe-looking, review then merge: GitHub Actions bumps (#1, #2, #3, #4, #7) need a check that the major tags exist and CI still passes.
- Dev-only minor/patch: pytest/pytest-asyncio/pytest-cov/mypy/redis ranges (#5, #8, #9, #10, #12), eslint-config-next (#15), @types/node (#6), react (#13).
- Needs its own review: Node 22 -> 26 (#19), Python 3.12 -> 3.15 Docker base (#20), TypeScript 5.9 -> 7.0 (#14). CI runs Node 22 and Python 3.12, so these are not tested by CI.

## Open Decisions and Known Issues
1. **No CI lock file.** `pyproject.toml` and `package.json` use version ranges with no lock for the backend. CI resolves latest each run, so release drift can break CI again (this happened once with pydantic). Proposal: add a backend lock or upper bounds. Not decided.
2. **D2C risk-seam change on `cursor/login-seed-ops-note-4b9d`.** Commit `bc6716c` (D2C-IV-P2-003 / P3-002, reject forged replay events) is NOT on `main`. It touches Risk authority code and needs an independent verification gate before any merge.
3. **UAT tag.** `uat-YYYY-MM-DD` NOT created. Requires UAT checklist sign-off on `bcc9b67` (or the then-current `main` SHA).
4. **Rate limiter.** The production API limiter (default 120/min per IP) was NOT changed. Only test-scoped overrides exist.
5. **Unrelated pm2 processes.** `aigold-backend` (id 1) and `eform-dev` (id 2, `C:\E-Form\next-eform`, Next 16.3.4) were not touched.

## Local Clone State (Windows dev server)
- Repo: `C:\AI Gold Trader`. Keep backup refs (local only): `refs/backup/main-pre-reconcile-2026-11-19`, `refs/backup/main-pre-clean-2026-11-19`.
- `backend/.venv` upgraded to pydantic 2.14.4 and FastAPI 0.165.0 to match CI. The contract test fails on the older versions.

## Next Actions
1. Merge PR for `cursor/market-socket-regression-test-2026-11-20` (backend regression test + this HANDOFF) once CI is green.
2. Merge PR for `cursor/frontend-next-security-2026-11-20` once CI is green.
3. Confirm CI on the new `main` SHA.
4. Only after CI is green on `main` AND UAT sign-off on that SHA: create `uat-YYYY-MM-DD` on `main`.
5. Decide on the CI lock-file proposal (Open Decision 1).
6. Review the D2C commit `bc6716c` through the independent gate before any merge.
7. Triage Dependabot in batches; Node 26 / Python 3.15 / TypeScript 7 need separate PRs with CI proof.

## Safety Invariants (unchanged)
- `TRADING_MODE=PAPER` and `LIVE_AUTO_TRADING=false` must be preserved in every environment.
- AI remains advisory only. No `order_send`, OMS, or live position management.
- Kill Switch > Risk Engine > Strategy Engine > AI Advisory > Human Operator.

## Independent Verification Gate
- D2C: independently verified and closed 2026-10-22 (PR #17, 350 tests).
- This session ran no independent gate. One is required before any D3+ work, any change to D2C or Risk authority (including `bc6716c`), and the first UAT tag. The market websocket change touches the live market path and should be included.
