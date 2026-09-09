# PHASE 3.5 — ECONOMIC CALENDAR / NEWS / MACRO INTELLIGENCE ENGINE

วันที่ 2026-09-09 · Workspace C:/AI Gold Trader · งานเพิ่มเติม TASK-N001–N012
รายละเอียดสถาปัตยกรรมและวิธีทำงาน: [economic-news.md](economic-news.md)

## STATUS

**IMPLEMENTATION COMPLETE — PENDING INDEPENDENT REVIEW.** Phase 4 DO NOT START.
ผู้ใช้แจ้ง Phase 1/1.1/2 PASS, Phase2.5 PASS ตาม Safe-Partial, Phase3 PASS และให้ทำ Phase3.5
ก่อน Phase4 รายงานเก่ายังคงไว้เป็นประวัติ การยอมรับ Phase เดิมเป็นข้อมูลจากผู้ใช้
รายงานนี้ไม่ได้อ้างว่าได้ทำ independent review แทนผู้ตรวจอิสระ

## DATA PROVIDER

Economic provider: FIXTURE / fixture_economic_v1 พร้อมป้าย DEMO NEWS DATA
Real economic provider: UNAVAILABLE — ไม่พบ API configuration ที่พร้อมใช้งาน
Market provider: actual IUX MT5 Demo / mt5_demo_iux / XAUUSD จาก pipeline เดิม
ไม่ scrape ForexFactory ไม่อ่านเว็บเป็นผลประกาศสด ไม่แสดง fixture ว่าเป็นข่าวจริง
NewsTextProvider/MacroNLPAnalyzer เป็น protocol เท่านั้น ไม่มี LLM invocation

## ECONOMIC CALENDAR

Canonical UTC/Decimal event พร้อม stable occurrence identity, category/impact/status,
Actual/Forecast/Previous/RevisedPrevious, release/availability times และ append-only revisions
รองรับ catalogue 18 รหัส /10 categories /3 impact levels /7 lifecycle statuses
Migration0005 เพิ่ม occurrence + revision JSONB, dedupe/reject conflicting payload และรักษาข้อมูลเดิม
Latest vintage selection เกิดก่อน schedule filter เพื่อป้องกัน reschedule ทำให้วันที่เก่ากลับมา
Downgrade ที่จะลบข้อมูลข่าวถูกปฏิเสธ

## XAUUSD RELEVANCE

Configurable currency score + impact score และ macro channels ผ่าน USD/interest rates/cross-currency/risk sentiment
USD HIGH default3, EUR MEDIUM default1; score>=2 เข้าบริบทหลัก
UI อธิบายช่องทางและความเกี่ยวข้อง ไม่ตีความว่าข้อมูลบวกต่อ USD เป็นคำสั่งขายทอง

## ECONOMIC SURPRISE ENGINE

Deterministic raw/relative surprise, higher/lower/context-dependent semantics, zero/negative/missing handling
ไม่มี invented z-score; normalized=null เพราะไม่มี historical distribution
NFP/wages higher-positive; unemployment lower-positive; inflation/FOMC context-dependent by default

## RELEASE GROUPING

NFP composite รวม headline, unemployment, wages และ negative revision
ALL_ALIGNED/MOSTLY_ALIGNED/MIXED/CONFLICTING พร้อม completeness
Mixed NFP fixture แสดง CONFLICTING; ไม่ใช้ headline ตัวเดียวสรุปทิศทาง

## NEWS REGIME

NORMAL / PRE_NEWS / NEWS_LOCK / RELEASE / POST_NEWS_VOLATILITY /
POST_NEWS_CONFIRMATION / NORMALIZED; UNKNOWN เมื่อ calendar unavailable
Configurable windows, delayed/cancelled/nonnumeric handling, overlapping risk priority
Eligibility เป็น metadata เบื้องต้น มี WAITING/BLOCKED/CAUTION ไม่ใช่ strategy execution

## MARKET REACTION

