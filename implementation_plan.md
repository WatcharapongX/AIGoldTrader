# Implementation Plan — AI-Assisted Trading Platform for XAUUSD & Forex

| รายการ | รายละเอียด |
|---|---|
| เอกสาร | `implementation_plan.md` — Single Source of Truth สำหรับติดตามความคืบหน้าของโปรเจกต์ |
| เวอร์ชัน | 1.5 |
| วันที่สร้าง | 2026-09-08 |
| อัปเดตล่าสุด | 2026-09-08 |
| Trading Mode เริ่มต้น | `TRADING_MODE=PAPER` — **`LIVE_AUTO_TRADING=false` ตลอดจนกว่าจะได้รับอนุมัติจากผู้ดูแลระบบโดยเจตนา** |
| Symbol เริ่มต้น | XAUUSD (ออกแบบให้รองรับ Forex หลาย Symbol ในอนาคต) |

---

## วิธีใช้เอกสารนี้

1. ทุกงานมีรหัส `TASK-XXX` ที่ไม่ซ้ำกันทั้งเอกสาร — **ก่อนเริ่ม Task ใหม่ทุกครั้ง ต้องตรวจ Status ของ Task ก่อน เพื่อไม่ทำงานซ้ำ**
2. เมื่อ Task เสร็จ ให้เปลี่ยน `- [ ]` เป็น `- [x]` และอัปเดตตาราง Progress Summary
3. แต่ละ Phase ต้องผ่าน **Phase Gate** = Build + Test + Verify + Definition of Done ครบ ก่อนเดินไป Phase ถัดไป — **ห้ามข้าม Phase Gate เด็ดขาด**
4. รายงานผลเมื่อจบแต่ละ Phase ตามรูปแบบในหัวข้อ 10 (รายงานผลระหว่างทำงาน)
5. การเปลี่ยนแปลงแผนต้องบันทึกใน Change Log (หัวข้อ 11)

### Status Legend

| สัญลักษณ์ | ความหมาย |
|---|---|
| `- [ ]` | NOT STARTED |
| `- [x]` | COMPLETED (ผ่าน Definition of Done ของ Task) |
| ⬜ NOT STARTED | Phase ยังไม่เริ่ม |
| ⏳ IN PROGRESS | Phase กำลังดำเนินการ |
| ✅ COMPLETED | Phase ผ่าน Phase Gate แล้ว |
| ⛔ BLOCKED | ติด Blocker — ดูหัวข้อ Stop Conditions |

### Progress Summary

| Phase | ชื่อ | Status | Tasks เสร็จ/รวม |
|---|---|---|---|
| 0 | Foundation Documents & Architecture | ✅ COMPLETED | 9/9 |
| 1 | Project Foundation | ✅ COMPLETED (native PostgreSQL + browser gate passed) | 11/11 |
| 2 | Market Data & Realtime Chart | ⬜ NOT STARTED | 0/9 |
| 3 | Analysis Engines (Structure / Liquidity / SMC / Regime) | ⬜ NOT STARTED | 0/9 |
| 4 | Strategy Engine & Signal Engine | ⬜ NOT STARTED | 0/9 |
| 5 | Risk Engine & Kill Switch | ⬜ NOT STARTED | 0/7 |
| 6 | AI Analysis Engine (Multi-Agent) | ⬜ NOT STARTED | 0/8 |
| 7 | Paper Trading & Order Management | ⬜ NOT STARTED | 0/7 |
| 8 | Trade Journal & Analytics | ⬜ NOT STARTED | 0/5 |
| 9 | Backtesting & Walk-Forward | ⬜ NOT STARTED | 0/7 |
| 10 | Broker Adapter (MT5 Demo) | ⬜ NOT STARTED | 0/6 |
| 11 | Semi-Automatic Trading | ⬜ NOT STARTED | 0/4 |
| 12 | Hardening (Security / Performance / Observability) | ⬜ NOT STARTED | 0/6 |
| 13 | UAT & Regression | ⬜ NOT STARTED | 0/4 |
| 14 | Production Readiness Review | ⬜ NOT STARTED | 0/3 |
| | **รวม** | | **20/104** |

---

## 1. Current Repository Assessment (PHASE 0 — ตรวจสอบแล้ว 2026-09-08)

- Workspace: `C:\AI Gold Trader` — **ว่างเปล่า ไม่มีไฟล์ใด ๆ** (ไม่มี README, AGENTS.md, package.json, requirements.txt, docs/ ฯลฯ)
- Git: ไม่มี Repository (ยังไม่ได้ `git init`)
- Technology Stack ปัจจุบัน: ไม่มี
- Code เดิม: ไม่มี → เป็น **Greenfield Project** ไม่มี Source of Truth เดิม ไม่ต้องกังวลเรื่อง Rewrite
- ข้อสรุป: สร้าง Architecture และ Project Structure ใหม่ทั้งหมดตาม Specification นี้

### Current Phase 1 assessment — 2026-09-08 (supersedes the historical empty-workspace assessment above)

- Source now contains FastAPI auth/audit/health + six-table Alembic foundation, Next.js shell/auth/client and tests.
- Branch main; all project files remain untracked; no commits and no tracked/staged diff. Existing work preserved.
- TASK-010..020 are complete. Phase 1 gate passed on native Windows; Phase 2 is not started and requires independent review.
- Python/Node and dependencies are installed. Native PostgreSQL 18.6 service is running; separate project DEV/TEST databases and restricted roles are configured in ignored backend/.env.
- Native Windows is the primary local DEV route. Docker/WSL are optional; Redis service and TimescaleDB extension are not Phase 1 prerequisites.
- DATABASE_URL, disabled Redis, Windows selector loop and explicit PostgreSQL integration tests now support this route.
- Current verification: backend 36 tests (including real PostgreSQL), frontend 6 tests, lint/typecheck/package/Next build and Chromium login/session/logout pass.
- Native PostgreSQL migration up/down/up, constraints/transactions, auth/audit and complete browser login evidence verified. See docs/phase-1-gate.md.

## 2. Gap Analysis (historical Phase 0 baseline)

| หมวดตาม Spec | สถานะปัจจุบัน | ช่องว่างที่ต้องสร้าง |
|---|---|---|
| Documentation / Architecture | ไม่มีเลย | ทั้งหมด (docs/01–20 + ADR + implementation_plan.md) |
| Frontend (Next.js) | ไม่มี | ทั้งหมด |
| Backend (FastAPI) | ไม่มี | ทั้งหมด |
| Database (PostgreSQL/Timescale/Redis) | ไม่มี | ทั้งหมด (30 tables) |
| Market Data / Analysis Engines | ไม่มี | 22 Core Modules ทั้งหมด |
| Risk Engine / Kill Switch | ไม่มี | ทั้งหมด |
| AI Engine / Multi-Agent | ไม่มี | ทั้งหมด |
| OMS / Paper Trading | ไม่มี | ทั้งหมด |
| Broker Adapter | ไม่มี | ทั้งหมด (เริ่มจาก MT5 Demo) |
| Infrastructure (Docker) | ไม่มี | ทั้งหมด |
| Security / Testing / Observability | ไม่มี | ทั้งหมด |

## 3. Target Architecture (สรุป — รายละเอียดใน docs/02-system-architecture.md)

### 3.1 Technology Stack

| Layer | เทคโนโลยี |
|---|---|
| Frontend | Next.js (App Router) + React + TypeScript + Tailwind CSS |
| Chart | TradingView Lightweight Charts |
| State Management | Zustand (เลือกเพราะ Complexity จริงคือ per-feature store + WS push — ดู ADR-001) |
| Realtime (FE↔BE) | WebSocket |
| Backend | Python 3.12+ / FastAPI (REST + WebSocket + Background Workers) |
| Primary Database | PostgreSQL 16 (Native Windows in local DEV); TimescaleDB for future ticks/candles phases |
| Cache / Realtime | Redis adapter optional/deferred in Phase 1; distributed use evaluated when needed |
| Infrastructure | Native Windows Node.js + Python + PostgreSQL service; Docker Compose optional |

