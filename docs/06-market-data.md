# 06 — Phase 2 Market Data and Trading Screen

## Authorization and scope

Phase 2 is provisional: the user explicitly authorized implementation before the final Phase 1.1
independent review. Phase 1.1 + Phase 2 require combined Sol High independent review.
This is market data and visualization only. PAPER, LIVE_AUTO_TRADING=false; no orders, broker
execution, recommendations, strategy, SMC/ICT, risk engine, AI signals or Phase 3 implementation.

The existing TASK-021–029 plan is retained. The current user requirement for native Windows,
optional Redis and optional Docker takes precedence over the original mandatory TimescaleDB/Redis
wording. This milestone uses indexed native PostgreSQL tables and LocalMarketBus.
TimescaleDB hypertables and distributed Redis publication are future deployment work, not prerequisites.

## Data flow and provider

MarketDataProvider → ReplayProvider → validation → M1 aggregation → higher candles →
PostgreSQL transaction → bounded LocalMarketBus → authenticated /ws/market → validated chart client.

Configuration: MARKET_DATA_PROVIDER=simulated. The registry currently implements ReplayProvider only.
A future real adapter must implement the interface and register/configure its key; no real-provider
credential is configured or needed. Unsupported provider keys fail validation. The UI always displays
SIMULATED DATA and labels the source. It never claims live market prices.

Replay is deterministic for a UTC second, using a daily periodic synthetic price function, normalized
to Decimal cents. Spread is a synthetic USD 0.30; volume counts synthetic one-second observations
and is not exchange volume. The provider's M1 blocks are canonical. Repeated daily M1 blocks allow
bounded generation of long histories without building millions of minute objects. This periodic
history is suitable for visual development, not market research or trading decisions.

Symbol metadata supports additional FX instruments. XAUUSD alone has a configured source.
Authenticated users read symbol specs; ADMIN can create/update and deactivate symbols. Delete is
a soft deactivation preserving historical foreign keys. Names cannot be renamed. The symbol's
default_spread is metadata; actual quotes always carry the source's observed/synthetic spread.
Other symbols appear unavailable until a source adapter supplies them.

## Domain and time policy

Prices and volumes are Decimal internally and exact decimal strings over REST/WS.
The chart converts to Number only at the rendering boundary. Validation rejects non-finite/nonpositive
prices, negative volume, ask below bid, inconsistent spread and invalid OHLC.

All timestamps serialize as UTC Z, including values returned by a PostgreSQL session configured in
a local timezone. UTC normalization is regression-tested with +07:00 database-style timestamps.
A timezone is required. Buckets are half-open [start, end); W1 begins Monday 00:00 UTC.

Timeframes: M1, M3, M5, M15, M30, H1, H4, D1, W1.
Candle fields: symbol, timeframe, open_time, open/high/low/close, volume, bid_close,
ask_close, source, is_closed. Candles represent BID prices.

The live engine replaces the forming M1 contribution, then recomputes each higher current candle
from its completed prefix plus that M1. Repeated M1 updates never double-count volume.
Rollover publishes the closed candle followed by the new current candle. Duplicate and out-of-order
ticks are rejected, not retroactively applied to closed candles. Initialization/restart fills
synthetic history from the same provider function, excluding the first live second.

## Persistence and retention

Additive revision 0003_phase2_market_data follows unchanged 0001_initial and
0002_phase1_schema_alignment. It adds symbols.default_spread and two native tables:

| Table | Idempotency / primary key | Data |
|---|---|---|
| ticks | symbol_id, source, ts | bid, ask, spread, volume |
| candles | symbol_id, source, timeframe, bucket_start | OHLCV, bid/ask close, closed flag |

Foreign keys preserve symbol ownership; source separates replay from future real datasets.
Candle upserts are batched (100 rows per statement during initialization), with tick and candle
updates in one transaction. Publication happens only after commit. On persistence failure the feed
enters ERROR, logs a sanitized exception and retries initialization; no failed transaction is published.

Initialization materializes 300 candles per timeframe. REST supports bounded limit 1–1000, from
inclusive and to exclusive, with next_cursor passed as the next to value. Results are oldest-first
inside each page; pagination moves backwards without overlapping the boundary. Empty results are valid.

