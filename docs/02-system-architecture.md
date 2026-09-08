# 02 — System Architecture (สถาปัตยกรรมระบบ)

| รายการ | รายละเอียด |
|---|---|
| เอกสาร | docs/02-system-architecture.md |
| เวอร์ชัน | 1.0 (2026-09-08) |
| สถานะ | ✅ Baseline (อ้างอิงโดย ADR-001..007) |

---

## 1. หลักการออกแบบ (Design Principles)

1. **Risk First** — ทุก order ผ่าน Risk Engine เท่านั้น; AI ไม่มีเส้นทางตรงไป Broker
2. **Explainable & Auditable** — ทุก decision มี evidence + audit trail + correlation id
3. **Modular Boundaries** — 22 core modules แยกกันชัดเจน สื่อสารผ่าน interface ที่นิยามไว้
4. **Deterministic Engines** — analysis engines เป็น pure function ของข้อมูล (เทียบเคียง backtest/live ได้)
5. **Fail Safe** — dependency ล่ม → degrade ปลอดภัย + kill switch หยุดความเสี่ยง
6. **Config over Code** — ห้าม hardcode, ทุก rule ปรับผ่าน config ได้

## 2. Layer Architecture (ตาม Specification)

```
Frontend (Next.js + WebSocket Client)
        ↓  REST / WS
API Layer (FastAPI: REST + WebSocket + Auth + Validation)
        ↓
Trading Backend (Services: Trading, OMS, Positions, Journal)
        ↓
Market Data Service (Provider Abstraction + Aggregation)
        ↓
Feature Engine (Indicators, Extracted Features)
        ↓
Strategy Engine (Plug-in Strategies)
        ↓
AI Analysis Engine (Multi-Agent + Decision + Confidence)
        ↓
Risk Engine (Rules + Position Sizing + Kill Switch)   ← Gate เดียวสู่การเทรด
        ↓
Trade Decision Engine (Trade Plan + Confirmation)
        ↓
Order Management System (State Machine + Idempotency)
        ↓
Broker Adapter (Interface → PaperBroker | MT5Adapter | อนาคต: OANDA/Saxo)
        ↓
Broker / MT5 (Demo ก่อน — LIVE บล็อกโดย Feature Flag)
```

**หมายเหตุสำคัญ:** ลำดับการประมวลผลจริงของ 1 รอบวิเคราะห์คือ Data → Analysis → Strategy → AI → **Risk → Trade Plan → (Paper/Human) Confirmation → OMS → Broker** — Risk Engine เป็นด่านบังคับก่อนถึง OMS เสมอ (enforce ใน `OrderService.submit()` และมี architectural test กันการ bypass)

## 3. Technology Stack (สรุป — เหตุผลเต็มอยู่ใน ADR)

| ส่วน | เทคโนโลยี | ADR |
|---|---|---|
| Frontend | Next.js (App Router) + React + TypeScript + Tailwind CSS | ADR-001 |
| Chart | TradingView Lightweight Charts | ADR-001 |
| State | Zustand (per-feature stores) | ADR-001 |
| Realtime FE↔BE | WebSocket (native) | ADR-001 |
| Backend | Python 3.12+ / FastAPI (REST + WS + workers) | ADR-002 |
| Validation | Pydantic v2 (ทุก boundary รวมถึง LLM output) | ADR-002 |
| Primary DB | PostgreSQL 16 + TimescaleDB (hypertables: ticks, candles) | ADR-003 |
| Cache/PubSub/Lock | Redis 7 | ADR-003 |
| Infra | Native Windows (Node + Python + PostgreSQL service); Docker Compose optional | ADR-002 |

### Phase 1 local DEV clarification — 2026-09-08

The diagram and worker/Redis/TimescaleDB flows describe the target system.
Current Phase 1 has auth, sessions, audit, health and application shells only.
Native PostgreSQL is primary; TimescaleDB is not required by its six foundation tables.
Redis is disabled by default because no distributed feature consumes it yet.
The current rate limiter is in process and sessions are stored in PostgreSQL.
With Redis disabled /readyz reports checks.redis=null; DB failure returns 503.
Future worker/order-lock failure policies below remain future-phase requirements.
See [18-devops.md](18-devops.md) for the current runnable setup.

