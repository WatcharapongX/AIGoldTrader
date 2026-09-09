// Generated from backend OpenAPI by scripts.export_api_contract. Do not hand-edit.

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

export interface CalendarPage {
  events: Array<EconomicEvent>;
  source: string;
  source_mode: "FIXTURE" | "LIVE" | "UNAVAILABLE";
  state: "AVAILABLE" | "CALENDAR_UNAVAILABLE";
  as_of: string;
  generated_at: string;
  truncated: boolean;
}

export interface EventDetail {
  event: EconomicEvent;
  revisions: Array<EconomicEvent>;
  as_of: string;
}

export interface EventRelevance {
  affected_currency: string;
  score: number;
  channels: Array<string>;
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
