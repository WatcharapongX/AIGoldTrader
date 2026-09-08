# ADR-005 — Trading Engine Architecture (Deterministic Pipeline + Event-Sourced OMS)

| รายการ | รายละเอียด |
|---|---|
| สถานะ | ✅ Accepted (2026-09-08) |
| บริบท | Spec หัวข้อ 2 (Target Architecture), 20 (OMS), 21 (Duplicate Protection), 50 (Final Principle) |

## Context

หัวใจของระบบคือ pipeline จากข้อมูล → การตัดสินใจ → order ที่ต้อง (1) audit ได้ทุกขั้น (2) ทำซ้ำได้เพื่อเทียบ backtest กับ live (3) กัน human/machine error (duplicate, invalid state) (4) รักษาลำดับ "Risk Engine เป็น gate เดียว"

## Decision

- **Deterministic analysis pipeline:** engines ทั้งหมดเป็น pure function `(candles, config) → structured output` — ไม่มี hidden state, ไม่เรียก I/O ภายใน engine → รันซ้ำบนข้อมูลเดิมได้ผลเดิม (เทียบ backtest/live ได้)
- **Risk Engine เป็น chokepoint เดียว:** เส้นทางสู่ `OrderService.submit()` ต้องเรียก `RiskEngine.evaluate()` เสมอ — บังคับด้วย (1) code structure (2) **architectural test** ที่ fail ถ้ามี path ไป BrokerAdapter ที่ไม่ผ่าน risk (INV-01, INV-02)
- **Event-sourced order/position:** state ปัจจุบัน + `*_events` append-only + audit ใน transaction เดียว — ตอบคำถาม "order นี้ผ่านอะไรมาบ้าง" ได้ครบทุกขั้น
- **Idempotency 3 ชั้น:** (1) `Idempotency-Key`/`ClientOrderID` unique ใน DB (2) Redis lock ระหว่างประมวลผล (3) state validation ก่อน transition — ครอบทุก source ของ duplicate (double click, network retry, WS retry, worker retry)
- **Invalid transition = reject + alert** — ไม่มี auto-repair ของ state; path เดียวที่ออกจาก ERROR คือ reconciliation
- **Error ระหว่าง submit:** timeout/unknown outcome → สถานะ ERROR + reconcile กับ broker ก่อนตัดสินใจต่อ (ห้าม retry ตาบอด)

## Consequences

- บวก: audit ครบ, ทดสอบ state machine ได้ทั้งตาราง transition, backtest/live ใช้ engine ชุดเดียว
- ลบ: overhead การเขียน event ทุก transition (ยอมรับได้ — เป็น requirement ของ auditability), ต้องเขียน architectural test ตั้งแต่ PHASE 7

## Alternatives

- **Mutable state + log บางส่วน:** ง่ายกว่าแต่ audit ไม่ครบ = ผิด requirement Spec หัวข้อ 20/35
- **Event sourcing เต็มรูปแบบ (ไม่มี current-state table):** บริสุทธิ์แต่ query ยาก — เลือก hybrid (state + events)
