# ADR-007 — Broker Architecture (Adapter Interface + Paper-First + Feature Flag)

| รายการ | รายละเอียด |
|---|---|
| สถานะ | ✅ Accepted (2026-09-08) |
| บริบท | Spec หัวข้อ 22 (Broker Adapter), 23 (Live Trading Feature Flag), 24 (Paper Trading) |

## Context

Spec ห้ามผูก trading logic เข้ากับ broker โดยตรง ต้องมี BrokerAdapter interface รองรับ MT5 ก่อนแล้วต่อยอด OANDA/Saxo โดยระยะพัฒนา LIVE = disabled, เริ่มจาก demo/paper เท่านั้น

## Decision

- **`BrokerAdapter` interface ครบตาม Spec:** connect, disconnect, get_account, get_symbol, get_price, get_positions, get_orders, place_order, modify_order, cancel_order, close_position, partial_close + connection state + event callbacks
- **เรียกได้จาก OMS/PositionService เท่านั้น** (import rule + architectural test) — analysis/AI layer ห้ามแตะ
- **Implementations:**
  1. **PaperBroker (PHASE 7)** — virtual broker ใช้ real market data จำลอง fill/spread/commission/slippage; เป็น default ของ `TRADING_MODE=PAPER`
  2. **MT5Adapter (PHASE 10)** — **Demo server เท่านั้นในระยะพัฒนา:** adapter ปฏิเสธ connection ที่ server ไม่อยู่ใน demo allow-list (enforce ที่ code)
  3. อนาคต: OANDAAdapter, SaxoAdapter ผ่าน interface เดียวกัน
- **TRADING_MODE feature flag:** `BACKTEST | PAPER | SEMI_AUTO | LIVE` — default `PAPER` ทุก environment; `LIVE` เปิดได้เฉพาะโดย ADMIN โดยเจตนา + audit (INV-08) — ไม่มี config path ใดเปิด LIVE อัตโนมัติ
- **Credentials:** เข้ารหัส AES-GCM ก่อนเก็บ (key จาก env), decrypt เฉพาะใน broker service, ห้ามออกทาง API/log (FR-SE-02)
- **Reconciliation:** worker เทียบ orders/positions ระบบกับ broker ตามรอบ + เมื่อเกิดเหตุการณ์ผิดปกติ — mismatch = alert + kill switch ตามนโยบาย

## Consequences

- บวก: เพิ่ม broker ใหม่ไม่แตะ trading logic, paper/live ใช้ flow เดียวกัน (เทียบพฤติกรรมได้), กัน live order โดยไม่ตั้งใจได้ 3 ชั้น (flag + demo allow-list + approval gate)
- ลบ: MT5 python library ผูก Windows — adapter ทำงานบน Windows host/container แยกจาก services อื่น (บันทึกข้อจำกัดนี้ไว้ใน docs/15 เมื่อ implement)

## Alternatives

- **FIX protocol กลาง:** ยืดหยุ่นสูงแต่ซับซ้อนเกิน v1 ที่คู่คือ MT5
- **เรียก MT5 ตรง ๆ ใน trading logic:** ผิ Spec หัวข้อ 22 — ปฏิเสธ