### 3.2 Core Data Flow (หลักการสำคัญ — ห้ามลำดับนี้เปลี่ยน)

```
MARKET DATA → MARKET STRUCTURE → LIQUIDITY → MARKET REGIME → STRATEGY
→ AI ANALYSIS → RISK ENGINE → TRADE PLAN → PAPER / HUMAN CONFIRMATION
→ ORDER MANAGEMENT → POSITION MANAGEMENT → TRADE JOURNAL
→ PERFORMANCE ANALYTICS → STRATEGY IMPROVEMENT
```

- **AI/LLM ห้าม** วิเคราะห์ Raw Chart แล้วสั่ง Buy/Sell โดยตรง, ห้าม Bypass Risk Engine, ห้ามส่ง Order เอง
- **Signal ใด ๆ** ต้องผ่าน Confluence + Risk Validation ก่อนเสมอ
- ทุก Decision ต้อง Explainable / Auditable / Testable

### 3.3 Trading Safety Configuration

- `TRADING_MODE`: `BACKTEST` | `PAPER` | `SEMI_AUTO` | `LIVE` — **Default = `PAPER`**, ห้าม Enable `LIVE` อัตโนมัติ
- `LIVE_AUTO_TRADING=false` จนกว่าจะผ่าน Approval ใน PHASE 14
- Feature เปิดในช่วงพัฒนา: Market Analysis, AI Signal, Paper Trading, Backtesting, Manual Confirmation เท่านั้น

## 4. Project Folder Structure (เป้าหมายเมื่อจบ PHASE 1)

```
AI Gold Trader/
├── implementation_plan.md          ← ไฟล์นี้
├── README.md
├── .env.example                    ← ไม่มี Secret จริง
├── .gitignore
├── docker-compose.yml
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/                   # config, security, logging, correlation_id
│   │   ├── api/                    # REST routers + WebSocket endpoints
│   │   ├── db/                     # session, base, migrations helper
│   │   ├── models/                 # SQLAlchemy models (30 tables)
│   │   ├── schemas/                # Pydantic schemas (validation layer)
│   │   ├── services/
│   │   │   ├── market_data/        # provider + candle aggregation
│   │   │   ├── analysis/           # structure, liquidity, smc, indicators, regime, session
│   │   │   ├── strategy/           # strategy framework + built-in strategies
│   │   │   ├── ai/                 # provider + agents + decision + confidence
│   │   │   ├── risk/               # risk checks, position sizing, kill switch
│   │   │   ├── trading/            # OMS, positions, paper trading
│   │   │   ├── journal/            # trade journal + analytics
│   │   │   ├── backtest/           # backtesting + walk-forward
│   │   │   ├── broker/             # broker adapters (interface + mt5 + paper)
│   │   │   └── notification/       # alerts
│   │   └── workers/                # background workers (data, analysis, position mgmt)
│   ├── alembic/                    # migrations
│   ├── tests/                      # unit / integration / api / critical cases
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── app/                    # Next.js App Router (pages ตาม Main Navigation)
│   │   ├── components/             # UI components (chart, panels, tables)
│   │   ├── features/               # feature modules (trading, signals, risk, journal, ...)
│   │   ├── stores/                 # Zustand stores
│   │   ├── lib/                    # api client, ws client, utils
│   │   └── types/                  # shared types
│   ├── package.json
│   └── Dockerfile
└── docs/
    ├── README.md                   # documentation index
    ├── 01-requirements.md … 20-production-readiness.md
    └── architecture-decision-records/
        └── ADR-001 … ADR-007
```

---

## 5. PHASE 0 — Foundation Documents & Architecture

- **Objective:** สร้างเอกสารรากฐานครบก่อนเขียน Code ฟีเจอร์หลัก — Requirements, System Architecture, Trading Domain Model, Database ERD, API Contract, ADR และแผนงานนี้
- **Scope:** เอกสารเท่านั้น (ไม่มี Code) + Repository Audit
- **Dependencies:** ไม่มี (Phase แรก)
- **Status:** ✅ COMPLETED (2026-09-08 — ผ่าน Phase Gate ทุกข้อ)

**Tasks:**

- [x] TASK-001: Repository Audit — ตรวจ Workspace, Folder, Git Status, Tech Stack, Code เดิม และสรุป Current State + Gap Analysis (ผลลัพธ์อยู่ในหัวข้อ 1–2 ของเอกสารนี้)
- [x] TASK-002: สร้าง `docs/01-requirements.md` — Functional/Non-functional Requirements ครบทุกหมวดตาม Spec
- [x] TASK-003: สร้าง `docs/02-system-architecture.md` — System Architecture, Service Boundaries (22 modules), Data Flow, Realtime Design, Environments
- [x] TASK-004: สร้าง `docs/03-trading-domain.md` — Trading Domain Model: Entities, Enums, State Machines (OMS/Position/Signal), Domain Invariants
- [x] TASK-005: สร้าง `docs/04-database-design.md` — Database ERD + Schema ครบ 30 tables ตาม Spec (+3 ตารางเสริม: analysis_snapshots, paper_equity_history, sessions = 33 ตาราง)
- [x] TASK-006: สร้าง `docs/05-api-design.md` — API Contract: REST endpoints + WebSocket topics + Error format + Auth
- [x] TASK-007: สร้าง `docs/architecture-decision-records/ADR-001` ถึง `ADR-007` (Frontend, Backend, Database, Market Data, Trading Engine, AI, Broker)
- [x] TASK-008: สร้าง `docs/README.md` — Documentation Index ระบุสถานะเอกสารทั้ง 20 ไฟล์ + Phase ที่รับผิดชอบ
- [x] TASK-009: PHASE 0 Gate — ตรวจ Definition of Done + อัปเดต Status ใน Progress Summary + รายงานผล (ตรวจ cross-reference พบ 2 จุดไม่สอดคล้อง แก้แล้ว: state EXPIRED_REF → CANCELLED, typo NO_NEW_TRAKE → NO_NEW_TRADE)

**Files:** `implementation_plan.md`, `docs/01-requirements.md`, `docs/02-system-architecture.md`, `docs/03-trading-domain.md`, `docs/04-database-design.md`, `docs/05-api-design.md`, `docs/architecture-decision-records/ADR-001..007.md`, `docs/README.md`

**Acceptance Criteria:**
- เอกสารทุกไฟล์ถูกสร้างครบตามรายการ Files
- ERD ครบ 30 tables ตาม Spec หัวข้อ 34 และ API Contract ครบทุก Module หลัก
- เอกสารทั้งหมดสอดคล้องกัน (ชื่อ Entity/Table/Endpoint/Enum เหมือนกันทุกไฟล์)
- หลักความปลอดภัย (AI ห้ามส่ง Order เอง, TRADING_MODE=PAPER, Confluence Rule) ปรากฏชัดในทุกเอกสารที่เกี่ยวข้อง

**Testing:** Documentation Review Checklist — ตรวจ cross-reference ชื่อ Table/Endpoint/Enum ระหว่างเอกสารให้ตรงกัน (ยังไม่มี Code ให้รัน Test)

**Risk:**
- เอกสารกว้างเกินไปจนไม่ตรงกับที่ implement → กันด้วยการให้แต่ละ Phase ถัดไปอัปเดตเอกสารของตัวเอง (Definition of Done ระบุ "Documentation updated")

---

## 6. PHASE 1 — Project Foundation

