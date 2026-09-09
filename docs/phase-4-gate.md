# Phase 4 implementation gate — 2026-09-09

## Status
IMPLEMENTATION COMPLETE — PENDING COMBINED SOL HIGH INDEPENDENT REVIEW PHASE 3.5 + 4.
This is an analysis/trade-plan layer, not a profitability or execution certification. Phase 5 DO NOT START.
Current engine: strategy-1.0.1. See [architecture and contracts](09-strategy-engine.md).

## Preconditions
Phase 3.5 final report was implementation complete pending review. Before Phase 4 code changes, runtime PostgreSQL/IUX verification passed: historical NewsMarketContext API equals pure engine, future cutoff rejected, operational clocks excluded. No blocking provenance/no-lookahead/data-integrity issue was found. Existing safe-partial W1 history and fixture news were disclosed and preserved.
Baseline source hashes and DEV record hashes were recorded before edits in data/local/phase4. Existing Phase 2.5/3/3.5 reports are historical; the latest user request explicitly authorized Phase 4 after this prerequisite check.

## Key-level / session engine
Reuses confirmed Phase 3 internal/external swings, liquidity/EQH/EQL, FVG/OB and equilibrium. Adds canonical previous-day/week extrema, known daily/weekly opens and IANA session ranges. Source IDs, input windows, origin/confirmation/valid-from and lifecycle states are retained.
DST-aware Asia/Tokyo, Europe/London and America/New_York windows use UTC instants. Running or incomplete coverage is provisional; closed extrema require exact M5 coverage. Missing historical periods are not reconstructed.

## Indicator / pattern engine
MACD(12,26,9) and stochastic K14/D3 use explicit warmup/flat-range conventions; Phase 3 RSI/ADX/ATR and existing indicators are reused. No indicator alone can trigger entry.
Deterministic confirmed-pivot templates cover double/triple top/bottom, H&S/inverse, triangles, flags and wedges, with tolerance/separation/lookback/slope checks, close confirmation and explicit failure/expiry. This first version is conservative and bounded; it is not visual recognition or a durable pattern ledger.

## HTF/LTF mapping
SCALP H1/M15/M5/M1; DAY_TRADE H4/H1/M15/M5; SWING W1/D1/H4/H1; RUN_TREND D1/H4/H1/M15. Minimum is configurable (default 60 closed bars per required frame).
Actual IUX verified nine TFs: M1/M5 300 closed, M3/M15/M30/H1/H4/D1 299 closed, W1 230 closed from 231 returned/300 requested. W1 is partial, meets the strategy minimum, and is never extended with fake bars.

## Strategy library / trader profiles
Six explicit playbooks: SMC liquidity reversal, trend pullback, breakout/retest, range mean reversion, post-news momentum, post-news liquidity reversal.
Seven immutable configuration profiles produce thirteen isolated evaluations from one context: Strategy Lab, SMC Specialist, Trend Runner, Liquidity Specialist, Breakout Trader, Range Trader, News Trader.
Single strategy, multiple strategy and multiple trader comparison work. Adaptive is RESERVED_DISABLED. No AI final selector or claims of comparative profitability.

## Setup / trade-plan engine
Direction LONG/SHORT/NO_TRADE is separate from status. Every result includes evidence, scores, missing conditions, conflicts, context/upstream identifiers and expiry. Hard blocks cannot be outscored.
Entry and SL derive from actual structural zones/ranges/patterns, with ATR buffer and verified tick rounding. At least two ordered structural targets and minimum RR are required. The nearest target below minimum RR rejects the plan; it is not skipped. No lots, risk-percent, account exposure or order object.
Actual-mode fixture/unavailable news, unknown spread/volatility, news restrictions, insufficient/stale context or HTF conflict block READY. UI shows “ยังไม่พบ Setup ที่ผ่านเกณฑ์” and the reasons. Offline LONG/SHORT goldens prove plan construction without fabricating a real setup.

