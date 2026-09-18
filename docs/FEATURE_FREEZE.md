# AIGoldTrader — Feature Freeze Baseline (FC-12)

> [!NOTE]
> ### AI CONTEXT NOTICE
> This document records the historical functional completion freeze baseline (FC-12 as of 2026-09-16).
> - For authoritative **CURRENT operational state**, see [`docs/CURRENT_STATE.md`](file:///c:/AI%20Gold%20Trader/docs/CURRENT_STATE.md).
> - For **active task scope**, see [`docs/CURRENT_BATCH.md`](file:///c:/AI%20Gold%20Trader/docs/CURRENT_BATCH.md).
> - This file is **Tier 3 Audit Evidence**; coding agents must **NOT** read this file by default unless performing freeze verification or regression audits.

- **Freeze Date**: 2026-09-16
- **Starting Baseline HEAD**: `56839e1c3b09a1849e76ee243dc15ce5f851dcaf`
- **Feature Freeze Status**: **FROZEN & VERIFIED**
- **Comprehensive Audit Baseline**: **READY FOR INDEPENDENT AUDIT (GPT-5.6 Sol High)**

---

## 1. Included Functional Milestones

The following functional milestones are verified, feature-complete for their designated scope, and officially frozen:

1. **FC-01 Dashboard**: Real-time quote, market pulse, ATR, daily high/low, M5 closed candle chart with moving averages, session status, latest candidate preview, portfolio risk reservations, account snapshot, AI advisory status, kill switch indicator, and drill-down navigation.
2. **FC-02 Market Overview**: Live/demo market quote, multi-timeframe candle stream (M1 through W1 with partial history indicators), global market session clocks (Sydney, Tokyo, London, New York), key support/resistance levels, and market regime.
3. **FC-03 Market Analysis**: Server-authoritative market structure workbench (Swing High/Low, BOS, CHoCH, MSS, Internal Liquidity, FVG, Order Blocks), multi-timeframe context, ATR, and manual on-demand AI Advisory panel.
4. **FC-04 Trading Signals**: Strategy candidate lifecycle (8 canonical states: `DETECTED`, `WAITING_CONFIRMATION`, `READY`, `BLOCKED_CONTEXT`, `NO_TRADE`, `INVALIDATED`, `EXPIRED`, `SUPERSEDED`), Setup Evidence Score, Suggestion-Only TradePlan, invalidation levels, multi-target R:R, and fail-closed risk binding.
5. **FC-05 Backtest & Strategy (Strategy Lab)**: Strategy Catalog (STRAT01 through STRAT06), 7 Trader Profiles, current and historical strategy evaluation snapshots (labeled explicitly as Snapshots, NOT a Backtest), and Backtest Readiness disclaimer (Backtest Engine explicitly NOT IMPLEMENTED).
6. **FC-06 Economic Calendar**: High/Medium/Low USD economic event feed, point-in-time release versions, revised previous tracking, Next High-Impact USD countdown, and fail-safe Bangkok timezone display.
7. **FC-07 News & Sentiment**: Macroeconomic bias (`USD_STRONG_POSITIVE` to `USD_STRONG_NEGATIVE`, `CONFLICTING`), Macro Strength, News Regime, Reaction Windows, Spread/Volatility states, and trade policy restrictions (`INFORMATIONAL`, `CAUTION`, `RESTRICTED`).
8. **FC-08 Performance**: Account capital snapshot, portfolio risk reservations, candidate analytics, strategy distribution, profile distribution, risk decision analytics, evaluation activity, and Performance Readiness matrix. Executed trading performance (Win Rate, Net P&L, Sharpe, Equity Curve) is strictly marked **NOT AVAILABLE**.
9. **FC-09 Reports**: Truthful operational report generators for System Health, Market/Data, Candidates, Strategy Evaluations, Risk Decisions, Economic Calendar, and Macro Context. Secure CSV (UTF-8 BOM, sanitized against formula injection) and JSON exports.
10. **FC-09.5 Global Data Truthfulness**: Strict provenance enforcement across all pages. API errors, missing fields, or offline subsystems never silently fall back to fixtures, simulated data, or zero.
11. **FC-10 Settings (Configuration Center)**: Read-only server configuration allow-list (`GET /api/configuration/safe`), strict secret masking (never exposing API keys, DB credentials, JWT secrets, or terminal paths), and local UI preferences.
12. **Runtime Hardening & Process Supervision**: PM2 supervision for frontend (port 3001) and backend (port 8000), persistent logging, clean shutdown/restart lifecycles, and health/readiness endpoints (`/healthz`, `/readyz`).
13. **FC-11 Cross-Page Integration**: End-to-end navigational matrix, cross-page entity identity persistence (Candidate ID, Strategy ID, Event ID), deep linking, safe query parameter validation, and internal redirect protection.

---

## 2. Implemented Route Inventory & Functional Acceptance Matrix

| Route | UI Screen Component | Authoritative Backend Source | Loading / Empty State | Error / Unavailable State | Provenance Badging | Responsive | Acceptance Status |
|---|---|---|---|---|---|---|---|
| `/` | Redirect to `/dashboard` | N/A | Instant redirect | N/A | N/A | All | **PASS** |
| `/dashboard` | `Dashboard` | `/api/dashboard/summary`, `/api/market/candles`, WS | Skeleton cards / Empty notice | Disconnected banner / Dash values | MT5 DEMO / SIMULATED | Desktop, Tablet, Mobile | **PASS** |
| `/trading` | `MarketOverviewScreen` | `/api/market/status`, `/api/market/candles`, WS | Loading skeleton | UNAVAILABLE badge | MT5 DEMO · REAL MARKET DATA | Desktop, Tablet, Mobile | **PASS** |
| `/analysis` | `MarketAnalysisScreen` | `/api/analysis/structure`, `/api/analysis/context`, `/api/ai/analyze` | Skeleton loader | Fail-closed / Error alert | DERIVED / ANALYSIS ENGINE | Desktop, Tablet, Mobile | **PASS** |
| `/signals` | `TradingSignalsScreen` | `/api/trade-candidates`, `/api/strategy/context`, `/api/risk/*` | Filter skeleton / Empty state | Fail-closed risk banner | CANDIDATE ≠ TRADE | Desktop, Tablet, Mobile | **PASS** |
| `/backtesting` | `StrategyLabScreen` | `/api/strategies`, `/api/trader-profiles`, `/api/strategy/evaluations` | Tab loading spinners | Error alerts | SNAPSHOT ONLY / NOT A BACKTEST | Desktop, Tablet, Mobile | **PASS** |
| `/calendar` | `CalendarWorkspace` | `/api/calendar/economic`, `/api/news/status` | Day group skeleton | Degraded/Unavailable badge | POINT-IN-TIME PROVIDER | Desktop, Tablet, Mobile | **PASS** |
| `/scanner` | `NewsSentimentScreen` | `/api/news/context`, `/api/news/status` | Shimmer cards | Provider degraded / Unavailable | MACRO BIAS ≠ TRADE SIGNAL | Desktop, Tablet, Mobile | **PASS** |
| `/analytics` | `PerformanceScreen` | `/api/risk/account`, `/api/risk/portfolio`, `/api/trade-candidates` | Panel spinners | Error isolation | READINESS ONLY / NOT AVAILABLE | Desktop, Tablet, Mobile | **PASS** |
| `/journal` | `ReportsScreen` | Bounded domain query APIs | Table skeleton | Isolated error banner | REPORT PROVENANCE / AUDIT | Desktop, Tablet, Mobile | **PASS** |
| `/settings` | `SettingsCenter` | `/api/configuration/safe`, `/api/system/status` | Read-only skeleton | Retry button | SAFE ALLOW-LIST / READ ONLY | Desktop, Tablet, Mobile | **PASS** |
| `/risk` | `RiskWorkspace` | `/api/risk/policy`, `/api/risk/portfolio`, `/api/risk/kill-switch` | Workspace skeleton | Fail-closed banner | FAIL-CLOSED / ACTIVE PROTECTION | Desktop, Tablet, Mobile | **PASS** |
| `/login` | `LoginPage` | `/api/auth/login`, `/healthz` | Button spinner | Thai error alert | NO FAKE PRICES / SAFE REDIRECT | Desktop, Tablet, Mobile | **PASS** |

*Note: Legacy unlinked stubs (`/alerts`, `/orders`, `/paper-trading`, `/positions`) remain unlinked in navigation and do not display fabricated data.*

---

## 3. Implemented Backend Domains & API Contracts

1. **Authentication & Authorization (`/api/auth`)**: JWT access tokens (30m) and refresh tokens (7d) stored securely, password hashing with bcrypt, role-based access control (`ADMIN`, `OPERATOR`, `VIEWER`), rate limiting, client IP resolution with CIDR proxy validation.
2. **Health & Readiness (`/healthz`, `/readyz`, `/api/system/status`)**: Authenticated 8-subsystem health status aggregation; unauthenticated `/healthz` process check; `/readyz` transactional database connectivity check.
3. **Market Data (`/api/market`, `/api/market/candles`, `/ws/market`)**: Real-time read-only MT5 IPC connector, tick/candle validation, jump ratio and maximum spread guards, stale detection (5s threshold), historical candle slicing.
4. **Market Structure Analysis (`/api/analysis/structure`, `/api/analysis/context`)**: Multi-timeframe swing high/low identification, BOS/CHoCH classification, dealing ranges, fair value gaps (FVG), order blocks, internal liquidity sweeps, and ATR.
5. **Strategy Engine (`/api/strategies`, `/api/trader-profiles`, `/api/trade-candidates`, `/api/strategy/evaluations`)**: Deterministic multi-profile evaluation, 8 canonical candidate states, Setup Evidence Score calculation, Suggestion-Only TradePlan generation.
6. **Economic Calendar & Macro News (`/api/calendar/economic`, `/api/news/context`)**: Forex Factory calendar feed, point-in-time snapshotting, economic revisions, macro bias synthesis, reaction window tracking, and news trade policies.
7. **Risk Engine & Kill Switch (`/api/risk/*`)**: Fail-closed risk evaluation, gross directional exposure bounding, risk reservations, account capital snapshot reconciliation, and emergency Kill Switch management.
8. **AI Advisory System (`/api/ai/*`)**: Exactly six analytical agents (`market_context`, `smc_ict`, `macro_news`, `strategy_critic`, `risk_interpreter`, `trade_thesis`) plus executive Meta Controller. Strict context minimization, advisory-only outputs, zero mutation authority.
9. **Configuration Governance (`/api/configuration/safe`)**: Allow-list DTO returning sanitized operational flags without leaking secrets.
10. **Dashboard Summary (`/api/dashboard/summary`)**: High-performance aggregate summary with independent failure isolation.

---

## 4. Safety Baseline & Authority Hierarchy

The safety invariants are strictly enforced by code and runtime configuration:

```
Kill Switch (Highest Authority)
      ↓
Risk Engine (Fail-Closed Bounding)
      ↓
Strategy Engine / TradePlan (Suggestion Only)
      ↓
AI Advisory (Informational / Meta Review Only)
      ↓
Human / Operator (Final Discretion)
```

- `TRADING_MODE`: **PAPER**
- `LIVE_AUTO_TRADING`: **false**
- `Broker Execution`: **NONE (No execution pathways exist in code)**
- `Paper Order Generation`: **NONE**
- `Position Management`: **NONE**
- `AI Authority`: **ADVISORY ONLY** (AI cannot place orders, alter trade plans, or bypass risk limits).

---

## 5. Global Data Provenance Taxonomy

All displayed values strictly conform to the 4 canonical categories:

1. **Category A — Authoritative Runtime Data**: Direct from live broker / database / engine (`MT5 DEMO · REAL MARKET DATA`).
2. **Category B — Derived Data**: Explicitly derived from Category A using transparent mathematical formulas (e.g. session clocks, R:R ratios).
3. **Category C — Explicit Simulation/Fixture**: Labeled with high-contrast badges:
   - `FIXTURE · TEST DATA`
   - `SIMULATED · NOT LIVE MARKET DATA`
   - `REPLAY · HISTORICAL`
   - `CONFIGURED PAPER`
4. **Category D — Unavailable / Not Implemented**:
   - `UNAVAILABLE`: Data missing, failed, disconnected, or stale.
   - `NOT IMPLEMENTED`: Engine or capability planned for future phases.

**Prohibited**: No silent fallbacks, no converting null to zero, no default-normal assumptions, and no fabricated financial records.

---

## 6. Test Verification Summary

### Comprehensive Test Matrix

| Domain / Suite | Test Count | Result | Framework | Execution Scope |
|---|---|---|---|---|
| **Backend Unit & Domain Tests** | 781 | **PASS** | Pytest 8.4.2 | Auth, Health, Market, Analysis, Strategy, News, Risk, AI, Config, Dashboard |
| **Backend PostgreSQL Integration** | 31 | **PASS** | Pytest (Real PG 18) | Migrations, Concurrency, Lost-Update Protection, Transaction Locks, Risk |
| **Frontend Component & Contract** | 256 | **PASS** | Vitest 4.1.0 | Provenance, Screens, Navigation, Contracts, Thai Labels, Safety Guards |
| **Frontend TypeScript Check** | 0 errors | **PASS** | `tsc --noEmit` | Strict type validation across all features and routes |
| **Frontend ESLint** | 0 errors | **PASS** | ESLint | Code standards, hook dependencies, formatting |
| **Next.js Production Build** | 18 routes | **PASS** | Next.js 16.3.4 | All dynamic and static routes compiled successfully with Turbopack |
| **Total Automated Tests** | **1,068** | **PASS** | — | **Zero failures, zero errors** |

### Static Code Scan Findings
- `TODO` / `FIXME` / `HACK`: **0 found** in production source code.
- `dangerouslySetInnerHTML`: **0 found** in frontend code.
- `order_send`: **0 found** in backend code.
- `Committed Secrets`: **0 found** (Strictly excluded via `.gitignore`).
- Obsolete enums (`NEUTRAL_USD`, generic `BLOCKED` as candidate state): **0 found**.

---

## 7. Current Runtime & Process Supervision Status

- **Supervisor**: PM2
- **Backend Service**: `aigold-backend` (FastAPI / Uvicorn on port 8000, Python 3.12 `.venv`) — **ONLINE** (Uptime: >4 hours, Health: OK, Readiness: Ready).
- **Frontend Service**: `aigold-frontend` (Next.js 16.3.4 on port 3001, Node.js) — **ONLINE** (HTTP 200 OK).
- **Database Service**: PostgreSQL 18 on port 5432 — **RUNNING** (Current revision: `0012_phase5_reconciliation (head)`).
- **Market Data Feed**: MT5 Demo IPC (IUX Markets Demo terminal session).
- **Economic News Feed**: Forex Factory calendar scraper.
- **AI Advisory Provider**: Fixture Provider (Safe offline canonical advisory).

---

## 8. Browser Visual QA Status

> [!WARNING]
> **BROWSER VISUAL QA BLOCKED BY TOOLING**
> 
> No interactive browser automation tooling or computer-use visual driver is configured in this agent environment.
> Automated regression has verified 100% of routes via Next.js Turbopack compilation, HTTP 200 health responses, and 256 Vitest DOM/contract tests.
> Manual end-to-end visual confirmation remains a mandatory verification step during the upcoming User Acceptance Testing (UAT) phase.

---

## 9. Feature Freeze Risk Register

| Risk ID | Severity | Area | Description | Current Impact | Required Action / Status |
|---|---|---|---|---|---|
| **FR-BLK-01** | **DEFERRED BLOCKER** | Phase 6.2 External AI Provider | Windows worker process lifecycle, survivor process tracking, and capacity semaphore lease ownership desynchronization under high concurrency in `execution.py`. | **Zero impact in current mode**: `ai_provider_mode="fixture"` runs entirely in-process without spawning child worker processes. | **DEFERRED ENABLEMENT BLOCKER**: Must be formally hardened and tested under Windows before switching `ai_provider_mode` to `external` in production. |
| **P0** | — | — | No open P0 issues. | — | None. |
| **P1** | — | — | No open P1 issues. | — | None. |
| **P2** | — | — | No open P2 issues. | — | None. |
| **P3** | — | — | No open P3 issues. | — | None. |

---

## 10. Explicit NOT IMPLEMENTED Scope Manifest (Future Roadmap)

The following engines and capabilities are **NOT IMPLEMENTED** in the current frozen baseline. They are explicitly reserved for future post-audit product phases:

1. **Paper Order Ledger & Order Book**: No simulated or real order ledger exists.
2. **Order Management System (OMS)**: No execution routing or order state machine.
3. **Position Management**: No open position tracking, lot allocation, or floating P&L calculations.
4. **Executed Trade Journal Engine**: No historical trade log or user journal entry system.
5. **Executed Performance Engine**: No live trade metrics (Total Trades, Win Rate, Net P&L, Profit Factor, Expectancy, Sharpe, Max Drawdown, Equity Curve).
6. **Deterministic Backtest Engine**: Strategy Lab displays point-in-time historical evaluation snapshots only; the backtest engine is not implemented.
7. **Walk-Forward Analysis Engine**: Not implemented.
8. **Out-of-Sample (OOS) Validation Pipeline**: Not implemented.
9. **Adaptive Strategy Selector**: No automated strategy weighting or dynamic selection based on market regime.
10. **Automatic Strategy Rotation**: Strategies do not rotate automatically.
11. **Broker Execution Adapters**: No MT5 or FIX trading bridge for order submission.
12. **Live Auto Trading**: Completely disabled and blocked by runtime guards.

---

## 11. Target Future Architecture (Roadmap)

```
Real Market Data (MT5 / Institutional Feed)
      ↓
Market Regime Classification (Trend / Range / Volatile / Pre-News)
      ↓
Eligible Strategy Candidates (STRAT01–06 Rules)
      ↓
Deterministic Backtest & Walk-Forward Evidence Engine
      ↓
Adaptive Strategy Selector (Regime-Aware Ranking)
      ↓
Trade Candidate Generation
      ↓
TradePlan Suggestion (Entry, Stop Loss, Multi-Targets)
      ↓
AI Multi-Agent Advisory & Meta Synthesis (Advisory Review)
      ↓
Risk Engine Validation & Kill Switch Verification (Fail-Closed)
      ↓
Paper / Approved Execution Gate (Human / Supervised Approval)
      ↓
Position Management & Real-Time Monitoring
      ↓
Trade Journal & Audit Ledger
      ↓
Performance Feedback Loop (Continuous Model & Parameter Review)
```

---

## 12. Feature Freeze Declaration

- **Functional Completion Gate**: **PASS**
- **Feature Freeze**: **APPROVED**
- **Codebase Status**: **FROZEN**
- **Next Milestone**: **COMPREHENSIVE SYSTEM AUDIT** (To be performed independently by GPT-5.6 Sol High from a fresh context starting from this exact Freeze SHA).