ใช้ actual canonical closed M1 รอบ synthetic event time; T+1/+5/+15m และ exact-coverage guard
Return/ATR/range/tick activity; strong/whipsaw/sweep reversal/breakout/failed breakout/muted/unconfirmed
ไม่ประมาณ sub-minute ที่ไม่มีข้อมูล ไม่เติม spread/ask ย้อนหลัง
Spread จริงต้องมี observations ก่อนข่าวและ fresh current sample; ไม่ครบแสดง UNAVAILABLE
การเกิดราคาขณะเวลาสาธิตไม่ใช่หลักฐาน causation ของข่าวเศรษฐกิจจริง

## NO-LOOKAHEAD

available_at <= as_of ก่อนเลือก latest revision; Actual/released state ไม่ปรากฏก่อน release time
Golden timeline T-30/-5/-1m / release /+5s /+1/+5/+15m และ batch/prefix equality
Future candles/quotes/observations excluded; future Phase3 lifecycle rejected
Fingerprint รวม inputs/config/version/source/cutoff และตัด operational clocks
API/pure deterministic equality บน actual IUX candles ตรวจจริง

## PHASE 3 INTEGRATION

QREV retention boundary: absence = NOT_INCLUDED_UNKNOWN ไม่อนุมาน INVALIDATED
Separate generated_at/served_at/cache_age_seconds จาก deterministic as_of/input
News structure provenance: input/config/version/window/as_of + explicit present lifecycle refs
Existing nine-TF analysis/market pipeline ยังคงใช้แหล่งราคาเดิม; ไม่เพิ่ม broker action

## USER-FACING LANGUAGE

Thai Analysis / Summary / Alerts: ภาษาไทยเป็นหลักทั้งแผงข่าว ปฏิทินและสรุปโครงสร้าง
Technical Terms: NFP/CPI/FOMC, BOS/CHOCH/MSS/FVG/OB และสถานะ API คงรหัสอังกฤษพร้อมคำอธิบาย
Asia/Bangkok UTC+7 สำหรับข่าว; ขอบเขตโครงสร้าง UTC ระบุชัดเจน
Missing Actual แสดง “ยังไม่มีผลประกาศ”; FIXTURE source warning แสดงเสมอ

## TRADING SCREEN

TradingNewsPanel: next event/countdown/impact, release components/revision,
macro explanation/regime, reaction/spread/volatility, structure, context eligibility และ provenance
Calendar: date/currency/impact/category/upcoming/released/relevant filters และ revision detail
Single server provider worker; browser refresh internal REST เท่านั้น
Desktop/tablet/mobile browser evidence อยู่ data/local/phase3-5/browser

## TEST RESULTS

| การตรวจ | ผล |
|---|---|
| Backend full regression | **277 passed**, 0 failed / 0 skipped; 10 opt-in external tests deselected ในรอบหลัก |
| PostgreSQL integration (subset ของ 277) | **16 passed** รวม fresh/up/down/re-upgrade, drift, preservation, auth/audit, market และ news |
| News targeted regression | **67 passed** รวม bounded revision case ที่เพิ่มหลังรอบหลัก; พร้อม PostgreSQL news rerun รวม **68 passed** |
| Direct MT5 external acceptance | **9 passed**: 8 timeframes มี300แท่ง + quotes/disconnect/reconnect; strict W1 test แยกตาม Safe-Partial |
| W1 actual acceptance | **231/300**, 230 closed; API/structure/prefix consistency PASS; ไม่อ้าง full300 |
| Frontend tests | **96 passed**, 0 failed / 0 skipped |
| Ruff / mypy | **PASS**; mypy54source files + scoped news body checks |
| Contracts / wheel / production build | **PASS**; generated-contract drift check, isolated wheel build, Next build/TypeScript/ESLint |
| Actual IUX API/pure/stream | **PASS** ครบ9TF, 45prefix checks; news API/pure fingerprint equality PASS |
| Native Chromium news/calendar | **PASS** 1440×1100, 820×1100, 390×844; pre/release/post/none/filter/detail; console0/assets0/API errors0 |
| Native Chromium Phase3 regression | **PASS** 9TF, overlays/toggles, reload, reconnect, M1 closed-bar refresh, Thai/mobile; console0/assets0 |
| DEV migration/audit | **PASS** head0005, original records deleted0, invalidcandles0, no secret exposure |