## 4. Core Modules และ Service Boundaries (22 Modules)

| # | Module | หน้าที่ | Phase ที่สร้าง | Boundary (input → output) |
|---|---|---|---|---|
| 1 | Market Data Service | ดึง/รับข้อมูลราคาจาก provider | P2 | provider events → ticks/candles |
| 2 | Candle Aggregation Engine | tick/M1 → candles 9 TF | P2 | ticks/M1 → candles |
| 3 | Market Structure Engine | swing/BOS/CHoCH/MSS | P3 | candles → structure events |
| 4 | Liquidity Engine | levels/sweeps | P3 | candles → liquidity zones |
| 5 | SMC/ICT Engine | OB/FVG/premium-discount/OTE | P3 | candles+structure → smc zones |
| 6 | Indicator Engine | ATR/RSI/EMA/ADX ฯลฯ | P3 | candles → indicator series |
| 7 | Market Regime Engine | จำแนก regime ต่อ TF | P3 | candles+indicators → regime |
| 8 | Strategy Engine | plug-in strategies | P4 | analysis ctx → strategy signals |
| 9 | AI Analysis Engine | multi-agent reasoning | P6 | structured ctx → recommendation |
| 10 | Risk Engine | rules + sizing + gate | P5 | trade plan + account → decision |
| 11 | Signal Engine | สร้าง signal + trade plan | P4 | strategy+analysis+ai → signal |
| 12 | Order Management System | order state machine | P7 | approved plan → broker order |
| 13 | Broker Adapter | interface + MT5/paper | P7/P10 | OMS commands → broker ops |
| 14 | Position Management Engine | BE/trailing/partial/time stop | P7 | price stream + rules → position ops |
| 15 | Portfolio / Account Engine | balance/equity/exposure | P7 | fills → account state |
| 16 | Paper Trading Engine | virtual broker simulation | P7 | market data → virtual fills |
| 17 | Backtesting Engine | event-driven replay | P9 | historical data → results |
| 18 | Trade Journal | บันทึกทุก trade | P8 | trade close → journal entry |
| 19 | Analytics Engine | metrics/calibration | P8 | journal/trades → analytics |
| 20 | Notification Service | alerts + notify | P8 | events → user alerts |
| 21 | Economic Calendar / News Filter | events + rules | P6 | calendar → trading windows |
| 22 | Audit Logging | audit trail ทุก action | P1 | ทุก service → audit_logs |

**กฎการอ้างอิงระหว่าง module:** อนุญาตเฉพาะทิศทางจากบนลงล่างตามลำดับ pipeline; ห้าม module วิเคราะห์เรียก OMS โดยตรง; Broker Adapter ถูกเรียกได้จาก OMS เท่านั้น

## 5. Core Data Flow

### 5.1 วงจรข้อมูลตลาด (ต่อเนื่อง)

```
Provider (Replay/MT5) → MarketDataService → [validate: stale/abnormal/spread]
  → TimescaleDB (ticks, candles) + Redis pub/sub (ch: market.{symbol})
  → WS Gateway → Frontend (chart/price)
  → Analysis Pipeline (structure → liquidity → smc → indicators → regime) [worker]
  → Analysis Snapshot (Redis + DB) → ใช้โดย Strategy/AI/UI
```

### 5.2 วงจรสร้าง Signal → Trade (ต่อรอบวิเคราะห์)

```
Analysis Snapshot → Strategy Engine (เลือกตาม regime + confluence gate)
  → Signal Engine → Trade Plan (draft) 
  → AI Analysis Engine (agents → decision → schema validation) [enhance + rank + explain]
  → Risk Engine → APPROVED / REJECTED / REDUCE_SIZE / WAIT (+reason)
  → [APPROVED เท่านั้น] Signal สถานะ WAITING_CONFIRMATION (+ expiration)
  → Human Confirm (SCALP/DAY mode) หรือ Paper auto-exec (ตาม config ต่อ mode)
  → OMS (idempotency + state machine) → BrokerAdapter (Paper ก่อน) → Position
  → Position Management → Trade Close → Journal → Analytics (ย้อนกลับปรับ strategy)
```

