# PHASE 2.5 — REAL MARKET DATA

Date: 2026-09-09. Local native Windows verification. This report separates actual
IUX observations from offline SDK fixtures and from the remaining acceptance failure.

## STATUS
**PARTIAL.** Real IUX Demo prices reach the Trading Screen. **Gate BLOCKED** because
the terminal supplies only 231 canonical W1 candles, below the required 300.
No synthetic bars were added to satisfy the requirement.

## PROVIDER
- Provider: MT5MarketDataProvider / official MetaTrader5 Python SDK 5.0.6180.
- Broker: IUX; connection: installed Windows MT5 terminal IPC.
- Account Mode: DEMO, checked from actual account metadata and private identity settings.
- External Trading Permission Used: NO.
- Discovery initially found no terminal/credentials. User then supplied IUX Demo, XAUUSD
  and terminal identity; private config was populated and an actual connection verified.
- Active local configuration: MARKET_DATA_PROVIDER=mt5. Replay remains selectable explicitly.

## SYMBOL
- Internal: XAUUSD.
- Provider Symbol: XAUUSD, confirmed by symbol_select/symbol_info and real quotes.
- Precision: 2 digits; point/tick size 0.01 USD.
- Source namespace: mt5_demo_iux; separate from simulated in every history query/storage key.

## REAL MARKET DATA
Example verified UI sample (historical observation, not a current price promise):
- Bid 4406.04; Ask 4406.08; Spread 0.04 USD.
- Canonical timestamp 2026-09-09T07:26:21.072000Z.
- Historical candles:300 each for 8 timeframes; W1=231.
- Realtime candles: authoritative rates replace forming OHLC/volume; quote polling 1 second.
- Historical ask_close:NULL because official rates do not contain an actual closing ask.
- Volume:broker tick_count, not traded lots; sampled quote volume0.
- Spread was 0.04 during the sampled interval; quote-derived spread was verified, but a
  change in spread size was not observed or artificially forced.

## TIMEFRAME MATRIX

| TF | History | Realtime | Source/Aggregated | Result |
| -- | ------- | -------- | ----------------- | ------ |
| M1 | 300 | Real stream | Native M1, UTC normalized | PASS |
| M3 | 300 | Real stream | M1 aggregated at backend | PASS |
| M5 | 300 | Real stream | Native M5, UTC normalized | PASS |
| M15 | 300 | Real stream | Native M15, UTC normalized | PASS |
| M30 | 300 | Real stream | Native M30, UTC normalized | PASS |
| H1 | 300 | Real stream | Native H1, UTC normalized | PASS |
| H4 | 300 | Real stream | Canonical H1 aggregation | PASS |
| D1 | 300 | Real stream | Canonical H1 aggregation | PASS |
| W1 | 231/300 | Real stream | H1 to Monday00:00UTC | BLOCKED: history depth |

IUX native weekly bars start Sunday. They are not relabeled as Monday. The available
H1 sample begins 2021-11-29; current history produces 231 weekly buckets (missing provider
periods are not filled). Terminal maxbars = 100000; a bounded request for older H1 did
not supply enough additional history. Need at least 300 complete/available canonical
weekly buckets from the same source, with enough lower-timeframe data for UTC boundaries.

## PROVIDER HEALTH
- Connect:actual IUX Demo PASS.
- Disconnect/reconnect:actual adapter lifecycle PASS; offline worker backoff 1/2/4/8/16/30/30 s PASS.
- Stale:offline real-adapter/service fixture and native Replay pause/recovery PASS.
- Market Closed:NOT OBSERVED. SDK methods used do not provide a trusted session schedule;
  no-update state remains STALE/UNKNOWN. No weekend-based CLOSED guess.
- Healthz remains liveness and does not require external feed availability.
- Account/server change detection fails closed; no silent fallback to Replay.

## TRADING SCREEN
- Source label:mt5_demo_iux.
- Mode label:REAL MARKET DATA / DEMO CONNECTION.
- Trading label:PAPER; execution disabled.
- Chart:real IUX history, stable canvas lifecycle, metadata precision.
- Realtime:Bid and Ask move; forming candle values and chart pixels change.
- Timeframes:all 9 source/history subscriptions; W1 visibly has 231 candles.
- Reconnect and reload/session recovery:PASS.
- Desktop 1440 px / tablet 820 px / mobile 390 px:PASS; no horizontal overflow.
- Console errors 0; failed critical assets 0.
- Partial history is stated in the feed detail. Browser overall history acceptance is PARTIAL.

## REALITY CROSS-CHECK
Five visible UI samples were matched to official MT5 tick history by exact normalized
timestamp, Bid and Ask. The browser never connects to the external provider.

| Field | Direct provider | UI/canonical payload | Result |
| -- | -- | -- | -- |
| Bid sample 1 | 4406.04 | 4,406.04 | Exact |
| Ask sample 1 | 4406.08 | 4,406.08 | Exact |
| Spread sample 1 | 0.04 | 0.04 | Exact |
| Timestamp | 07:26:21.072000 UTC | Same canonical instant | 0 ms difference |
| Closed M5 at 07:20 UTC | Official rates OHLCV | WS-delivered OHLCV | Exact |

Result: 5/5 quote samples PASS; closed M5 OHLCV PASS; changing real forming-candle values
and different rendered chart images verified. Provider clock currently leads host UTC
by about 3 seconds after timezone conversion. Explicit bounded tolerance 5 seconds is used;
timestamps are not shifted to hide this lead.

## TEST RESULTS
- Full backend regression: 155 PASS, 0 FAIL, 0 SKIP; 10 external tests deliberately deselected.
- Provider contract:Replay + fake official MT5 SDK; all 9 TF, mapping/precision/UTC/DST,
  unknown ask, source isolation, short history, read-only guard, masking and backoff PASS.
