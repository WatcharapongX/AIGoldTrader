// Generated from backend OpenAPI by scripts.export_api_contract. Do not hand-edit.

export interface DashboardHealth {
  module: string;
  state: "HEALTHY" | "DEGRADED" | "STALE" | "UNAVAILABLE" | "UNKNOWN" | "DISABLED";
  detail_th: string;
}

export interface EconomicEvent {
  id: string;
  provider_event_id: string;
  occurrence_key: string;
  event_name: string;
  event_code: string;
  group_id: string;
  country: string;
  currency: string;
  category: "EMPLOYMENT" | "INFLATION" | "CENTRAL_BANK" | "GROWTH" | "CONSUMER" | "MANUFACTURING" | "SERVICES" | "HOUSING" | "LABOR" | "OTHER";
  impact: "LOW" | "MEDIUM" | "HIGH" | "HOLIDAY" | "NON_ECONOMIC" | "UNKNOWN";
  scheduled_at: string;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  revised_previous?: string | null;
  previous_before_revision?: string | null;
  unit: "PERCENT" | "THOUSANDS" | "INDEX" | "RATE" | "NUMBER" | "NON_NUMERIC";
  status: "SCHEDULED" | "UPCOMING" | "RELEASED" | "REVISED" | "CANCELLED" | "DELAYED" | "UNKNOWN";
  source: string;
  source_mode: "FIXTURE" | "LIVE" | "UNAVAILABLE";
  updated_at: string;
  available_at: string;
  released_at?: string | null;
  revision_version: number;
  direction_rule?: "HIGHER_IS_POSITIVE" | "LOWER_IS_POSITIVE" | "CONTEXT_DEPENDENT";
  field_provenance?: Record<string, string>;
  field_conflicts?: Array<string>;
}

export interface EventRelevance {
  affected_currency: string;
  score: number;
  channels: Array<string>;
}

export interface Evidence {
  code: string;
  description_th: string;
  source_ids?: Array<string>;
  confirmed_at?: string | null;
  weight?: number;
}

export interface History {
  requested: number;
  returned: number;
  closed: number;
  status: "COMPLETE" | "PARTIAL" | "EMPTY";
}

export interface KeyLevel {
  id: string;
  symbol: string;
  timeframe: Timeframe;
  kind: string;
  price: string;
  upper?: string | null;
  origin: string;
  confirmed_at: string | null;
  valid_from: string;
  status: "CONFIRMED" | "PROVISIONAL" | "SWEPT" | "INVALIDATED";
  source_ids: Array<string>;
  input_id: string;
}

export interface LiquidityLevel {
  id: string;
  kind: "BSL" | "SSL" | "EQH" | "EQL" | "PDH" | "PDL" | "PWH" | "PWL" | "SESSION_HIGH" | "SESSION_LOW";
  side: "HIGH" | "LOW";
  price: string;
  created_at: string;
  confirmed_at: string;
  source_ids: Array<string>;
  status?: "ACTIVE" | "SWEPT" | "INVALIDATED";
  swept_at?: string | null;
  sweep_price?: string | null;
  ended_at?: string | null;
}

export interface MarketDataStatus {
  source: string;
  mode: "SIMULATED" | "DEMO" | "LIVE" | "UNCONFIRMED";
  status: "CONNECTING" | "CONNECTED" | "STALE" | "DISCONNECTED" | "ERROR";
  last_quote: string | null;
  server_time: string;
  stale_after_seconds: number;
  detail: string;
  subscriptions: number;
  history_counts?: Record<string, number>;
  history_complete?: boolean;
  digits?: number | null;
  tick_size?: string | null;
  provider_symbol?: string | null;
  market_state?: "OPEN" | "CLOSED" | "UNKNOWN";
  last_candle?: string | null;
  volume_kind?: "synthetic" | "tick_count";
}

export interface NewsCandidateProvenance {
  context_fingerprint: string;
  source: string;
  as_of: string;
  news_engine_version: string;
  event_vintages: Array<EconomicEvent>;
  phase3_input_ids: Array<string>;
}

