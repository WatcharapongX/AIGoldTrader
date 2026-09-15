# Data Provenance and Truthfulness Contract

This contract applies to every visible AI Gold Trader workspace and export. Its mandatory invariant is:

> An API error, missing field, invalid payload, or unavailable subsystem must never silently become fixture, simulated, sample, default-normal, or fabricated financial data.

## Taxonomy

Provenance and condition are separate dimensions.

| Mode | Required UI meaning |
| --- | --- |
| `LIVE` | `REAL MARKET DATA · LIVE`; production feed and account only when confirmed by the API |
| `DEMO` | `MT5 DEMO · REAL MARKET DATA`; real broker prices from a demo connection, not live capital |
| `SIMULATED` | Deterministic/synthetic data; never described as live market data |
| `REPLAY` | Historical point-in-time evaluation; never described as current/live |
| `FIXTURE` | Test/offline fixture; always visible and never entered because a live request failed |
| `PAPER` | Configured paper execution mode; not proof of account availability or performance |
| `DERIVED` | A transformation of named authoritative inputs; inherits their mode and weakest condition |
| `UNAVAILABLE` | No trustworthy value can be displayed |
| `NOT IMPLEMENTED` | The product has no authoritative implementation/dataset for the field |

Condition labels are `FRESH`, `PARTIAL`, `STALE`, `CONFLICT`, `DEGRADED`, and `UNAVAILABLE`. A generic `LIVE` condition is prohibited. `STALE` must include the last authoritative timestamp when one exists. Last-known data may remain visible only with `STALE` and that timestamp.

## Null, zero, empty, and fallback rules

- `null`, missing, invalid, and failed are not zero. Render `N/A` or `UNAVAILABLE`.
- Explicit numeric zero is preserved as zero, including balances, margin, counts, risk, scores, spreads, and drawdown.
- A successful empty list is an empty state. A failed request is an error/`UNAVAILABLE` state; it must not render as a legitimate zero-count dataset.
- Frontend calculation is allowed only for presentation/derivation when the inputs and formula are visible or documented. Trading decisions, ATR, market structure, risk decisions, and AI output remain backend-authoritative.
- Derived values inherit source, mode, timestamp, and the weakest freshness/quality state of their inputs.
- CSV and JSON exports must preserve report type, condition, source, mode, data-as-of, generation time, coverage, and active filters.

## Audit matrix

