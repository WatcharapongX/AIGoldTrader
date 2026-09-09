# 05 — API Design (REST + WebSocket Contract)

| รายการ | รายละเอียด |
|---|---|
| เอกสาร | docs/05-api-design.md |
| เวอร์ชัน | 1.0 (2026-09-08) |
| สถานะ | ✅ Baseline — endpoint ใหม่/เปลี่ยนต้องอัปเดตเอกสารนี้ก่อน implement |
| Base URL | `/api` (REST), `/ws` (WebSocket) |

---

## 1. Conventions

- **Auth:** `Authorization: Bearer <access_token>` (JWT) — ทุก endpoint ยกเว้น `/auth/login`, `/healthz`, `/readyz`
- **Roles:** ADMIN / TRADER / VIEWER — ระบุที่ endpoint ที่จำกัด
- **Content:** JSON (UTF-8); timestamps = ISO 8601 UTC; prices = string/decimal ปลอดภัยความแม่นยำ
- **Pagination:** `?limit=&cursor=` → ตอบ `{ items: [], next_cursor: ? }`
- **Idempotency:** ทุก mutation ฝั่ง trading ต้องมี header `Idempotency-Key` (และ/หรือ `ClientOrderID` ใน body) — ซ้ำ = คืนผลเดิม (INV-03)
- **Correlation:** ทุก request มี `X-Correlation-ID` (สร้างให้ถ้าไม่ส่ง) — ส่งต่อไป log/audit/WS
- **Error format มาตรฐาน:**

```json
{ "error": { "code": "RISK_LIMIT_EXCEEDED", "message": "Daily loss limit reached", "details": {}, "correlation_id": "..." } }
```

Error codes หลัก: `AUTH_FAILED`, `FORBIDDEN`, `VALIDATION_ERROR`, `NOT_FOUND`, `RISK_LIMIT_EXCEEDED`, `KILL_SWITCH_ACTIVE`, `DUPLICATE_ORDER`, `INVALID_STATE_TRANSITION`, `SIGNAL_EXPIRED`, `MARKET_DATA_STALE`, `AI_VALIDATION_FAILED`, `RATE_LIMITED`, `INTERNAL`

## 2. REST Endpoints

### 2.1 Auth & Users (PHASE 1)

| Method | Path | คำอธิบาย | Role |
|---|---|---|---|
| POST | `/auth/login` | login → access + refresh token | public (rate-limited) |
| POST | `/auth/refresh` | ต่ออายุ access token | refresh token |
| POST | `/auth/logout` | revoke session | any |
| GET | `/auth/me` | profile + role | any |
| GET/POST | /admin/users | Planned contract — not implemented in current Phase 1 source | ADMIN |

Phase 1 source currently provides interactive admin bootstrap (python -m app.db.seed)
and RBAC dependencies. The admin management endpoints above remain a known contract gap;
this gate review does not claim they exist or implement a new management feature.

### 2.2 Symbols & Market Data (PHASE 2)

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/symbols` | รายการ symbol ที่ active |
| GET | `/symbols/{name}` | spec เต็ม (digits, contract size, session hours) |
| GET | `/market/quote?symbol=XAUUSD` | bid/ask/spread ล่าสุด + staleness flag |
| GET | `/market/candles?symbol&timeframe&from&to&limit` | ประวัติ candles (cursor pagination) |
| GET | `/market/status?symbol` | market open/close + current session |

### 2.3 Analysis (PHASE 3)

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/analysis/snapshot?symbol&timeframe` | ผล engines ล่าสุด (structure, liquidity, smc, indicators, regime) |
| GET | `/analysis/structure?symbol&timeframe` | swing points + BOS/CHoCH/MSS events |
| GET | `/analysis/liquidity?symbol&timeframe` | liquidity levels + sweeps |
| GET | `/analysis/smc?symbol&timeframe` | zones (OB/breaker/FVG/IFVG) + premium/discount/OTE |
| GET | `/analysis/regime?symbol&timeframe` | regime ปัจจุบัน + เหตุผล |
| GET | `/analysis/bias?symbol&set=day_trading` | MTF bias (D1→H4→H1→M15→M5) + เหตุผลราย TF |

### 2.4 Strategies & Signals (PHASE 4)

