import type { AccessTokenResponse, User } from '@/types';
import { parseAccessTokenResponse, parseUser, ApiContractError } from '@/lib/contracts';
import {
  setAccessToken,
  getAccessToken,
  clearAccessToken,
  isAccessTokenUsable,
  advanceSessionEpoch,
  getSessionEpoch,
  purgeLegacyAuthStorage,
} from '@/lib/auth-token-memory';

export type AuthStatus =
  | 'idle'
  | 'bootstrapping'
  | 'authenticated'
  | 'refreshing'
  | 'logging_out'
  | 'unauthenticated';

export interface AuthCoordinatorState {
  user: User | null;
  status: AuthStatus;
  error: string | null;
}

type AuthStateListener = (state: AuthCoordinatorState) => void;

interface BroadcastEvent {
  type:
    | 'refresh-started'
    | 'refresh-completed'
    | 'refresh-failed'
    | 'session-changed'
    | 'logout'
    | 'session-expired';
}

const BROADCAST_CHANNEL_NAME = 'aigold-auth';
const AUTH_MUTATION_LOCK = 'aigold-auth-mutation';

export class AuthCoordinator {
  private baseUrl: string;
  private state: AuthCoordinatorState = {
    user: null,
    status: 'idle',
    error: null,
  };
  private listeners: Set<AuthStateListener> = new Set();
  private channel: BroadcastChannel | null = null;
  private inFlightRefresh: Promise<string> | null = null;
  private bootstrapPromise: Promise<boolean> | null = null;
  private remoteRefreshing = false;
  private remoteRefreshWaiters: Array<{
    resolve: () => void;
    reject: (err: Error) => void;
  }> = [];

  constructor(baseUrl?: string) {
    this.baseUrl =
      baseUrl ||
      (typeof window !== 'undefined'
        ? '/api'
        : process.env.BACKEND_INTERNAL_URL || 'http://127.0.0.1:8000/api');

    if (typeof window !== 'undefined' && 'BroadcastChannel' in window) {
      try {
        this.channel = new BroadcastChannel(BROADCAST_CHANNEL_NAME);
        this.channel.onmessage = this.handleBroadcastMessage.bind(this);
      } catch {
        this.channel = null;
      }
    }
  }

