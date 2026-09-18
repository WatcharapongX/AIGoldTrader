import type { User, AccessTokenResponse, HealthResponse, ReadyResponse } from '@/types';

export class ApiContractError extends Error {}

function invalid(): never {
  // Do not include the untrusted response body (which may contain tokens).
  throw new ApiContractError('Invalid API response contract');
}
function object(value: unknown): Record<string, unknown> {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) return invalid();
  return value as Record<string, unknown>;
}
function string(value: unknown): string {
  return typeof value === 'string' ? value : invalid();
}
function boolean(value: unknown): boolean {
  return typeof value === 'boolean' ? value : invalid();
}
function number(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : invalid();
}
export function parseUser(value: unknown): User {
  const data = object(value);
  const role = data.role;
  if (role !== 'ADMIN' && role !== 'TRADER' && role !== 'VIEWER') return invalid();
  return { id: string(data.id), email: string(data.email), role, is_active: boolean(data.is_active) };
}
function token(value: unknown): string {
  const result = string(value);
  return result.length > 0 && !/\s/u.test(result) ? result : invalid();
}
function expiryInstant(value: string): number {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  if (!match) return invalid();
  const [, year, month, day, hour, minute, second, fraction, zone] = match;
  const y = Number(year), m = Number(month), d = Number(day);
  const h = Number(hour), min = Number(minute), sec = Number(second);
  if (y < 1 || m < 1 || m > 12 || d < 1 || d > 31 || h > 23 || min > 59 || sec > 59) return invalid();
  const date = new Date(0);
  date.setUTCFullYear(y, m - 1, d);
  date.setUTCHours(h, min, sec, Number((fraction || '').padEnd(3, '0').slice(0, 3)));
  if (date.getUTCFullYear() !== y || date.getUTCMonth() !== m - 1 || date.getUTCDate() !== d) return invalid();
  const offsetHours = zone === 'Z' ? 0 : Number(zone.slice(1, 3));
  const offsetMinutes = zone === 'Z' ? 0 : Number(zone.slice(4, 6));
  if (offsetHours > 23 || offsetMinutes > 59) return invalid();
  const offset = (offsetHours * 60 + offsetMinutes) * (zone[0] === '-' ? -1 : 1);
  return date.getTime() - offset * 60_000;
}
export function parseAccessTokenResponse(value: unknown, now: number = Date.now()): AccessTokenResponse {
  const data = object(value);
  const expires_at = string(data.expires_at);
  if (data.token_type !== 'bearer' || expiryInstant(expires_at) <= now) return invalid();
  return {
    access_token: token(data.access_token),
    token_type: data.token_type,
    expires_at,
  };
}
export const parseTokenPair = parseAccessTokenResponse;
export function parseHealth(value: unknown): HealthResponse {
  const data = object(value);
  if (data.status !== 'ok') return invalid();
  return {
    status: data.status, app: string(data.app), env: string(data.env),
    trading_mode: string(data.trading_mode), live_auto_trading: boolean(data.live_auto_trading),
    uptime_seconds: number(data.uptime_seconds),
  };
}
export function parseReady(value: unknown): ReadyResponse {
  const data = object(value);
  if (data.status !== 'ready' && data.status !== 'not_ready') return invalid();
  const checks = object(data.checks);
  return {
    status: data.status, checks: {
      database: boolean(checks.database), redis: checks.redis === null ? null : boolean(checks.redis),
    }, redis_enabled: boolean(data.redis_enabled),
  };
}
export function errorMessage(value: unknown): string | undefined {
  if (typeof value !== 'object' || value === null || !('error' in value)) return undefined;
  const error = value.error;
  if (typeof error !== 'object' || error === null || !('message' in error)) return undefined;
  return typeof error.message === 'string' ? error.message : undefined;
}