Retention prunes only the current symbol's simulated source: ticks older than one day and candles
older than 1000 timeframe intervals, checked at initialization and every 60 accepted ticks.
This does not delete user/account/audit rows or other source data. Native composite primary keys
serve the symbol/source/timeframe/time queries. TimescaleDB is not installed or required.

## Service lifecycle, quality and health

A single lazy service starts on the first authenticated market-status/quote/history or WS request.
It seeds XAUUSD if missing. Liveness and auth startup remain independent of market feed availability.
The worker owns one provider stream, bounded current aggregation state and bounded subscriptions.
It runs in an empty ContextVar context, so a long-lived worker cannot retain an initiating HTTP ID.

MARKET_STALE_SECONDS defaults to 5. Quality rejects stale/future timestamps, unsupported symbols,
duplicate/out-of-order ticks, bid jumps above MARKET_MAX_JUMP_RATIO (default 0.05) and spread above
MARKET_MAX_SPREAD (default 10). Fixed-category system_events are throttled to one/code/minute.
Stale monitoring keeps running while a provider awaits its next tick and emits MARKET_STALE.
No kill-switch business logic is implemented in this phase.

GET /api/market/status reports CONNECTING/CONNECTED/STALE/ERROR/DISCONNECTED, source/mode,
last_quote, server_time, stale_after_seconds, detail and subscription count.
GET /healthz is process liveness and does not fail because the feed is unavailable.
GET /readyz retains database/optional Redis readiness; market status is inspected separately.
Worker recovery retries with delays up to 30 seconds. Shutdown cancels the owned feed task.

## REST and WebSocket contracts

REST requires the existing access bearer authentication:
GET /api/symbols, GET /api/symbols/{name}, POST/PUT/DELETE symbols (ADMIN);
GET /api/market/status, GET /api/market/quote?symbol=XAUUSD;
GET /api/market/candles?symbol=XAUUSD&timeframe=M5&limit=300&from=...&to=....

Canonical Pydantic market models also define WS frames, where OpenAPI alone cannot describe the
transport. The existing scripts.export_api_contract emits market.generated.ts and
market-contract.generated.json alongside the unchanged auth contract workflow.
Frontend structural validation executes this generated schema, then validates exact Decimal spread,
OHLC, volume, UTC boundaries, matching symbol/timeframe and sorted/unique candles.
Unknown or malformed frames fail visibly; payload contents are not echoed in errors.

WS endpoint: /ws/market. Origin must exactly match CORS_ORIGINS. Query parameters are rejected.
After upgrade, the first frame within five seconds must be:

    {"type":"auth","token":"<current access token>"}

No token is put in a URL. Before successful authentication, no market message is sent.
JWT type/signature/expiry and active user are checked. Expiry closes the stream; active-user status
is rechecked during the stream. Existing JWT/session architecture remains unchanged.

Commands:

    {"type":"subscribe","symbol":"XAUUSD","timeframe":"M5"}
    {"type":"unsubscribe","symbol":"XAUUSD","timeframe":"M5"}
    {"type":"ping"}

Each socket has one active subscription. Subscribe sends an authoritative 300-candle snapshot.
Update frames carry quote plus selected candles. Status/heartbeat frames keep the connection
observable; sequence deduplicates updates within a connection. Reconnect uses a fresh snapshot and
resets sequence tracking, including after backend restart.

MarketMessage has required type, symbol, timeframe, sequence, quote (nullable), candles, status and
error (nullable). Limits: 128 concurrent/reserved sockets, 60 commands/minute/socket, 2048-character
commands and 8192-character auth tokens. Bus queues hold at most 16 updates; overflow closes a slow
consumer with 1013 so it reconnects for a full snapshot rather than silently missing candles.

## Trading screen and recovery

/trading uses TradingView Lightweight Charts 5.0.9 with a local candlestick series fed by this backend.
It displays symbol, Bid/Ask/Spread, last UTC update, source/mode, connection text, nine timeframes,
market information and a clearly unavailable Phase 3 analysis placeholder. No execution controls.

Historical loading is bounded; unavailable history presents NO DATA / error with a retry control.
One chart instance survives ticks and timeframe changes; updates use series.update, with bounded
1000-candle storage. Subscription cleanup cancels sockets, watchdogs, retries and pending REST calls.
The library handles responsive resizing, price/time scales and crosshair.
Desktop/tablet/mobile acceptance checks chart rendering and no horizontal overflow.