## Candidate lifecycle / storage
Meaningful context/config revisions are immutable; exact repeated evaluations are idempotent. New evaluation revisions supersede predecessors, expiry uses market cutoffs, and explicit upstream invalidation or a later known close through structural SL can invalidate.
QREV-R01: absent objects mean NOT_INCLUDED_UNKNOWN, never invalidation. Historical evidence remains frozen. QREV-R02: deterministic as_of/content IDs are separate from UTC generated_at/served_at.
Migration 0006 adds four tables. TEST up/down/up, drift, original-row preservation, unique IDs and populated-history downgrade guard were exercised. Migrations 0001–0005 remain unchanged. DEV was upgraded additively.

## Provenance / no-lookahead / multi-trader
One PostgreSQL REPEATABLE READ snapshot feeds all profiles. Serialized immutable upstream payloads, full strategy/analysis configuration, canonical source/window/input IDs and point-in-time news are stored with evaluations.
Tests cover future-bar exclusion, candle-by-candle prefixes, 100/150/200/300 and rolling windows, config revisions, W1 partial minimum, causal pivots/session extrema/news, profile isolation, score blocks and plan geometry.
Different bounded windows may legitimately produce different context IDs. This is not a claim that windowed indicators or pivots are invariant under truncation. Replay requires the recorded engine version; older DEV acceptance versions remain historical records.

## Trading Screen / API / security
Authenticated typed GET APIs expose current context/plans, registry, profiles, evaluations, candidates and transitions. Pydantic/OpenAPI exports TypeScript and runtime schema. No new public write or execution route, no provider keys in the browser, no query-string tokens.
Thai strategy workspace includes mode/profile comparison, evidence/missing/conflict reasons, current plan or no-plan state, HTF/LTF history, key levels/patterns/indicators and independent chart overlays. Desktop/tablet/mobile were visually inspected. Existing chart/news/calendar remain available.
Native browser login uses the private local credential file. It is not included in source or reports.

## Validation evidence
Final frozen-source acceptance: PASS. Local evidence: data/local/phase4.

| Check | Result |
|---|---|
| Full backend regression | 345 passed, 10 external tests deselected; backend-tests-frozen.xml |
| PostgreSQL integration (included above) | 17 passed, isolated TEST schemas |
| Strategy-specific tests (included above) | 66 passed |
| Frontend regression | 112 passed |
| Real MT5 direct tests | 9 passed; strict W1 300-bar case excluded because actual availability is partial |
| Real Phase 3 API / batch / stream / causal prefix | 9 TFs, 45 prefixes passed |
| Real news API / historical pure / clock boundary | Passed |
| Real strategy API / pure / idempotence / auth | Passed, seven profiles and thirteen candidate evaluations |
| Strategy / news / calendar browser | Passed, 1440/820/390 widths, zero console/API/asset errors |
| Phase 3 chart browser regression | All TFs, toggles, reload, reconnect, closed-bar refresh and mobile passed |
| Ruff / project mypy / new-module body typing | Passed |
| Wheel / generated contracts / frontend build | Passed |
| DEV migration / protected foundation / secret audit | Passed; no original records deleted, 30 protected files unchanged |


- Strategy unit/contract/lifecycle/auth tests: 66 passed.
- Frontend regression: 112 passed; lint/typecheck/build passed.
- PostgreSQL migration/history acceptance: passed.
- Actual strategy API/pure equality, seven-profile shared context, duplicate request idempotence, future cutoff 422, unauthenticated 401: passed.
- Strategy browser: three modes, 1440/820/390 widths, reload, chart layer toggles; console/API/asset errors 0.
- News/calendar browser regression: pre/release/post/none, revisions, filters and three widths; console/API/asset errors 0.
- Standard project mypy: 64 source files passed. New strategy/API function bodies also passed --check-untyped-defs.
- Expanded --check-untyped-defs over all legacy modules found 27 pre-existing typing findings in Phase 3 analysis engine and market service. These protected modules were not changed; this broader optional gate is not represented as passed.
- Native wheel and generated-contract checks passed; final version packaging is verified again.
Two integration corrections were made: PostgreSQL operational clocks now normalize UTC in StrategyResponse; schema assertions include the two new FK-bearing tables. A mid-run schema regeneration produced a transient version mismatch; frozen-source regression is the authoritative final run.