- **Objective:** วางโครงสร้างโปรเจกต์ที่รันได้จริงบน Native Windows — Backend shell + Frontend shell + PostgreSQL + Auth + Logging; Redis/Docker optional
- **Scope:** Scaffold, Infrastructure, Authentication, Database Migration Framework, Frontend Shell (ไม่รวม Business Logic การเทรด)
- **Dependencies:** PHASE 0 ✅
- **Status:** ✅ COMPLETED — TASK-020: native PostgreSQL 18.6 migration/auth/audit, Chromium login/session/logout and final regression passed. See docs/phase-1-gate.md. Stop before Phase 2 for independent review.

**Tasks:**

- [x] TASK-010: Initialize Repository — `git init`, `.gitignore`, สร้างโครงสร้าง Folder ตามหัวข้อ 4, `README.md`, `.env.example` (ไม่มี Secret จริง)
- [x] TASK-011: Backend Scaffold — FastAPI + pyproject.toml + app/core (settings จาก Environment Variables, structured logging + correlation ID) + `/healthz` `/readyz` + Lint (ruff) + Typecheck (mypy) + pytest setup
- [x] TASK-012: Frontend Scaffold — Next.js + TypeScript + Tailwind + ESLint + main layout + Main Navigation (16 เมนูตาม Spec หัวข้อ 30) + placeholder pages
- [x] TASK-013: Docker Compose — services: postgres (TimescaleDB image), redis, backend, frontend + volumes + healthchecks + dev overrides
- [x] TASK-014: Database Foundation — Alembic migrations + `users`, `accounts`, `symbols`, `audit_logs`, `system_events` + connection pooling
- [x] TASK-015: Redis Integration — connection management + cache utility + pub/sub helper + health check
- [x] TASK-016: Authentication — JWT (access + refresh), password hashing, session management, RBAC roles (ADMIN/TRADER/VIEWER), login/logout/me endpoints + rate limiting พื้นฐาน
- [x] TASK-017: Audit Logging Service — audit_logs writer (timestamp, user, action, entity, entity_id, before, after, reason, source, correlation_id) + ทดสอบบันทึกจริง
- [x] TASK-018: Frontend Auth + API/WS Client — login page, protected routes, auth store (Zustand), typed REST client, WebSocket client พร้อม reconnect
- [x] TASK-019: Security Baseline — CORS policy, input validation middleware, sensitive data masking ใน log, secret management ผ่าน env เท่านั้น
- [x] TASK-020: PHASE 1 Gate — Build + Test + Verify + DoD review complete: 36 backend tests including native PostgreSQL migration up/down/up, constraints, transactions, auth/audit; 6 frontend tests; real Chromium login/reload/refresh/logout; lint/typecheck/build pass. See [Phase 1 gate evidence](docs/phase-1-gate.md). Phase 2 not started.

**Files:** `.gitignore`, `README.md`, `.env.example`, `docker-compose.yml`, `backend/**` (core + api + db + models + tests), `frontend/**` (app shell + stores + lib), `docs/18-devops.md` (อัปเดต)

**Acceptance Criteria:**
- Native Windows backend :8000 responds at /healthz and frontend :3000 provides shell/login without Docker/WSL; Docker Compose is an optional deployment check
- Login ด้วย user จริง (จาก DB) ผ่าน JWT และ audit log บันทึก Login event
- Migration รันได้ และ rollback ได้
- Lint + Typecheck + Unit test ผ่านทั้ง backend และ frontend

**Testing:** Native unit/API tests (auth, audit, health, optional Redis behavior), isolated SQLite migration + PostgreSQL offline DDL, opt-in native PostgreSQL migration up/down/auth/audit, native HTTP/browser smoke; real Redis/Compose tests optional

**Risk:** Windows async driver compatibility → shared selector event-loop factory for psycopg entry points; document tested dependencies. Missing PostgreSQL blocks only actual DB integration evidence; run independent checks and keep TASK-020 unchecked.

---


## 7. PHASE 2 — Market Data & Realtime Chart

- **Objective:** ระบบ Market Data ครบวงจร — รับข้อมูลราคา, สร้าง Candles 9 Timeframes, เก็บลง TimescaleDB, ส่งต่อผ่าน WebSocket และแสดง Chart แบบ Realtime
- **Scope:** Symbol Management, Market Data Provider (Replay/Demo), Tick→Candle Aggregation, WebSocket API, TradingView Chart (XAUUSD)
- **Dependencies:** PHASE 1 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-021: Symbol Management — CRUD + seed XAUUSD (contract size, digits, spread config, session hours) + `GET /api/symbols`
- [ ] TASK-022: Market Data Provider Interface — abstract `MarketDataProvider` (connect, subscribe ticks, fetch history) + **ReplayProvider** (เล่นข้อมูลย้อนหลัง/simulated เพื่อพัฒนาโดยไม่ต้องพึ่ง Broker จริง) + provider registry ตาม config
- [ ] TASK-023: Tick Ingestion Pipeline — รับ tick (bid/ask/spread/volume), ตรวจ stale/abnormal price, เก็บลง `ticks` hypertable, publish ไป Redis pub/sub
- [ ] TASK-024: Candle Aggregation Engine — สร้าง/อัปเดต candles จาก M1 base: M1, M3, M5, M15, M30, H1, H4, D1, W1 (OHLCV, bid/ask close) + แก้ไข candle ที่ยังไม่ปิด
- [ ] TASK-025: Candle Persistence & Query — `candles` hypertable + `GET /api/market/candles?symbol&timeframe&from&to` + pagination
- [ ] TASK-026: Realtime WebSocket — `/ws/market` (subscribe/unsubscribe by symbol+timeframe, push tick + candle update) + heartbeat + reconnect protocol
- [ ] TASK-027: Frontend Chart — TradingView Lightweight Charts + realtime candle update + Timeframe Selector + Symbol Selector + Bid/Ask/Spread/Market Status bar
- [ ] TASK-028: Market Data Freshness Monitoring — worker ตรวจอายุข้อมูล + แจ้งเตือน + `system_events` เมื่อ stale/abnormal (ต่อเข้า Kill Switch ใน PHASE 5)
- [ ] TASK-029: PHASE 2 Gate — Build + Test + Verify + DoD review + รายงานผล + อัปเดต `docs/06-market-data.md`

**Files:** `backend/app/services/market_data/**`, `backend/app/api/market.py`, `backend/app/workers/market_data_worker.py`, `frontend/src/features/chart/**`, `docs/06-market-data.md`

**Acceptance Criteria:**
- รันด้วย ReplayProvider แล้ว Chart XAUUSD อัปเดต realtime ผ่าน WebSocket ได้ทุก Timeframe ที่กำหนด
- Candle ที่สร้างจาก tick ถูกต้อง (ตรวจสอบเทียบกับข้อมูลต้นทาง) และ candle ที่ยังไม่ปิดอัปเดต in-place ได้
- API ดึงประวัติ candle ถูกต้อง + รองรับหลาย Symbol (schema) แม้ v1 จะ seed แค่ XAUUSD
- Stale detection ทำงาน (ทดสอบด้วยการหยุด feed)

**Testing:** Unit test (aggregation, timeframe bucketing, stale detector), Integration test (tick→candle→DB→WS e2e), Frontend component test (chart render, tf selector)

**Risk:** ไม่มีข้อมูลจริงในช่วงพัฒนา → ReplayProvider + ข้อมูล historical สังเคราะห์; ปริมาณ tick ใหญ่ → batch insert + retention policy ของ TimescaleDB

---

## 8. PHASE 3 — Analysis Engines (Structure / Liquidity / SMC / Indicators / Regime)

