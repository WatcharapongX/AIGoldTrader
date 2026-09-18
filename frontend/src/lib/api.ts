import type { AccessTokenResponse, User, HealthResponse, ReadyResponse } from '@/types';
import { parseUser, parseAccessTokenResponse, parseHealth, parseReady, errorMessage, ApiContractError } from '@/lib/contracts';

export function clearSession() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('access_token');
  window.dispatchEvent(new Event('auth:expired'));
}

export class ApiClient {
  private baseUrl: string;
  private refreshPromise: Promise<string> | null = null;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || (typeof window !== 'undefined' ? '/api' : (process.env.BACKEND_INTERNAL_URL || 'http://127.0.0.1:8000/api'));
  }

  private refreshAccessToken(): Promise<string> {
    if (!this.refreshPromise) {
      this.refreshPromise = (async () => {
        const tokens = await this.refreshTokenRequest();
        if (!tokens) {
          clearSession();
          throw new Error('Session expired. Please sign in again.');
        }
        localStorage.setItem('access_token', tokens.access_token);
        return tokens.access_token;
      })().finally(() => { this.refreshPromise = null; });
    }
    return this.refreshPromise;
  }

  private async request(method: string, path: string, body?: unknown, options?: RequestInit): Promise<unknown> {
    const url = `${this.baseUrl}${path}`;
    const accessToken = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const headers = new Headers(options?.headers);
    headers.set('Content-Type', 'application/json');
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
    const config: RequestInit = {
      credentials: 'same-origin',
      ...options,
      method,
      headers,
    };
    if (body !== undefined) config.body = JSON.stringify(body);
    let response = await fetch(url, config);
    if (response.status === 401 && accessToken && path !== '/auth/login') {
      // Every concurrent request shares the same resolving/rejecting promise.
      const currentToken = localStorage.getItem('access_token');
      const token = currentToken && currentToken !== accessToken
        ? currentToken : await this.refreshAccessToken();
      headers.set('Authorization', `Bearer ${token}`);
      response = await fetch(url, { ...config, headers });
      if (response.status === 401) clearSession();
    }
    if (!response.ok) {
      let message: string | undefined;
      try { message = errorMessage(await response.json()); } catch { /* Non-JSON error response. */ }
      throw new Error(message || response.statusText || 'An API error occurred');
    }
    if (response.status === 204) return null;
    return await response.json();
  }

  public get(path: string, options?: RequestInit): Promise<unknown> {
    return this.request('GET', path, undefined, options);
  }

  public post(path: string, body?: unknown, options?: RequestInit): Promise<unknown> {
    return this.request('POST', path, body, options);
  }

  public put(path: string, body?: unknown, options?: RequestInit): Promise<unknown> {
    return this.request('PUT', path, body, options);
  }

  public patch(path: string, body?: unknown, options?: RequestInit): Promise<unknown> {
    return this.request('PATCH', path, body, options);
  }

  public delete(path: string, options?: RequestInit): Promise<unknown> {
    return this.request('DELETE', path, undefined, options);
  }

  // Auth methods
  private async refreshTokenRequest(): Promise<AccessTokenResponse | null> {
    try {
      const response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        return null;
      }

      return parseAccessTokenResponse(await response.json());
    } catch (error) {
      if (error instanceof ApiContractError) throw error;
      return null;
    }
  }

  public async login(email: string, password: string): Promise<AccessTokenResponse> {
    const data = parseAccessTokenResponse(await this.post('/auth/login', { email, password }));
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', data.access_token);
    }
    return data;
  }

  public async logout(): Promise<void> {
    try {
      await this.post('/auth/logout');
    } finally {
      clearSession();
    }
  }

  public async getMe(): Promise<User> {
    return parseUser(await this.get('/auth/me'));
  }

  public async healthz(): Promise<HealthResponse> {
    return parseHealth(await this.get('/healthz'));
  }

  public async readyz(): Promise<ReadyResponse> {
    return parseReady(await this.get('/readyz'));
  }
}

export const api = new ApiClient();
