import canonical from './dashboard-contract.generated.json';
import type { DashboardSummary } from '@/types/dashboard.generated';
import { parseNews } from '../news/contracts';

type Schema = {
  $ref?: string; anyOf?: Schema[]; enum?: unknown[]; const?: unknown; type?: string;
  properties?: Record<string, Schema>; required?: string[]; additionalProperties?: boolean | Schema;
  items?: Schema; pattern?: string; format?: string; minLength?: number; maxLength?: number;
  minimum?: number; maximum?: number; exclusiveMinimum?: number; maxItems?: number;
};
const schemas: Record<string, Schema> = canonical.schemas;
export class DashboardContractError extends Error {
  constructor() { super('Invalid dashboard contract'); }
}
function fail(): never { throw new DashboardContractError(); }
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
export function parseDashboard(value: unknown): DashboardSummary {
  validate(schemas.DashboardSummary, value);
  const d = value as DashboardSummary;
  const served = instant(d.served_at);
  if (instant(d.generated_at) > served || d.trading_mode !== 'PAPER' || d.live_auto_trading) fail();
  if (d.news) parseNews(d.news);
  const eventIds = new Set<string>();
  for (const e of d.calendar_events) {
    if (eventIds.has(e.id) || e.source !== d.news_provider?.source || e.source_mode !== d.news_provider?.source_mode ||
      instant(e.available_at) > served || instant(e.updated_at) > instant(e.available_at)) fail();
    if (e.actual !== null && (!e.released_at || instant(e.scheduled_at) > instant(e.released_at) ||
      instant(e.released_at) > instant(e.available_at) || ['SCHEDULED','CANCELLED','DELAYED'].includes(e.status))) fail();
    eventIds.add(e.id);
  }
  for (const row of d.structure) if (row.as_of && instant(row.as_of) > served ||
    row.latest_event && (!row.as_of || instant(row.latest_event.confirmed_at) > instant(row.as_of))) fail();
  for (const c of d.candidates) {
    if (c.context_id !== (['STRAT05','STRAT06'].includes(c.strategy_id) ? d.strategy_context_id : d.strategy_market_context_id) || !d.profiles.some(p => p.id === c.profile_id) ||
      !d.strategies.some(s => s.id === c.strategy_id) || instant(c.detected_at) > served) fail();
    if (c.status === 'READY' && (!c.plan || c.plan.candidate_id !== c.id)) fail();
  }
  for (const rows of [d.candidates,d.profiles,d.strategies]) {
    if (new Set(rows.map(r=>r.id)).size!==rows.length) fail();
  }
  if (d.strategy_as_of && instant(d.strategy_as_of)>served ||
      d.strategy_generated_at && instant(d.strategy_generated_at)>served) fail();
  const plan = d.current_plan;
  if (plan) {
    const c = d.candidates.find(c => c.id === plan.candidate_id);
    if ((c && ['STRAT05','STRAT06'].includes(c.strategy_id) && !d.news_provider?.calendar_usable_for_trading) || !c || c.status !== 'READY' || d.strategy_stale || plan.context_id !== c.context_id ||
      JSON.stringify(c.plan) !== JSON.stringify(plan) || instant(plan.expires_at) <= served) fail();
    const low = Number(plan.entry_lower), high = Number(plan.entry_upper), sl = Number(plan.stop_loss);
    if (!(0 < low && low <= high && sl > 0) ||
      !(plan.direction === 'LONG' ? sl < low : sl > high) || plan.targets.length < 2) fail();
    let last = plan.direction === 'LONG' ? high : low;
    for (const target of plan.targets) {
      const price = Number(target.price);
      if (Number(target.rr) <= 0 || !(plan.direction === 'LONG' ? price > last : price > 0 && price < last)) fail();
      last = price;
    }
  }
  return d;
}
