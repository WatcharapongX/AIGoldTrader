import type { AccessTokenResponse, User, HealthResponse, ReadyResponse } from '@/types';
import { parseUser, parseHealth, parseReady, errorMessage } from '@/lib/contracts';
import {
  getTokenSnapshot,
  clearAccessToken,
  purgeLegacyAuthStorage,
} from '@/lib/auth-token-memory';
import { authCoordinator, AuthCoordinator } from '@/lib/auth-coordinator';

export function clearSession() {
  clearAccessToken();
  purgeLegacyAuthStorage();
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('auth:expired'));
  }
}

export class ApiClient {
  private baseUrl: string;
  private coordinator: AuthCoordinator;

  constructor(baseUrl?: string, coordinator?: AuthCoordinator) {
    this.baseUrl =
      baseUrl ||
      (typeof window !== 'undefined'
        ? '/api'
        : process.env.BACKEND_INTERNAL_URL || 'http://127.0.0.1:8000/api');
    this.coordinator =
      coordinator || (baseUrl ? new AuthCoordinator(this.baseUrl) : authCoordinator);
  }

  private async request(
    method: string,
    path: string,
    body?: unknown,
    options?: RequestInit,
  ): Promise<unknown> {
    const url = `${this.baseUrl}${path}`;
    const initialSnapshot = getTokenSnapshot();
    const headers = new Headers(options?.headers);
    headers.set('Content-Type', 'application/json');

    if (initialSnapshot.token) {
      headers.set('Authorization', `Bearer ${initialSnapshot.token}`);
    }

    const config: RequestInit = {
      credentials: 'same-origin',
      ...options,
      method,
      headers,
    };

    if (body !== undefined) {
      config.body = JSON.stringify(body);
    }

    let response = await fetch(url, config);

    // Bounded 401 retry:
    // Exclude /auth/login and /auth/refresh from refresh recursion.
    if (response.status === 401 && path !== '/auth/login' && path !== '/auth/refresh') {
      const currentSnapshot = getTokenSnapshot();
      let retryToken: string;

      if (
        currentSnapshot.generation !== initialSnapshot.generation &&
        currentSnapshot.token
      ) {
        // Generation already changed by another request/coordinator; retry once with new token
        retryToken = currentSnapshot.token;
      } else {
        // Generation unchanged: perform coordinated refresh
        try {
          retryToken = await this.coordinator.refreshAccessToken();
        } catch {
          clearSession();
          throw new Error('Session expired. Please sign in again.');
        }
      }

      headers.set('Authorization', `Bearer ${retryToken}`);
      response = await fetch(url, { ...config, headers });

      if (response.status === 401) {
        clearSession();
        throw new Error('Session expired. Please sign in again.');
      }
    }

    if (!response.ok) {
      let message: string | undefined;
      try {
        message = errorMessage(await response.json());
      } catch {
        /* Non-JSON error response. */
      }
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
  public async login(email: string, password: string): Promise<AccessTokenResponse> {
    return await this.coordinator.login(email, password);
  }

  public async logout(): Promise<void> {
    await this.coordinator.logout();
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