Reconnect delays are exponential, capped at 30 seconds and 10 attempts. Only a sustained healthy
connection resets the attempt budget; manual Reconnect can start a new attempt sequence.
An eight-second silent-socket watchdog reconnects, while quote freshness uses the server-configured
stale threshold. Visible STALE/DISCONNECTED/ERROR text prevents old quotes appearing current.
Session recovery uses the existing API client's validated refresh path before first-frame WS auth.

Official chart API reference: https://tradingview.github.io/lightweight-charts/docs/5.0
TradingView attribution and link are visible on the screen. No TradingView external-price widget is used.

## Local operation and tests

From backend after configuring the existing private .env:

    python -m alembic upgrade head
    python -m app.db.seed --skip-admin
    python -m scripts.export_api_contract --check

Use the existing README native Uvicorn command, retaining --no-proxy-headers. Run frontend npm run dev,
or stop the standalone process before npm run build on Windows to avoid EBUSY directory locks.
Default browser origin is http://localhost:3000; another frontend port must be explicitly included
in backend CORS_ORIGINS. Docker/WSL/Redis are not required. Do not run multiple feed workers against
the same DEV dataset; distributed coordination is not implemented.

Automated tests:
- backend/tests/test_market_data.py: domain, UTC, all timeframe buckets, M1 consistency, rollover,
  duplicate/out-of-order, provider lifecycle, bounded bus, persistence, quality, pagination and auth.
- backend/tests/integration/test_market_live.py: isolated real PostgreSQL, native launch, all histories,
  authenticated WS, subscriptions, provider pause/stale event, recovery and fresh reconnect snapshots.
- frontend/tests/market.test.cjs: canonical schema, semantic rejection, deduplication, first-frame auth,
  bounded reconnect and timer cleanup.
- frontend/tests/e2e/market-screen.cjs: actual login/trading/chart/quote updates, all timeframes,
  canvas lifecycle, responsive layouts, reconnect, reload and console/assets checks.
- Existing full foundation and HARD-R01/R02/R03 regression suites remain mandatory.

See phase-2-gate.md for final results, Git inventory and combined-review status.

## Phase 2.5 — official MT5 market data (2026-09-09)

Phase 2 Replay architecture remains available. MT5MarketDataProvider implements the
same provider interface; the backend owns the only polling feed per application.
The browser only consumes canonical REST and first-frame-authenticated WebSocket
messages. Real data does not enable execution: PAPER and live_auto_trading=false
are mandatory in the adapter, whose gateway only permits initialize/shutdown,
terminal/account metadata, symbol selection/info/tick, and copy_rates_from.

User selected IUX Demo / XAUUSD. Exact terminal path, expected server and optional
expected login stay in backend/.env (repr excluded); no password is needed in this
adapter because the user authenticates in the official terminal. The optional
mt5 dependency extra installs MetaTrader5 and tzdata on native Windows. Use one
Uvicorn worker. Do not run a second feed process writing the same source.

Configuration:
- MARKET_DATA_PROVIDER=simulated or mt5; default stays simulated in the template.
- MT5_TERMINAL_PATH: installed terminal64.exe, already logged into the selected account.
- MT5_SYMBOL_XAUUSD: explicit provider symbol; MT5_FEED_ID: public source namespace.
- MT5_EXPECTED_SERVER and optional MT5_EXPECTED_LOGIN: verify exact account identity.
- MT5_ACCOUNT_MODE=DEMO (or explicit LIVE data-only): verified from account.trade_mode.
- MT5_SERVER_TIMEZONE=UTC by default; explicit IANA server-wall-time policy for brokers
  with encoded local timestamps. This is not inferred automatically from quote age.
- MT5_POLL_SECONDS >=1; MT5_TIMEOUT_MS default10000; MT5_FUTURE_TOLERANCE_SECONDS
  default2, bounded0..10. IUX observed clock lead of about3seconds uses tolerance5.
  Tolerance accepts a bounded clock difference; it does not rewrite timestamps.

### IUX time evidence and canonical candles

