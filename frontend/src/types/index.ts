// Endpoint response types come from authoritative backend OpenAPI.
export type { MeResponse as User, TokenPair, HealthResponse, ReadyResponse } from './api.generated';

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
