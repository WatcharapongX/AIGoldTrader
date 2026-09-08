# 01 — Requirements (ความต้องการของระบบ)

| รายการ | รายละเอียด |
|---|---|
| เอกสาร | docs/01-requirements.md |
| เวอร์ชัน | 1.0 (2026-09-08) |
| สถานะ | ✅ อนุมัติใช้งาน (baseline สำหรับ PHASE 1+) |
| เกี่ยวข้องกับ | implementation_plan.md, docs/02-system-architecture.md |

---

## 1. ภาพรวมโปรเจกต์

สร้าง **Web Application สำหรับวิเคราะห์และช่วยเทรด XAUUSD และ Forex แบบ Real-time** ประกอบด้วยระบบวิเคราะห์ตลาด, AI Trading Analysis, Risk Management, Paper Trading, Backtesting, Trade Journal และ Broker Integration

- **ช่วงแรกโฟกัส XAUUSD** (ออกแบบให้รองรับ Forex หลาย Symbol: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD ในอนาคต)
- เป้าหมายสูงสุด: ระบบเทรดที่ **Explainable, Auditable, Testable, Risk-controlled, Modular, Extensible, Production-ready**
- ระบบต้องรองรับการพัฒนาต่อเป็น: Manual → AI-Assisted → Semi-Automatic → Automated Trading

## 2. Guardrails บังคับ (ไม่สามารถต่อรองได้)

| ID | กฎ |
|---|---|
| G-01 | **LIVE AUTO TRADING = DISABLED** ในช่วงพัฒนา — เปิดเฉพาะ Market Analysis, AI Signal, Paper Trading, Backtesting, Manual Confirmation จนกว่าระบบผ่าน Test + Validation ครบ |
| G-02 | **ห้าม**ให้ LLM ส่งคำสั่งซื้อขายโดยตรงโดยไม่มี Risk Engine และ Validation Layer |
| G-03 | **TRADING_MODE** (`BACKTEST` / `PAPER` / `SEMI_AUTO` / `LIVE`) — Default = `PAPER`, ห้าม Enable `LIVE` อัตโนมัติ |
| G-04 | AI ห้าม Bypass Risk Engine, ห้ามส่ง order เอง, ห้ามแก้ account risk, ห้าม override kill switch |
| G-05 | ห้ามใช้ Signal ใด Signal หนึ่งเป็น Entry โดยลำพัง — ต้องใช้ Confluence เสมอ |
| G-06 | ห้าม Hardcode credentials / API keys / risk config / symbol config — ใช้ Environment Variables + DB config เท่านั้น |
| G-07 | ห้าม Broker Secret ส่งไป Frontend |

## 3. ผู้ใช้และสิทธิ์ (RBAC)

| Role | สิทธิ์ |
|---|---|
| ADMIN | จัดการ users, risk config ระดับระบบ, broker connections, kill switch, อนุมัติเปิด LIVE |
| TRADER | เทรด (paper/semi-auto), ยืนยัน/ปฏิเสธ signal, จัดการ strategy config, ดู analytics |
| VIEWER | ดู dashboard/analysis/journal อย่างเดียว |

## 4. Functional Requirements

รหัส FR-XX ใช้อ้างอิงใน Test plan และ Acceptance Criteria ของแต่ละ Phase

### 4.1 Market Data (FR-MD)

- FR-MD-01 รองรับข้อมูล Tick, Bid, Ask, Spread, OHLC, Volume (ถ้ามี), Candle
- FR-MD-02 Timeframes: M1, M3, M5, M15, M30, H1, H4, D1, W1
- FR-MD-03 Candle Aggregation จาก M1 base ขึ้นไปทุก TF, แก้ไข candle ที่ยังไม่ปิดได้ (in-place update)
- FR-MD-04 เก็บ tick/candle ลง time-series storage (TimescaleDB hypertable)
- FR-MD-05 แสดงราคา Realtime ผ่าน WebSocket (tick + candle update) พร้อม heartbeat + reconnect
- FR-MD-06 Market data freshness monitoring — ตรวจ stale/abnormal data และแจ้งเตือน
- FR-MD-07 Market Data Provider เป็น abstraction — รองรับหลายแหล่ง (Replay/Simulated สำหรับ dev, MT5 ใน PHASE 10) โดยไม่ต้องแก้ engine
- FR-MD-08 Symbol management — config ต่อ symbol (digits, contract size, session hours, spread defaults) v1 = XAUUSD

### 4.2 Analysis Engines (FR-AN)