- **Objective:** สร้าง Analysis Engines แยก Module ชัดเจน — Market Structure, Liquidity, SMC/ICT, Indicators, Sessions, Market Regime และ Multi-Timeframe Bias Aggregation + แสดงผลบน Chart
- **Scope:** 5 Engines + Session Engine + MTF Aggregation + Chart Overlays (ยังไม่มี Strategy/Signal)
- **Dependencies:** PHASE 2 ✅ (ต้องมี candles)
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-030: Market Structure Engine — Swing High/Low (fractal), HH/HL/LH/LL, BOS, CHoCH, MSS + แยก Internal / External Structure + version ผลลัพธ์ต่อ candle
- [ ] TASK-031: Liquidity Engine — PDH/PDL, PWH/PWL, Asian/London/NY High-Low, Equal High/Low, Buy-side/Sell-side Liquidity, Liquidity Sweep/Grab detection
- [ ] TASK-032: SMC/ICT Engine — Order Block, Breaker Block, FVG, IFVG, Premium/Discount/Equilibrium, OTE + Confluence Model (เก็บเป็น structured zones)
- [ ] TASK-033: Indicator Engine — ATR, RSI, EMA/SMA, ADX, Bollinger, Volume avg + framework เพิ่ม indicator ได้
- [ ] TASK-034: Session Engine — Asian/London/NY sessions (config ได้), overlap detection, current session + ประวัติ session levels
- [ ] TASK-035: Market Regime Engine — จำแนก TRENDING_UP/TRENDING_DOWN/RANGING/HIGH_VOLATILITY/LOW_VOLATILITY/BREAKOUT/PULLBACK/NEWS_CONDITION/UNKNOWN ต่อ Timeframe
- [ ] TASK-036: Multi-Timeframe Analysis — Top-Down (D1→H4→H1→M15→M5) แยกวิเคราะห์ต่อ TF + Aggregate เป็น Market Bias + `GET /api/analysis/*`
- [ ] TASK-037: Chart Overlays — แสดง Structure (BOS/CHoCH/MSS), Liquidity levels, FVG, Order Blocks, Sessions บน Chart (toggle ได้)
- [ ] TASK-038: PHASE 3 Gate — Build + Test + Verify + DoD + อัปเดต `docs/07-market-structure.md`, `docs/08-smc-ict.md`

**Files:** `backend/app/services/analysis/**`, `backend/app/api/analysis.py`, `frontend/src/features/chart/overlays/**`, `docs/07-market-structure.md`, `docs/08-smc-ict.md`

**Acceptance Criteria:**
- Engine ทุกตัวเป็น pure function ของ candle data (deterministic, testable ย้อนหลังได้)
- ตรวจสอบผล BOS/CHoCH/MSS/FVG/OB/Liquidity Sweep กับชุดข้อมูลที่รู้ผลลัพธ์ (golden dataset) ได้ถูกต้อง
- MTF Bias แสดงผลบน UI พร้อมเหตุผล (evidence ระดับ TF) และแสดง zones บน Chart ได้
- ยังไม่มีการสร้าง Signal ใด ๆ ใน Phase นี้

**Testing:** Unit test ทุก engine ด้วย golden dataset + synthetic candles, Integration test (candles→analysis→API→chart overlay), Property test (aggregation ไม่แตกเมื่อข้อมูล edge case)

**Risk:** นิยาม SMC หลายสำนัป → เลือกนิยามชัดเจนใน `docs/08-smc-ict.md` + ทำ parameters configurable; การ detect ผิดพลาด → ทุก detection ต้องมี confidence/parameter และผ่าน golden dataset ก่อนใช้

---

## 9. PHASE 4 — Strategy Engine & Signal Engine

- **Objective:** สร้าง Strategy Framework แบบ Plug-in + 5 Strategies ตาม Spec + Signal Engine ที่สร้าง Trade Plan ครบองค์ประกอบ
- **Scope:** Strategy Framework, 5 Built-in Strategies, Trading Modes, Signal Engine, Trade Plan (ยังไม่มี Risk Engine จริง — เรียกผ่าน interface stub ที่ PHASE 5 มา replace)
- **Dependencies:** PHASE 3 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-039: Strategy Framework — `Strategy` interface (entry condition, invalidation, SL logic, TP logic, risk rule, session rule, regime rule) + registry + config schema + enable/disable per account
- [ ] TASK-040: Strategy 1 — Liquidity Sweep + MSS + FVG (Confluence ตาม Spec หัวข้อ 9)
- [ ] TASK-041: Strategy 2 — Trend Pullback (HTF bias + pullback สู่ zone + confirmation)
- [ ] TASK-042: Strategy 3 — Breakout Momentum (regime BREAKOUT + volume/momentum filter)
- [ ] TASK-043: Strategy 4 — Mean Reversion (regime RANGING + premium/discount)
- [ ] TASK-044: Strategy 5 — Run Trend (trend continuation + trailing)
- [ ] TASK-045: Trading Modes — SCALP / DAY_TRADE / SWING / RUN_TREND + config แยกกัน (timeframe, risk, min RR, max holding, trailing, partial close)
- [ ] TASK-046: Signal Engine & Trade Plan — สร้าง `signals` + `signal_evidence` + `trade_plans` ครบทุกฟิลด์ตาม Spec หัวข้อ 18 + expiration + invalidation + Confluence Gate (ห้าม signal เดี่ยวเป็น entry)
- [ ] TASK-047: PHASE 4 Gate — Build + Test + Verify + DoD + อัปเดต `docs/09-strategy-engine.md`

**Files:** `backend/app/services/strategy/**`, `backend/app/services/trading/signal_engine.py`, `backend/app/models` (strategies, strategy_configs, signals, signal_evidence, trade_plans), `frontend/src/features/signals/**`, `docs/09-strategy-engine.md`

**Acceptance Criteria:**
- เพิ่ม Strategy ใหม่ได้โดยไม่แก้ engine code (plug-in ผ่าน registry + config)
- ทุก signal มี evidence ครบ + Confluence rule บังคับใช้จริง (test ยืนยันว่า signal ที่ไม่ผ่าน confluence ถูกปฏิเสธ)
- Trade Plan ครบทุกฟิลด์ตาม Spec หัวข้อ 18 + มี expiration และ invalidation
- ทุก strategy ระบุ Market Regime ที่รองรับและปฏิเสธ regime อื่นจริง

**Testing:** Unit test ทุก strategy บน synthetic + golden dataset, Confluence gate tests, Trade plan schema validation tests, Signal lifecycle tests (create→expire)

**Risk:** Overfit กับข้อมูลทดสอบ → กันด้วย PHASE 9 (backtest + walk-forward) ก่อนถือว่า strategy ใช้ได้จริง; Signal ปลอมเกิน → strict confluence + min RR gate

---

## 10. PHASE 5 — Risk Engine & Kill Switch

- **Objective:** สร้าง Critical Component ที่ต้องมีก่อนการเทรดจริง — Risk Engine ครบทุก Rule, Position Sizing, Kill Switch, Risk Dashboard
- **Scope:** Risk Config, Risk Check Pipeline (ทุก rule ตาม Spec หัวข้อ 16), Position Sizing, Kill Switch (ทุก trigger ตาม Spec หัวข้อ 17), Risk Dashboard UI, Risk Events Audit
- **Dependencies:** PHASE 4 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-048: Risk Config Management — `risk_configs` + API + validation (risk per trade, max daily/weekly loss, max DD, max concurrent, exposure ต่อ symbol/correlated, min RR, max spread/slippage, min free margin, news protection, session restriction) — ทุกค่ามาจาก config ห้าม hardcode
- [ ] TASK-049: Risk Check Pipeline — ประเมินทุก trade plan → `APPROVED` / `REJECTED` / `REDUCE_SIZE` / `WAIT` + reason ทุกกรณี + `risk_events` บันทึกผล
- [ ] TASK-050: Position Sizing Engine — คำนวณ lot size จาก risk % + SL distance + contract spec + margin check (XAUUSD ก่อน)
- [ ] TASK-051: Kill Switch — triggers: daily/weekly loss exceeded, max DD, broker disconnected, market data stale/abnormal, spread abnormal, price gap abnormal, AI unavailable, DB unavailable, reconciliation error + manual kill + **หยุดเปิด position ใหม่ทันทีแต่ไม่ทิ้ง position เปิดอยู่** + ต้องมี manual reset โดยเจตนา
- [ ] TASK-052: Risk Dashboard UI — Balance, Equity, Floating PnL, Today/Weekly PnL, Drawdown, Daily Risk Used, Open Risk, Exposure, Limits, Trading Status, Kill Switch Status
- [ ] TASK-053: Risk Events & Audit — บันทึกทุก risk decision + kill switch trigger/reset ลง `risk_events` + `audit_logs`
- [ ] TASK-054: PHASE 5 Gate — Build + Test + Verify + DoD + อัปเดต `docs/11-risk-engine.md`

