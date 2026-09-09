import canonical from './analysis-contract.generated.json';
import type { AnalysisSnapshot, AnalysisResponse, MultiTimeframeContext } from '@/types/analysis.generated';

type Schema = {
  $ref?: string; anyOf?: Schema[]; enum?: unknown[]; const?: unknown; type?: string;
  properties?: Record<string, Schema>; required?: string[]; additionalProperties?: boolean | Schema;
  items?: Schema; pattern?: string; format?: string; minLength?: number; maxLength?: number;
  minimum?: number; maximum?: number; exclusiveMinimum?: number; maxItems?: number;
};
const schemas: Record<string, Schema> = canonical.schemas;
export class AnalysisContractError extends Error {
  constructor() { super('Invalid analysis contract'); }
}
function fail(): never { throw new AnalysisContractError(); }
function validate(schema: Schema, value: unknown): void {
  if (schema.$ref) return validate(schemas[schema.$ref.split('/').pop()!], value);
  if (schema.anyOf) {
    for (const choice of schema.anyOf) { try { validate(choice, value); return; } catch {} }
    return fail();
  }
  if (schema.enum && !schema.enum.includes(value)) fail();
  if ('const' in schema && schema.const !== value) fail();
  switch (schema.type) {
    case 'null': if (value !== null) fail(); break;
    case 'boolean': if (typeof value !== 'boolean') fail(); break;
    case 'string':
      if (typeof value !== 'string') return fail();
      if (schema.minLength !== undefined && value.length < schema.minLength) fail();
      if (schema.maxLength !== undefined && value.length > schema.maxLength) fail();
      if (schema.pattern && !new RegExp(schema.pattern).test(value)) fail();
      if (schema.pattern?.includes('[0-9]') && !Number.isFinite(Number(value))) fail();
      if (schema.format === 'date-time') instant(value);
      break;
    case 'integer':
    case 'number':
      if (typeof value !== 'number' || !Number.isFinite(value)) return fail();
      if (schema.type === 'integer' && !Number.isInteger(value)) fail();
      if (schema.minimum !== undefined && value < schema.minimum) fail();
      if (schema.maximum !== undefined && value > schema.maximum) fail();
      if (schema.exclusiveMinimum !== undefined && value <= schema.exclusiveMinimum) fail();
      break;
    case 'array':
      if (!Array.isArray(value) || value.length > (schema.maxItems ?? 1000)) return fail();
      for (const item of value) validate(schema.items!, item);
      break;
    case 'object':
      if (!value || typeof value !== 'object' || Array.isArray(value)) return fail();
      const object = value as Record<string, unknown>;
      for (const key of schema.required || []) if (!(key in object)) fail();
      for (const [key, item] of Object.entries(object)) {
        const child = schema.properties?.[key];
        if (child) validate(child, item);
        else if (schema.additionalProperties === false) fail();
        else if (typeof schema.additionalProperties === 'object') validate(schema.additionalProperties, item);
      }
  }
}
export function instant(value: string): number {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/.test(value)) return fail();
  const time = Date.parse(value);
  if (!Number.isFinite(time) || new Date(time).toISOString().slice(0, 19) !== value.slice(0, 19)) return fail();
  return time;
}
function finite(value: string): number {
  if (!/^-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?$/.test(value) || !Number.isFinite(Number(value))) return fail();
  return Number(value);
}
function history(value: AnalysisSnapshot['history']) {
  if (value.requested < 1 || value.requested > 1000 || value.returned < 0 || value.returned > value.requested ||
      value.closed < 0 || value.closed > value.returned ||
      value.status !== (value.returned === 0 ? 'EMPTY' : value.returned < value.requested ? 'PARTIAL' : 'COMPLETE')) fail();
}
export function parseAnalysis(value: unknown): AnalysisResponse {
  validate(schemas.AnalysisResponse, value);
  const result = value as AnalysisResponse;
  history(result.history);
  if (instant(result.generated_at) > instant(result.served_at) || result.cache_age_seconds < 0) fail();
  const end = result.as_of === null ? -Infinity : instant(result.as_of);
  const ids = new Set<string>();
  const confirmed = (id: string, origin: string, at: string) => {
    if (ids.has(id) || instant(origin) > instant(at) || instant(at) > end) fail();
    ids.add(id);
  };
  for (const swing of result.swings) { finite(swing.price); confirmed(swing.id, swing.swing_time, swing.confirmed_at); }
  for (const event of result.events) { finite(event.price); confirmed(event.id, event.occurred_at, event.confirmed_at); }
  for (const level of result.liquidity) {
    finite(level.price); confirmed(level.id, level.created_at, level.confirmed_at);
    if (level.ended_at && (instant(level.ended_at) < instant(level.confirmed_at) || instant(level.ended_at) > end)) fail();
  }
  for (const zone of result.zones) {
    confirmed(zone.id, zone.occurred_at, zone.confirmed_at);
    if (finite(zone.lower_bound) >= finite(zone.upper_bound) || finite(zone.fill_fraction ?? '0') < 0 ||
        finite(zone.fill_fraction ?? '0') > 1) fail();
    if (zone.ended_at && (instant(zone.ended_at) < instant(zone.confirmed_at) || instant(zone.ended_at) > end)) fail();
  }
  for (const item of Object.values(result.indicators)) if (item.value !== null) finite(item.value);
  if (result.dealing_range) {
    const r = result.dealing_range;
    if (!(finite(r.lower_bound) < finite(r.equilibrium) && finite(r.equilibrium) < finite(r.upper_bound)) ||
        instant(r.confirmed_at) > end || instant(r.origin_time) > instant(r.confirmed_at)) fail();
  }
  return result;
}
export function parseContext(value: unknown): MultiTimeframeContext {
  validate(schemas.MultiTimeframeContext, value);
  const result = value as MultiTimeframeContext;
  if (result.timeframes.length !== 9 || new Set(result.timeframes.map(row => row.timeframe)).size !== 9) fail();
  for (const row of result.timeframes) history(row.history);
  return result;
}
