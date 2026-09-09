// Generated from backend OpenAPI by scripts.export_api_contract. Do not hand-edit.

export type Timeframe = "M1" | "M3" | "M5" | "M15" | "M30" | "H1" | "H4" | "D1" | "W1";

export interface Candle {
  symbol: string;
  timeframe: Timeframe;
  open_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
  bid_close: string;
  ask_close: string | null;
  source: string;
  is_closed: boolean;
}

export interface CandlePage {
  candles: Array<Candle>;
  next_cursor: string | null;
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

export interface MarketMessage {
  type: "snapshot" | "update" | "status" | "heartbeat" | "error";
  symbol: string;
  timeframe: Timeframe;
  sequence: number;
  quote: Quote | null;
  candles: Array<Candle>;
  status: MarketDataStatus;
  error: string | null;
}

export interface SymbolInfo {
  name: string;
  asset_class?: string;
  digits?: number;
  contract_size?: string;
  tick_value?: string;
  default_spread?: string;
  session_hours?: Record<string, Array<string>>;
  is_active: boolean;
  source_available: boolean;
}

export interface WsAuth {
  type: "auth";
  token: string;
}

export interface WsCommand {
  type: "subscribe" | "unsubscribe" | "ping";
  symbol?: string;
  timeframe?: Timeframe;
}
