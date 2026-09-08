# ADR-003 — Database & Storage Strategy

| รายการ | รายละเอียด |
|---|---|
| สถานะ | ✅ Accepted (2026-09-08) |
| บริบท | Spec หัวข้อ 3 (Database), 34 (Database Design) |

## Context

ระบบมีข้อมูล 2 ลักษณะที่ต่างกันมาก: (1) time-series ความถี่สูง (ticks/candles) ปริมาณมหาศาล (2) transactional data ของการเทรด (orders/positions/audit) ที่ต้อง ACID + append-only audit Spec กำหนด PostgreSQL + TimescaleDB (ถ้าจำเป็น) + Redis

## Decision

- **PostgreSQL 16 เป็น primary database ทุกตาราง** (33 ตารางตาม docs/04-database-design.md)
- **TimescaleDB extension สำหรับ `ticks` และ `candles`** เป็น hypertables:
  - เหตุผลที่ "จำเป็น": XAUUSD tick ต่อเนื่อง + candles 9 TF — ต้องการ chunk-based query และ compression; แต่เป็น extension ของ Postgres จึงไม่เพิ่มระบบ DB ใหม่ (single engine)
  - Retention: ticks เก็บตาม config (เช่น 30 วัน), candles M1 1 ปี+ / TF สูง ตลอด — ปรับต่อ environment ได้
- **Redis 7** มีบทบาทชัดเจน 3 อย่าง: (1) cache (analysis snapshot, quote ล่าสุด) (2) pub/sub ระหว่าง worker↔WS gateway (3) **order lock สำหรับ idempotency/duplicate protection** — ไม่ใช้เป็น source of truth ของสิ่งใด
- **Alembic migration** ทั้งหมด — schema เปลี่ยนผ่าน migration เท่านั้น + อัปเดต docs/04 พร้อมกัน
- Audit/event tables append-only (บังคับที่ permission + review)

## Phase 1 applicability — 2026-09-08

Native Windows PostgreSQL is the local primary database. The foundation migration needs no
TimescaleDB extension. Redis service is optional (REDIS_ENABLED=false by default):
auth, sessions and audit use PostgreSQL and rate limiting is currently in process.
Existing cache/pubsub helpers remain an adapter boundary; disabled publishing returns false.
No distributed lock or order execution is implemented in Phase 1.
TimescaleDB and distributed worker/order-lock requirements must be evaluated in their respective phases.
Docker Compose remains an optional deployment option, never a local DEV prerequisite.

## Consequences

- บวก: engine เดียว, ACID ครบ, hypertable query เร็ว, Redis แยกบทบาทชัด
- ลบ: ต้องดูแล TimescaleDB extension ใน Docker image (ใช้ official timescale image); ถ้าอนาคต tick โหลดมากจริง อาจแยก instance สำหรับ time-series — ออกแบบ schema ให้แยกได้โดยไม่แตะ transactional tables

## Alternatives

- **PostgreSQL ล้วน (ไม่ใช้ Timescale):** ทำได้แต่ partitioning ต้องจัดการเอง + compression ไม่มี
- **InfluxDB/ClickHouse สำหรับ time-series:** เร็วมากแต่เพิ่มระบบใหม่ + ข้อมูลเทรดต้อง join ข้าม engine — เกินจำเป็นของ v1
