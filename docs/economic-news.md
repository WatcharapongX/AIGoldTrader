# Phase 3.5 — Economic calendar and macro context

> Current targeted integration (2026-09-09): Forex Factory weekly JSON is the configured
> primary schedule/Forecast/Previous source for STRAT05–06. STRAT01–04 have market-only
> safety, candidate identities and cache dependencies. See [current acceptance report](forex-factory-news-strategies.md).
> Provider-selection and shared news-blocking statements below describe the earlier baseline.
> Final semantic versions: strategy-1.2.1 / news-1.2.0. Phase 5 remains NOT STARTED.


วันที่ 2026-09-09 · สถานะเป็นบริบทเชิงพรรณนาเท่านั้น · PAPER / live execution disabled

## Current runtime update — Phase 3.5R

Earlier Phase 3.5R runtime used xoomar_calendar / LIVE, a documented keyless
real feed with LIMITED coverage. Fixture remains for explicit tests/replay only.
Phase3.5R is PARTIAL; broad coverage and consensus are not available.
See [current architecture](10-dashboard-command-center.md) and [batch gate](pre-review-3.5r-4.1.md).
The section below records the original Phase3.5 baseline.

## ขอบเขตและแหล่งข้อมูล

ราคาใช้ canonical XAUUSD จาก IUX MT5 Demo ผ่าน market service เดิม ส่วนข่าวใช้
EconomicCalendarReplayProvider (fixture_economic_v1 / FIXTURE) และแสดง “ข้อมูลข่าวสาธิต · DEMO NEWS DATA”
เสมอ ไม่พบ economic API credentials/configuration ที่พร้อมใช้งานใน environment ที่ตรวจแล้ว
ไม่มีการ scrape ForexFactory หรือใช้ผลค้นเว็บเป็นปฏิทินสด ไม่มีการประดิษฐ์ผลประกาศจริง

Replay ใน UI เป็นชุดการจ้างงานสังเคราะห์ทุกชั่วโมงที่นาที 30 มี positive/mixed/negative ตามชั่วโมง
และ revision ที่นาที 10 หลังประกาศ กำหนดเวลาและตัวเลขเป็น fixture สำหรับตรวจระบบเท่านั้น
CATALOG รองรับ 18 รหัส NFP, unemployment, wages, CPI/core CPI, PCE/core PCE, FOMC rate,
Fed press/Powell, GDP/PPI, retail, ISM manufacturing/services, ADP/JOLTS/claims
แต่ catalogue ไม่ใช่การรับรองว่าเชื่อมข้อมูลสดของทุกรหัสแล้ว

EconomicCalendarProvider เป็น async protocol; UnavailableCalendarProvider แสดงสถานะ unavailable
โดยไม่มี silent fallback ไปเป็นข้อมูลสด NewsTextProvider และ MacroNLPAnalyzer เป็น extension protocols
เท่านั้น ไม่เรียก LLM และไม่มี strategy, signal, Entry/SL/TP, risk engine, broker execution

## Canonical event และ revision

EconomicEvent ใช้ English API/DB names, UTC-aware timestamps และ finite Decimal fixed-point JSON strings
แยก scheduled_at, released_at, updated_at, available_at และ revision_version
Actual ต้องไม่มีใน scheduled/upcoming/delayed/cancelled และ release time ต้องไม่เกิน available_at
ข่าว non-numeric ไม่มีผล Actual/Forecast/Previous ที่แต่งขึ้น การแถลงนโยบายยังต้องตีความตามบริบท
สถานะ released/revised ต้องมี release time แม้ไม่มีตัวเลข

Identity เป็น UUIDv5(source, provider_event_id, occurrence_key); occurrence_key ระบุ occurrence/period
และต้องไม่เปลี่ยนเพียงเพราะ scheduled_at เปลี่ยน ห้ามรวมข่าวชื่อเหมือนกันคนละ occurrence
รับข้อมูลซ้ำ version เดิม/payload เดิมเป็น no-op; version เดิม/payload ต่างเป็น error
ไม่ overwrite history และไม่คำนวณ latest ด้วยชื่อข่าวเพียงอย่างเดียว

Migration 0005_economic_events ต่อจาก 0004 โดยไม่เปลี่ยน migrations 0001–0004:
- economic_events: canonical identity, source/provider key, unique occurrence constraint
- economic_event_revisions: composite PK(event_id, revision_version), available_at,
  scheduled_at, payload_hash, canonical JSONB payload (SQLite JSON สำหรับ unit tests)
- index available_at/event_id สำหรับ point-in-time selection

