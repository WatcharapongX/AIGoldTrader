# ADR-002 — Backend Framework & Service Model

| รายการ | รายละเอียด |
|---|---|
| สถานะ | ✅ Accepted (2026-09-08) |
| บริบท | Spec หัวข้อ 3 (Backend), 2 (Target Architecture) |

## Context

Spec กำหนด Python + FastAPI พร้อม REST + WebSocket + Background Workers ต้องรองรับ: realtime data, analysis pipeline, OMS พร้อม transaction/event, AI calls ที่ช้า, และ testability สูง

## Decision

- **Python 3.12+ / FastAPI** + Uvicorn — async native รองรับ WS และ I/O หนัก, Pydantic v2 เป็น validation layer ทุก boundary (รวม LLM output)
- **โครงสร้าง service แบบ modular monolith** (ไม่ใช่ microservices) — แยก module ตาม 22 core modules ที่ boundary ชัดเจน (interface + import rule) แต่รันใน process เดียว + worker processes
  - เหตุผล: ทีมเล็ก, ยังไม่มี scale requirement แยก service, transaction ข้าม module (order+event+audit) ทำง่ายและปลอดภัยกว่า
  - ทางออกสู่การแยกในอนาคต: สื่อสารข้าม module ผ่าน interface + pub/sub (Redis) เท่านั้น — แยกออกเป็น service ได้เมื่อจำเป็น
- **Background workers = separate processes** (market_data, analysis, signal, risk_monitor, ai, position, news, reconciliation) สื่อสารผ่าน Redis pub/sub + DB
- **Transaction pattern:** state change + event + audit ใน DB transaction เดียว (INV-06)
- Tooling: ruff (lint), mypy (typecheck), pytest; config ทั้งหมดจาก env (pydantic-settings)

## Consequences

- บวก: พัฒนาเร็ว, test ง่าย, deploy ง่าย (compose), Python ecosystem การเงิน/วิเคราะห์ครบ
- ลบ: ต้องคุม import rule ระหว่าง module (ใช้ lint rule + architectural test บังคับ), CPU-bound analysis ต้องระวัง event loop (ใช้ worker/offload เมื่อจำเป็น)

## Alternatives

- **Node/NestJS:** TypeScript ร่วมกับ frontend แต่ ecosystem เชิง quant/วิเคราะห์อ่อนกว่า
- **Microservices ตั้งแต่ต้น:** ต้นทุน ops สูงเกินประโยชน์ในขั้นนี้
- **Django:** admin ดีแต่ WS/async ไม่ใช่จุดแข็งหลัก
