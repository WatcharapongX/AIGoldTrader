# Market structure — Phase 3

Version: structure-1.0.0. Implemented 2026-09-09. Descriptive, deterministic analysis of canonical closed candles. The current user authorization permits Phase 3 implementation before the combined Phase 2.5 + Phase 3 Sol High review. This is not permission to start Phase 4.

## Inputs, identity and availability

The provider-independent engine accepts the existing Candle model: symbol, timeframe, UTC open_time, exact Decimal OHLC/volume, source and is_closed. Supported timeframes: M1, M3, M5, M15, M30, H1, H4, D1, W1. It does not import MT5, request prices, read a clock, invoke AI or create orders. Duplicate/reversed timestamps, mixed identity/source, malformed OHLC, non-finite values, naive timestamps and a forming candle before the final position are rejected. analyze() ignores the final forming candle; incremental feed() accepts closed candles only.

Each snapshot contains algorithm_version, config_id, input_id (SHA-256 prefix of ordered closed canonical records), window_start and as_of (last included closed bar's end). Events have stable IDs scoped by algorithm, config, symbol, timeframe, source and origin. Swings separate swing_time from confirmed_at; structure events separate occurred_at from confirmed_at. No provisional pivot is emitted.

history.requested, returned and closed are different counts. A 300-row window containing a forming bar has 299 closed bars. W1 231/300 is PARTIAL, with approximately 230 closed bars while the week forms. Each module reports minimum_bars_required, available_bars, status and reason. Status is INSUFFICIENT_DATA below minimum, NO_STRUCTURE when no qualifying feature exists, PARTIAL_HISTORY for available features on a partial input, otherwise READY. ERROR is reserved in the contract; invalid API input returns a controlled error, not manufactured structure. Empty data has UNKNOWN state and EMPTY history.

## Confirmed pivots and state

Defaults: internal left/right=2/2, external=5/5. A candidate at index i becomes available only after right later closed candles, at close time of i+right. It must be strictly higher (high pivot) or lower (low pivot) than every other candle in its left/right window. Equal plateaus produce no arbitrary pivot. An outside bar may confirm both extrema; equal-time opposite pivots cannot form a dealing range.

Same-kind comparisons use abs(price - previous_price) <= tick_size * equal_ticks (default one tick) for EQH/EQL. Otherwise highs become HH/LH and lows HL/LL. First extrema are SH/SL. Strict extrema detection itself does not use the equality tolerance. External and internal states are independent.

A fresh, unbroken HH+HL pair establishes BULLISH; LH+LL establishes BEARISH. Initial mixed pairs become NEUTRAL. An existing break state is retained until evidence changes it. Broken swing pairs cannot restore a prior trend after CHOCH.

A close beyond the latest confirmed swing by more than tolerance consumes that level once:

- In the same established direction: BOS (continuation).
- Against an established direction: CHOCH (warning), then NEUTRAL.
- That same counter-break also emits MSS only with qualifying directional displacement; MSS links its CHOCH parent and establishes the opposite direction.
- From UNKNOWN/NEUTRAL: establish direction, without inventing a continuation BOS.

Wick penetration alone is never BOS/CHOCH/MSS. Displacement requires directional body, body >= prior closed ATR * 1.5 and close in the directional outer 25% of the candle. Zero/unwarmed ATR cannot qualify. The candidate's own range is excluded from its ATR threshold.

## Minimum closed bars (defaults)

| Module | Minimum |
|---|---:|
| Internal / external structure | 5 / 11 |
| Swing liquidity | 11 |
| FVG | 3 adjacent bars |
| Order-block qualification | max(ATR period + 2, internal pivot width + 1) = 16 |
| Aggregate indicator/regime readiness | max(2 * ATR period, average period) = 28 |
| ATR / RSI | 15 |
| ADX | 28 |
| EMA / SMA / Bollinger / volume average | 20 |
| Complete observed UTC session | M1 480, M3 160, M5 96, M15 32, M30 16, H1 8, H4 2 |

Session minimum describes the shortest compatible configured window; input alignment can require more bars. D1/W1 cannot resolve these intraday sessions and return NO_STRUCTURE rather than inventing extrema. A structure minimum is a prerequisite, not a promise that a pivot/BOS exists.

## Indicators, sessions and regimes

ATR and RSI seed from p=14 changes, then use Wilder smoothing. Flat RSI=50, all-gain RSI=100. ADX seeds from p DX values after directional movement warm-up, uses Wilder smoothing, and returns zero for zero directional movement. EMA seeds from the first average_period=20 closes. SMA and population-standard-deviation Bollinger bands use the last 20 closes, with bands at mean +/- 2 sigma. Volume average is an average of the canonical volume, which is tick count for the MT5 feed, not exchange contracts. Output rounds to eight decimal places and serializes as fixed-point strings; calculation uses Decimal.

UTC configurable sessions: ASIA 00–08, LONDON 07–16, NEW_YORK 12–21. current_sessions uses the snapshot as_of; multiple names indicate overlap. These are fixed UTC analytical windows, not a claim about exchange/broker opening hours or automatic DST adjustment. Completed observed day/week/session high/lows are confirmed only once their boundary has passed in the closed-candle stream. A period beginning before the available window is omitted. Scheduled/data gaps are not filled: extrema refer only to observed candles. A bar must fit wholly inside the period; incompatible coarse timeframe/session boundaries are omitted. With a market gap at period end, confirmation is conservatively delayed until the next observed candle closes.

Regime priority after warm-up: HIGH_VOLATILITY if ATR/close >= .02; LOW_VOLATILITY if <= .001; BREAKOUT for a newly confirmed BOS; established directional state + ADX >=25 gives TRENDING_UP/DOWN, or PULLBACK when close is across EMA against that direction; known non-trending structure gives RANGING; otherwise UNKNOWN. NEWS_CONDITION is not guessed: news_context remains UNKNOWN because this phase has no news input.

## API, streaming and reproducibility

Authenticated GET /api/analysis/structure?symbol=XAUUSD&timeframe=M5&limit=300 and GET /api/analysis/context?symbol=XAUUSD&limit=300. Limits 1–1000. Symbol and active source are resolved from the existing market service and repository. Context includes all nine independently evaluated rows and their timestamps/history/status. Opposing known directions yield MIXED; one known direction yields that direction; no direction but a NEUTRAL row yields NEUTRAL; otherwise UNKNOWN. This is descriptive context over known rows, not confidence or an entry recommendation. The rows allow top-down inspection without masking partial history.

Optional backend ANALYSIS_CONFIG JSON validates the AnalysisConfig model. Provider tick size overrides the configured tick size for the API. Example: {"internal_left":2,"internal_right":2,"external_left":5,"external_right":5,"equal_ticks":1}. No configuration or credential is accepted from an untrusted analysis query.

The frontend reacts to authoritative market snapshots/closed-bar revisions through the existing authenticated WebSocket and requests typed analysis REST. Forming quotes continue updating the chart without recalculating structure. Abort/identity guards discard responses from previous timeframe/source selections; old overlays clear on switch. No new WebSocket channel or authentication scheme was introduced.

AnalysisService stores at most 32 snapshots, keyed by source/symbol/timeframe/config/limit/returned count and the complete closed-input fingerprint. Closed source corrections invalidate the cache. CPU replay is offloaded from the async event loop and serialized on cache misses. Each replay is bounded to 1000 input rows; the default is 300. The incremental engine retains at most 150 recent candles (or required lookback), 128 objects of each family by default (configurable up to 256), 32 sessions and bounded calendar accumulators.

**Reproducibility boundary:** identical inputs/config give identical output. Appending bars to the same fixed-origin stream preserves already confirmed swing/event facts while zone/liquidity lifecycles may evolve. REST rebuilds its bounded window on a close/correction; moving the left boundary can change initial labels, indicator warm-up and downstream state. window_start/input_id and the UI explicitly disclose this. This implementation does not claim immutable all-history analysis across rolling-window resets, source corrections or configuration changes. No persistent analysis-event ledger or schema migration is added.

## UI and verification

Native Lightweight Charts series primitive uses the existing candle series price/time scales. External swing dots/labels, BOS/CHOCH and liquidity default on; MSS, FVG/IFVG, OB/Breaker, Premium/Discount and sessions can be toggled. Swings anchor to origin only after confirmation; actionable-zone visualization starts at confirmation. Sweep dots anchor to the actual sweep candle, not the next candle's open. Off-chart time boundaries use nearest existing bar coordinates without adding synthetic chart data. No overlay expands autoscale. Drawing is clipped, label collisions suppressed and object counts capped. Status text accompanies color.

The panel shows external/internal state, regime, dealing range, counts, all module readiness, indicators, origin/confirmation tables and all-nine-TF context. Canonical generated TypeScript + JSON schema are validated at runtime; non-finite prices, duplicate IDs, future confirmations and malformed time/zone/history data are rejected.

See tests/test_analysis.py, tests/integration/test_analysis_postgres.py, frontend/tests/analysis.test.cjs and frontend/tests/e2e/analysis-screen.cjs. PostgreSQL synthetic fixtures and real IUX browser acceptance are reported separately in phase-3-gate.md. Chart implementation follows the official [series primitive API](https://tradingview.github.io/lightweight-charts/docs/5.0/plugins/series-primitives).
