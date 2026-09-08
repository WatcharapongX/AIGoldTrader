# AI-Assisted Trading Platform for XAUUSD & Forex

ระบบ Web Application สำหรับวิเคราะห์และช่วยเทรด XAUUSD/Forex แบบ Real-time — Market Analysis, AI Signal (multi-agent), Risk Engine, Paper Trading, Backtesting, Trade Journal, Broker Integration

> ⚠️ **LIVE AUTO TRADING = DISABLED** — ระบบพัฒนาและทดสอบในโหมด `TRADING_MODE=PAPER` เท่านั้น การเปิด LIVE ต้องได้รับอนุมัติจากผู้ดูแลระบบโดยเจตนา (ดู `docs/20-production-readiness.md`)

## เอกสารสำคัญ

| เอกสาร | คำอธิบาย |
|---|---|
| [implementation_plan.md](implementation_plan.md) | แผนงานหลัก 15 Phase + ติดตาม Task (Source of Truth ของความคืบหน้า) |
| [docs/README.md](docs/README.md) | สารบัญเอกสารทั้งหมด (Requirements, Architecture, ADR-001..007) |

## Technology Stack

- **Frontend:** Next.js + React + TypeScript + Tailwind CSS + TradingView Lightweight Charts + Zustand
- **Backend:** Python 3.12 / FastAPI (REST + WebSocket + Background Workers)
- **Database:** PostgreSQL 16 (Native Windows service for local DEV); TimescaleDB belongs to later market-data work
- **Cache/PubSub:** Redis adapter retained, disabled by default in Phase 1
- **Local DEV:** Native Windows + Python/FastAPI + Node.js/Next.js; Docker Compose is optional

## โครงสร้าง

```
backend/   FastAPI application + workers + migrations (alembic)
frontend/  Next.js dashboard
docs/      เอกสารสถาปัตยกรรม + ADR
```

## การรัน (Development — Native Windows)

ดูขั้นตอนตั้งค่า PostgreSQL, environment, migration และ seed ใน [docs/18-devops.md](docs/18-devops.md).
Backend อ่าน backend/.env: ตั้ง DATABASE_URL และ SECRET_KEY ของคุณ พร้อม
REDIS_ENABLED=false, TRADING_MODE=PAPER, LIVE_AUTO_TRADING=false.

~~~powershell
# Terminal 1 — หลังติดตั้ง dependencies และตั้ง environment/migrate/seed
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000 --loop app.core.event_loop:new_event_loop

# Terminal 2 — เริ่มจาก repository root
Set-Location frontend
npm.cmd ci
npm.cmd run dev
~~~

เปิด http://localhost:3000/login. ไม่มี PostgreSQL ยังรัน unit tests และ API health ได้;
การ login และ audit จริงต้องเชื่อม PostgreSQL. Docker/WSL/Redis service ไม่จำเป็นสำหรับ Local DEV Phase 1.

## Working Rules (สรุป — เต็มใน implementation_plan.md §21)

1. ห้าม Trial-and-Error — Identify → Analyze → Plan → Implement → Verify
2. ห้าม Duplicate Architecture — search ก่อนสร้างใหม่
3. ห้าม Hardcode secret/config — ใช้ Environment Variables
4. AI ห้ามส่ง order เอง / ห้าม bypass Risk Engine
5. ทุก Phase ต้องผ่าน Build + Test + Verify ก่อนไป Phase ถัดไป

## Phase 1 verification

See [test commands](docs/17-testing.md), [native startup](docs/18-devops.md), and
[gate evidence](docs/phase-1-gate.md). Phase 1 is COMPLETE (11/11 tasks).
TASK-020 passed with native PostgreSQL 18.6 migration/rollback/auth/audit, real Chromium login/session/logout,
36 backend tests, 6 frontend tests and build/lint/typecheck. Phase 2 has not started; independent review is next.
# AIGoldTrader