| Method | Path | คำอธิบาย | Role |
|---|---|---|---|
| GET | `/strategies` | รายการ strategy registry | any |
| GET/PUT | `/strategies/{code}/configs?account&style` | ดู/แก้ config (audit) | TRADER |
| GET | `/signals?status&symbol&strategy&from&to` | รายการ signals | any |
| GET | `/signals/{id}` | signal + evidence + trade plan | any |
| POST | `/signals/{id}/cancel` | ยกเลิก (ยัง active) | TRADER |

### 2.5 Risk (PHASE 5)

| Method | Path | คำอธิบาย | Role |
|---|---|---|---|
| GET/PUT | `/risk/configs?account` | ดู/แก้ risk config (audit before/after) | ADMIN (PUT) |
| GET | `/risk/status?account` | risk dashboard payload (daily used, open risk, exposure, limits) | any |
| GET | `/risk/events?account&from&to` | ประวัติ risk decisions | any |
| POST | `/risk/kill-switch/trigger` | manual trigger (reason บังคับ) | ADMIN |
| POST | `/risk/kill-switch/reset` | manual reset (reason บังคับ) | ADMIN |
| POST | `/risk/evaluate` | (test/dry-run) ประเมิน trade plan โดยไม่สั่งจริง | TRADER |

### 2.6 AI (PHASE 6)

| Method | Path | คำอธิบาย |
|---|---|---|
| POST | `/ai/analyze` | ขอ analysis รอบใหม่ (symbol, timeframes) → `ai_analysis` |
| GET | `/ai/analysis?symbol&latest=true` | ผลล่าสุด + confidence breakdown + narrative |
| GET | `/ai/analysis/{id}` | ผลเต็ม + agent results |
| GET | `/ai/agents` | สถานะ agents (health/latency) |
| GET | `/calendar/economic?from&to&impact` | ปฏิทินเศรษฐกิจ + trading windows |
| GET | `/calendar/news-status?symbol` | สถานะ news window ปัจจุบัน (NO_NEW_TRADE/REDUCE_RISK/COOLING/OK) |

### 2.7 Trading — Orders / Positions / Paper (PHASE 7)

| Method | Path | คำอธิบาย | Role |
|---|---|---|---|
| GET | `/trading/mode` | TRADING_MODE ปัจจุบันของ account | any |
| POST | `/orders` | สร้าง order (จาก signal หรือ manual) — ผ่าน Risk Engine ภายใน | TRADER |
| GET | `/orders?state&symbol&from&to` | รายการ orders + events | any |
| GET | `/orders/{id}` | order + event trail | any |
| POST | `/orders/{id}/confirm` | ยืนยัน WAITING_CONFIRMATION (SEMI_AUTO/confirm flow) | TRADER |
| POST | `/orders/{id}/cancel` | ยกเลิก (state ที่อนุญาตเท่านั้น) | TRADER |
| GET | `/positions?state` | รายการ positions | any |
| GET | `/positions/{id}` | position + events | any |
| POST | `/positions/{id}/close` | ปิดทั้งหมด/บางส่วน (`size`) | TRADER |
| POST | `/positions/{id}/modify` | แก้ SL/TP (ผ่าน risk guard) | TRADER |
| GET | `/paper/account` | paper balance/equity/drawdown + equity history | any |
| POST | `/paper/account/reset` | reset paper account (starting balance) | TRADER |

### 2.8 Journal / Analytics / Backtest (PHASE 8–9)

| Method | Path | คำอธิบาย |
|---|---|---|
| GET | `/journal?filters...` | รายการ trades + journal fields |
| GET | `/journal/{trade_id}` / PUT `/journal/{trade_id}` | ดู/เพิ่ม notes, tags, screenshot_ref |
| GET | `/analytics/summary?from&to` | win rate, PF, expectancy, DD, consecutive loss |
| GET | `/analytics/breakdown?by=strategy|setup|timeframe|session|weekday|side|regime` | breakdown ตามมิติ |
| GET | `/analytics/equity-curve?from&to` | equity curve |
| GET | `/analytics/confidence-calibration` | bucket เทียบ actual win rate |
| POST | `/backtests` | สร้าง run (config: strategy, period, TF, cost model, walk-forward) |
| GET | `/backtests` / `/backtests/{id}` | รายการ/ผลลัพธ์ run (metrics + equity + trades) |
| GET | `/backtests/{id}/trades` | รายการ trades ของ run |