The connected IUX terminal's raw tick timestamps were one hour ahead of independently
checked UTC. IUX's client agreement describes terminal GMT in winter and BST in summer.
The explicit local policy is Europe/London, checked against current quotes. Conversion
uses historical IANA DST rules; ambiguous/nonexistent wall times fail closed rather
than choosing an arbitrary fold. A broker policy change requires revalidation and a
new source namespace, not rewriting already persisted prices under another time policy.

Native M1/M5/M15/M30/H1 rates are normalized to UTC and their boundaries validated.
M3 always folds M1. H4/D1/W1 fold H1 so UTC four-hour/day/Monday-week boundaries do not
reuse misaligned broker OHLC. The observed IUX native W1 starts Sunday and is deliberately
not relabeled as Monday. Prefixes truncated by the bounded history request are omitted.
Missing trading bars remain missing; the backend does not synthesize weekend/gap candles.
Native rate reads cap at100000 rows, results at the requested limit (normally300).
Current IUX H1 availability yields only231 canonical weekly bars: this is explicitly
partial history, not an accepted300-bar weekly history.

The current and last closed candles come from authoritative rates at each shared poll,
not from summing sampled bid snapshots. This preserves broker extrema and tick volume;
intermediate quote changes are intentionally coalesced at the poll interval. Repeated
snapshots replace OHLC/volume, never add volume twice. Reconnect rebuilds history and
closes internal clients for a fresh snapshot; timestamp gaps trigger the same resync.
Replay keeps its deterministic M1 engine unchanged.

### Storage, metadata and health

Source is included in existing tick/candle keys and every REST/WS history query.
The IUX source is mt5_demo_iux; simulated remains separate. No automatic Replay fallback.
Quote mode and status source/mode are validated together. Provider precision and tick size
drive both price text and chart formatting. UI labels distinguish SIMULATED, UNCONFIRMED,
REAL MARKET DATA / DEMO CONNECTION and REAL MARKET DATA / LIVE CONNECTION.

Migration0004 only makes candles.ask_close nullable: MT5 rates contain bid OHLC and
tick_volume but no actual closing ask. Unknown ask is NULL, never inferred from spread.
0001/0002/0003 are unchanged. Downgrade refuses rows with unknown ask; it does not delete
them or fabricate values. Existing Replay prices remain unchanged.

Market status includes history_counts/history_complete, last_quote/last_candle, digits,
tick_size, provider symbol, mode and volume_kind. Fewer than300 nonempty real bars remain
usable with explicit PARTIAL HISTORY detail; the Phase2.5 acceptance gate still fails.
An empty required timeframe blocks startup. Liveness remains independent of the provider.
Fresh quotes indicate OPEN; with no trustworthy session schedule, no-update state is
STALE/UNKNOWN, never an invented CLOSED classification. Confirmed CLOSED cannot be
asserted from these Python SDK methods alone.

Real tick archival defaults off; sampled quote volume is zero because it is not an actual
trade volume. Candle volume is broker tick_count. Real candles are not destructively
pruned by the Replay retention routine. Operator-approved real candle/tick retention,
distributed coordination, proven broker timezone history and production load testing
remain technical debt. Bus bounds stay128clients ×16messages; slow clients resnapshot.

### Verification and official references

Offline suites explicitly force Replay unless the test injects a fake SDK. External
tests are deselected by default, never counted as passing offline fixtures. From backend,
opt in with LIVE_EXTERNAL_TEST=true and MARKET_DATA_PROVIDER=mt5, then run:
python -m pytest -m live_external -o addopts= -q

The real gate checks300bars per timeframe separately from quote/disconnect/reconnect.
Browser harness E2E_MARKET_SOURCE=mt5_demo_iux validates the real label/source, quote
movement and each timeframe, reporting PARTIAL if any history is below300.
Direct terminal-to-API-to-browser value checks are additional required evidence.

Official references:
- [MT5 rates and UTC/timeframes](https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrom_py)
- [MT5 quote fields](https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfotick_py)
- [MT5 account metadata](https://www.mql5.com/en/docs/python_metatrader5/mt5accountinfo_py)
- [IUX terminal timezone seasonal policy](https://policy.iux.com/en/client-agreement/)
- [Official IUX MT5 download](https://www.iux.com/en/platforms/mt5)

See phase-2.5-gate.md for measured results, remaining blockers and the Phase3 stop.