- FR-AN-01 **Market Structure Engine**: Swing High/Low, HH, HL, LH, LL, BOS, CHoCH, MSS — แยก Internal / External structure, แสดงบน chart ได้
- FR-AN-02 **Liquidity Engine**: Previous Day/Week High-Low, Asian/London/NY High-Low, Equal High/Low, Buy-side/Sell-side Liquidity, Liquidity Sweep/Grab
- FR-AN-03 **SMC/ICT Engine**: Order Block, Breaker Block, FVG, IFVG, BOS, CHoCH, MSS, Premium/Discount/Equilibrium, OTE, Liquidity Sweep, Session Liquidity
- FR-AN-04 **Indicator Engine**: ATR, RSI, EMA/SMA, ADX, Bollinger, Volume average + framework เพิ่ม indicator ได้
- FR-AN-05 **Market Regime Engine**: TRENDING_UP, TRENDING_DOWN, RANGING, HIGH_VOLATILITY, LOW_VOLATILITY, BREAKOUT, PULLBACK, NEWS_CONDITION, UNKNOWN (ต่อ timeframe)
- FR-AN-06 **Session Engine**: Asian/London/New York sessions, overlap detection (config ได้)
- FR-AN-07 **Multi-Timeframe Top-Down Analysis** (เช่น D1→H4→H1→M15→M5): วิเคราะห์แยกต่อ TF แล้ว aggregate เป็น Market Bias พร้อมเหตุผลราย TF
- FR-AN-08 ทุก engine เป็น deterministic pure function ของข้อมูล candle — ทดสอบย้อนหลัง/กับ golden dataset ได้

### 4.3 Strategy & Signal (FR-ST)

- FR-ST-01 Strategy Framework แบบ plug-in — เพิ่ม strategy ใหม่ไม่ต้องแก้ engine
- FR-ST-02 Strategy ใน v1: (1) Liquidity Sweep + MSS + FVG (2) Trend Pullback (3) Breakout Momentum (4) Mean Reversion (5) Run Trend
- FR-ST-03 ทุก strategy ต้องมี: Entry condition, Invalidation, Stop Loss logic, Take Profit logic, Risk Rule, Session Rule, Market Regime Rule
- FR-ST-04 Strategy Engine เลือก strategy ตาม Market Regime — ห้ามใช้ strategy เดียวกับทุกตลาด
- FR-ST-05 Trading Modes: SCALP, DAY_TRADE, SWING, RUN_TREND — config แยกกัน (timeframe, risk, min RR, max holding period, trailing, partial close)
- FR-ST-06 ตัวอย่าง Confluence ที่ถือเป็น Valid Setup: Liquidity Sweep + MSS + FVG + HTF Bias + Valid Session + Risk Reward ครบ
- FR-ST-07 ทุก Signal ต้องสร้าง **Trade Plan** ครบ: Symbol, Direction, Setup, Market Regime, Entry, Entry Zone, SL, TP1/TP2/TP3, RR, Risk %, Position Size, Session, Confidence, Evidence, Invalidation, Expiration
- FR-ST-08 Signal มีวงจรชีวิต (active → confirmed/rejected/expired/cancelled)

### 4.4 Risk Management (FR-RK)

- FR-RK-01 Risk rules ครบ: Risk Per Trade, Max Daily Loss, Max Weekly Loss, Max Drawdown, Max Concurrent Trades, Max Symbol Exposure, Max Correlated Exposure, Minimum RR, Max Spread, Max Slippage, Min Free Margin, News Protection, Session Restriction, Position Sizing
- FR-RK-02 Risk Engine คืน: APPROVED / REJECTED / REDUCE_SIZE / WAIT พร้อม reason เสมอ
- FR-RK-03 ทุกค่า risk เป็น configuration (DB + env) — แก้ได้ผ่าน API พร้อม audit before/after
- FR-RK-04 **Kill Switch**: triggers ครบ (daily/weekly loss, max DD, broker disconnected, market data stale/abnormal, spread abnormal, price gap abnormal, AI unavailable, DB unavailable, order/broker reconciliation error) + manual trigger — หยุดเปิด position ใหม่ทันที แต่ **ไม่ทิ้ง position ที่เปิดอยู่** (position management ทำงานต่อ) + manual reset โดยเจตนา
- FR-RK-05 ทุก risk decision บันทึกลง risk_events + audit_logs

### 4.5 AI Analysis (FR-AI)