## Safety
TRADING_MODE=PAPER; LIVE_AUTO_TRADING=false. Broker execution NONE; MT5 order_send NONE; paper-order creation NONE; risk/position management NONE; AI/LLM decisions NONE.
The existing MT5 terminal is read-only market input. No trading-account password, API token or database URL is copied into tracked artifacts.
No Git staging, commit, push, branch creation, merge, reset or clean was performed.

## Known limitations and gate decision
- Real economic API is not configured. Fixture news cannot enable real-mode READY; this is a deliberate safe block.
- Direct W1 300-bar availability remains partial. Strategy context uses known available closed bars and explicit minimums.
- LONG/SHORT playbook goldens use explicit upstream Phase 3/news contract fixtures; they are not evidence of profitable end-to-end market performance.
- Conservative first-version patterns/playbooks need independent quant review and later walk-forward research; no performance/profitability assertion.
- HTTP evaluation on actual nine-TF data measured roughly 2–9 seconds under concurrent acceptance workload; pure thirteen-candidate evaluation roughly 0.7–0.9 seconds. This is suitable for current closed-minute analysis acceptance, not a latency guarantee.
- Evaluation is on demand; there is no unattended scheduler. Historical candidate reads expose immutable original revisions plus a separate transition endpoint, not active position state.
- Full context JSON history is retained without automatic purge. Storage archival and multi-instance/distributed coordination require a later design before unattended deployment.
- Profile authoring/per-account editing and adaptive selection remain deferred interfaces.
- Additional legacy whole-body typing findings and existing dependency deprecation warnings remain documented.
- Combined independent review is NOT RUN in this task and is required next. Stop before Phase 5.

## Git and final preservation evidence
Branch: main. HEAD: 857e764bea47279af7986a449d80505b74820432.
Phase 4 changed 16 existing files and added 25 files; prior-phase uncommitted work remains present. Git index is empty. No stage/commit/push performed.
DEV schema head is 0006_strategy. Original users/sessions/accounts/symbols/audit/system records were not deleted; original session/account/symbol/audit/system hashes are unchanged. User row changed during test login (last-login update expected). New login/logout audit rows are expected. Canonical invalid-candle count is zero. Exact file lists and record counts are in local final-audit.json.

Worktree totals including earlier phases: 43 modified, 105 untracked files, 0 staged. Acceptance refresh sessions were closed (0 active at final audit).

### Phase 4 changed existing files

- backend/app/api/__init__.py
- backend/app/core/config.py
- backend/app/models/__init__.py
- backend/pyproject.toml
- backend/scripts/export_api_contract.py
- backend/tests/integration/test_mt5_storage.py
- backend/tests/integration/test_postgres.py
- backend/tests/test_foundation_gate.py
- docs/04-database-design.md
- docs/05-api-design.md
- docs/17-testing.md
- docs/README.md
- frontend/src/app/globals.css
- frontend/src/features/analysis/primitive.ts
- frontend/src/features/chart/TradingScreen.tsx
- implementation_plan.md

### Phase 4 new files

- backend/alembic/versions/0006_strategy.py
- backend/app/api/strategy.py
- backend/app/models/strategy.py
- backend/app/services/strategy/__init__.py
- backend/app/services/strategy/context.py
- backend/app/services/strategy/domain.py
- backend/app/services/strategy/engine.py
- backend/app/services/strategy/indicators.py
- backend/app/services/strategy/lifecycle.py
- backend/app/services/strategy/patterns.py
- backend/app/services/strategy/repository.py
- backend/tests/integration/test_strategy_postgres.py
- backend/tests/test_strategy.py
- docs/09-strategy-engine.md
- docs/phase-4-gate.md
- frontend/src/features/strategy/StrategyWorkspace.tsx
- frontend/src/features/strategy/contracts.ts
- frontend/src/features/strategy/overlays.ts
- frontend/src/features/strategy/strategy-contract.generated.json
- frontend/src/features/strategy/thai.ts
- frontend/src/types/strategy.generated.ts
- frontend/tests/e2e/strategy-screen.cjs
- frontend/tests/fixtures/strategy-ready.json
- frontend/tests/fixtures/strategy.json
- frontend/tests/strategy.test.cjs
