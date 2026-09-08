# ADR-006 — AI Architecture (LLM as Reasoning Layer, Never Order Sender)

| รายการ | รายละเอียด |
|---|---|
| สถานะ | ✅ Accepted (2026-09-08) |
| บริบท | Spec หัวข้อ 13 (AI Analysis Engine), 14 (Multi-Agent), 15 (Confidence) |

## Context

Spec ห้ามชัดเจน: LLM ห้ามวิเคราะห์ raw chart แล้วตัดสิน Buy/Sell โดยตรง, ห้าม bypass Risk Engine, ห้ามส่ง order เอง แต่ต้องใช้ AI ให้เป็นประโยชน์: aggregate, explain, rank, detect conflicts, สร้าง narrative, ประเมิน confidence จาก evidence

## Decision

- **AI ได้รับเฉพาะ structured context** (ผลจาก Feature Extraction: structure/liquidity/smc/regime/indicators/sessions + risk context) — ไม่มี raw chart/raw price series ส่งเข้า LLM เพื่อตัดสินทิศทาง
- **Multi-agent 9 ตัว** (Trend, Structure, Liquidity, SMC, Momentum, Volatility, News, Risk, Decision) — agents 1–8 วิเคราะห์เฉพาะด้านตนเองจาก context เดียวกัน; **Decision Agent** รวมผลเป็น `AIRecommendation` (schema ตาม docs/03 §9)
- **Validation เหนือ output:** ทุก LLM response ผ่าน Pydantic `AIRecommendation` — fail = ปฏิเสธ + บันทึก `ai_analysis.validation_status=FAILED` (ไม่มีทางใช้ output เพื่อการเทรด)
- **Confidence ไม่ได้มาจาก LLM:** ConfidenceEngine คำนวณจาก weighted evidence ที่ agents/engines ส่งมา (weights configurable) — LLM เสนอได้แค่ input บางส่วน, ตัวเลขสุดท้ายคำนวณแบบ deterministic + เก็บ breakdown ลง DB (INV-07)
- **ทางเดินของ AI output:** `AIRecommendation` → enrich signal/trade plan → **Risk Engine** → WAITING_CONFIRMATION — **ไม่มี code path ใดจาก AI module ไป BrokerAdapter/OMS โดยตรง** (บังคับด้วย import rule + architectural test, INV-02)
- **Provider abstraction:** `AIProvider` interface (config ผ่าน env) + timeout/retry + health check — AI unavailable เป็น kill switch trigger ตาม config; ระบบทำงานต่อได้แบบ quant-only degraded mode
- `risk_status` ใน output ของ AI ถูกระบบ **overwrite เสมอ** ด้วยผลจริงของ Risk Engine

## Consequences

- บวก: hallucination ไม่สามารถทำอันตรายการเงินได้, ทุกคำแนะนำตรวจย้อนได้, เปลี่ยน provider ไม่กระทบ pipeline
- ลบ: ค่าใช้จ่าย/latency ของ LLM calls — กันด้วยเรียกเมื่อมี candidate setup เท่านั้น + cache ผล analysis ตาม candle close; agent 9 ตัว = จำนวน call สูง → เริ่มด้วย batched prompt ต่อรอบ (จัดกลุ่ม agents ที่ใช้ context เดียวกัน) แล้ววัดผลก่อน

## Alternatives

- **Single-LLM direct decision:** ตรงข้าม Spec ทั้งหมด — ปฏิเสธ
- **Fine-tuned local model:** น่าสนใจระยะยาวแต่เกิน scope v1 (เก็บเป็นแนวทางอนาคต)
