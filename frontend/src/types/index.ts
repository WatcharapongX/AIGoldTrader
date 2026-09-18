import type { AccessTokenResponse, HealthResponse, MeResponse, ReadyResponse } from './api.generated';
export type { AccessTokenResponse, HealthResponse, ReadyResponse };
export type User = MeResponse;
export type TokenPair = AccessTokenResponse;

export interface LoginRequest {
  email: string;
  password: string;
}

export interface ApiError {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
    correlation_id?: string;
  };
}

// Navigation
export interface NavItem {
  name: string;
  href: string;
  icon: string; // We'll use simple emoji or text icons for now
  badge?: number;
}

export interface SubsystemStatus {
  module: string;
  state: 'HEALTHY' | 'DEGRADED' | 'STALE' | 'UNAVAILABLE' | 'NORMAL' | 'ACTIVE' | 'FIXTURE_READY' | 'EXTERNAL_READY' | 'EXTERNAL_NOT_CONFIGURED' | 'DISABLED';
  detail_th: string;
  updated_at: string;
}

export interface SystemStatusResponse {
  as_of: string;
  trading_mode: string;
  live_auto_trading: boolean;
  ai_mode: string;
  ai_status_label: string;
  modules: Record<string, SubsystemStatus>;
}

export interface AccountSnapshotData {
  id: string;
  account_id: string;
  balance: string | number;
  equity: string | number;
  free_margin: string | number | null;
  daily_realized_pnl: string | number;
  weekly_realized_pnl: string | number;
  floating_pnl: string | number | null;
  peak_equity: string | number;
  open_risk_pct: string | number;
  reserved_risk_pct: string | number;
  consecutive_losses: number;
  trading_mode: string;
  source: string;
  as_of: string;
}