| Page | Section | Displayed Field | Frontend Component | API/Source | Backend Field | Transformation | Provenance | Freshness | Fallback | UI Label | Truthful? | Action Required |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FC-01 Dashboard | Safety | trading/auto mode | `DashboardView` | `/dashboard/summary` | `trading_mode`, `live_auto_trading` | none | configured runtime | summary age | UNKNOWN | explicit mode | Yes | Fixed invented PAPER/OFF |
| FC-01 Dashboard | Quote | bid/ask/spread | `DashboardView` | market WS + summary | quote fields | formatting only | market provider | quote age/transport | dash | source, mode, timestamp | Yes | None |
| FC-01 Dashboard | Chart | M5 OHLC/MAs | `DashboardView` | `/market/candles` | closed candles | OHLC select; display MA | inherited market | candle/summary | dash | M5 + market label | Yes | Documented derived scope |
| FC-01 Dashboard | Risk | reservations/limits | `DashboardView` | `/risk/*` | portfolio/policy | rounding only | risk API | state enum | UNAVAILABLE | state banner | Yes | Fixed default 0/3%/1% |
| FC-01 Dashboard | Capital | balance/equity/margin | `DashboardView` | `/risk/account` | account snapshot | formatting only | account source/mode | state + as-of | UNAVAILABLE | account mode/state | Yes | Fixed fabricated $10,000 |
| FC-01 Dashboard | Capital | current snapshot drawdown | `DashboardView` | `/risk/account` | equity, peak equity | current ratio | inherited account | state + as-of | UNAVAILABLE | Current Snapshot Drawdown | Yes | Renamed from peak/max claim |
| FC-01 Dashboard | AI | provider status | `DashboardView` | `/system/status` | AI mode/label | none | system status | status request | UNAVAILABLE | AI status | Yes | Fixed fixture fallback |
| FC-02 Market Overview | Header | provider/mode/condition | `DataProvenanceLine` | `/market/status`, WS | source/mode/status/time | normalized label | market provider | separate condition | UNAVAILABLE | canonical badges | Yes | Added shared component |
| FC-02 Market Overview | Sessions | open/closed | `MarketOverviewView` | client clock + UTC rules | clock | deterministic schedule | DERIVED | current client clock | unavailable clock | derived label | Yes | Added derivation label |
| FC-02 Market Overview | Metrics | midpoint/change/range | `MarketOverviewView` | quote + candles | prices/OHLC | arithmetic | inherited market | weakest input | dash | market section provenance | Yes | None |
| FC-02 Market Overview | ATR | ATR(14) | `MarketOverviewView` | `/analysis/structure` | `indicators.ATR` | formatting only | analysis engine | analysis state/as-of | dash | analysis state | Yes | Backend-authoritative |
| FC-02 Market Overview | Health | provider/risk/kill switch | `MarketOverviewView` | market + system APIs | status fields | none | respective API | latest response | UNAVAILABLE | explicit field state | Yes | Fixed healthy/connected defaults |
| FC-03 Market Analysis | Structure | BOS/CHoCH/liquidity | `AnalysisWorkspace` | `/analysis/structure` | canonical analysis | formatting/selection | analysis engine | `as_of`, history | no fake structures | source/detail | Yes | None |
| FC-03 Market Analysis | MTF | frame states | `StrategyAnalysisContext` | `/analysis/context` | frame history/state | none | analysis engine | frame status | unavailable | context provenance | Yes | None |
| FC-03 Market Analysis | AI | agent result/model | `AIAgent*` | `/ai/analyze`, system | result/provenance | none | external or fixture explicit | response status | UNAVAILABLE | advisory-only + provider | Yes | Fixed fixture model/readiness defaults |
| FC-04 Trading Signals | Candidates | state/score/plan | `TradingSignalsScreen` | `/trade-candidates`, strategy context | candidate fields | filtering only | strategy engine | detected/expires | empty vs notice | Candidate ≠ trade | Yes | None |
| FC-04 Trading Signals | Risk | decision/kill switch | signal components | `/risk/*` | risk fields | none | risk engine | response state | unavailable | fail-closed | Yes | None |
| FC-05 Backtest & Strategy | Catalog | strategies/profiles | `StrategyLabScreen` | `/strategies`, `/trader-profiles` | arrays | count | strategy config | request state | UNAVAILABLE | endpoint alert | Yes | Fixed failed-as-zero |
| FC-05 Backtest & Strategy | Evaluations | current/history | `EvaluationsTab` | `/strategy/context`, `/strategy/evaluations` | snapshots | descriptive counts | analysis/replay | `stale`, `as_of` | UNAVAILABLE | FRESH/STALE | Yes | Fixed LIVE wording/version fallback |
| FC-05 Backtest & Strategy | Provider | market source | `DataProvenanceLine` | `/market/status` | direct status contract | normalization only | market provider | separate condition | UNAVAILABLE | canonical badges | Yes | Fixed nested-contract/fake DEMO fallback |
| FC-05 Backtest & Strategy | Backtest | performance | `BacktestReadinessTab` | no dataset | none | none | NOT IMPLEMENTED | n/a | N/A | NOT IMPLEMENTED | Yes | None |
| FC-06 Economic Calendar | Feed | events/actual/forecast/revision | `CalendarWorkspace` | `/calendar/economic` | calendar/event fields | filtering/grouping | calendar provider | point-in-time/as-of | UNAVAILABLE | source/mode/state | Yes | Fixed fixture/available fallback |
| FC-06 Economic Calendar | Countdown | time-to-event | `NextEconomicEventCard` | event time + as-of/client clock | scheduled time | deterministic difference | DERIVED from event | ticking clock | dash | source/mode | Yes | Fixed default fixture provenance |
| FC-07 News & Sentiment | Macro | bias/quality/regime | `MacroBiasCard` | `/news/context` | macro fields | none | news provider | as-of/data quality | UNAVAILABLE | not-a-signal | Yes | Fixed default normal/complete |
| FC-07 News & Sentiment | Reaction | spread/volatility/reaction | `MarketReactionPanel` | `/news/context` | reaction fields | formatting only | market reference + news | reaction state | UNAVAILABLE | source mode | Yes | Fixed default LIVE/normal |
| FC-08 Performance | Account | account snapshot | `AccountSnapshotCard` | `/risk/account` | account fields | formatting only | account source | as-of | error state | mode/source | Yes | None |
| FC-08 Performance | Operational | candidates/decisions/risk | analytics panels | bounded strategy/risk APIs | records | descriptive aggregates | source endpoints | loaded-at | error state | analysis-only scope | Yes | None |
| FC-08 Performance | Executed metrics | win rate/P&L/equity curve | `ExecutionPerformanceSection` | no execution ledger | none | none | NOT IMPLEMENTED | n/a | N/A | NOT AVAILABLE | Yes | None |
| FC-09 Reports | Datasets | report table/facts | `ReportsScreen` | bounded domain APIs | records | filters only | per report | per report | isolated UNAVAILABLE | status/source/mode/as-of | Yes | None |
| FC-09 Reports | Export | CSV/JSON artifact | report contracts | visible report | rows + metadata | serialization | inherited report | condition + data-as-of | disabled if empty | metadata envelope/columns | Yes | Fixed CSV provenance loss |
| Shared | Sidebar | runtime health | `RuntimeStatus` | health/ready/market/system | status fields | none | per subsystem | polling response | UNKNOWN | explicit status | Yes | Fixed AI NOT IMPLEMENTED fallback |
| Shared | Topbar | user/session | layout/auth store | authenticated session | identity/session | formatting only | auth | session lifecycle | signed-out/unknown | account UI | Yes | None |

## Enforcement

`frontend/tests/data-provenance.test.cjs` locks the canonical labels and scans production TypeScript for the known silent-fallback patterns. Domain contract tests continue to validate payload shape, point-in-time semantics, safety invariants, and export behavior. Any new page must add its lineage row here and reuse the shared provenance labels where a source/mode/condition is visible.
