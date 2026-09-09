# Deterministic SMC / ICT semantics — Phase 3

Algorithm structure-1.0.0 uses explicit definitions below. Terminology varies; these are reproducible descriptive rules, not claims of institutional intent or validated trading profitability. Inputs and availability rules are in [07-market-structure.md](07-market-structure.md).

## Liquidity

Each confirmed external high creates BSL and low creates SSL at its exact price. Consecutive equal extrema within one configured tick create EQH/EQL at their arithmetic midpoint. Levels include stable identity, source swing IDs, created_at and confirmed_at. Completed observed prior day/week and configured session extrema produce PDH/PDL/PWH/PWL/SESSION_HIGH/SESSION_LOW with the period reference. Missing history is never filled.

Only bars whose open is at or after confirmation can change a level. A high-side wick beyond price+tolerance followed by a close at/below the level is SWEPT; low-side is mirrored. sweep_price and swept_at record the extremum and confirmation close. A close beyond tolerance instead makes the level INVALIDATED. A wick between the level and tolerance, or a close in the tolerance band above/below the level, leaves it ACTIVE. SWEPT and INVALIDATED are terminal in this version. A sweep is descriptive and has no buy/sell action.

## Fair value gaps

Three adjacent closed canonical bars A/B/C qualify when C.low - A.high >= tick_size * minimum_gap_ticks (default two ticks), giving a bullish interval [A.high,C.low]. Bearish is A.low - C.high >= threshold, interval [C.high,A.low]. Equality at the minimum qualifies; zero-width gaps do not. B need not pass an additional displacement filter. Non-adjacent bars across market/data gaps do not create FVGs.

The zone originates at A.open_time but is only confirmed at C.close_time. Subsequent bar penetration updates fill_fraction monotonically from the near boundary; touch at zero penetration is PARTIALLY_FILLED with zero fraction; reaching the far boundary with a close still inside tolerance gives FILLED. Close beyond the distal edge by more than tolerance takes precedence and INVALIDATES the zone. This creates one reverse-direction IFVG at that bar's close. Terminal FILLED/INVALIDATED zones are not reopened. IFVG uses the same fill/invalidation rules but does not invert indefinitely.

## Order blocks and breakers

Only displacement-qualified BOS or MSS creates an OB. Search the previous ob_lookback=20 closed bars backward for the most recent opposing-body candle (bearish before bullish event, bullish before bearish event). The full high/low range must have positive height. Doji is not opposing. The zone links its qualifying structure event, carries the origin candle time and the event's confirmed_at, and begins ACTIVE. Same-direction/same-origin blocks are deduplicated.

A subsequent range overlap marks MITIGATED. A close beyond the distal boundary+tolerance marks INVALIDATED, even after mitigation. Invalidation creates one reverse-direction BREAKER with identical bounds, confirmed at the invalidating close. Breakers can mitigate/invalidate but do not spawn further breakers. No nearest-candle fallback or unconfirmed candidate OB is emitted.

These lifecycles update existing zone state; the original bounds, origin, confirming event and confirmed_at remain fixed. ended_at identifies terminal transitions. Result retention is bounded and is not a historical order ledger.

## Dealing range, premium/discount and retracements

Choose the latest confirmed external pivot and its preceding opposite-kind pivot at an earlier time; fall back to internal if no valid external pair exists. High must exceed low by more than tolerance; otherwise no range. No guessed range is fabricated. Equilibrium is the midpoint, premium is above it and discount below, with the configured tolerance band reported EQUILIBRIUM. Current price may be outside the historical range and is still classified by the midpoint.

The .62/.79 retracement coordinates implement the plan's OTE geometry only: from the upper edge for an upward leg and the lower edge for a downward leg. They are structured descriptive values, not entries, targets or recommendations. Confluence is explicitly limited to counts of currently OPEN/ACTIVE zones by direction. There is no weighted score, probability, AI confidence or strategy signal.

## Guardrails and limitations

No strategy matching, Entry/SL/TP/RR, risk sizing, broker execution, paper order creation, AI or order_send path exists here. TRADING_MODE remains PAPER and LIVE_AUTO_TRADING remains false. No database migration was added: existing head remains 0004_market_unknown_ask.

The available W1 feed remains 231/300 during this acceptance. Modules run when their minimum is satisfied and retain PARTIAL_HISTORY/NO_STRUCTURE as appropriate. Intraday session levels cannot be inferred from D1/W1 OHLC. UTC session labels are configurable analytical windows. Missing interior candles can reduce observed period extrema; coverage is never repaired with invented bars. The provider/history quality status remains visible alongside analysis.

Confirmed-event no-lookahead guarantees apply to fixed-origin input prefixes. A rolling input-window reset/configuration change/source correction is a disclosed new input revision; see the reproducibility boundary in docs/07. This limitation and the absence of a persistent analysis ledger must be considered in the combined independent review before any strategy or execution work.

Golden tests cover both-direction BOS/CHOCH/MSS, CHOCH without displacement, equality/plateaus, wick sweeps versus close breaks, both-direction gap filling/inversion, OB mitigation/invalidation/breakers, indicators, session boundaries, malformed data, minimum counts, bounded state and prefix/batch/stream consistency. Native browser results use actual IUX data and are recorded separately in [phase-3-gate.md](phase-3-gate.md).
