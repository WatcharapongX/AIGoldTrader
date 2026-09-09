// Generated from backend OpenAPI by scripts.export_api_contract. Do not hand-edit.

export interface DealingRange {
  lower_bound: string;
  equilibrium: string;
  upper_bound: string;
  origin_time: string;
  confirmed_at: string;
  direction: "BULLISH" | "BEARISH";
  swing_ids: Array<string>;
  location: "PREMIUM" | "DISCOUNT" | "EQUILIBRIUM";
  retracement_62: string;
  retracement_79: string;
}

export interface History {
  requested: number;
  returned: number;
  closed: number;
  status: "COMPLETE" | "PARTIAL" | "EMPTY";
}

export interface IndicatorValue {
  value: string | null;
  minimum_bars_required: number;
  status: "READY" | "INSUFFICIENT_DATA";
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

export interface ModuleStatus {
  status: "READY" | "PARTIAL_HISTORY" | "INSUFFICIENT_DATA" | "NO_STRUCTURE" | "ERROR";
  minimum_bars_required: number;
  available_bars: number;
  reason: string;
}

export interface RetentionPolicy {
  mode?: "BOUNDED_SNAPSHOT";
  absence_means?: "NOT_INCLUDED_UNKNOWN";
  absence_is_invalidation?: false;
}

export interface SessionRange {
  name: string;
  start: string;
  end: string;
  high: string;
  low: string;
  confirmed_at: string;
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

export interface SwingPoint {
  id: string;
  scope: "INTERNAL" | "EXTERNAL";
  kind: "HIGH" | "LOW";
  label: "SH" | "SL" | "HH" | "HL" | "LH" | "LL" | "EQH" | "EQL";
  price: string;
  swing_time: string;
  confirmed_at: string;
  confirmation?: "CONFIRMED";
}

export type Timeframe = "M1" | "M3" | "M5" | "M15" | "M30" | "H1" | "H4" | "D1" | "W1";

export interface Zone {
  id: string;
  kind: "FVG" | "IFVG" | "OB" | "BREAKER";
  direction: "BULLISH" | "BEARISH";
  lower_bound: string;
  upper_bound: string;
  occurred_at: string;
  confirmed_at: string;
  status: "OPEN" | "PARTIALLY_FILLED" | "FILLED" | "ACTIVE" | "MITIGATED" | "INVALIDATED";
  source_event_id?: string | null;
  fill_fraction?: string;
  ended_at?: string | null;
}

export interface AnalysisSnapshot {
  symbol: string;
  timeframe: Timeframe;
  source: string;
  algorithm_version: string;
  config_id: string;
  retention?: RetentionPolicy;
  input_id: string;
  window_start: string | null;
  history: History;
  as_of: string | null;
  modules: Record<string, ModuleStatus>;
  internal_state: "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN";
  external_state: "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN";
  swings: Array<SwingPoint>;
  events: Array<StructureEvent>;
  liquidity: Array<LiquidityLevel>;
  zones: Array<Zone>;
  dealing_range: DealingRange | null;
  indicators: Record<string, IndicatorValue>;
  sessions: Array<SessionRange>;
  current_sessions: Array<string>;
  regime: "TRENDING_UP" | "TRENDING_DOWN" | "RANGING" | "HIGH_VOLATILITY" | "LOW_VOLATILITY" | "BREAKOUT" | "PULLBACK" | "UNKNOWN";
  news_context?: "UNKNOWN";
  confluence_counts: Record<string, number>;
}

export interface AnalysisResponse {
  symbol: string;
  timeframe: Timeframe;
  source: string;
  algorithm_version: string;
  config_id: string;
  retention?: RetentionPolicy;
  input_id: string;
  window_start: string | null;
  history: History;
  as_of: string | null;
  modules: Record<string, ModuleStatus>;
  internal_state: "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN";
  external_state: "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN";
  swings: Array<SwingPoint>;
  events: Array<StructureEvent>;
  liquidity: Array<LiquidityLevel>;
  zones: Array<Zone>;
  dealing_range: DealingRange | null;
  indicators: Record<string, IndicatorValue>;
  sessions: Array<SessionRange>;
  current_sessions: Array<string>;
  regime: "TRENDING_UP" | "TRENDING_DOWN" | "RANGING" | "HIGH_VOLATILITY" | "LOW_VOLATILITY" | "BREAKOUT" | "PULLBACK" | "UNKNOWN";
  news_context?: "UNKNOWN";
  confluence_counts: Record<string, number>;
  generated_at: string;
  served_at: string;
  cache_age_seconds: number;
}

export interface ContextRow {
  timeframe: Timeframe;
  state: "BULLISH" | "BEARISH" | "NEUTRAL" | "UNKNOWN";
  history: History;
  status: "READY" | "PARTIAL_HISTORY" | "INSUFFICIENT_DATA" | "NO_STRUCTURE" | "ERROR";
  as_of: string | null;
}

export interface MultiTimeframeContext {
  symbol: string;
  source: string;
  algorithm_version: string;
  bias: "BULLISH" | "BEARISH" | "NEUTRAL" | "MIXED" | "UNKNOWN";
  timeframes: Array<ContextRow>;
}
