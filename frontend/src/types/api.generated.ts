// Generated from backend OpenAPI by scripts.export_api_contract. Do not hand-edit.

export interface MeResponse {
  id: string;
  email: string;
  role: Role;
  is_active: boolean;
}

export interface AccessTokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
}

export interface HealthResponse {
  status: "ok";
  app: string;
  env: string;
  trading_mode: string;
  live_auto_trading: boolean;
  uptime_seconds: number;
}

export interface ReadyResponse {
  status: "ready" | "not_ready";
  checks: ReadyChecks;
  redis_enabled: boolean;
}

export interface ReadyChecks {
  database: boolean;
  redis: boolean | null;
}

export type Role = "ADMIN" | "TRADER" | "VIEWER";
