# Phase 3.5R + 4.1 — architecture and operating boundaries

> Current targeted integration (2026-09-09): Forex Factory weekly JSON is the configured
> primary schedule/Forecast/Previous source for STRAT05–06. STRAT01–04 have market-only
> safety, candidate identities and cache dependencies. See [current acceptance report](forex-factory-news-strategies.md).
> Provider-selection and shared news-blocking statements below describe the earlier baseline.
> Final semantic versions: strategy-1.2.1 / news-1.2.0. Phase 5 remains NOT STARTED.


2026-09-09. PAPER / execution disabled. This batch does not implement Phase 5.

## Real economic provider decision

Earlier Phase 3.5R selected **Xoomar public economic calendar**, keyless documented JSON API.
Official provider documentation: https://xoomar.com/markets/api/calendar
Terms: https://xoomar.com/terms (reviewed September 9, 2026).
Its terms permit API data in personal and commercial projects within limits.
Provider states 30 requests/minute per IP without a key, weekly schedule sync and
CPI/NFP actuals within an hour. Consensus forecasts are not supplied.
Observed response: four USD events, one NFP actual and three upcoming releases.
This is **LIVE/REAL, LIMITED, DEGRADED**, not a complete or low-latency calendar.

Trading Economics requires credentials; none supplied. Forex Factory weekly
export was reachable but lacks actuals and robust occurrence IDs; no HTML scraper
or redistribution assumption was introduced. No account, paid subscription or
third-party integration was purchased or created.

Official cross-checks:
- BLS employment release: https://www.bls.gov/news.release/archives/empsit_09042026.htm
- BLS CPI schedule: https://www.bls.gov/cpi/
- NFP August: 162 thousand, September 4 at 12:30 UTC / 19:30 Bangkok.
- CPI August schedule: September 11 at 12:30 UTC / 19:30 Bangkok.

## Configuration and operations

- Local backend/.env explicitly sets NEWS_CALENDAR_PROVIDER=xoomar.
- Default without an explicit provider is unavailable, never implicit fixture.
- .env.example documents xoomar. fixture is explicit test/replay/demo only.
- NEWS_REAL_POLL_SECONDS=300, bounded 60–3600. One process-wide NewsService worker.
- Only backend calls fixed HTTPS host/path. No secret or configurable redirect URL.
- Maximum response one MB / 500 events; timeout 10 seconds and outer timeout 15.
- Failures back off exponentially to one hour; HTTP429 Retry-After respected up
  to the documented operational bound of one day. No immediate per-browser retry.
- Health is authenticated at /api/news/provider/status. Disconnection, stale receipt,
  limited coverage and last sync are distinct. Successful HTTP is not trading readiness.
- PublicCalendarProvider is deliberately limited_coverage=true; NewsService.available
  stays false. Existing NewsMarketContext and Phase4 gates therefore remain restrictive.
- Real provider failure retains observed history with unhealthy status; never
  substitutes fixture rows. Source-scoped repository reads prevent cross-mode leakage.
- No remote text-news service or LLM. This provider supplies calendar events only.

## Identity, time and observed revisions

Canonical EconomicEvent schema remains unchanged. Xoomar lacks event ID and event
revision timestamps; identity uses source + exact series code + required reference
period, independent of scheduled time. Unknown series, duplicate identities,
missing periods, invalid numbers, ambiguous timezone or future actual reject the
batch. Supported exact feed series map to NFP, YoY CPI, FOMC rate and GDP; catalogue
support for other Phase3.5 codes is not proof of live coverage.

updated_at and available_at on canonical events are local observation receipt.
released_at is first observed availability of an actual, not a reconstructed
economic publication timestamp. scheduled_at remains the provider schedule.
Provider snapshot updatedAt is retained separately in health metadata. Observed
upstream clock ran about four seconds ahead of this host: allow at most ten
seconds of snapshot-metadata skew, reported explicitly. This tolerance never
applies to scheduled/actual knowledge checks.

store_observations compares economic content rather than polling clocks, reads
the last stored revision on restart, and appends only changes. Local revision
numbers are not vendor revision numbers. Changes to actual, previous, schedule or
explicit status retain prior payloads. Previous is the latest provider value;
revised_previous records an observed change, while the original remains in history.
Rows absent from a snapshot are not cancelled. No history before the first receipt
is invented; corrections that occurred between polls cannot be recovered.

Existing occurrence/revision tables suffice. No migration0007 is needed; migrations
0001–0006 and existing foundation/strategy algorithms remain unchanged.
Native single-process ownership is required; this is not a distributed poll scheduler.

## Dashboard contract and update model

GET /api/dashboard/summary requires the existing JWT user dependency.
DashboardSummary is a frozen, extra-forbid Pydantic model, exported to generated
TypeScript and JSON schema. Browser validates schema, UTC clocks, source/mode,
candidate/profile/context identity and current plan geometry/eligibility.

Independent bounded market/news/analysis/strategy/database operations preserve
other cards on one module failure. Every operation has a 25-second timeout.
One application lock and 30-second cache coalesce browser requests; raw strategy
context JSON/candles are omitted from the summary. No per-browser provider polling.

Cards show canonical market quote/status, H4/H1/M15/M5 closed-bar summaries,
key levels from Phase4, recent/upcoming real events, six strategy definitions,
seven actual profiles, 13 evaluated candidates, current structural plan or
missing/conflict reasons, module health/freshness and safety.
Current plan selection: READY only, not stale/expired, descending score then stable
candidate ID. This is a display policy over existing candidates, not a new strategy.
A plan is suppressed if current provider or market health no longer permits it.

Dashboard owns one existing MarketConnection using first-frame JWT auth and
existing refresh flow. Route cleanup closes socket and timers. Quote updates
come through internal WS; health shows the actual client connection state.
Summary fetch runs every 30 seconds; stale/error hides the current plan. Backend
WebSocket status is UNKNOWN until the client supplies its actual transport state.

No win rate, PnL, equity, account balance, lot sizing, risk score, positions or orders
are generated. Adaptive is RESERVED_DISABLED. Links go to Trading and Calendar.
All primary analysis/explanation text is Thai; protocol/source identifiers remain
visible for provenance. News UI distinguishes missing actual/forecast/previous.

## Remaining scope / gate

Phase3.5R is PARTIAL: a real keyless feed works, but broad USD events, component
actuals, consensus forecasts, complete provider revision/reschedule/cancellation
history and low-latency post-news acceptance are unavailable. Missing NFP
unemployment/wages components are not invented or collapsed into a full macro score.
A documented, appropriately licensed richer feed is needed for the full original
3.5R gate. No API key is required for the implemented subset.

Phase4.1 is independently reviewable. Risk/execution remains disabled even if
future data becomes complete. Full review includes Phase3.5,3.5R,4,4.1.
STOP before Phase5; no Git mutation is authorized.