- Actual LIVE_EXTERNAL_TEST: 9 PASS, 1 FAIL (W1=231/300); no hidden skip or fixture substitution.
- Replay regression:native Chromium all 9 TF/history/realtime/reconnect/reload PASS.
- WebSocket:first-frame auth preserved; no query-token; REST/WS source isolation PASS.
- Frontend: 63 PASS; lint/typecheck/production build PASS (20 static pages).
- Browser:IUX flow works; 300-per-TF gate PARTIAL as above. Native auth wrong-password,
  login, refresh, reload, logout and route protection PASS against actual PostgreSQL.
- PostgreSQL: 14 integration tests PASS including owned-schema migration roundtrips,
  unknown-ask downgrade refusal, source coexistence and preserved prior rows.
- Alembic:DEV at 0004_market_unknown_ask (head); check PASS/no schema drift.
- SQLite and PostgreSQL:fresh upgrade/downgrade/re-upgrade PASS with known-ask fixtures.
- Backend Ruff/mypy/compileall/wheel build and generated contract freshness PASS.
- Existing 3 deprecation warnings remain; no unrelated dependency refactor.

Intermediate verification issues were resolved: one contract test ran while its generated
file was being updated; the frozen-source full rerun passed. A broken Turbopack cache was
removed within the workspace and production build passed. Browser selector ambiguity
was corrected to target the mode badge. No intermediate failure was used as final PASS.

## PERFORMANCE AND RETENTION
A 20 second native API sample measured approximately 3.28% of one CPU core, with private
memory 518.89 → 518.86 MiB and 23 threads: no growth in this short sanity sample. This is not
a production load test. Bootstrap and IPC arrays are bounded; WS queues remain
128 clients × 16 messages with resnapshot for slow consumers. DB writes commit one bounded
quote/rates batch per successful poll, not one external connection per browser.

Real tick archival is disabled and real tick rows remain 0. Real candle retention needs
an operator policy; this task does not introduce destructive cleanup of real history.
Replay's source-scoped retention remains unchanged.

## SECURITY
- Credentials:terminal-managed login; identity settings only in ignored backend/.env.
- Logs:Python SDK exception text masked; actual private values absent from scanned source,
  frontend bundles and owned logs.
- Frontend exposure:only public source/mode/symbol and canonical values. No external
  account ID, server, terminal path, password or token in responses/bundles.
- First-frame WS auth, trusted-proxy hardening, auth implementation and token validation preserved.
- Read-only SDK gateway rejects all non-allowlisted methods before calling the SDK.

## DATABASE AND SOURCE PRESERVATION
0001/0002/0003 hashes match the pre-task baseline. New 0004 changes only ask_close nullability.
Downgrade refuses existing NULL asks instead of inventing prices or deleting data.

Before browser tests: 1 user, 23 sessions, 1 symbol, 37 audit rows. All original rows remain;
original sessions/symbol/audit hashes unchanged. The user row hash changes through expected
login activity. Browser test sessions are revoked after logout. Existing Replay candles
coexist with IUX candles, with source isolation enforced. No orders/accounts were created.

## TRADING SAFETY
- TRADING_MODE:PAPER.
- LIVE_AUTO_TRADING:false.
- Order Execution:NONE.
- MT5 order_send or equivalent:never called; gateway denies non-market methods.
- Position execution:NONE.
- Phase 3 implementation:NONE.

## KNOWN LIMITATIONS
- W1 short history is the current acceptance blocker.
- Explicit Europe/London timestamp policy follows observed terminal data and IUX's
  seasonal terminal-time policy; historical broker-policy changes require independent
  validation. Ambiguous/nonexistent DST wall times are rejected.
- Quotes are sampled 1 Hz; authoritative rates preserve candle extrema but no full tick
  tape is claimed or archived by default.
- Market-closed classification is UNKNOWN without authoritative session evidence.
- Single application worker; no distributed coordinator. Long-run load/retention work deferred.
- Historical Ask close is unknown; NULL is intentional and visible in the contract.
- Previously deferred token-storage architecture and ordinary failed-login audit remain out of scope.

## BLOCKERS
Provide deeper same-source history sufficient for 300 canonical W1 bars (currently 231),
or explicitly revise the acceptance requirement in a later user instruction. Do not
fill the gap with Replay, shift a Sunday weekly candle to Monday, or mix another provider.

## PHASE 2.5 GATE
**BLOCKED — INSUFFICIENT REAL HISTORICAL DATA (W1).**
The initial missing-terminal prerequisite was resolved. Actual market flow is verified,
but the full Definition of Done is not complete. Independent Sol High Review is still required.

## PHASE 3
**DO NOT START. STOP after Phase 2.5.**

## EVIDENCE AND REVIEW
Ignored local evidence: data/local/phase2-5/
- backend-final.xml/log; external-tests.xml/log; frontend-final.log.
- real-preflight.json (raw issue discovery), real-preflight-normalized.json.
- replay-browser/ and real-browser/ results plus desktop/tablet/mobile screenshots.
- crosscheck/ui-observed.json, reality-crosscheck.json, chart-before/after.png, real-values-desktop.png.
- native-auth/browser-results.json; performance.json; final-safety.json; native logs.
- baseline.json and db-before.json for pre-task source/data fingerprints.

Git remains main at 857e764bea47279af7986a449d80505b74820432; no staging, commit or push.
Earlier phase changes remain uncommitted and preserved. Implementation plan adds scoped
TASK-2.5-01..09, with 8 foundation tasks complete and full acceptance unchecked.

Official implementation references and timezone rationale are in [market data architecture](06-market-data.md).