**Files:** `backend/app/services/risk/**`, `backend/app/api/risk.py`, `frontend/src/features/risk/**`, `docs/11-risk-engine.md`

**Acceptance Criteria:**
- Risk Engine เป็น **Gate เดียว** ของการเทรด — ทุก trade (paper/live) ต้องผ่าน `risk_engine.evaluate()` ก่อนเสมอ (architectural enforcement + test)
- ครบทุก rule ตาม Spec หัวข้อ 16 และ return 4 สถานะ + reason ได้ถูกต้อง
- Kill Switch ทดสอบ trigger ได้ทุกเคส + หยุด new position ทันที + position management ยังทำงานต่อ
- แก้ risk config ผ่าน API ได้ + audit ครบ (before/after)

**Testing:** Unit test ทุก rule (ผ่าน/ไม่ผ่าน/ขอบเขต), Kill switch trigger tests ทุกเคส, Integration test (signal→risk→approved/rejected), API test, Critical test cases: Risk เกิน limit, Daily loss limit, Drawdown limit

**Risk:** Risk rule ผิดพลาด = ความเสียหายจริง → บังคับ unit test ครบทุก rule + default config อนุรักษ์นิยม; Kill switch ล็อกตัวเอง → manual reset + audit

---

## 11. PHASE 6 — AI Analysis Engine (Multi-Agent)

- **Objective:** สร้าง AI Analysis ตามสถาปัตยกรรม "AI = Reasoning ไม่ใช่ Order Sender" — Multi-Agent + Decision Agent + Confidence Engine + AI Panel + Economic Calendar/News Filter
- **Scope:** AI Provider Abstraction, Feature Extraction → Structured Context, 8 Analysis Agents + Decision Agent, Schema Validation, Confidence (Weighted Evidence), AI Panel UI, News Agent + Economic Calendar
- **Dependencies:** PHASE 3, 4, 5 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-055: AI Provider Abstraction — LLM adapter (config ผ่าน env, รองรับหลาย provider) + timeout/retry/fallback + AI unavailable detection (ต่อ Kill Switch)
- [ ] TASK-056: Feature Extraction & Context Builder — รวมผลจาก Engines (structure/liquidity/smc/regime/indicators/sessions) เป็น structured context ให้ agents (ห้ามส่ง raw chart ให้ LLM ตัดสิน buy/sell)
- [ ] TASK-057: Analysis Agents 1–8 — Trend, Structure, Liquidity, SMC, Momentum, Volatility, News, Risk — แต่ละตัวคืน structured result + evidence
- [ ] TASK-058: Decision Agent — aggregate ผล agents → Trade Recommendation (structured JSON ตาม Spec หัวข้อ 14) + **Pydantic schema validation ทุกครั้ง** (AI Invalid JSON → reject + บันทึก) + บันทึก `ai_analysis` + `ai_agent_results`
- [ ] TASK-059: Confidence Engine — weighted evidence (HTF trend, structure, liquidity, SMC, momentum, volatility, session, news, historical performance, risk quality) + weights configurable + **audit ได้ว่า confidence มาจากอะไร** — ห้าม LLM สุ่ม confidence
- [ ] TASK-060: AI Panel UI — Market Bias, Regime, Trend, Structure, Liquidity, Momentum, Volatility, News Status, Confidence, Strategy, Entry/SL/TP/RR/Risk/Size, Evidence, Invalidation + ปุ่ม Create Paper Trade / Confirm / Reject
- [ ] TASK-061: Economic Calendar & News Filter — `economic_events` (CPI, PPI, NFP, FOMC, Fed Rate, Powell Speech, PCE, GDP, Unemployment, ISM, Jobless Claims) + rules: -30 นาที no new trade, -10 นาที reduce risk, ช่วงข่าว disable auto entry, หลังข่าว cooling period — **ทุกค่า configurable**
- [ ] TASK-062: PHASE 6 Gate — Build + Test + Verify + DoD + อัปเดต `docs/10-ai-engine.md`

**Files:** `backend/app/services/ai/**`, `backend/app/api/ai.py`, `backend/app/services/notification/news.py`, `frontend/src/features/ai/**`, `docs/10-ai-engine.md`

**Acceptance Criteria:**
- AI ทุก output ผ่าน Pydantic validation — JSON ไม่ valid ถูกปฏิเสธ (มี test ยืนยัน)
- Decision Agent **ไม่มี** เส้นทางไปที่ Broker/OMS โดยตรง (architectural test) — output เป็น `trade_status: WAITING_CONFIRMATION` เท่านั้น
- Confidence คำนวณจาก weighted evidence + บันทึก breakdown ลง DB ตรวจสอบย้อนหลังได้
- News filter บล็อก/ลด risk ตาม rule config ได้จริง (test ทุกช่วงเวลา)

**Testing:** Unit test (confidence weights, news window logic), AI mock tests (invalid JSON, timeout, unavailable), Schema validation tests, Integration test (context→agents→decision→validation), Critical cases: AI Invalid JSON, AI Timeout

**Risk:** LLM hallucination → structured input + schema validation + AI ไม่มีอำนาจสั่งเทรด; ค่าใช้จ่าย API → cache + rate limit + config; Provider down → fallback/degraded mode + Kill Switch trigger

---

## 12. PHASE 7 — Paper Trading & Order Management

- **Objective:** ระบบ Paper Trading ใช้ข้อมูลจริงแต่ order เป็น virtual + OMS State Machine + Duplicate Protection + Position Management ครบ
- **Scope:** OMS (state machine + audit), Idempotency/Duplicate Protection, Paper Broker (spread/commission/slippage simulation), Paper Account/Orders/Positions, Position Management (BE/trailing/partial/time stop), Trading Screen UI
- **Dependencies:** PHASE 5 ✅ (Risk Engine บังคับผ่านก่อน order), PHASE 6 (AI Panel สร้าง paper trade ได้)
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-063: OMS State Machine — SIGNAL_CREATED → RISK_CHECK → WAITING_CONFIRMATION → APPROVED → ORDER_SUBMITTED → BROKER_ACCEPTED → PARTIALLY_FILLED → FILLED → POSITION_OPEN → PARTIAL_CLOSE → POSITION_CLOSED (+ CANCELLED/REJECTED/ERROR) — **ทุก transition บันทึก `order_events` + audit**
- [ ] TASK-064: Duplicate Order Protection — Idempotency Key + Client Order ID (unique constraint) + order lock (Redis) + state validation — กัน double click / retry ทุกชนิด
- [ ] TASK-065: Paper Broker Engine — จำลอง fill จากราคาจริง: entry, spread, commission, slippage, SL/TP execution, partial close, position size, equity/balance/drawdown tracking
- [ ] TASK-066: Paper Account Management — `paper_accounts` / `paper_orders` / `paper_positions` + API + reset/seed เงินต้น + equity curve history
- [ ] TASK-067: Position Management Engine — Break Even, Trailing Stop, Partial Close (TP1/TP2/TP3 เช่น 30/30/40), Scale Out, Structure-based Stop, Time Stop, Dynamic Stop, Run Trend — ทำงานเป็น background worker กับราคา realtime + config ได้
- [ ] TASK-068: Trading Screen UI — Symbol selector, realtime price/bid/ask/spread, chart + levels (entry/SL/TP lines), order ticket + risk panel + **Trade Confirmation dialog**, open positions/orders พร้อม action ปิด/แก้ไข
- [ ] TASK-069: PHASE 7 Gate — Build + Test + Verify + DoD + อัปเดต `docs/12-order-management.md`, `docs/13-paper-trading.md`