## 6. Realtime Architecture

- **WS Topics:** `/ws/market` (tick/candle ตาม subscription), `/ws/trading` (orders/positions/signals), `/ws/ai` (analysis updates), `/ws/system` (health/kill switch/alerts)
- **Protocol:** JSON message + `type` + `correlation_id`; subscribe/unsubscribe by `symbol`+`timeframe`; heartbeat 10s; client auto-reconnect + resync ด้วย REST snapshot
- **Backend pub/sub:** Redis pub/sub แยก channel ตาม domain — WS gateway เป็น stateless fan-out

## 7. Background Workers

| Worker | หน้าที่ | Phase |
|---|---|---|
| market_data_worker | รับ provider events, aggregate candles, publish | P2 |
| analysis_worker | รัน analysis pipeline ตาม trigger (candle close / interval) | P3 |
| signal_worker | รัน strategy + สร้าง signal/trade plan | P4 |
| risk_monitor_worker | ตรวจ limits ต่อเนื่อง + kill switch triggers | P5 |
| ai_worker | รัน AI analysis เมื่อมี candidate setup | P6 |
| position_worker | จัดการ BE/trailing/partial/time stop | P7 |
| news_worker | sync economic calendar + คำนวณ trading windows | P6 |
| reconciliation_worker | เทียบระบบกับ broker | P10 |

## 8. Environments

| Env | วัตถุประสงค์ | TRADING_MODE |
|---|---|---|
| DEV | พัฒนา (ReplayProvider, DB สังเคราะห์) | PAPER |
| UAT | Paper trading + Integration test กับข้อมูลจริง | PAPER / SEMI_AUTO (demo broker) |
| PROD | Production | **ไม่ใช่ LIVE** จนกว่า admin เปิด feature flag โดยเจตนา |

Environment config แยกกันผ่าน `.env` ต่อ environment (ไม่ commit secret; `.env.example` ไม่มีค่าจริง)

## 9. Failure Handling Overview (รายละเอียดใน PHASE 12)

| เหตุการณ์ | พฤติกรรมระบบ |
|---|---|
| Broker disconnected | Kill switch trigger → หยุด order ใหม่, position management ทำงานต่อ, reconnect + reconcile |
| Market data stale/abnormal | Kill switch trigger + alert + UI แสดง stale status |
| Redis unavailable | Degrade: ตัด cache/pubsub (fallback DB polling), ห้ามรับ order ใหม่จนกลับมา (เสีย order lock) |
| DB unavailable | หยุดรับ order ทันที (ไม่มี audit = ไม่มี order), retry + alert |
| AI unavailable | Kill switch (ตาม config) หรือ degraded mode แบบ quant-only, บันทึก system_events |
| WS dropped | Client reconnect + resync ผ่าน REST snapshot; ไม่มี order ซ้ำเพราะ idempotency key |
| Order timeout / accepted-but-timeout | Mark UNKNOWN → reconcile กับ broker ก่อน retry/cancel (ห้าม retry ตาบอด) |
| Duplicate callback | Idempotent by client_order_id + state validation |
| Position mismatch | Reconciliation process + alert + risk recompute |

## 10. Observability Overview

- **Logging:** JSON structured log + correlation_id ทุก request/job/order
- **Health/Readiness:** `/healthz` (process), `/readyz` (DB+Redis+provider ready)
- **Metrics:** API latency, WS connections, candle lag, order latency, risk decisions, kill switch state
- **Trading Event Log:** order_events/position_events/risk_events/audit_logs = source of truth ของสิ่งที่เกิดขึ้น
- **Monitoring:** broker connectivity + market data freshness dashboard

## 11. Security Architecture Overview (รายละเอียด docs/16-security.md)

- JWT (access+refresh) + RBAC (ADMIN/TRADER/VIEWER) + rate limiting ที่ API layer
- Broker credentials เข้ารหัส (AES-GCM ด้วย key จาก env) — decrypt เฉพาะใน broker service, ไม่ออกทาง API ใด ๆ
- Masking ของ sensitive field ใน log; CORS allow-list; input validation ด้วย Pydantic ทุก endpoint
- Audit ทุก action สำคัญ (docs/01-requirements.md FR-SE-03)