Normal tests omit direct external opt-in by design; separate explicit MT5 run executed9/10.
W1 strict300 is not claimed PASS: its real partial dataset was independently checked through API/prefix/browser.
News-engine five-run local median35.46ms; Phase3 batch median52.88ms. These are local sanity samples, not load certification.
Existing dependency deprecation warnings remain3, unrelated to business correctness.

ข้อผิดพลาดที่พบระหว่างพัฒนาและแก้แล้ว: overlapping risk ไม่รวม normalized group,
migration schema expectations เดิม, accessible filter label, numeric/non-numeric future release guards และ detail pagination ที่ต้องคืน100revisionsล่าสุด.
API replay harness ต้องใช้ market cutoff parameter to; หลังแก้ได้ input window/fingerprint ตรงกัน
ผลทดสอบระหว่างแก้ source/fixture เป็น intermediate evidence; ใช้ backend-tests-accepted.log และ final reports เป็น gate.
หลักฐานอยู่ data/local/phase3-5 (Git-ignored):
backend-tests-accepted.log, news-final.log, news-bounded-final.log, frontend-tests.log, mypy.log, build.log, wheel.log,
news-api-results.json, real-analysis-results.json, browser/results.json,
analysis-browser/browser-results.json, final-audit.json

## SECURITY

Existing auth dependency protects every news endpoint; no provider secrets in frontend
Strict runtime response validation; bounds/time-range checks; no future as_of;
single process polling/timeout/backoff/staleness; no browser direct external API
No change to prior auth/rate-limit/correlation/MT5 safety foundations
Secret scan and DEV original-row preservation captured in final-audit.json
Original rows deleted0. Existing account/symbol/audit/system records unchanged.
User last_login_at เปลี่ยนตาม login test; session เดิม1รายการถูก revoke ตาม logout-all ของระบบเดิม
ตรวจ hash โดยคืน revoked_at=null แล้วตรงต้นฉบับ จึงพิสูจน์ว่า field อื่นไม่เปลี่ยน
Active refresh sessions หลัง tests=0. Protected baseline files18 unchanged, Git HEAD unchanged,
index empty, no staging/commit/push.

## TRADING SAFETY

TRADING_MODE: PAPER
LIVE_AUTO_TRADING: false
MT5 order_send: NOT CALLED / no new import or execution path
Broker Execution: NOT IMPLEMENTED
Strategy / Signal / Entry / SL / TP / Risk / AI Decision: NOT IMPLEMENTED
News eligibility in FIXTURE is replay metadata only

## QREV FINDINGS

QREV-R01: FIXED — explicit bounded retention/absence boundary, present lifecycle only
QREV-R02: FIXED — operational freshness envelope outside deterministic inputs/fingerprint
QREV-R03: DEFERRED P3 for pre-existing analysis/market core bodies; scoped news+news API
check_untyped_defs enabled and checked. ไม่อ้างว่า existing core มี strict typing ครบ

## KNOWN LIMITATIONS

- ข่าวเป็น deterministic fixture ยังไม่มี live economic API acceptance
- NFP suite เป็น hourly UI demo; catalogue ของข่าวอื่นไม่ได้แปลว่ามี live coverage
- Historical bid/ask observations และ sub-minute reaction อาจไม่มี; ไม่ fabricate
- Spread samples เป็น bounded in-memory observations เสียเมื่อ restart ไม่ใช่ full tick archive
- Phase3 rolling windows สามารถ rebuild; price history ไม่ใช่ bitemporal archive
- W1 ยังคง 231/300 (230 closed) ตาม Safe-Partial; ไม่มีการเติมข้อมูลสังเคราะห์
- Single native process; distributed polling locks, NLP และ production-load acceptance ยังไม่อยู่ใน scope
- กฎ surprise/regime/eligibility เป็น configurable engineering baseline ไม่ใช่ผลวิจัยยืนยันกำไร

## PHASE 3.5 GATE

**IMPLEMENTATION COMPLETE — PENDING INDEPENDENT REVIEW**

TASK-N001–N012 delivered and verified. ไม่อ้าง independent review PASS ล่วงหน้า

## PHASE 4

DO NOT START — รอ SOL HIGH INDEPENDENT REVIEW PHASE 3.5 หรือ Combined Review ตามคำสั่งผู้ใช้
