import canonical from './news-contract.generated.json';
import type { CalendarPage, EconomicEvent, EventDetail, NewsResponse, ProviderHealth } from '@/types/news.generated';

type Schema = {
  $ref?: string; anyOf?: Schema[]; enum?: unknown[]; const?: unknown; type?: string;
  properties?: Record<string, Schema>; required?: string[]; additionalProperties?: boolean | Schema;
  items?: Schema; pattern?: string; format?: string; minLength?: number; maxLength?: number;
  minimum?: number; maximum?: number; exclusiveMinimum?: number; maxItems?: number;
};
const schemas: Record<string, Schema> = canonical.schemas;
export class NewsContractError extends Error {
  constructor() { super('Invalid news contract'); }
}
function fail(): never { throw new NewsContractError(); }
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
function eventAt(e: EconomicEvent, at: number) {
  if (instant(e.available_at) > at || instant(e.updated_at) > instant(e.available_at)) fail();
  if (e.actual !== null && (!e.released_at || instant(e.released_at) > instant(e.available_at) ||
      instant(e.released_at) < instant(e.scheduled_at) ||
      ['SCHEDULED', 'UPCOMING', 'DELAYED', 'CANCELLED'].includes(e.status))) fail();
}
export function parseNews(value: unknown): NewsResponse {
  validate(schemas.NewsResponse, value);
  const data = value as NewsResponse, at = instant(data.as_of);
  if (instant(data.generated_at) > instant(data.served_at) || data.cache_age_seconds < 0 ||
      data.market_as_of && instant(data.market_as_of) > at ||
      data.structure_confirmation.upstream_as_of && instant(data.structure_confirmation.upstream_as_of) > at) fail();
  const ids = new Set<string>();
  for (const event of data.events) {
    eventAt(event, at); if (ids.has(event.id) || event.source !== data.source || event.source_mode !== data.source_mode) fail();
    ids.add(event.id);
  }
  for (const e of data.upcoming_events) { eventAt(e, at); if (!ids.has(e.id) || instant(e.scheduled_at) <= at) fail(); }
  for (const window of data.reaction_windows) if (window.status === 'READY' && instant(window.cutoff) > at) fail();
  return data;
}
export function parseCalendar(value: unknown): CalendarPage {
  validate(schemas.CalendarPage, value);
  const data = value as CalendarPage;
  const ids = new Set<string>();
  for (const event of data.events) {
    eventAt(event, instant(data.as_of));
    if (ids.has(event.id) || event.source !== data.source || event.source_mode !== data.source_mode) fail();
    ids.add(event.id);
  }
  return data;
}
export function parseEvent(value: unknown): EventDetail {
  validate(schemas.EventDetail, value);
  const data = value as EventDetail;
  eventAt(data.event, instant(data.as_of));
  let version = 0;
  for (const e of data.revisions) {
    eventAt(e, instant(data.as_of));
    if (e.id !== data.event.id || e.revision_version <= version) fail();
    version = e.revision_version;
  }
  if (version !== data.event.revision_version) fail();
  return data;
}

export function parseProviderHealth(value: unknown): ProviderHealth {
 validate(schemas.ProviderHealth,value); return value as ProviderHealth;
}