### 2.9 Broker / Admin / System (PHASE 1, 10)

| Method | Path | คำอธิบาย | Role |
|---|---|---|---|
| GET/POST/DELETE | `/broker/connections` | จัดการการเชื่อมต่อ (**response ไม่มี credentials เด็ดขาด**) | ADMIN |
| POST | `/broker/connections/{id}/test` | ทดสอบการเชื่อมต่อ | ADMIN |
| GET | `/broker/connections/{id}/status` | connectivity + last sync | ADMIN |
| POST | `/admin/reconcile` | สั่ง reconciliation ด้วยมือ | ADMIN |
| GET | `/admin/audit-logs?filters...` | ค้นหา audit | ADMIN |
| GET | `/alerts` / POST `/alerts/{id}/read` | การแจ้งเตือน | any |
| GET | `/healthz` / `/readyz` | health / readiness (public) | public |

## 3. WebSocket Protocol

### 3.1 `/ws/market`

```json
// client → server
{"type": "subscribe", "channel": "ticks", "symbol": "XAUUSD", "correlation_id": "..."}
{"type": "subscribe", "channel": "candles", "symbol": "XAUUSD", "timeframe": "M5"}
{"type": "unsubscribe", "channel": "..."}

// server → client
{"type": "tick", "symbol": "XAUUSD", "bid": 2650.10, "ask": 2650.40, "spread": 0.30, "ts": "..."}
{"type": "candle_update", "symbol": "...", "timeframe": "M5", "candle": {...}, "is_closed": false}
{"type": "heartbeat", "ts": "..."}          // ทุก 10s
{"type": "error", "code": "...", "message": "..."}
```

### 3.2 `/ws/trading`

```json
// push อัตโนมัติตาม account ที่ auth
{"type": "signal_created", "signal": {...}}
{"type": "signal_status", "signal_id": "...", "status": "WAITING_CONFIRMATION"}
{"type": "order_state", "order_id": "...", "from": "ORDER_SUBMITTED", "to": "BROKER_ACCEPTED", "correlation_id": "..."}
{"type": "position_update", "position": {...}}
{"type": "trade_closed", "trade": {...}}
{"type": "paper_account", "balance": ..., "equity": ..., "floating_pnl": ...}
```

### 3.3 `/ws/system`

```json
{"type": "kill_switch", "state": "TRIGGERED", "reason": "DAILY_LOSS_EXCEEDED"}
{"type": "market_data_stale", "symbol": "XAUUSD", "last_ts": "..."}
{"type": "alert", "severity": "CRITICAL", "title": "...", "payload": {}}
{"type": "news_window", "symbol": "XAUUSD", "status": "NO_NEW_TRADE", "until": "..."}
```

**กฎ WS:** auth ด้วย query token ครั้งเดียวตอน connect; client ต้อง reconnect + ดึง REST snapshot ใหม่ (ไม่พึ่งการ replay); ทุก message มี `correlation_id` เมื่อเกี่ยวกับ order/signal

## 4. API Design Rules

1. ทุก endpoint มี Pydantic request/response schema — schema คือ contract ที่ frontend ใช้ generate types
2. Mutation ฝั่ง trading = idempotent ทั้งหมด
3. Rate limit: auth endpoints เข้มที่สุด; trading endpoints ตาม config
4. ห้าม endpoint ใดคืน secret (credentials, keys) — มี test ตรวจใน PHASE 12
5. Versioning: ยังไม่มี `/v1` จนกว่าจะมี breaking change ครั้งแรก (บันทึกในเอกสารนี้เมื่อเกิด)

## Phase 1.1 implemented response contracts (2026-09-09)

Backend OpenAPI/Pydantic is authoritative for implemented endpoint responses. The rest of this document retains
planned future endpoints; this correction does not implement them.

| Endpoint | Response model | Actual fields |
|---|---|---|
| GET /api/auth/me | MeResponse | id:string, email:string, role:ADMIN/TRADER/VIEWER, is_active:boolean; all required/non-null |
| POST /api/auth/login, /api/auth/refresh | TokenPair | access_token/refresh_token:nonempty whitespace-free strings; token_type:literal bearer; expires_at:timezone-aware RFC3339; all required |
| GET /api/healthz (+ /healthz alias) | HealthResponse | status:ok, app:string, env:string, trading_mode:string, live_auto_trading:boolean, uptime_seconds:number; all required |
| GET /api/readyz (+ /readyz alias) | ReadyResponse | status:ready/not_ready, checks:{database:boolean, redis:boolean|null}, redis_enabled:boolean; all required |