Query ใช้ row_number เลือก latest revision ที่ available_at <= as_of ก่อนใช้ schedule filters
จึงไม่ทำให้วันที่เก่าฟื้นกลับมาหลัง reschedule Query/detail bounded 1000/100 versions;
calendar/context แสดงไม่เกิน 200 events; calendar มี truncated flag
ห้าม downgrade ตารางข่าวที่มีข้อมูล: migration ปฏิเสธเพื่อรักษาประวัติ
ไม่มี retention deletion ของข่าวใน Phase นี้; การเติบโตของฐานข้อมูลระยะยาวต้องมีนโยบายก่อนใช้ production
เก็บ canonical payload ไม่เก็บ HTTP response ดิบ เพราะ provider ปัจจุบันเป็น fixture ใน process

## Relevance และ surprise

NEWS_CONFIG เป็น validated JSON ผ่าน Settings โดยชื่อค่าภายในเป็น English:
- relevance: currency score 0–3 (USD=3, EUR=1)
- impact_relevance: HIGH=3, MEDIUM=2, LOW=1
- score = min(currency score, impact score); >=2 เข้าบริบทข่าวหลัก
- macro_channels: USD → USD/INTEREST_RATES, EUR → CROSS_CURRENCY; ปรับได้จาก config
- direction_overrides, weights (NFP=2, unemployment=1, wages=1), revision_weight=.5

Raw surprise = Actual - Forecast; relative = raw / abs(Forecast)
Forecast=0 ไม่มี relative division; ค่าศูนย์/ค่าลบ/ข้อมูลหายจัดการอย่างเปิดเผย
normalized เป็น null / UNAVAILABLE_NO_DISTRIBUTION เพราะยังไม่มี historical distribution
Higher/lower/context-dependent semantics แยกจาก raw numeric surprise:
NFP/wages ตามกฎ higher-positive, unemployment lower-positive;
inflation และ central-bank policy เป็น context-dependent โดย default
ข้อมูลสนับสนุน USD ไม่ใช่คำสั่งขาย XAUUSD

Release group รวม components และ revised_previous - previous โดยไม่ซ่อน negative revision
ALL_ALIGNED / MOSTLY_ALIGNED / MIXED / CONFLICTING / UNAVAILABLE พร้อม completeness
กรณี NFP beat + unemployment miss + wages beat + negative NFP revision เป็น CONFLICTING

## Timeline และ eligibility

Default HIGH pre=1800s / lock=300s; MEDIUM pre=900s / lock=120s; LOW ไม่ lock
Release=60s, observation=300s, confirmation=900s, normalized=1800s
NORMAL → PRE_NEWS → NEWS_LOCK → RELEASE → POST_NEWS_VOLATILITY →
POST_NEWS_CONFIRMATION → NORMALIZED → NORMAL
เวลาเลื่อน/ยังไม่มี release ที่ยืนยัน: คง NEWS_LOCK หลังผ่านช่วง release
Cancelled ไม่ก่อ risk; overlapping groups ใช้สถานะที่เข้มกว่า ไม่มี NORMAL reset ระหว่างความเสี่ยง
กลุ่มที่ยังอยู่ NORMALIZED ยังคงนับใน multiple-event context ร่วมกับกลุ่มถัดไป

trade_policy_state = INFORMATIONAL / CAUTION / RESTRICTED
strategy_eligibility เป็น metadata เบื้องต้นสำหรับ trend, mean reversion, breakout, news momentum/reversal
ไม่มี strategy execution consumer ข่าว unavailable, lock/release/post-volatility, whipsaw หรือ extreme spread
จำกัดบริบท; news momentum/reversal ต้องรอ reaction, spread และโครงสร้างสอดคล้อง
ค่า ELIGIBLE ใน fixture ใช้ได้เฉพาะ replay; future execution consumer ต้องตรวจ source_mode ก่อนเสมอ
ไม่มีการเปิด live trading จาก metadata เหล่านี้

## Market reaction และ no-lookahead

ใช้เฉพาะ closed canonical M1 ที่ close boundary <= as_of, source/symbol/timeframe ตรงกัน
default T+1m/+5m/+15m; configured +5/+15/+30s ส่ง REACTION_UNAVAILABLE ถ้าไม่มี exact input coverage
ไม่ interpolate วินาทีจากแท่ง M1 ไม่ใช้ forming candle หรือแท่งที่ปิดเกิน reaction window
ใช้ baseline close ก่อนกำหนดข่าว, return%, pre-event ATR, range/ATR และ tick activity เทียบก่อนข่าว
READY ต้องมีแท่ง M1 ครบช่วงและต่อเนื่อง รวม baseline ที่จบตรงเวลาเหตุการณ์
คำว่า volume หมายถึง broker tick count ไม่ใช่ exchange traded volume

Classifications: STRONG_DIRECTIONAL, WHIPSAW, LIQUIDITY_SWEEP_REVERSAL, BREAKOUT,
FAILED_BREAKOUT, MUTED, UNCONFIRMED ใช้ thresholds ใน config และ confirmed structure evidence
ค่า USD context และ price response แยกกัน ไม่อ้างเหตุและผลจริงจากข่าวสาธิต

