# ADR-004 — Market Data Architecture

| รายการ | รายละเอียด |
|---|---|
| สถานะ | ✅ Accepted (2026-09-08) |
| บริบท | Spec หัวข้อ 5 (Market Data), 22 (Broker Adapter), PHASE 2 vs PHASE 10 |

## Context

ต้องมีข้อมูลตลาดตั้งแต่ PHASE 2 (candles, chart, analysis) แต่ Broker integration (MT5) มาถึง PHASE 10 เท่านั้น — และ MT5 python library ผูกกับ Windows terminal การพัฒนาต้องไม่สะดุดเรื่องแหล่งข้อมูล

## Decision

- **`MarketDataProvider` เป็น abstraction เดียว** ที่ engine ทั้งหมดรู้จัก — engines ห้าม import broker lib โดยตรง
- **M1 เป็น base timeframe:** provider ส่ง ticks (และ/หรือ M1 candles) → **Candle Aggregation Engine** สร้าง/อัปเดต M3..W1 จาก M1 — ไม่ขอ candle ทุก TF จาก provider
  - เหตุผล: ควบคุมความสอดคล้องข้าม TF ได้ + เทียบ backtest/live ได้ (engine เดียว)
- **Implementations ตามลำดับ Phase:**
  1. **ReplayProvider (PHASE 2)** — เล่น historical/synthetic data เป็น stream (ควบคุม speed ได้) ใช้พัฒนา/ทดสอบทั้งหมดก่อนมี broker
  2. **MT5Provider (PHASE 10)** — ดึงจาก MT5 demo, ใช้ interface เดียวกัน
  - (อนาคต: REST provider อื่น ๆ ได้โดยไม่แก้ engine)
- **Quality gate ก่อนเข้าระบบ:** ทุก tick ผ่าน validate (stale, abnormal jump, spread ผิดปกติ) — fail = system_events + kill switch ตามระดับความรุนแรง
- Realtime distribution: Redis pub/sub `market.{symbol}` → WS gateway → client

## Consequences

- บวก: PHASE 2–9 พัฒนาได้ไม่ต้องรอ broker; เปรียบเทียบ backtest/live บน aggregation logic ชุดเดียว; เพิ่ม provider ไม่กระทบ engine
- ลบ: aggregation ของ TF สูงจาก M1 อาจต่างจาก candle ของ broker เล็กน้อย (เช่น boundary timezone) — กำหนด bucketing เป็น UTC ตายตัว + บันทึกไว้ที่ docs/06 เมื่อ implement

## Alternatives

- **ดึง candle ทุก TF จาก provider ตรง ๆ:** ง่ายกว่าแต่ควบคุมความสอดคล้อง/เทียบ backtest ไม่ได้
- **รอ MT5 ตั้งแต่ PHASE 2:** บล็อกการพัฒนา analysis/strategy ยาวถึง PHASE 10