**Files:** `backend/app/services/trading/**` (oms, paper, positions), `backend/app/services/broker/paper_broker.py`, `backend/app/api/trading.py`, `frontend/src/features/trading/**`, `docs/12-order-management.md`, `docs/13-paper-trading.md`

**Acceptance Criteria:**
- ทุก order ผ่าน Risk Engine ก่อนเสมอ + ทุก state transition มี event + audit
- ส่ง order ซ้ำ (double click / retry 3 ทาง) ไม่เกิด position ซ้ำ — test ยืนยัน
- Paper trading PnL/equity/drawdown คำนวณถูกต้องเทียบกับ manual calc บน golden scenario
- Position management rules ทำงานบน scenario test (BE move, trailing, partial TP)
- ทั้งหมดนี้เกิดในโหมด PAPER เท่านั้น (TRADING_MODE=PAPER)

**Testing:** OMS state tests (ทุก transition + invalid transition ถูกปฏิเสธ), Idempotency tests, Paper fill simulation tests, Position management scenario tests, API tests, E2E: signal→confirm→fill→manage→close→journal

**Risk:** State bug ทำให้ order ค้าง → invalid transition ต้อง reject + alert; Sim ผลลัพธ์ไม่เหมือนจริง → conservative slippage/commission defaults + ปรับได้

---

## 13. PHASE 8 — Trade Journal & Analytics

- **Objective:** บันทึกทุก trade ครบฟิลด์ + Analytics Dashboard วิเคราะห์ performance ทุกมุม + Confidence Calibration
- **Scope:** Journal auto-capture + manual notes, Analytics Engine, Performance Dashboard
- **Dependencies:** PHASE 7 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-070: Trade Journal Service — auto-capture ทุกฟิลด์ตาม Spec หัวข้อ 27 (date/time, symbol, direction, strategy, mode, regime, entry/SL/TP, size, risk, RR, AI confidence/evidence, session, result, PnL, MFE/MAE, duration, exit reason, screenshot ref) + manual notes/tags
- [ ] TASK-071: Journal UI — รายการ trades + filter (date/symbol/strategy/session/result) + detail view + notes + screenshot upload reference
- [ ] TASK-072: Analytics Engine — Win Rate, Profit Factor, Expectancy, Avg RR, Max DD, Max Consecutive Loss, Sharpe, Sortino, Equity Curve, Monthly Return + Breakdown: strategy/setup/timeframe/session/day-of-week/long-vs-short/regime
- [ ] TASK-073: Confidence Calibration — group ตาม AI confidence bucket (เช่น 80–90%) เทียบ actual win rate + แสดงบน dashboard
- [ ] TASK-074: PHASE 8 Gate — Build + Test + Verify + DoD + อัปเดต `docs/09-strategy-engine.md` (ส่วน analytics)

**Files:** `backend/app/services/journal/**`, `backend/app/api/journal.py`, `backend/app/api/analytics.py`, `frontend/src/features/journal/**`, `frontend/src/features/analytics/**`

**Acceptance Criteria:**
- ทุก trade ที่ปิด (paper) มี journal entry ครบฟิลด์อัตโนมัติ (ทดสอบยืนยัน)
- ตัวเลข analytics ตรงกับคำนวณมือบน golden dataset
- Confidence calibration ตอบคำถาม "AI 80–90% ชนะจริงกี่ %" ได้

**Testing:** Unit test metric calculations (golden dataset), Journal capture integration test, API tests

**Risk:** ข้อมูล journal ไม่ครบ → บังคับที่ point of close (transaction); Metric ผิด → golden dataset tests

---

## 14. PHASE 9 — Backtesting & Walk-Forward

- **Objective:** Backtest Engine ที่เทียบเคียงกับ Paper Trading Engine ได้ + Walk-Forward Validation + Strategy Comparison
- **Scope:** Historical data import, Backtest Engine (multi-TF, cost model, sessions, news filter), Metrics Report, Walk-Forward, Comparison UI
- **Dependencies:** PHASE 4, 7, 8 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-075: Historical Data Management — import candles (CSV/API) + quality check (gap detection) + backfill tool
- [ ] TASK-076: Backtest Engine — รัน strategy บน historical data แบบ event-driven (ใช้ engine ชุดเดียวกับ live ที่ทำได้) + spread/commission/slippage + trading session + news filter (ถ้ามี data)
- [ ] TASK-077: Backtest Metrics — ทุก metric ตาม Spec หัวข้อ 25 + equity curve + monthly return + session breakdown + strategy breakdown + เก็บ `backtest_runs` / `backtest_trades`
- [ ] TASK-078: Walk-Forward Testing — train/validation split + out-of-sample + ห้าม optimize จาก dataset เดียว (enforce ใน tooling)
- [ ] TASK-079: Backtesting UI — config run, ผลลัพธ์, equity curve, trade list, strategy comparison
- [ ] TASK-080: Backtest → Journal Integration — ส่ง backtest trades เข้า analytics ชุดเดียวกับ paper/live เพื่อเทียบ
- [ ] TASK-081: PHASE 9 Gate — Build + Test + Verify + DoD + อัปเดต `docs/14-backtesting.md`

**Files:** `backend/app/services/backtest/**`, `backend/app/api/backtest.py`, `frontend/src/features/backtesting/**`, `docs/14-backtesting.md`

**Acceptance Criteria:**
- Backtest 5 strategies หลักได้ + ผลชุดเดียวกันรันซ้ำได้ deterministic
- Cost model (spread/commission/slippage) มีผลต่อผลลัพธ์จริง (test ยืนยัน)
- Walk-forward รันได้ + รายงาน out-of-sample แยกจาก in-sample
- Look-ahead bias ถูกป้องกัน (test: engine เห็นเฉพาะข้อมูลถึงเวลา t)

**Testing:** Look-ahead bias tests, Determinism tests, Metric validation vs golden dataset, Engine equivalence test (backtest engine vs paper engine บนข้อมูลเดียวกัน)

**Risk:** Overfitting → walk-forward บังคับ + ห้าม optimize จาก dataset เดียว; Data quality → gap detection + reject ช่วงข้อมูลเสีย

---

## 15. PHASE 10 — Broker Adapter (MT5 Demo)

- **Objective:** สร้าง BrokerAdapter interface + MT5Adapter เชื่อมต่อ **Demo account เท่านั้น** — ยังไม่มี Live order ใด ๆ
- **Scope:** Broker Interface, MT5 Demo integration (data + account + orders), credential encryption, reconciliation, connection UI
- **Dependencies:** PHASE 7 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-082: BrokerAdapter Interface — connect/disconnect/get_account/get_symbol/get_price/get_positions/get_orders/place_order/modify_order/cancel_order/close_position/partial_close + BrokerConnection state + event callbacks
- [ ] TASK-083: MT5 Data Adapter — ดึง ticks/candles จาก MT5 demo เป็นอีก MarketDataProvider (ทางเลือกแทน ReplayProvider)
- [ ] TASK-084: MT5 Trading Adapter — order operations ผ่าน MT5 demo (เฉพาะ DEMO server) + enforce ที่ code level ว่า server ต้องเป็น demo
- [ ] TASK-085: Credential Encryption & Connection Management — `broker_connections` เข้ารหัส credentials (ไม่ส่งไป frontend เด็ดขาด) + connection health monitor + audit
- [ ] TASK-086: Reconciliation Process — เทียบ position/order ระหว่างระบบกับ broker + จัดการ mismatch + trigger kill switch เมื่อ reconcile error
- [ ] TASK-087: PHASE 10 Gate — Build + Test + Verify + DoD + อัปเดต `docs/15-broker-integration.md`

