import { TokenPair, User, HealthResponse, ApiError } from '@/types';

/** Sync token to a cookie so Next.js middleware can check auth state. */
function syncTokenCookie(token: string | null) {
  if (typeof document === 'undefined') return;
  if (token) {
    document.cookie = `access_token=${token}; path=/; SameSite=Strict; max-age=86400`;
  } else {
    document.cookie = 'access_token=; path=/; SameSite=Strict; max-age=0';
  }
}

export function clearSession() {
  if (typeof window === 'undefined') return;
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
  syncTokenCookie(null);
  window.dispatchEvent(new Event('auth:expired'));
}

export class ApiClient {
  private baseUrl: string;
  private refreshPromise: Promise<string> | null = null;

  constructor(baseUrl?: string) {
    this.baseUrl = baseUrl || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api';
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
        localStorage.setItem('refresh_token', tokens.refresh_token);
        syncTokenCookie(tokens.access_token);
        return tokens.access_token;
      })().finally(() => { this.refreshPromise = null; });
    }
    return this.refreshPromise;
  }

  private async request<T>(method: string, path: string, body?: unknown, options?: RequestInit): Promise<T> {
    const url = `${this.baseUrl}${path}`;
    const accessToken = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    const headers = new Headers(options?.headers);
    headers.set('Content-Type', 'application/json');
    if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`);
    const config: RequestInit = { ...options, method, headers };
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
      let errorData: ApiError | undefined;
      try { errorData = await response.json() as ApiError; } catch { /* Non-JSON error response. */ }
      throw new Error(errorData?.error?.message || response.statusText || 'An API error occurred');
    }
    if (response.status === 204) return {} as T;
    return await response.json() as T;
  }

  public get<T>(path: string, options?: RequestInit): Promise<T> {
    return this.request<T>('GET', path, undefined, options);
  }

  public post<T>(path: string, body?: unknown, options?: RequestInit): Promise<T> {
    return this.request<T>('POST', path, body, options);
  }

  public put<T>(path: string, body?: unknown, options?: RequestInit): Promise<T> {
    return this.request<T>('PUT', path, body, options);
  }

  public patch<T>(path: string, body?: unknown, options?: RequestInit): Promise<T> {
    return this.request<T>('PATCH', path, body, options);
  }

  public delete<T>(path: string, options?: RequestInit): Promise<T> {
    return this.request<T>('DELETE', path, undefined, options);
  }

  // Auth methods
  private async refreshTokenRequest(): Promise<TokenPair | null> {
    const refreshToken = typeof window !== 'undefined' ? localStorage.getItem('refresh_token') : null;
    if (!refreshToken) return null;

    try {
      const response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        return null;
      }

      return await response.json() as TokenPair;
    } catch {
      return null;
    }
  }

  public async login(email: string, password: string): Promise<TokenPair> {
    const data = await this.post<TokenPair>('/auth/login', { email, password });
    if (typeof window !== 'undefined') {
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
      syncTokenCookie(data.access_token);
    }
    return data;
  }

  public async logout(): Promise<void> {
     await this.post('/auth/logout');
  }

  public getMe(): Promise<User> {
    return this.get<User>('/auth/me');
  }

  public healthz(): Promise<HealthResponse> {
    return this.get<HealthResponse>('/healthz');
  }

  public readyz(): Promise<HealthResponse> {
    return this.get<HealthResponse>('/readyz');
  }
}

export const api = new ApiClient();
