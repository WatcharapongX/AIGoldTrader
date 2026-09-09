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

export interface Evaluation {
  id: string;
  identity_version?: string;
  scope?: "LEGACY" | "REQUEST" | "STRATEGY" | "EMPTY";
  component_ids?: Record<string, string>;
  context: StrategyMarketContext;
  profiles: Array<TraderProfile>;
  strategies: Array<StrategyDefinition>;
  candidates: Array<SetupCandidate>;
  modes?: Array<string>;
  adaptive_status?: "RESERVED_DISABLED";
}

export interface Evidence {
  code: string;
  description_th: string;
  source_ids?: Array<string>;
  confirmed_at?: string | null;
  weight?: number;
}

export interface Frame {
  timeframe: Timeframe;
  input_id: string;
  config_id: string;
  algorithm_version: string;
  window_start: string | null;
  as_of: string | null;
  bars: number;
  requested: number;
  candles_json: string;
  analysis_json: string;
  indicators: Array<Indicator>;
  patterns: Array<Pattern>;
}

export interface Indicator {
  name: string;
  value: string | null;
  minimum_bars: number;
  status: "READY" | "WARMUP" | "UNAVAILABLE";
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

export interface MarketSafetyContext {
  spread_state?: "SPREAD_NORMAL" | "SPREAD_ELEVATED" | "SPREAD_EXTREME" | "UNAVAILABLE";
  volatility_state?: "NORMAL" | "ELEVATED" | "EXTREME" | "UNAVAILABLE";
  current_spread?: string | null;
  baseline_spread?: string | null;
  quote_as_of?: string | null;
  source_ids?: Array<string>;
}

export interface NewsCandidateProvenance {
  context_fingerprint: string;
  source: string;
  as_of: string;
  news_engine_version: string;
  event_vintages: Array<EconomicEvent>;
  phase3_input_ids: Array<string>;
}

export interface Pattern {
  id: string;
  kind: string;
  direction: "LONG" | "SHORT" | "NO_TRADE";
  status: "FORMING" | "CANDIDATE" | "CONFIRMED" | "FAILED" | "INVALIDATED" | "EXPIRED";
  points: Array<PatternPoint>;
  neckline: string;
  upper: string;
  lower: string;
  confirmed_at: string | null;
  detected_at: string;
  expires_at: string;
  source_ids: Array<string>;
  reason_th: string;
}

export interface PatternPoint {
  id: string;
  time: string;
  confirmed_at: string;
  price: string;
  kind: "HIGH" | "LOW";
}

export interface SessionRange {
  id: string;
  name: string;
  timezone: string;
  start: string;
  end: string;
  high: string;
  low: string;
  status: "CONFIRMED" | "PROVISIONAL";
  complete_coverage: boolean;
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

export interface StrategyMarketContext {
  id: string;
  symbol: string;
  source: string;
  mode: "ACTUAL" | "REPLAY";
  as_of: string;
  config_id: string;
  strategy_config_json: string;
  analysis_config_json: string;
  engine_version?: string;
  tick_size: string | null;
  frames: Array<Frame>;
  key_levels: Array<KeyLevel>;
  sessions: Array<SessionRange>;
  current_session: string;
  market_context_id?: string;
  market_safety?: MarketSafetyContext;
  news_json: string | null;
  news_fingerprint: string | null;
  absence_means?: "NOT_INCLUDED_UNKNOWN";
  execution?: "ANALYSIS_ONLY";
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

export interface StrategyResponse {
  evaluation: Evaluation;
  generated_at: string;
  served_at: string;
  stale: boolean;
}

export interface Transition {
  id: string;
  candidate_id: string;
  context_id: string;
  from_status: "DETECTED" | "WAITING_CONFIRMATION" | "READY" | "BLOCKED_CONTEXT" | "NO_TRADE" | "INVALIDATED" | "EXPIRED" | "SUPERSEDED";
  to_status: "DETECTED" | "WAITING_CONFIRMATION" | "READY" | "BLOCKED_CONTEXT" | "NO_TRADE" | "INVALIDATED" | "EXPIRED" | "SUPERSEDED";
  as_of: string;
  reason_th: string;
}