Spread ใช้ตัวอย่าง bid/ask จริงจาก market.quote เดิม เก็บใน deque ไม่เกิน 3600
timestamp และ observed_at ต้อง <= as_of; baseline 60s/อย่างน้อย 3 observations, current fresh <=10s
ratio elevated>=2/extreme>=4; ถ้าไม่มี historical observations ส่ง null/UNAVAILABLE
การ restart จะเสียตัวอย่าง spread ในหน่วยความจำ ไม่มีการเติม ask ย้อนหลังหรือเปิด tick archive
1-second worker ไม่ใช่ tick-complete archive และไม่รับรอง microstructure ระดับวินาที

Phase 3 snapshot ใช้ M5 bounded history, configured tick size, closed bars ภายใต้ cutoff เดียวกัน
BOS/CHOCH/MSS/liquidity/zones ใช้ confirmed_at และ lifecycle ที่ทราบแล้วเท่านั้น
snapshot.as_of เกิน cutoff ไม่นำมาใช้; snapshot ที่อ้าง future lifecycle ทั้งที่ as_of ย้อนหลังถูกปฏิเสธ
QREV-R01: absent object = NOT_INCLUDED_UNKNOWN; explicit ACTIVE/SWEPT/INVALIDATED จึงมีความหมาย
bounded snapshots ไม่ใช่ durable ledger และการเลื่อน input window อาจ rebuild structure

Fingerprint SHA256 รวม version/config/source/mode/view/as_of/events-vintages/canonical candles/
observed quotes/Phase3 snapshot ข้อมูลอนาคตถูกตัดก่อน hash
generated_at/served_at/cache_age_seconds แยกใน response envelope และไม่อยู่ใน deterministic payload
Cache bounded 32; คง generated_at เมื่อ fingerprint เหมือนเดิม การสร้าง candidate ยังทำ validation/hash ทุกครั้ง
API/pure equality และ event replay prefix มี tests บน input เดียวกัน
Historical market corrections ยังเป็น canonical latest storage ตาม Phase 3 ไม่ใช่ราคาแบบ bitemporal archive

## Runtime / API / UI

Single native backend instance; lazy idempotent start worker หนึ่งตัวต่อ app,
provider polling default60s, timeout15s, capped exponential backoff<=300s, stale after300s
ไม่มี external poll ต่อ browser; internal REST refresh 15s Trading /30s Calendar
พร้อม cancellation, in-flight guard และ graceful worker shutdown
Multi-process provider locking และ long-duration production operations ยังอยู่นอก gate นี้

Authenticated GET endpoints:
- /api/calendar/economic: start/end (<=7days), as_of, currency, impact, category,
  status=upcoming|released, relevant_only
- /api/news/events/{event_id}: as_of + ordered revision history
- /api/news/context: as_of (ห้ามอนาคต), view=current|pre|release|post|none
  replay views ใช้ได้เฉพาะ fixture provider; pre/release/post anchored ณ ชั่วโมงก่อนหน้า
Existing market candles endpoint ใช้ from/to (ห้ามสับสนกับ start/end ของ calendar)
Existing /analysis/structure เพิ่ม retention และ generated_at/served_at/cache_age_seconds
ไม่มี news WebSocket ใหม่; ใช้ typed REST กับ WebSocket ราคาเดิม

Backend Pydantic → export_api_contract → generated TypeScript/JSON Schema →
runtime parser ตรวจ unknown fields, UTC/finite numbers, duplicate/source mismatch,
future revision/reaction/structure, operational clocks ก่อนแสดงผล
TradingNewsPanel, CalendarWorkspace และสรุป Phase3 ใช้ภาษาไทยเป็นหลัก
Calendar มี impact text/date/filter/detail revision; timezone Asia/Bangkok UTC+7
มี countdown, missing Actual “ยังไม่มีผลประกาศ”, no-news state, source badge, stale warning,
regime/macro/reaction/structure/eligibility และ provenance

## Validation และข้อจำกัด

ดู phase-3.5-gate.md สำหรับผลตรวจและหลักฐาน local
QREV-R03: เปิด check_untyped_defs เฉพาะ app.services.news.* และ app.api.news แล้ว
analysis core/market core เดิมยังมี mypy body gaps ระดับ P3 และ DEFERRED อย่างชัดเจน
ไม่ลดเกณฑ์ static checks เดิม ไม่อ้าง full strict typing

เอกสารอ้างอิงความหมาย (ไม่ได้ใช้เป็น live data source):
- BLS employment statistics/revision context: https://www.bls.gov/ces/
- BEA core PCE definition: https://www.bea.gov/help/faq/518
- Federal Reserve FOMC calendar: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm

ก่อนเปลี่ยนเป็น real economic provider ต้องมี approved API/permission/credentials,
explicit occurrence identity, release timestamps/availability/revision handling, quota/backoff,
source mode และ acceptance tests แยกจาก fixtures ไม่ให้ fixture masquerade เป็น live
Phase 4 DO NOT START; รอ SOL HIGH INDEPENDENT REVIEW PHASE 3.5