  public subscribe(listener: AuthStateListener): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => {
      this.listeners.delete(listener);
    };
  }

  public getState(): AuthCoordinatorState {
    return this.state;
  }

  private updateState(partial: Partial<AuthCoordinatorState>): void {
    this.state = { ...this.state, ...partial };
    for (const listener of this.listeners) {
      listener(this.state);
    }
  }

  private broadcast(event: BroadcastEvent): void {
    if (this.channel) {
      try {
        this.channel.postMessage(event);
      } catch {
        // Ignore channel communication errors
      }
    }
  }

  private handleBroadcastMessage(event: MessageEvent<BroadcastEvent>): void {
    const data = event.data;
    if (!data || !data.type) return;

    switch (data.type) {
      case 'refresh-started':
        this.remoteRefreshing = true;
        break;

      case 'refresh-completed':
        this.remoteRefreshing = false;
        this.notifyRemoteWaiters(true);
        break;

      case 'refresh-failed':
        this.remoteRefreshing = false;
        this.notifyRemoteWaiters(false);
        break;

      case 'logout':
      case 'session-expired':
        advanceSessionEpoch();
        clearAccessToken();
        purgeLegacyAuthStorage();
        this.updateState({
          user: null,
          status: 'unauthenticated',
          error: null,
        });
        if (typeof window !== 'undefined') {
          window.dispatchEvent(new Event('auth:expired'));
        }
        break;

      case 'session-changed':
        // Another tab logged in: clear local tokens and bootstrap into the new shared session
        advanceSessionEpoch();
        clearAccessToken();
        purgeLegacyAuthStorage();
        this.updateState({
          user: null,
          status: 'bootstrapping',
          error: null,
        });
        void this.bootstrap({ force: true });
        break;
    }
  }

  private notifyRemoteWaiters(success: boolean): void {
    const waiters = [...this.remoteRefreshWaiters];
    this.remoteRefreshWaiters = [];
    for (const waiter of waiters) {
      if (success) {
        waiter.resolve();
      } else {
        waiter.reject(new Error('Remote refresh failed'));
      }
    }
  }

  private async waitForRemoteRefresh(timeoutMs = 3000): Promise<void> {
    if (!this.remoteRefreshing) return;
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.remoteRefreshWaiters = this.remoteRefreshWaiters.filter(
          (w) => w.resolve !== resolve,
        );
        resolve();
      }, timeoutMs);

      this.remoteRefreshWaiters.push({
        resolve: () => {
          clearTimeout(timer);
          resolve();
        },
        reject: (err) => {
          clearTimeout(timer);
          reject(err);
        },
      });
    });
  }

  private async withAuthLock<T>(action: () => Promise<T>): Promise<T> {
    if (
      typeof navigator !== 'undefined' &&
      'locks' in navigator &&
      typeof navigator.locks?.request === 'function'
    ) {
      return await navigator.locks.request(AUTH_MUTATION_LOCK, action);
    }
    return await action();
  }

  /**
   * Bootstrap application authentication at initialization.
   * Executes at most once per page lifecycle unless forced.
   */
  public async bootstrap(options?: { force?: boolean }): Promise<boolean> {
    if (this.bootstrapPromise && !options?.force) {
      return this.bootstrapPromise;
    }

    this.bootstrapPromise = (async () => {
      this.updateState({ status: 'bootstrapping', error: null });
      purgeLegacyAuthStorage();

      const epoch = advanceSessionEpoch();
      try {
        const tokenResponse = await this.executeRefreshRequest();
        if (!tokenResponse) {
          if (getSessionEpoch() === epoch) {
            clearAccessToken();
            this.updateState({
              user: null,
              status: 'unauthenticated',
              error: null,
            });
          }
          return false;
        }

        if (getSessionEpoch() !== epoch) {
          return false;
        }

        setAccessToken(tokenResponse.access_token, tokenResponse.expires_at);

        const user = await this.executeMeRequest(tokenResponse.access_token);
        if (getSessionEpoch() !== epoch) {
          return false;
        }

        this.updateState({
          user,
          status: 'authenticated',
          error: null,
        });
        return true;
      } catch (error) {
        if (getSessionEpoch() === epoch) {
          clearAccessToken();
          this.updateState({
            user: null,
            status: 'unauthenticated',
            error: error instanceof Error ? error.message : 'Authentication failed',
          });
        }
        return false;
      }
    })();

    return this.bootstrapPromise;
  }

  /**
   * Coordinate refresh token rotation across tabs and in-tab callers.
   */
  public async refreshAccessToken(): Promise<string> {
    if (this.inFlightRefresh) {
      return this.inFlightRefresh;
    }

    this.inFlightRefresh = (async () => {
      const startEpoch = getSessionEpoch();
      this.updateState({ status: 'refreshing' });

      try {
        const token = await this.withAuthLock(async () => {
          if (getSessionEpoch() !== startEpoch) {
            throw new Error('Session invalidated during refresh wait');
          }

          // Broadcast refresh started to advise other tabs without Web Locks
          this.broadcast({ type: 'refresh-started' });

          let response = await this.executeRefreshRequest();

          // Fallback race recovery if Web Locks were unavailable:
          // If we received a 401, another tab may have won the cookie race.
          // Wait briefly for its completion and retry refresh ONCE.
          if (!response && !('locks' in (typeof navigator !== 'undefined' ? navigator : {}))) {
            await this.waitForRemoteRefresh(2000).catch(() => {});
            if (getSessionEpoch() === startEpoch) {
              response = await this.executeRefreshRequest();
            }
          }

          if (!response) {
            this.broadcast({ type: 'refresh-failed' });
            throw new Error('Session expired. Please sign in again.');
          }

          if (getSessionEpoch() !== startEpoch) {
            throw new Error('Session invalidated during refresh');
          }

          setAccessToken(response.access_token, response.expires_at);
          this.broadcast({ type: 'refresh-completed' });
          return response.access_token;
        });

        if (getSessionEpoch() === startEpoch) {
          this.updateState({ status: 'authenticated', error: null });
        }
        return token;
      } catch (error) {
        if (getSessionEpoch() === startEpoch) {
          clearAccessToken();
          purgeLegacyAuthStorage();
          this.updateState({
            user: null,
            status: 'unauthenticated',
            error: error instanceof Error ? error.message : 'Session expired',
          });
          if (typeof window !== 'undefined') {
            window.dispatchEvent(new Event('auth:expired'));
          }
        }
        throw error;
      } finally {
        this.inFlightRefresh = null;
      }
    })();

    return this.inFlightRefresh;
  }

  /**
   * Authenticate user with credentials, store access token in memory,
   * fetch user profile, and broadcast session-changed event.
   */
  public async login(email: string, password: string): Promise<AccessTokenResponse> {
    return await this.withAuthLock(async () => {
      const epoch = advanceSessionEpoch();
      this.updateState({ status: 'bootstrapping', error: null });
      purgeLegacyAuthStorage();

      const response = await fetch(`${this.baseUrl}/auth/login`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password }),
      });

      if (!response.ok) {
        let message = 'Login failed';
        try {
          const errData = await response.json();
          message = errData.detail || message;
        } catch {
          // ignore non-json error
        }
        this.updateState({ status: 'unauthenticated', error: message });
        throw new Error(message);
      }

      const tokenData = parseAccessTokenResponse(await response.json());
      if (getSessionEpoch() !== epoch) {
        throw new Error('Login aborted: session changed');
      }

      setAccessToken(tokenData.access_token, tokenData.expires_at);

      const user = await this.executeMeRequest(tokenData.access_token);
      if (getSessionEpoch() !== epoch) {
        throw new Error('Login aborted: session changed');
      }

      this.updateState({
        user,
        status: 'authenticated',
        error: null,
      });

      // Broadcast to other tabs that login occurred so they can synchronize
      this.broadcast({ type: 'session-changed' });
      return tokenData;
    });
  }

  /**
   * Authenticated logout: calls backend logout endpoint with memory token and cookie,
   * clears memory tokens, purges legacy storage, and broadcasts logout to other tabs.
   */
  public async logout(): Promise<void> {
    const token = getAccessToken();
    advanceSessionEpoch();
    clearAccessToken();
    purgeLegacyAuthStorage();
    this.updateState({
      user: null,
      status: 'unauthenticated',
      error: null,
    });
    this.broadcast({ type: 'logout' });
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('auth:expired'));
    }

    try {
      await this.withAuthLock(async () => {
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        };
        if (token) {
          headers.Authorization = `Bearer ${token}`;
        }
        await fetch(`${this.baseUrl}/auth/logout`, {
          method: 'POST',
          credentials: 'same-origin',
          headers,
        }).catch(() => {});
      });
    } catch {
      // Ignore network/lock failures on logout
    }
  }

  /**
   * Token supplier for WebSocket transports and API requests.
   * Proactively checks validity against proactive clock skew.
   */
  public async getValidAccessToken(options?: { forceRefresh?: boolean }): Promise<string> {
    if (!options?.forceRefresh && isAccessTokenUsable(15)) {
      const token = getAccessToken();
      if (token) return token;
    }
    return await this.refreshAccessToken();
  }

  public async fetchMe(): Promise<User> {
    const token = await this.getValidAccessToken();
    const user = await this.executeMeRequest(token);
    this.updateState({ user, status: 'authenticated' });
    return user;
  }

  public clearSession(): void {
    advanceSessionEpoch();
    clearAccessToken();
    purgeLegacyAuthStorage();
    this.updateState({
      user: null,
      status: 'unauthenticated',
      error: null,
    });
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new Event('auth:expired'));
    }
  }

  private async executeRefreshRequest(): Promise<AccessTokenResponse | null> {
    try {
      const response = await fetch(`${this.baseUrl}/auth/refresh`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
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

  private async executeMeRequest(accessToken: string): Promise<User> {
    const response = await fetch(`${this.baseUrl}/auth/me`, {
      method: 'GET',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch user profile: ${response.status}`);
    }

    return parseUser(await response.json());
  }
}

export const authCoordinator = new AuthCoordinator();
export const getValidAccessToken = (options?: { forceRefresh?: boolean }) =>
  authCoordinator.getValidAccessToken(options);
