# ADR-001 — Frontend Framework & State Management

| รายการ | รายละเอียด |
|---|---|
| สถานะ | ✅ Accepted (2026-09-08) |
| บริบท | Spec หัวข้อ 3 (Technology Stack), 30–33 (Web UI) |

## Context

ต้องเลือก frontend stack สำหรับ Enterprise Trading Dashboard: หลายหน้า (16 เมนู), chart realtime, WebSocket push, form/validation จำนวนมาก และต้อง type-safe ต่อ contract กับ backend Spec กำหนด Next.js + React + TypeScript + Tailwind + TradingView Lightweight Charts และให้ "เลือก state management ตาม complexity จริง" ระหว่าง Zustand กับ Redux Toolkit

## Decision

- **Next.js (App Router) + React + TypeScript + Tailwind CSS** ตาม Spec — TypeScript บังคับทั้ง repo
- **Chart = TradingView Lightweight Charts** — ผูกข้อมูลผ่าน data layer ของเรา (ครอบด้วย component เดียว `TradingChart` กัน vendor lock)
- **State = Zustand** — เหตุผลจาก complexity จริง:
  - state ส่วนใหญ่เป็น **per-feature push data** (ราคา, positions, signals) ที่มาจาก WebSocket ไม่ใช่ client-side app state ซับซ้อนที่ต้อง orchestrate
  - ต้องการ re-render ที่แคบ (เฉพาะ component ที่ฟัง slice นั้น) เพื่อรับ tick ถี่โดยไม่กระทบทั้งหน้า
  - ไม่มี requirement ที่ต้องการ devtools/boilerplate ระดับ Redux (เช่น middleware stack ใหญ่, strict immutability contract ข้ามทีมใหญ่)
- **WebSocket = native WebSocket ครอบด้วย client เดียว** (`lib/ws.ts`) + auto-reconnect + resync ผ่าน REST snapshot
- API types generate จาก Pydantic schema ของ backend (single source of truth)

## Consequences

- บวก: bundle เบา, เร็วต่อการพัฒนา, test component ง่าย
- ลบ: ถ้าอนาคต state logic ซับซ้อนขึ้นมาก (เช่น workflow engine ฝั่ง client) ต้องประเมินใหม่ — บันทึก ADR ใหม่
- ต้องมี discipline: 1 store ต่อ feature ห้ามสร้าง global store กลางที่ใหญ่จนควบคุมไม่ได้

## Alternatives

- **Redux Toolkit:** เหมาะกับทีมใหญ่/state ซับซ้อน — แต่ boilerplate เกินจำเป็นสำหรับ push-data dominated UI
- **React Query + context:** ไม่ครอบคลุม WS push ที่เป็นหัวใจของระบบ

## Phase 1 implementation note (2026-09-08)

Installed versions: Next.js 16.3.4, React 19.2.8, Zustand 5.0.15. Follow the bundled Next.js documentation. Use `src/proxy.ts` (Next.js 16 convention) for optimistic routing and client hydration plus authenticated backend endpoints for actual session verification. Login stays accessible with expired cookies. Native WebSocket wrapper is `src/lib/websocket.ts`. Docker uses standalone output with static/public assets copied explicitly. API types remain manually maintained in Phase 1; automatic schema generation has not been implemented.
