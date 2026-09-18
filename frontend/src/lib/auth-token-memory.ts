/**
 * In-memory volatile access token management for Batch B3.
 *
 * Tokens reside strictly in JavaScript memory for the current document lifetime.
 * Access tokens are NEVER persisted in localStorage, sessionStorage, IndexedDB,
 * Cache Storage, JavaScript cookies, or query strings.
 */

export interface TokenSnapshot {
  token: string | null;
  expiresAt: number | null;
  generation: number;
  sessionEpoch: number;
}

let currentAccessToken: string | null = null;
let currentExpiresAt: number | null = null;
let tokenGeneration = 0;
let sessionEpoch = 0;

export function setAccessToken(token: string, expiresAtIso: string): void {
  currentAccessToken = token;
  const parsed = Date.parse(expiresAtIso);
  currentExpiresAt = Number.isNaN(parsed) ? null : parsed;
  tokenGeneration++;
}

export function getAccessToken(): string | null {
  return currentAccessToken;
}

export function getTokenSnapshot(): TokenSnapshot {
  return {
    token: currentAccessToken,
    expiresAt: currentExpiresAt,
    generation: tokenGeneration,
    sessionEpoch,
  };
}

export function clearAccessToken(): void {
  currentAccessToken = null;
  currentExpiresAt = null;
  tokenGeneration++;
}

export function isAccessTokenUsable(skewSeconds = 15): boolean {
  if (!currentAccessToken) return false;
  if (currentExpiresAt === null) return true;
  return Date.now() < currentExpiresAt - skewSeconds * 1000;
}

export function advanceSessionEpoch(): number {
  return ++sessionEpoch;
}

export function getSessionEpoch(): number {
  return sessionEpoch;
}

export function purgeLegacyAuthStorage(): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  } catch {
    // Ignore storage access errors
  }
  try {
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
  } catch {
    // Ignore storage access errors
  }
}