export interface NewsResponse {
  symbol?: "XAUUSD";
  as_of: string;
  market_as_of: string | null;
  news_engine_version?: string;
  config_id: string;
  fingerprint: string;
  source: string;
  source_mode: "FIXTURE" | "LIVE" | "UNAVAILABLE";
  calendar_state: "AVAILABLE" | "CALENDAR_UNAVAILABLE";
  view: "current" | "pre" | "release" | "post" | "none";
  events: Array<EconomicEvent>;
  xauusd_relevance: Record<string, EventRelevance>;
  upcoming_events: Array<EconomicEvent>;
  active_group: ReleaseGroup | null;
  active_event_id: string | null;
  news_regime: "NORMAL" | "PRE_NEWS" | "NEWS_LOCK" | "RELEASE" | "POST_NEWS_VOLATILITY" | "POST_NEWS_CONFIRMATION" | "NORMALIZED" | "UNKNOWN";
  macro_bias: "USD_STRONG_POSITIVE" | "USD_POSITIVE" | "USD_NEUTRAL" | "USD_NEGATIVE" | "USD_STRONG_NEGATIVE" | "CONFLICTING" | "UNKNOWN";
  macro_strength: "STRONG" | "MODERATE" | "MIXED" | "UNKNOWN";
  multiple_event_risk: boolean;
  reaction_windows: Array<ReactionWindow>;
  reaction_state: string;
  spread_state: "SPREAD_NORMAL" | "SPREAD_ELEVATED" | "SPREAD_EXTREME" | "UNAVAILABLE";
  baseline_spread: string | null;
  current_spread: string | null;
  spread_ratio: string | null;
  volatility_state: "NORMAL" | "ELEVATED" | "EXTREME" | "UNAVAILABLE";
  structure_confirmation: StructureContext;
  trade_policy_state: "INFORMATIONAL" | "CAUTION" | "RESTRICTED";
  strategy_eligibility: Record<string, "ALLOWED" | "CAUTION" | "BLOCKED" | "WAITING" | "ELIGIBLE">;
  reason_codes: Array<string>;
  market_source: string | null;
  release_status?: "NO_EVENT" | "PRE_NEWS" | "WAITING_FOR_ACTUAL" | "WAITING_FOR_RELEASE" | "RELEASED";
  data_quality?: "COMPLETE" | "PARTIAL" | "CONFLICT" | "UNAVAILABLE";
  generated_at: string;
  served_at: string;
  cache_age_seconds: number;
}

export interface ProviderHealth {
  source: string;
  source_mode: "FIXTURE" | "LIVE" | "UNAVAILABLE";
  state: "HEALTHY" | "DEGRADED" | "STALE" | "UNAVAILABLE" | "CONFIGURATION_REQUIRED";
  connected: boolean;
  coverage: "FULL" | "LIMITED" | "FIXTURE" | "NONE";
  calendar_usable_for_trading: boolean;
  provider_updated_at: string | null;
  received_at: string | null;
  snapshot_clock_skew_seconds?: number;
  last_sync_at: string | null;
  next_poll_at: string | null;
  event_count: number;
  failures: number;
  poll_seconds: number;
  reason_code: string;
  detail_th: string;
}

export interface Quote {
  symbol: string;
  timestamp: string;
  bid: string;
  ask: string;
  volume: string;
  source: string;
  mode?: "SIMULATED" | "DEMO" | "LIVE";
  spread: string;
  status: "CONNECTED" | "STALE" | "DISCONNECTED" | "ERROR";
}

export interface ReactionWindow {
  seconds: number;
  status: "READY" | "WAITING" | "REACTION_UNAVAILABLE";
  cutoff: string;
  price_before?: string | null;
  price_after?: string | null;
  return_percent?: string | null;
  move_atr?: string | null;
  range_atr?: string | null;
  tick_activity_ratio?: string | null;
  classification?: "STRONG_DIRECTIONAL" | "WHIPSAW" | "LIQUIDITY_SWEEP_REVERSAL" | "BREAKOUT" | "FAILED_BREAKOUT" | "MUTED" | "UNCONFIRMED";
}

export interface ReleaseGroup {
  group_id: string;
  event_ids: Array<string>;
  alignment: "ALL_ALIGNED" | "MOSTLY_ALIGNED" | "MIXED" | "CONFLICTING" | "UNAVAILABLE";
  bias: "USD_STRONG_POSITIVE" | "USD_POSITIVE" | "USD_NEUTRAL" | "USD_NEGATIVE" | "USD_STRONG_NEGATIVE" | "CONFLICTING" | "UNKNOWN";
  score: string;
  completeness: "COMPLETE" | "PARTIAL";
  surprises: Array<Surprise>;
}

export interface SetupCandidate {
  id: string;
  profile_id: string;
  strategy_id: string;
  strategy_version?: string;
  symbol: string;
  direction: "LONG" | "SHORT" | "NO_TRADE";
  status: "DETECTED" | "WAITING_CONFIRMATION" | "READY" | "BLOCKED_CONTEXT" | "NO_TRADE" | "INVALIDATED" | "EXPIRED" | "SUPERSEDED";
  score: number;
  detected_at: string;
  confirmed_at: string | null;
  expires_at: string;
  context_id: string;
  upstream_ids: Array<string>;
  news_provenance?: NewsCandidateProvenance | null;
  evidence: Array<Evidence>;
  missing_conditions: Array<string>;
  conflicts: Array<string>;
  invalidation_th: string;
  plan: TradePlanSuggestion | null;
}

