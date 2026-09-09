# Documentation Index — AI-Assisted Trading Platform (XAUUSD & Forex)

| เอกสาร | สถานะ | สร้าง/อัปเดตใน Phase | คำอธิบาย |
|---|---|---|---|
| [../implementation_plan.md](../implementation_plan.md) | ✅ Live | P0 (อัปเดตตลอด) | แผนงานหลัก + ติดตาม task |
| [01-requirements.md](01-requirements.md) | ✅ Baseline | P0 | ความต้องการ FR/NFR + Guardrails |
| [02-system-architecture.md](02-system-architecture.md) | ✅ Baseline | P0 | สถาปัตยกรรมระบบ + 22 modules |
| [03-trading-domain.md](03-trading-domain.md) | ✅ Baseline | P0 | Domain model + enums + state machines + invariants |
| [04-database-design.md](04-database-design.md) | ✅ Baseline | P0 | ERD + schema 33 ตาราง |
| [05-api-design.md](05-api-design.md) | ✅ Baseline | P0 | REST + WebSocket contract |
| [06-market-data.md](06-market-data.md) | Implementation complete / review pending | P2 | รายละเอียด market data + aggregation + providers |
| [07-market-structure.md](07-market-structure.md) | Implementation complete / combined review pending | P3 | นิยาม structure (swing/BOS/CHoCH/MSS) + parameters |
| [08-smc-ict.md](08-smc-ict.md) | Implementation complete / combined review pending | P3 | นิยาม SMC/ICT + confluence model |
| [phase-3-gate.md](phase-3-gate.md) | Implementation complete / combined review pending | P3 | Golden, PostgreSQL, actual IUX and browser acceptance evidence |
| 09-strategy-engine.md | ⬜ Planned | P4 | Strategy framework + 5 strategies + trading styles |
| 10-ai-engine.md | ⬜ Planned | P6 | Multi-agent + prompt design + validation |
| 11-risk-engine.md | ⬜ Planned | P5 | ทุก rule + sizing + kill switch |
| 12-order-management.md | ⬜ Planned | P7/P11 | OMS state machine + idempotency + confirmation flow |
| 13-paper-trading.md | ⬜ Planned | P7 | Simulation model (spread/slippage/commission) |
| 14-backtesting.md | ⬜ Planned | P9 | Backtest engine + walk-forward |
| 15-broker-integration.md | ⬜ Planned | P10 | BrokerAdapter + MT5 demo + reconciliation |
| 16-security.md | ⬜ Planned | P12 | Security architecture + hardening |
| [17-testing.md](17-testing.md) | Baseline (Phase 1) | P1 (เริ่ม) + สะสม | กลยุทธ์การทดสอบทั้งหมด |
| [18-devops.md](18-devops.md) | Baseline (Phase 1) | P1 (เริ่ม) + P12 | Native Windows DEV, optional Docker, environments |
| 19-uat.md | ⬜ Planned | P13 | แผน UAT + ผลการทดสอบ |
| 20-production-readiness.md | ⬜ Planned | P14 | Readiness checklist + approval record |
| architecture-decision-records/ADR-001..007 | ✅ Accepted | P0 | บันทึกการตัดสินใจเชิงสถาปัตยกรรม |

## สถานะ

| สัญลักษณ์ | ความหมาย |
|---|---|
| ✅ Baseline / Accepted | ใช้เป็น contract ได้ — เปลี่ยนแปลงต้องผ่าน Change Log ของเอกสารนั้น |
| ⬜ Planned | จะสร้างใน Phase ที่ระบุ (ตาม implementation_plan.md) |
| 🔄 In Progress | กำลังเขียน/อัปเดต |

**กฎ:** เอกสาร Baseline (01–05 + ADR) คือ contract ของ codebase — code ต้องตรงกับเอกสาร ถ้าจำเป็นต้องเบี่ยง ให้อัปเดตเอกสารก่อน implement (Definition of Done ทุก phase)

Phase 1 verification report: [phase-1-gate.md](phase-1-gate.md).

Phase 2 provisional verification: [phase-2-gate.md](phase-2-gate.md). Combined Phase 1.1 + Phase 2 independent review pending.

Phase 3.5 economic context: [economic-news.md](economic-news.md).
Verification: [phase-3.5-gate.md](phase-3.5-gate.md). Phase4 DO NOT START.

- [Phase 4 strategy architecture](09-strategy-engine.md)
- [Phase 4 implementation gate](phase-4-gate.md)

- [Phase3.5R + 4.1 architecture and provider limits](10-dashboard-command-center.md)
- [Pre-review completion batch verification](pre-review-3.5r-4.1.md)
Current stop gate supersedes earlier historical next-phase notes: Phase5 DO NOT START.

- [SOL-P1-001 corrective identity and persistence verification](sol-p1-001-corrective.md)
