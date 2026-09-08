// User & Auth
export interface User {
  id: string;
  email: string;
  role: 'ADMIN' | 'TRADER' | 'VIEWER';
  is_active: boolean;
  mfa_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

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

export interface HealthResponse {
  status: string;
  app: string;
  trading_mode: string;
  live_auto_trading: boolean;
  uptime_seconds: number;
}

// Navigation
export interface NavItem {
  name: string;
  href: string;
  icon: string; // We'll use simple emoji or text icons for now
  badge?: number;
}