- FR-AI-01 Pipeline บังคับ: Raw Market Data → Feature Extraction → Quant/Strategy Analysis → Risk Analysis → AI Reasoning → Trade Recommendation (ห้าม AI วิเคราะห์ raw chart แล้วตัดสิน Buy/Sell โดยตรง)
- FR-AI-02 Multi-Agent อย่างน้อย 9 ตัว: Trend, Structure, Liquidity, SMC, Momentum, Volatility, News, Risk, Decision
- FR-AI-03 Decision Agent รวมผล → Structured Data (ตาม schema ใน docs/03-trading-domain.md) — **ห้ามส่ง Order โดยตรง**, output = `trade_status: WAITING_CONFIRMATION`
- FR-AI-04 ผลลัพธ์ LLM ทุกครั้งต้องผ่าน Schema Validation — ไม่ valid ถูกปฏิเสธและบันทึก
- FR-AI-05 Confidence มาจาก Weighted Evidence (HTF Trend, Structure, Liquidity, SMC, Momentum, Volatility, Session, News, Historical Strategy Performance, Risk Quality) — ห้าม AI สุ่ม, ต้อง audit ย้อนหลังได้ว่ามาจากอะไร
- FR-AI-06 AI Provider เป็น abstraction — config ผ่าน env, มี timeout/retry/fallback, ตรวจจับ AI unavailable (ต่อ kill switch)
- FR-AI-07 AI Panel แสดงครบ: Bias, Regime, Trend, Structure, Liquidity, Momentum, Volatility, News Status, Confidence, Strategy, Entry/SL/TP/RR/Risk/Size, Evidence, Invalidation + ปุ่ม Create Paper Trade / Confirm Trade / Reject Signal

### 4.6 Trading / OMS / Paper (FR-TR)

- FR-TR-01 OMS State Machine ชัดเจน: SIGNAL_CREATED → RISK_CHECK → WAITING_CONFIRMATION → APPROVED → ORDER_SUBMITTED → BROKER_ACCEPTED → PARTIALLY_FILLED → FILLED → POSITION_OPEN → PARTIAL_CLOSE → POSITION_CLOSED (+ CANCELLED / REJECTED / ERROR) — ทุก transition audit ได้
- FR-TR-02 Duplicate Order Protection: Idempotency Key, Client Order ID, Order Lock, State Validation — กัน double click / retry ทุกชนิด (network, websocket, worker)
- FR-TR-03 Paper Trading ใช้ **Real Market Data** + virtual orders จำลอง: Entry, Spread, Commission, Slippage, SL, TP, Partial Close, Trailing Stop, Position Size, Equity, Balance, Drawdown
- FR-TR-04 Position Management: Break Even, Trailing Stop, Partial Close (TP1/TP2/TP3 เช่น 30/30/40 — configurable), Scale Out, Scale In (ถ้าเปิด feature), Structure-based Stop, Time Stop, Dynamic Stop, Run Trend
- FR-TR-05 Trading Screen: Symbol Selector, Realtime Price/Bid/Ask/Spread, Market Status, Realtime Chart + TF selector + indicators + structure/liquidity/FVG/OB/session overlays + Entry/SL/TP lines + Open Positions + AI Signal + Risk Panel + Trade Confirmation

### 4.7 Journal & Analytics (FR-JR)

- FR-JR-01 ทุก trade บันทึกครบ: Date, Time, Symbol, Direction, Strategy, Trading Mode, Market Regime, Entry, SL, TP, Position Size, Risk, RR, AI Confidence, AI Evidence, Session, Result, PnL, MFE, MAE, Duration, Exit reason, Screenshot reference
- FR-JR-02 Analytics Dashboard: Win Rate, Profit Factor, Expectancy, Drawdown, Strategy/Setup/Timeframe/Session/Day-of-week Performance, Long vs Short, Confidence Calibration, Market Regime Performance
- FR-JR-03 Confidence Calibration — ตรวจย้อนหลังได้ว่า AI confidence ช่วง 80–90% มี actual win rate เท่าไร

### 4.8 Backtesting (FR-BT)

- FR-BT-01 รองรับ Historical Candle Data + Multi-Timeframe + Strategy + Risk + Spread + Commission + Slippage + Trading Session + News Filter (ถ้า data รองรับ)
- FR-BT-02 Metrics ครบ: Total Trades, Win/Loss Rate, Profit Factor, Expectancy, Average RR, Max Drawdown, Max Consecutive Loss, Sharpe, Sortino, Equity Curve, Monthly Return, Strategy Breakdown, Session Breakdown
- FR-BT-03 Walk-Forward Test: Train Period, Validation Period, Out-of-sample — ห้าม optimize จาก dataset เดียวแล้วถือว่าใช้ได้จริง
- FR-BT-04 กัน Look-ahead bias (engine เห็นเฉพาะข้อมูลถึงเวลา t)

### 4.9 Broker Integration (FR-BR)

- FR-BR-01 Broker Interface (BrokerAdapter) ครบ methods: connect, disconnect, get_account, get_symbol, get_price, get_positions, get_orders, place_order, modify_order, cancel_order, close_position, partial_close
- FR-BR-02 MT5Adapter เป็น implementation แรก — **Demo เท่านั้น** ในระยะพัฒนา, ออกแบบรองรับ OANDA/Saxo ในอนาคต
- FR-BR-03 Broker credentials เข้ารหัส + ห้ามส่งไป frontend
- FR-BR-04 Reconciliation Process — เทียบระบบกับ broker, จัดการ mismatch

