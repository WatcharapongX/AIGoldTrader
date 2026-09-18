# Implementation Plan — AI-Assisted Trading Platform for XAUUSD & Forex

> [!IMPORTANT]
> ### AI CONTEXT NOTICE
> This document contains historical planning information and project roadmap tracking.
> - For authoritative **CURRENT operational state**, see [`docs/CURRENT_STATE.md`](file:///c:/AI%20Gold%20Trader/docs/CURRENT_STATE.md).
> - For **active task scope and current authorization**, see [`docs/CURRENT_BATCH.md`](file:///c:/AI%20Gold%20Trader/docs/CURRENT_BATCH.md).
> - Historical notes or phase authorizations in this document **MUST NOT** be interpreted as current authorization.
> - Coding agents must **NOT** read this entire document by default.

| รายการ | รายละเอียด |
|---|---|
| เอกสาร | `implementation_plan.md` — Single Source of Truth สำหรับติดตามความคืบหน้าของโปรเจกต์ |
| เวอร์ชัน | 2.5 |
| วันที่สร้าง | 2026-09-08 |
| อัปเดตล่าสุด | 2026-09-10 |
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

### Current authorization — 2026-09-09

คำสั่งล่าสุดคือ Targeted Forex Factory Integration เฉพาะ STRAT05–06
ใช้ official weekly JSON สำหรับ Schedule/Forecast/Previous; Actual ที่ไม่มียังคงเป็น null
STRAT01–04 แยก market safety, candidate identity และ cache ออกจากข่าว
Xoomar เก็บไว้เป็นทางเลือก ไม่มีการรวม Actual ข้ามแหล่งโดยอัตโนมัติ
ห้าม Risk Engine, AI decision, order/execution, position management และ Git mutation
รายงานตรวจรับ: [Forex Factory news strategies](docs/forex-factory-news-strategies.md)
STOP ก่อน Phase5 รอ COMBINED SOL HIGH REVIEW; จำนวน Phase tasks เดิมไม่เปลี่ยน

### Progress Summary

| Phase | ชื่อ | Status | Tasks เสร็จ/รวม |
|---|---|---|---|
| 0 | Foundation Documents & Architecture | ✅ COMPLETED | 9/9 |
| 1 | Project Foundation | ✅ COMPLETED — Independent Re-review PASS WITH MINOR ISSUES; P1-001 verified | 11/11 |
| 1.1 | Foundation Hardening | Independent Gate PASS reported by user | 3/3 |
| 2 | Market Data & Realtime Chart | Independent Gate PASS reported by user; historical evidence preserved | 9/9 |
| 2.5 | Real Market Data | PASS under Safe-Partial Rule reported by user — W1 231/300 retained | 8/9 foundation tasks |
| 3 | Analysis Engines (Structure / Liquidity / SMC / Regime) | Independent Gate PASS reported by user | 9/9 |
| 3.5 | Economic Calendar / News / Macro Context | IMPLEMENTATION COMPLETE — PENDING INDEPENDENT REVIEW | 12/12 |
| 3.5R | Real Economic Calendar | PARTIAL — real keyless subset connected; richer coverage pending | 5/6 |
| 4 | Strategy / Trader Profile / Setup / Trade Plan | IMPLEMENTATION COMPLETE — PENDING COMBINED SOL HIGH REVIEW | 9/9 |
| 4.1 | Dashboard Command Center | IMPLEMENTATION COMPLETE — PENDING COMBINED REVIEW | 5/5 |
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
| | **รวม** | | **80/139** (original 104 + 3 hardening + 9 real-data + 12 news + 6 provider + 5 dashboard tasks) |

---

## 1. Current Repository Assessment (PHASE 0 — ตรวจสอบแล้ว 2026-09-08)

- Workspace: `C:\AI Gold Trader` — **ว่างเปล่า ไม่มีไฟล์ใด ๆ** (ไม่มี README, AGENTS.md, package.json, requirements.txt, docs/ ฯลฯ)
- Git: ไม่มี Repository (ยังไม่ได้ `git init`)
- Technology Stack ปัจจุบัน: ไม่มี
- Code เดิม: ไม่มี → เป็น **Greenfield Project** ไม่มี Source of Truth เดิม ไม่ต้องกังวลเรื่อง Rewrite
- ข้อสรุป: สร้าง Architecture และ Project Structure ใหม่ทั้งหมดตาม Specification นี้

### Current Phase 1 assessment — 2026-09-09

- Source contains FastAPI auth/audit/health + six-table Alembic foundation, Next.js shell/auth/client and tests.
- Branch main, baseline commit 857e764; P1-001 corrective changes are uncommitted. No commit or push in this round.
- Initial TASK-020 PASS (36 backend / 6 frontend tests) was invalidated by independent review FAIL:
  four JSON/JSONB columns and refresh-session uniqueness drift. TASK-020 was reopened before corrective code work.
- Corrective revision 0002_phase1_schema_alignment follows unchanged 0001_initial. Existing DEV data fingerprints
  and table/index identities match before/after upgrade; real TEST fresh/rollback/re-upgrade all pass.
- Canonical refresh-session uniqueness is the existing unique index; ORM now matches it with unique=True, index=True.
- Real PostgreSQL alembic check passes. The automated integration gate catches both deliberately introduced drift classes.
- Reverification: backend 37 tests including 2 PostgreSQL integration tests, frontend 6 tests, lint/typecheck/build,
  native startup/health/readiness, Chromium login/reload/refresh/logout and JSONB audit persistence PASS.
- TASK-010..020 complete again (11/11; total 20/104). Phase 1 technical gate PASS; Independent Sol High Re-review pending.
- Phase 2: DO NOT START / NO-GO. P2-001, P2-002, P2-003, P2-R01 and P3-001 remain UNCHANGED.
- Native PostgreSQL 18.6 remains running; restricted DEV/TEST roles and ignored configuration are preserved.
  PAPER / live_auto_trading=false / Redis disabled remain in effect. See docs/phase-1-gate.md for the full evidence trail.

### Independent re-review and Phase 1.1 authorization — 2026-09-09

User-provided Independent Re-review result: PASS WITH MINOR ISSUES; P1-001 FIXED AND INDEPENDENTLY VERIFIED.
Phase 1 is accepted. Although the review grants Phase 2 GO, the current user instruction requires Phase 1.1
hardening and another Independent Sol High Review first. Phase 2 / TASK-021+: DO NOT START in this session.
The preceding Phase 1 assessment is the historical pre-re-review state.

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
- **Status:** ✅ COMPLETED — P1-001 corrective migration and full reverification PASS. Await Independent Sol High Re-review; Phase 2 DO NOT START. See docs/phase-1-gate.md.

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
- [x] TASK-020: PHASE 1 Gate — RE-CLOSED after P1-001: DEV upgrade/data preservation, fresh PostgreSQL migration, rollback/re-upgrade, alembic check and drift regression PASS. Backend 37 tests (2 PostgreSQL), frontend 6 tests, lint/typecheck/build, native HTTP and Chromium auth/audit PASS. [Evidence trail](docs/phase-1-gate.md) preserves initial claim → independent review FAIL → correction → reverification. Phase 2 DO NOT START.

**Files:** `.gitignore`, `README.md`, `.env.example`, `docker-compose.yml`, `backend/**` (core + api + db + models + tests), `frontend/**` (app shell + stores + lib), `docs/18-devops.md` (อัปเดต)

**Acceptance Criteria:**
- Native Windows backend :8000 responds at /healthz and frontend :3000 provides shell/login without Docker/WSL; Docker Compose is an optional deployment check
- Login ด้วย user จริง (จาก DB) ผ่าน JWT และ audit log บันทึก Login event
- Migration รันได้ และ rollback ได้
- Lint + Typecheck + Unit test ผ่านทั้ง backend และ frontend

**Testing:** Native unit/API tests (auth, audit, health, optional Redis behavior), isolated SQLite migration + PostgreSQL offline DDL, opt-in native PostgreSQL migration up/down/auth/audit, native HTTP/browser smoke; real Redis/Compose tests optional

**Risk:** Windows async driver compatibility → shared selector event-loop factory for psycopg entry points; document tested dependencies. Missing PostgreSQL blocks only actual DB integration evidence; run independent checks and keep TASK-020 unchecked.

---


## PHASE 1.1 — Foundation Hardening

- **Objective:** close confirmed P2-001/002/003 with incremental security and API contract fixes.
- **Dependencies:** Phase 1 independently accepted (PASS WITH MINOR ISSUES), P1-001 verified.
- **Status:** Corrective verification PASS / Independent Sol High Re-review PENDING. Independent Review FAIL reopened HARD-R01/R02/R03 before correction; all three are now reproduced, fixed and verified. The original 71/17-test claim remains historical.
- **Scope:** trusted-proxy/client identity, bounded login budgets, safe correlation/exception logging,
  authoritative backend response contracts and frontend runtime validation. Redis remains optional.
- **Excluded:** P2-R01 token storage architecture, P3-001 ordinary failed-login audit, all Phase 2 implementation.

- [x] TASK-H001: P2-001 — direct peer by default; bounded trusted proxy opt-in; client/account budgets;
  expiry/cleanup/capacity; deterministic spoofing/proxy/account/limiter tests and native server verification.
- [x] TASK-H002: P2-002 — central safe correlation ID <=64; replacement for invalid headers;
  PostgreSQL audit/overflow tests; safe error context without SQL/driver parameters in logs.
- [x] TASK-H003: P2-003 — authoritative backend OpenAPI response models, matching generated TypeScript
  and validated endpoint responses; contract drift tests; full backend/frontend/browser regression.

**Acceptance:** all targeted security assertions, real PostgreSQL tests, alembic check, lint/typecheck/build,
full tests and available Chromium smoke PASS. No migration 0001/0002 edits, no trading code or secrets.
**Corrective evidence (2026-09-09):** backend 93 tests (12 real PostgreSQL), frontend 41 tests;
all lint/typecheck/build/contract/Alembic checks PASS. Five source-derived Uvicorn launch surfaces
pass native transport probes; full Docker orchestration/reload supervisor NOT RUN (optional).
Live correlation/error/concurrent requests and real Chromium login/refresh/recovery/logout plus
malformed-token rejection PASS. Migration 0001/0002 and accepted resolver fingerprints unchanged.
0002 remains untracked. Full review history and Git inventory: docs/phase-1.1-gate.md.

**Stop:** Phase 1.1 corrective verification PASS → Independent Sol High Re-review PENDING;
Phase 2 DO NOT START / NO-GO. No stage, commit or push.

---

## 7. PHASE 2 — Market Data & Realtime Chart

- **Objective:** ระบบ Market Data ครบวงจร — รับข้อมูลราคา, สร้าง Candles 9 Timeframes, เก็บลง PostgreSQL, ส่งต่อผ่าน WebSocket และแสดง Chart แบบ Realtime
- **Current authorization (2026-09-09):** User explicitly permits Phase 2 before final Sol review.
  Phase 1.1 remains pending; historical NO-GO statements above describe the superseded authorization.
  Phase 2 is provisional until combined independent review. Phase 3 / TASK-030+: DO NOT START.
- **Native adaptation:** Per current user instructions, native PostgreSQL tables and bounded in-process
  pub/sub replace mandatory hypertables/Redis in TASK-023/025 for this single-instance DEV milestone.
  TimescaleDB and distributed Redis integration remain future deployment work, not hidden dependencies.
- **Scope:** Symbol Management, Market Data Provider (Replay/Demo), Tick→Candle Aggregation, WebSocket API, TradingView Chart (XAUUSD)
- **Dependencies:** PHASE 1 ✅
- **Status:** IMPLEMENTATION COMPLETE — PENDING COMBINED SOL HIGH REVIEW (provisional; not production approved).

**Tasks:**

- [x] TASK-021: Symbol Management — CRUD + seed XAUUSD (contract size, digits, spread config, session hours) + `GET /api/symbols`
- [x] TASK-022: Market Data Provider Interface — abstract `MarketDataProvider` (connect, subscribe ticks, fetch history) + **ReplayProvider** (เล่นข้อมูลย้อนหลัง/simulated เพื่อพัฒนาโดยไม่ต้องพึ่ง Broker จริง) + provider registry ตาม config
- [x] TASK-023: Tick Ingestion Pipeline — รับ tick (bid/ask/spread/volume), ตรวจ stale/abnormal price, เก็บลง `ticks` PostgreSQL table, publish ผ่าน bounded local pub/sub (native adaptation)
- [x] TASK-024: Candle Aggregation Engine — สร้าง/อัปเดต candles จาก M1 base: M1, M3, M5, M15, M30, H1, H4, D1, W1 (OHLCV, bid/ask close) + แก้ไข candle ที่ยังไม่ปิด
- [x] TASK-025: Candle Persistence & Query — `candles` PostgreSQL table (native adaptation) + `GET /api/market/candles?symbol&timeframe&from&to` + pagination
- [x] TASK-026: Realtime WebSocket — `/ws/market` (subscribe/unsubscribe by symbol+timeframe, push tick + candle update) + heartbeat + reconnect protocol
- [x] TASK-027: Frontend Chart — TradingView Lightweight Charts + realtime candle update + Timeframe Selector + Symbol Selector + Bid/Ask/Spread/Market Status bar
- [x] TASK-028: Market Data Freshness Monitoring — worker ตรวจอายุข้อมูล + แจ้งเตือน + `system_events` เมื่อ stale/abnormal (ต่อเข้า Kill Switch ใน PHASE 5)
- [x] TASK-029: PHASE 2 Gate — Build + Test + Verify + DoD review + รายงานผล + อัปเดต `docs/06-market-data.md`

**Files:** `backend/app/services/market_data/**`, `backend/app/api/market.py`, `backend/app/workers/market_data_worker.py`, `frontend/src/features/chart/**`, `docs/06-market-data.md`

**Acceptance Criteria:**
- รันด้วย ReplayProvider แล้ว Chart XAUUSD อัปเดต realtime ผ่าน WebSocket ได้ทุก Timeframe ที่กำหนด
- Candle ที่สร้างจาก tick ถูกต้อง (ตรวจสอบเทียบกับข้อมูลต้นทาง) และ candle ที่ยังไม่ปิดอัปเดต in-place ได้
- API ดึงประวัติ candle ถูกต้อง + รองรับหลาย Symbol (schema) แม้ v1 จะ seed แค่ XAUUSD
- Stale detection ทำงาน (ทดสอบด้วยการหยุด feed)

**Testing:** Unit test (aggregation, timeframe bucketing, stale detector), Integration test (tick→candle→DB→WS e2e), Frontend component test (chart render, tf selector)

**Risk:** ไม่มีข้อมูลจริงในช่วงพัฒนา → ReplayProvider + ข้อมูล historical สังเคราะห์; ปริมาณ tick
ควบคุมด้วย bounded state, batched candle upserts และ simulated-source retention บน native PostgreSQL.
TimescaleDB/distributed Redis เป็น future deployment work ตาม native adaptation ข้างต้น.

**Verification (2026-09-09):** backend 127 tests (13 PostgreSQL integration), frontend 61 tests;
Ruff/mypy/syntax/wheel, lint/typecheck/build, generated contract and Alembic check PASS.
Chromium valid/invalid auth, refresh/logout, Trading chart/realtime, all nine timeframes,
canvas lifecycle, reconnect/reload and desktop/tablet/mobile PASS; console errors/assets failures 0.
Native Windows PostgreSQL 18.6 works with optional Redis/Docker/WSL. 0001/0002 and HARD fixes preserved.
Full evidence and Git inventory: docs/phase-2-gate.md.
**Stop:** Phase 3 / TASK-030+ DO NOT START. Phase 1.1 + Phase 2 combined Sol High review PENDING.
No stage, commit or push.

---

## 7.5. PHASE 2.5 — Real Market Data

Current authorization: user reports Phase2 Independent Gate PASS and requests real
market data only. No review artifact was supplied in this turn. PAPER, live false,
read-only MT5, no broker execution and no Phase3 remain mandatory.

- [x] TASK-2.5-01: Provider discovery/config foundation — user-selected IUX Demo; private terminal identity and explicit XAUUSD mapping.
- [x] TASK-2.5-02: Official MT5 adapter foundation — lifecycle, read-only method allowlist, account/mode checks and error masking.
- [x] TASK-2.5-03: Symbol/timeframe mapping foundation — metadata precision, explicit IANA server time, canonical UTC boundaries.
- [x] TASK-2.5-04: Historical adapter foundation — native lower bars, M3 from M1, H4/D1/W1 from H1; report short history honestly.
- [x] TASK-2.5-05: Realtime provider foundation — bounded shared quote polling and authoritative rates; no per-browser provider connection.
- [x] TASK-2.5-06: Continuity/storage foundation — source-scoped REST/WS/persistence, replacement OHLC, resnapshot on gaps; minimal nullable-ask migration0004.
- [x] TASK-2.5-07: Health/reconnect/stale foundation — bounded backoff, freshness, unknown market session and queue bounds.
- [x] TASK-2.5-08: Trading UI integration — canonical real/demo/simulated labels, precision/tick size, current source and partial-history detail.
- [ ] TASK-2.5-09: Full real integration/browser acceptance — BLOCKED on at least300 canonical real candles per timeframe; IUX W1 currently231/300.

Task completion above refers to implemented adapter foundation. It does not assert
the full real-data DoD or Phase2.5 Gate PASS. Acceptance requires all actual market,
300-history, UI, continuity, security, PostgreSQL and independent review evidence.
See docs/phase-2.5-gate.md. Phase3/TASK-030+ DO NOT START.

---

## 8. PHASE 3 — Analysis Engines (Structure / Liquidity / SMC / Indicators / Regime)

- **Objective:** สร้าง Analysis Engines แยก Module ชัดเจน — Market Structure, Liquidity, SMC/ICT, Indicators, Sessions, Market Regime และ Multi-Timeframe Bias Aggregation + แสดงผลบน Chart
- **Scope:** 5 Engines + Session Engine + MTF Aggregation + Chart Overlays (ยังไม่มี Strategy/Signal)
- **Dependencies:** PHASE 2 ✅ (ต้องมี candles)
- **Status:** IMPLEMENTATION COMPLETE — PENDING COMBINED SOL HIGH REVIEW

**Tasks:**

- [x] TASK-030: Market Structure Engine — Swing High/Low (fractal), HH/HL/LH/LL, BOS, CHoCH, MSS + แยก Internal / External Structure + version ผลลัพธ์ต่อ candle
- [x] TASK-031: Liquidity Engine — PDH/PDL, PWH/PWL, Asian/London/NY High-Low, Equal High/Low, Buy-side/Sell-side Liquidity, Liquidity Sweep/Grab detection
- [x] TASK-032: SMC/ICT Engine — Order Block, Breaker Block, FVG, IFVG, Premium/Discount/Equilibrium, OTE + Confluence Model (เก็บเป็น structured zones)
- [x] TASK-033: Indicator Engine — ATR, RSI, EMA/SMA, ADX, Bollinger, Volume avg + framework เพิ่ม indicator ได้
- [x] TASK-034: Session Engine — Asian/London/NY sessions (config ได้), overlap detection, current session + ประวัติ session levels
- [x] TASK-035: Market Regime Engine — จำแนก TRENDING_UP/TRENDING_DOWN/RANGING/HIGH_VOLATILITY/LOW_VOLATILITY/BREAKOUT/PULLBACK/NEWS_CONDITION/UNKNOWN ต่อ Timeframe
- [x] TASK-036: Multi-Timeframe Analysis — Top-Down (D1→H4→H1→M15→M5) แยกวิเคราะห์ต่อ TF + Aggregate เป็น Market Bias + `GET /api/analysis/*`
- [x] TASK-037: Chart Overlays — แสดง Structure (BOS/CHoCH/MSS), Liquidity levels, FVG, Order Blocks, Sessions บน Chart (toggle ได้)
- [x] TASK-038: PHASE 3 Gate — Build + Test + Verify + DoD + อัปเดต `docs/07-market-structure.md`, `docs/08-smc-ict.md`

**Files:** `backend/app/services/analysis/**`, `backend/app/api/analysis.py`, `frontend/src/features/analysis/**`, `docs/07-market-structure.md`, `docs/08-smc-ict.md`

**Implementation decisions:** NEWS_CONDITION remains news_context=UNKNOWN without a news source; OTE is retracement geometry only; confluence is factual zone counts. All nine TF are exposed for top-down inspection. No strategy score, recommendation, risk or execution is included. No migration added; actual head 0004_market_unknown_ask preserved.

**Verification:** backend 210 PASS (15 PostgreSQL), frontend 80 PASS, build/static/contracts/Alembic PASS, actual IUX all-nine-TF API/batch/incremental/prefix checks and Chromium overlays/closed-refresh/reload/reconnect/responsive PASS. W1 231/300 PARTIAL (230 closed) remains honestly reported. Rolling-window revisions are explicitly disclosed rather than claimed immutable. See [Phase 3 gate](docs/phase-3-gate.md), [structure semantics](docs/07-market-structure.md), [SMC semantics](docs/08-smc-ict.md). Phase 4 STOP.

**Acceptance Criteria:**
- Engine ทุกตัวเป็น pure function ของ candle data (deterministic, testable ย้อนหลังได้)
- ตรวจสอบผล BOS/CHoCH/MSS/FVG/OB/Liquidity Sweep กับชุดข้อมูลที่รู้ผลลัพธ์ (golden dataset) ได้ถูกต้อง
- MTF Bias แสดงผลบน UI พร้อมเหตุผล (evidence ระดับ TF) และแสดง zones บน Chart ได้
- ยังไม่มีการสร้าง Signal ใด ๆ ใน Phase นี้

**Testing:** Unit test ทุก engine ด้วย golden dataset + synthetic candles, Integration test (candles→analysis→API→chart overlay), Property test (aggregation ไม่แตกเมื่อข้อมูล edge case)

**Risk:** นิยาม SMC หลายสำนัป → เลือกนิยามชัดเจนใน `docs/08-smc-ict.md` + ทำ parameters configurable; การ detect ผิดพลาด → ทุก detection ต้องมี confidence/parameter และผ่าน golden dataset ก่อนใช้

---

## 9. PHASE 4 — Strategy / Trader Profile / Setup / Trade Plan Engine

- **Scope:** Immutable shared context, key levels/sessions/indicators/patterns, six deterministic playbooks, seven profiles, setup/structural plans, lifecycle/persistence/API/Thai UI.
- **Dependencies:** Phase 3 and Phase 3.5 implementation complete under disclosed safe-partial conditions.
- **Status:** IMPLEMENTATION COMPLETE — PENDING COMBINED SOL HIGH INDEPENDENT REVIEW PHASE 3.5+4.
- **Safety:** Analysis only. No risk sizing, trailing, partial-close, order, execution, AI or position management.

**Tasks (original IDs retained; latest authorized scope replaces old execution/risk placeholders):**

- [x] TASK-039: Immutable StrategyMarketContext + configuration/provenance, context engines and six-playbook registry.
- [x] TASK-040: SMC liquidity reversal — HTF/sweep/reclaim/CHOCH-MSS/zone/retest evidence chain.
- [x] TASK-041: Trend pullback — established context/BOS/zone/LTF confirmation.
- [x] TASK-042: Confirmed pattern breakout + displacement + subsequent retest.
- [x] TASK-043: Range mean reversion — confirmed boundaries, weak trend, rejection and structure.
- [x] TASK-044: Post-news momentum and liquidity reversal playbooks; RUN_TREND context/profile only, no management.
- [x] TASK-045: SCALP/DAY_TRADE/SWING/RUN_TREND mappings; seven isolated profiles, three comparison modes, adaptive reserved.
- [x] TASK-046: Setup/structural plan geometry, immutable revisions/lifecycle, additive migration 0006, authenticated generated contracts and Thai chart/workspace.
- [x] TASK-047: Final regression, actual IUX/browser/DB preservation gate and combined-review report.

**Files:** backend/app/services/strategy, backend/app/api/strategy.py, backend/app/models/strategy.py, migration 0006, frontend/src/features/strategy, generated contracts, tests, [architecture](docs/09-strategy-engine.md), [gate](docs/phase-4-gate.md).

**Acceptance:** Explicit mandatory context gates precede scoring. No absent-snapshot invalidation, no future candles/pivots/news/session extrema, no forced TP/RR, no fixture news enabling real READY. Existing market/analysis/news engines and old migrations remain protected. W1 partial remains explicit.

**Next:** STOP before Phase 5. COMBINED SOL HIGH INDEPENDENT REVIEW PHASE 3.5+4 is required.

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
| 2026-09-09 | 1.6 | Independent review FAIL reopened TASK-020 (10/11; 19/104) for P1-001. Added 0002_phase1_schema_alignment without changing 0001; aligned refresh-token unique-index ORM metadata; added real PostgreSQL drift/roundtrip gate. DEV data preserved, fresh/rollback/re-upgrade/alembic check PASS; full backend 37/frontend 6 tests, lint/typecheck/build, browser auth and JSONB audit PASS. TASK-020 re-closed (11/11; 20/104), pending Independent Sol High Re-review. P2/P3 unchanged; Phase 2 NO-GO; no commit/push. |
| 2026-09-09 | 1.7 | User supplied Independent Re-review PASS WITH MINOR ISSUES, P1-001 independently verified. Added Phase 1.1 TASK-H001/H002/H003 without renumbering original tasks: proxy/login budgets, correlation/logging, OpenAPI/frontend contract hardening. Reproduced defects, then verified backend 71 (4 PostgreSQL)/frontend 17 tests, build/typecheck/lint, alembic/contract checks, native spoofing and Chromium auth smoke PASS. Hardening 3/3, total 23/107. Migration 0001/0002 preserved; P2-R01/P3-001 deferred; no Phase 2, commit or push. Stop for Independent Sol High Review. |
| 2026-09-09 | 1.8 | Independent Review FAIL: HARD-R01 base Compose proxy rewriting, HARD-R02 malformed token semantics/persistence, HARD-R03 access-log correlation lifecycle. Reopened hardening tasks and gate before reproduction/correction. Minimal fixes and source-derived runtime tests now pass: backend 93 (12 PostgreSQL), frontend 41, complete build/lint/typecheck/contract/Alembic, native Windows and Chromium valid/malformed auth checks. Corrective verification PASS, 3/3 hardening, total 23/107. Initial claim and independent FAIL preserved in gate history. Migrations 0001/0002 unchanged; 0002 still untracked; no staging/commit/push. STOP for Independent Sol High Re-review; Phase 2 NO-GO. |
| 2026-09-09 | 1.9 | User explicitly authorized provisional Phase 2 before final Sol review. Retained TASK-021–029 and adapted mandatory TimescaleDB/Redis wording to native PostgreSQL + bounded LocalMarketBus per current instructions. Implemented deterministic ReplayProvider, validated UTC/Decimal domain, M1-to-nine-timeframe aggregation, persistence/retention, authenticated REST/first-frame-auth WS, stale/events/recovery and responsive Lightweight Charts Trading screen. Fixed local-timezone serialization found by real browser verification. Final backend 127 (13 PostgreSQL) and frontend 61 tests, builds/static/contract/Alembic and real Chromium auth/Trading visual gate PASS. Tasks 9/9; total 32/107. 0001/0002 and corrective security code preserved; no commit/stage/push. IMPLEMENTATION COMPLETE — PENDING COMBINED INDEPENDENT REVIEW. Phase 3 DO NOT START. |

| 2026-09-09 | 2.0 | User-reported Phase2 independent acceptance authorizes Phase2.5. Added nine scoped tasks (8 foundation tasks complete, real acceptance pending), official read-only IUX MT5 adapter, explicit broker-time normalization, UTC higher aggregation, source isolation, precision/labels, nullable historical ask migration0004 and offline/external tests. Current real W1 history231/300 prevents Gate PASS. See phase-2.5-gate.md. No Phase3 or Git publication. |

| 2026-09-09 | 2.1 | Latest user explicitly authorizes provisional Phase 3 despite Phase 2.5 W1 partial and pending review. TASK-030–038 implemented/verified without renumbering: causal structure/liquidity/SMC, indicators/sessions/regime, authenticated typed API and chart overlays. 210 backend (15 PostgreSQL), 80 frontend tests, real IUX 9-TF cross-checks and native Chromium acceptance pass. Bounded-window/no-lookahead scope disclosed, no fake W1 history, no migration, protected foundation unchanged. Phase 3 9/9; total 49/116. IMPLEMENTATION COMPLETE — PENDING COMBINED SOL HIGH REVIEW. Phase 4 DO NOT START; no staging/commit/push. |


## Phase 3.5 — Economic context extension

ใช้รหัส TASK-N001–N012 เพิ่มเติม ไม่เปลี่ยนเลขเดิม งาน future news risk enforcement ใน Phase5 ยังไม่ถือว่าทำแล้ว

- [x] **TASK-N001** — Audit Phase prerequisites, provider discovery และ QREV-R01/R02 boundaries
- [x] **TASK-N002** — Canonical economic provider/18-event catalogue และ explicit FIXTURE fallback
- [x] **TASK-N003** — Economic occurrence/revision schema + migration0005 + point-in-time repository
- [x] **TASK-N004** — Configurable XAUUSD currency/channel/relevance semantics
- [x] **TASK-N005** — Deterministic numeric surprise and directional semantics
- [x] **TASK-N006** — Composite release groups/NFP negative revision/conflict analysis
- [x] **TASK-N007** — News timeline/overlapping risk/context eligibility metadata
- [x] **TASK-N008** — Canonical market reaction/spread/volatility context without fabricated data
- [x] **TASK-N009** — Phase3 provenance/no-lookahead/fingerprint/operational freshness
- [x] **TASK-N010** — Authenticated typed REST and runtime frontend contracts
- [x] **TASK-N011** — Thai Trading News Panel/Calendar/countdown/responsive UI
- [x] **TASK-N012** — Unit/PostgreSQL/build/regression/browser gate + documentation + STOP Phase4

Gate: [docs/phase-3.5-gate.md](docs/phase-3.5-gate.md). IMPLEMENTATION COMPLETE — PENDING INDEPENDENT REVIEW.

| 2026-09-09 | 2.2 | User-directed Phase3.5 before Phase4: added TASK-N001–N012 (12), total128; canonical economic revisions/migration0005, deterministic news context, QREV boundaries, Thai UI and verified acceptance: 277 backend (16 PostgreSQL), 96 frontend, 9 direct MT5 external tests, native news/calendar/Phase3 browser PASS. W1 231/300 Safe-Partial retained. 12/12 news tasks; total61/128. Phase4 remains DO NOT START. |

| 2026-09-09 | 2.3 | Latest user authorized Phase4 after safe-partial Phase3.5 runtime verification. TASK-039–047 completed with six playbooks, seven profiles, shared immutable context, structural plans/lifecycle, migration0006 and Thai UI. 345 backend tests (17 PostgreSQL), 112 frontend tests, 9 direct MT5 tests, actual API/pure and browser regression passed. W1/news limitations retained; no execution or Git mutation. Phase4 9/9, total70/128. STOP before Phase5 pending combined independent review. |


## Phase 3.5R — Real provider completion

- [x] **TASK-NR001** — Audit providers, keyless endpoint and documented usage terms
- [x] **TASK-NR002** — Explicit real adapter/configuration and fail-safe unconfigured default
- [x] **TASK-NR003** — Canonical UTC/Decimal/observation identity and append-only revisions
- [x] **TASK-NR004** — Bounded polling/backoff, health/freshness and no fixture fallback
- [x] **TASK-NR005** — Real USD subset acceptance against raw provider; restricted canonical Phase4 context
- [ ] **TASK-NR006** — Full original USD coverage, forecasts/components/revision history and release-latency acceptance (provider capability unavailable)

## Phase 4.1 — Dashboard command center

- [x] **TASK-D001** — Typed aggregated contract, isolated module failures and bounded cache
- [x] **TASK-D002** — Thai market/structure/key levels/news summaries
- [x] **TASK-D003** — Canonical strategies/profiles/plan/no-trade explanation summaries
- [x] **TASK-D004** — Health/freshness/safety, internal WS reuse and cleanup
- [x] **TASK-D005** — Final regression/browser/security evidence and mandatory stop report

Gate and limitations: [docs/pre-review-3.5r-4.1.md](docs/pre-review-3.5r-4.1.md).
No Phase5 implementation, Git stage/commit/push or order execution.


| 2026-09-09 | 2.4 | Pre-review batch: keyless Xoomar real economic subset connected (NR5/6, full coverage PARTIAL), Dashboard command center D5/5;371 backend incl18 PostgreSQL,130 frontend,9 MT5, raw/provider/API and all browser regressions PASS. Protected33 files unchanged, no secret exposure, migrations remain0006. Total80/139. No Git mutation. STOP before Phase5; ready for combined review with explicit real-calendar limitations. |
| 2026-09-10 | 2.5 | Targeted Forex Factory integration for STRAT05–06 only; market-only invariance for STRAT01–04; strategy-1.2.1/news-1.2.0. No migration or Git mutation. See dedicated acceptance report for final checks and actual-feed limitations. Phase5 NOT STARTED. |


## SOL corrective milestone — SOL-P1-001

Finding status: **FIXED — PENDING SOL RE-REVIEW** (implementation verification, not independent approval).
Dependency-aware per-profile/strategy evaluation projections align general/news IDs, immutable
payloads, candidate ownership and idempotent persistence. Separate evaluation-2.0.0 identity
version; strategy-1.2.1 logic and migrations remain unchanged.
Latest user authorization supersedes historical no-Git restrictions for one reviewed completed
pre-Phase-5 baseline + corrective commit/push. No Phase5 task is marked complete.
P2-001/002/003/004/005 and P3-001 remain DEFERRED — unchanged by this corrective batch.
Evidence and scope: [SOL-P1-001 corrective report](docs/sol-p1-001-corrective.md).
STOP after the authorized commit/push and wait for SOL HIGH RE-REVIEW.