**Files:** `backend/app/services/broker/**`, `backend/app/api/broker.py`, `frontend/src/features/settings/broker/**`, `docs/15-broker-integration.md`

**Acceptance Criteria:**
- Broker trading logic แยกจาก business logic ทั้งหมด (ผ่าน interface เท่านั้น — review ยืนยัน)
- เชื่อมต่อ MT5 **demo** ได้: account info, prices, positions แสดงจริง
- สั่ง order บน demo ผ่าน OMS flow (risk → confirm → submit) ได้ และ **ปฏิเสธ server ที่ไม่ใช่ demo**
- Credentials เข้ารหัส + ไม่ปรากฏใน API response/log ใด ๆ (test ยืนยัน)

**Testing:** Broker adapter mock tests (ทุก method + error cases), Demo integration smoke test, Reconciliation tests (match/mismatch), Critical cases: Broker Disconnect, Partial Fill, Order timeout, Broker accepted but API timeout

**Risk:** Live order โดยไม่ตั้งใจ → demo-server whitelist + TRADING_MODE=PAPER + live gate ใน PHASE 14; MT5 lib เฉพาะ Windows → พัฒนาบน Windows, deploy ผ่าน container สำหรับ service อื่น

---

## 16. PHASE 11 — Semi-Automatic Trading

- **Objective:** เปิดเส้นทาง AI Signal → Risk Engine → **Human Confirmation** → Broker (demo) — มนุษย์กดยืนยันทุก order เท่านั้น
- **Scope:** Confirmation flow end-to-end, Confirmation UI, Order routing ภายใต้ TRADING_MODE=SEMI_AUTO
- **Dependencies:** PHASE 6, 10 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-088: Confirmation Flow — signal ที่ risk APPROVED เข้าสถานะ WAITING_CONFIRMATION + expiration + ปุ่ม Confirm/Reject (บันทึก audit + reason)
- [ ] TASK-089: Confirmation UI — หน้าจอยืนยันแสดง trade plan ครบ (entry/SL/TP/RR/risk/size/evidence/invalidation) + ต้องกดยืนยัน 2 ขั้น (review + confirm)
- [ ] TASK-090: Order Routing (SEMI_AUTO) — confirmed signal → OMS → broker (demo) โดย risk re-check ก่อน submit จริง + slippage/spread guard ขั้นสุดท้าย
- [ ] TASK-091: PHASE 11 Gate — Build + Test + Verify + DoD + อัปเดต `docs/12-order-management.md`

**Files:** `backend/app/services/trading/confirmation.py`, `frontend/src/features/trading/confirmation/**`, `docs/12-order-management.md`

**Acceptance Criteria:**
- ไม่มี order ใดถึง broker โดยไม่มี human confirmation record (architectural + audit test)
- Confirm หลัง signal expire ถูกปฏิเสธ; Risk re-check ต้นทุนสุดท้าย (spread/slippage) ทำงานจริง
- ทุก confirmation/rejection มี audit log ครบ

**Testing:** Confirmation lifecycle tests, Expired signal tests, Final risk guard tests, E2E semi-auto flow on demo

**Risk:** คนกดผิด → two-step confirm + แสดง risk ชัด; Latency ระหว่าง confirm กับ submit → re-check ราคา/risk ก่อน submit

---

## 17. PHASE 12 — Hardening (Security / Performance / Observability / DR)

- **Objective:** ยกระดับเป็นระดับ Production — Security ครบ, Performance โหลดได้, Observability ครบ, Disaster Recovery
- **Scope:** Security hardening, Load/performance, Metrics/monitoring, Failure handling ครบทุกเคสตาม Spec หัวข้อ 38, Backup/restore
- **Dependencies:** PHASE 1–11 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-092: Security Hardening — RBAC เต็มรูปแบบ, rate limiting, CORS/CSRF ตาม architecture, input validation ครบ, TLS-ready, MFA-ready, sensitive masking, security test suite
- [ ] TASK-093: Performance — DB index audit, query optimization, WS broadcast scaling, candle query cache, load test และแก้ปัญหา
- [ ] TASK-094: Observability — metrics (Prometheus format), error tracking, trading event logs, broker connectivity monitoring, market data freshness dashboard, correlation ID ทุก log
- [ ] TASK-095: Failure Handling ครบชุด — Redis unavailable, DB unavailable, WS dropped, order timeout, broker accepted but API timeout, duplicate callback, partial fill, stale/invalid price, unexpected spread, position mismatch + recovery runbook
- [ ] TASK-096: Disaster Recovery — DB backup/restore procedure + verify restore จริง + config recovery + RPO/RTO กำหนด
- [ ] TASK-097: PHASE 12 Gate — Build + Test + Verify + DoD + อัปเดต `docs/16-security.md`, `docs/18-devops.md`

**Files:** `backend/app/core/security.py`, `backend/app/core/metrics.py`, `docs/16-security.md`, `docs/18-devops.md`, runbooks

**Acceptance Criteria:**
- ผ่าน security test suite (auth bypass, injection, IDOR, secret exposure)
- Load test ผ่านเป้าหมายที่กำหนด (candle query, WS concurrent connections)
- Chaos test: หยุด Redis/DB/WS แล้วระบบ degrade อย่างปลอดภัย + recover ได้ (ไม่มี order ผิดปกติ)
- Restore DB จาก backup ได้จริงและข้อมูลถูกต้อง

**Testing:** Security tests, Load tests, Chaos/failure injection tests, Backup/restore drill

**Risk:** Scope ใหญ่ → แยก task ย่อยตามด้านบนและทำเป็นรอบ; Performance bottleneck ไม่รู้ตำแหน่ง → วัดก่อนแก้ (profile-first)

---

## 18. PHASE 13 — UAT & Regression

- **Objective:** ทดสอบระบบรวมเต็มรูปแบบ — Regression ทุก Critical Case, Load Test, Trading Simulation ยาว
- **Scope:** Regression suite, Load test, Extended paper trading simulation, UAT sign-off
- **Dependencies:** PHASE 12 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-098: Regression Test Suite — ครบทุก Critical Case ตาม Spec หัวข้อ 40 (risk เกิน limit, daily loss, drawdown, spread สูง, broker disconnect, duplicate order, partial fill, stale price, invalid SL, insufficient margin, AI invalid JSON, AI timeout, DB/Redis failure, WS reconnect, kill switch, trade close ระหว่าง connection failure)
- [ ] TASK-099: Load & Stability Test — จำลองผู้ใช้ + ข้อมูลตลาดต่อเนื่อง ตามเป้าที่กำหนด
- [ ] TASK-100: Trading Simulation — รัน paper trading ต่อเนื่อง (เป้า: ≥ 2 สัปดาห์) บนข้อมูลจริง/demo + ตรวจ journal + analytics + risk events
- [ ] TASK-101: UAT Sign-off — ตรวจผล simulation + แก้จนผ่าน + เอกสาร `docs/19-uat.md` + บันทึกผลการตรวจรับ

**Files:** `backend/tests/regression/**`, `docs/19-uat.md`, load test scripts