### 4.10 ปฏิทินเศรษฐกิจ / News Filter (FR-NW)

- FR-NW-01 เหตุการณ์: CPI, PPI, NFP, FOMC, Fed Rate Decision, Powell Speech, PCE, GDP, Unemployment, ISM, Jobless Claims
- FR-NW-02 Rules ที่ configurable ทั้งหมด: −30 นาทีก่อนข่าว = No New Trade, −10 นาที = Reduce Risk, ช่วงข่าว = Disable Auto Entry, หลังข่าว = Cooling Period

### 4.11 UI / Navigation (FR-UI)

- FR-UI-01 Main Navigation ครบ 16 เมนู: Dashboard, Trading, Market Scanner, AI Signals, Analysis, Orders, Positions, Trade Journal, Backtesting, Paper Trading, Risk Management, Analytics, Economic Calendar, Alerts, Settings (+ Auth)
- FR-UI-02 Risk Dashboard: Balance, Equity, Floating PnL, Today/Weekly PnL, Current Drawdown, Daily Risk Used, Open Risk, Exposure, Maximum Limit, Trading Status, Kill Switch Status
- FR-UI-03 Realtime ทุกหน้าจอสำคัญผ่าน WebSocket

### 4.12 Security / Audit / Observability (FR-SE)

- FR-SE-01 Authentication + Secure Session + MFA-ready + RBAC + CSRF (ตาม architecture) + CORS + Input Validation + Rate Limiting + TLS-ready + API Authentication
- FR-SE-02 Broker Credential Encryption + Sensitive Data Masking
- FR-SE-03 Audit Log ทุก action สำคัญ: Login, Risk/Broker Setting Change, Signal Generated, Trade Confirm, Order Submit/Modify/Cancel, Position Close, Kill Switch, AI Decision, System Error — ครบฟิลด์ timestamp, user, action, entity, entity_id, before, after, reason, source, correlation_id
- FR-SE-04 Observability: Structured Logging + Correlation ID, Health/Readiness Check, Metrics, Error Tracking, Trading Event Logs, Broker Connectivity Monitoring, Market Data Freshness Monitoring
- FR-SE-05 Failure Handling ครบชุดตาม Spec (broker/data disconnect, Redis/DB unavailable, AI unavailable, WS dropped, order timeout, duplicate callback, partial fill, stale/invalid price, unexpected spread, position mismatch) + Reconciliation Process

## 5. Non-Functional Requirements

| ID | หมวด | ความต้องการ |
|---|---|---|
| NFR-01 | Performance | Candle query API < 500ms (1,000 candles); WS push tick→client < 250ms; หน้าจอหลักโหลด < 3s |
| NFR-02 | Scalability | รองรับผู้ใช้หลายคนพร้อมกัน + symbols หลายตัวในอนาคต (v1 = XAUUSD) |
| NFR-03 | Availability | Degrade อย่างปลอดภัยเมื่อ dependency ล่ม (ไม่มี order ผิดปกติ) — kill switch หยุดความเสี่ยงก่อนเสมอ |
| NFR-04 | Security | ตาม FR-SE-01..03 + ผ่าน security test suite ใน PHASE 12 |
| NFR-05 | Testability | Unit/Integration/API/DB/Strategy/Risk/OMS/Mock Broker/Paper/Backtest/Frontend/E2E/Security — ตาม docs/17-testing.md |
| NFR-06 | Observability | ตาม FR-SE-04 |
| NFR-07 | Maintainability | Modular boundaries ชัด (22 modules), no duplicate implementation, lint/typecheck ผ่าน |
| NFR-08 | Portability | Docker Compose รันได้ทั้ง DEV/UAT/PROD |
| NFR-09 | Data Integrity | Audit ทุก transition, idempotent orders, reconciliation, ไม่มี data loss บน order path |
| NFR-10 | Extensibility | Strategy/Broker/Provider/AI Provider เพิ่มได้แบบ plug-in |

## 6. Out of Scope (ระยะแรก)

- Live auto trading (บล็อกโดย G-01/G-03 จนกว่า PHASE 14 approval)
- Broker นอกเหนือ MT5 (ออกแบบ interface รองรับไว้ก่อน)
- Forex symbols นอกเหนือ XAUUSD (ออกแบบ schema รองรับ)
- Mobile application (responsive web ก่อน)

## 7. Acceptance ระดับโปรเจกต์

โปรเจกต์ถือว่า "พร้อมใช้งานจริง" เมื่อ: ผ่าน PHASE 13 (UAT + Regression + Load + Simulation) และ PHASE 14 (Production Readiness Review) — โดยที่ LIVE_AUTO_TRADING ยังเป็น false จนกว่าผู้ดูแลระบบเปิดโดยเจตนา