MeResponse intentionally does not contain mfa_enabled, last_login_at or created_at. Frontend User aliases MeResponse.
Readiness uses HTTP 503 with the same ReadyResponse when the database is unavailable; disabled Redis is null,
not false. Existing API client non-2xx responses still reject; parseReady covers both readiness payload statuses.

Run from backend: python -m scripts.export_api_contract. This small dependency-free exporter produces
frontend/src/types/api.generated.ts and frontend/tests/fixtures/api-contract.json from selected actual OpenAPI
responses and referenced models. python -m scripts.export_api_contract --check detects stale artifacts;
the full backend test suite also checks exact regeneration. Review generated diffs when changing a response.

The frontend generic transport returns unknown. Endpoint methods validate /auth/me, tokens, health and readiness
before use; malformed token responses cannot be written to browser storage. Parsers accept additive fields and
validate required fields, nullability, role/status values and primitive types. Error text never embeds the invalid
response body. Generated types give compile-time alignment; OpenAPI-derived fixture/mutation tests verify runtime
parsers and API methods. No frontend type assertion substitutes for endpoint validation.

Incoming X-Correlation-ID is accepted only for a safe ASCII identifier of 1..64 characters starting with an
alphanumeric character; '.', '_' and '-' may follow. Otherwise the server supplies a UUID hex replacement.
The response includes the canonical ID for ordinary requests and controlled errors. Invalid IDs do not produce 500.
Login rate limiting returns the existing generic 429/RATE_LIMITED response; no account-existence detail is added.

### HARD-R02 corrective semantics

The TokenPair OpenAPI schema requires all four fields. Token strings use minLength=1 and a no-whitespace pattern;
token_type is the exact lowercase literal bearer. Datetime strings require uppercase T, seconds, optional 1..6
fractional digits and Z or a numeric timezone offset; invalid calendar values and naive/numeric dates are rejected.
Backend serialization supplies an aware datetime; the response model remains independent of the receiver's clock.
The frontend validates the calendar/offset explicitly and requires the expiry instant to be strictly later than
Date.now() at acceptance (conservative millisecond precision). There is no permissive Date.parse fallback.

Malformed login/refresh/recovery payloads raise ApiContractError before token/cookie writes. Existing stored values
are preserved and recovery does not mark the user authenticated. Genuine rejected/expired refresh sessions retain
the existing session-clearing policy. Generated types/fixtures must be regenerated with the existing exporter.


## Implemented Phase 2 market protocol (2026-09-09)

The current implementation adds authenticated symbol CRUD/read, market status/quote and paginated
candles. /ws/market uses allowlisted Origin plus a validated auth first frame; query tokens are rejected.
Canonical MarketMessage/WS command schemas are exported by the existing contract generator.
All market timestamps serialize UTC Z and Decimal values serialize strings. The Phase 2 protocol
in docs/06-market-data.md is authoritative over the earlier conceptual WS examples in section 3.

## Phase 3.5 authenticated economic APIs
GET /api/calendar/economic: bounded start/end (max7days), as_of, currency, impact, category,
status=upcoming|released, relevant_only. GET /api/news/events/{event_id}: revision history at as_of.
GET /api/news/context: as_of, fixture-only view=current|pre|release|post|none.
Pydantic/exported TypeScript+JSONSchema/runtime validation share the same contract.
GET /api/analysis/structure adds retention plus generated_at/served_at/cache_age_seconds;
as_of remains deterministic market cutoff. No new news WS is required; existing market WS is reused.
See [economic-news.md](economic-news.md) for field semantics, no-lookahead and source labels.

## Phase 4 analysis-only API
Authenticated GET /api/strategy/context and /api/trade-plan/current return the same current evaluation envelope. Registry/profiles, evaluation history, immutable candidate history and explicit candidate transitions have separate read endpoints. No order/write endpoint. Historical candidates must be interpreted with transitions and expiry. See [contracts](09-strategy-engine.md).