**Acceptance Criteria:**
- Regression suite ผ่าน 100% ของ Critical Cases
- Load test ผ่านเป้าหมายโดยไม่มี critical error
- Simulation ไม่มี critical incident (kill switch ทำงานถูก, ไม่มี order ผิดปกติ, journal ครบ)

**Testing:** ตัว Phase นี้คือ Testing ทั้งหมดของระบบ

**Risk:** พบ defect ช้า → regression รันอัตโนมัติทุก phase ตั้งแต่ PHASE 1; Simulation ระหว่างทางเจอ regime ไม่ครบ → ยืดระยะเวลา simulation

---

## 19. PHASE 14 — Production Readiness Review

- **Objective:** ตรวจรับครั้งสุดท้ายก่อนใช้งานจริง — โดย **LIVE_AUTO_TRADING ยังคงเป็น false**
- **Scope:** Readiness checklist, Environment separation (DEV/UAT/PROD), Final approval gate
- **Dependencies:** PHASE 13 ✅
- **Status:** ⬜ NOT STARTED

**Tasks:**

- [ ] TASK-102: Production Readiness Review — checklist ครบทุกด้าน (security, risk, ops, docs, runbook) ตาม `docs/20-production-readiness.md`
- [ ] TASK-103: Environment Separation — config DEV/UAT/PROD แยกจริง + TRADING_MODE ต่อ environment + ห้าม enable LIVE อัตโนมัติในทุก environment
- [ ] TASK-104: Final Approval Gate — บันทึกผลการอนุมัติ; **การเปิด LIVE ต้องเป็นการกระทำโดยเจตนาของผู้ดูแลระบบเท่านั้น** (ผู้พัฒนาเปิดเองไม่ได้)

**Files:** `docs/20-production-readiness.md`, environment configs

**Acceptance Criteria:**
- Checklist ผ่านครบพร้อม evidence
- ทุก environment มี TRADING_MODE ชัดเจนและ PROD = ไม่ใช่ LIVE
- มีบันทึก approval ชัดเจน (ใคร อนุมัติอะไร เมื่อไร)

**Testing:** Deployment smoke test ต่อ environment + config audit (หา LIVE flag ที่ถูกเปิดโดยไม่ได้ตั้งใจ)

**Risk:** เปิด LIVE ก่อนเวลา → gate + audit + ต้องมีการอนุมัติบันทึกไว้

---

## 20. Definition of Done (ใช้ร่วมทุก Task / Phase)

Task จะถือว่าเสร็จเมื่อครบทุกข้อ:

- [ ] Code implemented (หรือเอกสารสร้างครบ สำหรับ phase เอกสาร)
- [ ] Lint ผ่าน
- [ ] Typecheck ผ่าน
- [ ] Tests ผ่าน
- [ ] No Critical Error
- [ ] No unresolved import
- [ ] No duplicate implementation (ตรวจ codebase ก่อนสร้างของใหม่เสมอ)
- [ ] Documentation updated
- [ ] Acceptance Criteria ของ task/phase ผ่านครบ

**Phase Gate เพิ่มเติม:** Build ผ่าน + Test suite ผ่าน + Verify ด้วยหลักฐาน (evidence) + รายงานผลตามหัวข้อ 10 + อัปเดต Progress Summary ในไฟล์นี้

## 21. Working Rules (บังคับใช้ตลอดโปรเจกต์)

1. **ห้าม Trial-and-Error วนซ้ำ** — ทุกการแก้ code: Identify → Analyze → Plan → Implement → Verify
2. **ก่อนแก้ code ต้องระบุ** ปัญหา, Root Cause, files เกี่ยวข้อง, files ที่จะเปลี่ยน, ผลกระทบ, วิธี Verify
3. **ห้าม Duplicate Architecture** — search codebase ก่อนสร้าง component/hook/service/API/utility/type/model ใหม่เสมอ
4. **ห้าม Hardcode** — credentials, API keys, risk config, symbol config ต้องมาจาก Environment Variables / DB config เท่านั้น (`.env.example` ห้ามมี secret จริง)
5. **AI ห้ามส่ง Order เอง / ห้าม Bypass Risk Engine / ห้ามแก้ account risk / ห้าม override kill switch**
6. **ทุก signal ต้องผ่าน Confluence + Risk Validation** — ห้ามใช้ signal เดี่ยวเป็น entry
7. **Code ปัจจุบันคือ Source of Truth** — ห้าม rewrite ทั้งระบบโดยไม่จำเป็น

## 22. Stop Conditions

หากพบเหตุการณ์ต่อไปนี้ ให้**หยุดเฉพาะ operation ที่เสี่ยง** วิเคราะห์สาเหตุ เสนอ safe solution ก่อนเดินต่อ (ห้ามลบข้อมูลหรือ rewrite code โดยพลการ):

- Critical Architecture Conflict
- Database Migration Risk
- Data Loss Risk
- Secret Exposure
- Broker Live Order Risk
- Git Conflict
- Destructive Operation

## 23. รายงานผลระหว่างทำงาน (ทุก Phase)

รายงานเมื่อจบแต่ละ Phase ต้องมีครบ: **PHASE / Status / Completed (tasks) / Changed Files / Created Files / Tests (ผลการรันจริง) / Issues / Risks / Next Phase** — ห้ามตอบแค่ "Done" ต้องมี Evidence

## 24. Change Log

| วันที่ | เวอร์ชัน | การเปลี่ยนแปลง |
|---|---|---|
| 2026-09-08 | 1.0 | สร้างเอกสารครั้งแรก — Repository Audit + แผน 15 Phase (104 Tasks) ตาม Specification |
| 2026-09-08 | 1.1 | PHASE 0 COMPLETED — สร้าง docs 01–05 + ADR-001..007 + docs/README.md; ตรวจ cross-reference ผ่าน (แก้ 2 จุด: EXPIRED_REF, NO_NEW_TRAKE) |
| 2026-09-08 | 1.2 | PHASE 1 IN PROGRESS (10/11) — TASK-010..019 COMPLETED: Backend scaffold (FastAPI + auth + audit + Redis + DB migrations), Frontend scaffold (Next.js + 16 nav menus + 15 placeholder pages + login + auth store + API/WS client + protected routes), Docker Compose, Security baseline. เหลือ TASK-020 (Phase Gate). Evidence: ruff ✅, pytest 17/17 ✅, next build ✅ (20 routes) |
| 2026-09-08 | 1.3 | TASK-020 review: fixed auth loading/refresh/session recovery, safe validation errors, Docker packaging/dev overrides, health aliases and lint. Backend 21 tests + frontend 6 tests, lint/typecheck/build and local HTTP checks pass. Gate BLOCKED on Docker runtime and real PostgreSQL/Redis/browser integration; Phase 2 not started. Evidence: docs/phase-1-gate.md. |
| 2026-09-08 | 1.4 | User-directed native Windows Phase 1 continuation: DATABASE_URL and escaped credentials, Windows psycopg loop, Redis disabled by default, startup secret validation, isolated PostgreSQL test and native docs. Backend 35/frontend 6 tests and build/typecheck/lint/HTTP smoke pass. TASK-020 remains unchecked; Phase 1 PARTIAL (10/11), total 19/104. Only database integration is BLOCKED BY LOCAL POSTGRESQL; full browser login pending. Docker/WSL are not blockers. Phase 2 not started. |
| 2026-09-08 | 1.5 | TASK-020 / PHASE 1 COMPLETE (11/11; total 20/104). User installed PostgreSQL 18.6; authorized hidden-password setup created separate DEV/TEST databases and restricted roles. Real migration up/down/up, schema/constraints/transactions, persisted auth/audit and Chromium login/reload/refresh/logout pass. Fixed unbound Logout button using existing auth store. Final backend 36/frontend 6 tests, lint/typecheck/build pass. No Phase 2 work, commit or push. |