export interface StrategyDefinition {
  id: string;
  name: string;
  version?: string;
  category: string;
  styles: Array<"SCALP" | "DAY_TRADE" | "SWING" | "RUN_TREND">;
  required_context: Array<string>;
  minimum_bars?: number;
  description_th: string;
}

export interface StructureContext {
  status: "ALIGNED" | "CONFLICTING" | "WAITING" | "STRUCTURE_UNAVAILABLE";
  upstream_input_id: string | null;
  upstream_config_id: string | null;
  upstream_algorithm_version: string | null;
  upstream_as_of: string | null;
  upstream_window_start: string | null;
  absence_means?: "NOT_INCLUDED_UNKNOWN";
  references: Record<string, string>;
}

export interface StructureEvent {
  id: string;
  scope: "INTERNAL" | "EXTERNAL";
  kind: "BOS" | "CHOCH" | "MSS";
  direction: "BULLISH" | "BEARISH";
  price: string;
  swing_id: string;
  swing_time: string;
  occurred_at: string;
  confirmed_at: string;
  displacement: boolean;
  parent_event_id?: string | null;
  confirmation?: "CONFIRMED";
}

export interface StructureSummary {
  timeframe: Timeframe;
  input_id: string;
  as_of: string | null;
  internal_state: string;
  external_state: string;
  regime: string;
  history: History;
  latest_event: StructureEvent | null;
  liquidity: Array<LiquidityLevel>;
}

export interface Surprise {
  event_id: string;
  raw: string | null;
  relative: string | null;
  normalized?: string | null;
  normalized_method?: "UNAVAILABLE_NO_DISTRIBUTION";
  direction: "ABOVE" | "BELOW" | "INLINE" | "UNAVAILABLE";
  magnitude: "LARGE" | "SMALL" | "ZERO" | "UNAVAILABLE";
  usd_direction: "POSITIVE" | "NEGATIVE" | "NEUTRAL" | "UNKNOWN";
  revision_delta: string | null;
  reason_code: string;
}

export interface Target {
  name: string;
  price: string;
  source_id: string;
  rr: string;
}

export type Timeframe = "M1" | "M3" | "M5" | "M15" | "M30" | "H1" | "H4" | "D1" | "W1";

export interface TimeframeMap {
  style: "SCALP" | "DAY_TRADE" | "SWING" | "RUN_TREND";
  context: Timeframe;
  bias: Timeframe;
  setup: Timeframe;
  trigger: Timeframe;
  minimum_bars?: number;
}

export interface TradePlanSuggestion {
  id: string;
  candidate_id: string;
  symbol: string;
  direction: "LONG" | "SHORT";
  entry_type: "MARKET_REFERENCE" | "LIMIT_ZONE" | "RETEST_ZONE" | "BREAKOUT_RETEST";
  entry_lower: string;
  entry_upper: string;
  entry_source_id: string;
  stop_loss: string;
  stop_source_id: string;
  invalidation_th: string;
  targets: Array<Target>;
  score: number;
  evidence: Array<Evidence>;
  warnings_th: Array<string>;
  news_state: string;
  status?: "SUGGESTION_ONLY";
  as_of: string;
  context_id: string;
  expires_at: string;
}

export interface TraderProfile {
  id: string;
  name: string;
  description_th: string;
  style: "SCALP" | "DAY_TRADE" | "SWING" | "RUN_TREND";
  enabled?: boolean;
  allowed_strategies: Array<string>;
  timeframe_map: TimeframeMap;
  config_id: string;
  candidate_policy?: "ALL_EXPLAINED";
  execution_mode?: "ANALYSIS_ONLY";
  created_at?: string;
  updated_at?: string;
}

export interface DashboardSummary {
  generated_at: string;
  served_at: string;
  refresh_seconds?: 30;
  symbol?: "XAUUSD";
  trading_mode?: "PAPER";
  live_auto_trading?: false;
  broker_execution?: "DISABLED";
  risk_engine?: "NOT_IMPLEMENTED";
  market: MarketDataStatus | null;
  quote: Quote | null;
  structure: Array<StructureSummary>;
  analysis_generated_at: string | null;
  current_session: string | null;
  key_levels: Array<KeyLevel>;
  news: NewsResponse | null;
  news_provider: ProviderHealth | null;
  calendar_events: Array<EconomicEvent>;
  strategies: Array<StrategyDefinition>;
  profiles: Array<TraderProfile>;
  candidates: Array<SetupCandidate>;
  strategy_market_context_id?: string | null;
  strategy_context_id: string | null;
  strategy_generated_at: string | null;
  strategy_as_of: string | null;
  strategy_stale: boolean;
  current_plan: TradePlanSuggestion | null;
  adaptive_status?: "RESERVED_DISABLED";
  health: Array<DashboardHealth>;
}
