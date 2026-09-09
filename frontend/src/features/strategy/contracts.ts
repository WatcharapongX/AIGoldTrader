import canonical from './strategy-contract.generated.json';
import type { StrategyResponse } from '@/types/strategy.generated';
import { parseAnalysis } from '@/features/analysis/contracts';
import { parseNews } from '@/features/news/contracts';
type Schema = {
  $ref?: string; anyOf?: Schema[]; enum?: unknown[]; const?: unknown; type?: string;
  properties?: Record<string, Schema>; required?: string[]; additionalProperties?: boolean | Schema;
  items?: Schema; pattern?: string; format?: string; minLength?: number; maxLength?: number;
  minimum?: number; maximum?: number; exclusiveMinimum?: number; maxItems?: number;
};
const schemas: Record<string, Schema> = canonical.schemas;
export class StrategyContractError extends Error {
  constructor() { super('Invalid strategy contract'); }
}
function fail(): never { throw new StrategyContractError(); }
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
      if (schema.pattern && (schema.pattern.includes('[0-9]') || schema.pattern.includes('\\d')) && !Number.isFinite(Number(value))) fail();
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

export function parseStrategy(value: unknown): StrategyResponse {
  validate(schemas.StrategyResponse, value);
  const data = value as StrategyResponse, ev = data.evaluation, ctx = ev.context;
  if (ev.identity_version === 'evaluation-2.0.0') {
    const refs = ev.component_ids ?? {};
    if (!['REQUEST','STRATEGY','EMPTY'].includes(ev.scope ?? '') ||
        Object.keys(refs).length !== ev.candidates.length ||
        new Set(Object.values(refs)).size !== ev.candidates.length ||
        ev.candidates.some(c=>!refs[c.id])) fail();
    if (ev.scope === 'STRATEGY' && (ev.candidates.length !== 1 || ev.profiles.length !== 1 ||
        ev.strategies.length !== 1 || refs[ev.candidates[0].id] !== ev.id)) fail();
    if (ev.scope === 'EMPTY' && ev.candidates.length !== 0) fail();
    if (ctx.news_json === null && ev.scope === 'REQUEST') fail();
    if (ev.scope === 'STRATEGY' && !['STRAT05','STRAT06'].includes(ev.candidates[0].strategy_id) &&
        (ctx.news_json !== null || ctx.id !== ctx.market_context_id)) fail();
  }
  const at = instant(ctx.as_of), generated = instant(data.generated_at), served = instant(data.served_at);
  if (generated > served || at > served || ctx.execution !== 'ANALYSIS_ONLY') fail();
  const frames = new Set<string>(), candidates = new Set<string>(), profiles = new Set(ev.profiles.map(p => p.id));
  if (profiles.size !== ev.profiles.length) fail();
  const news = ctx.news_json === null ? null : parseNews({...JSON.parse(ctx.news_json), generated_at:data.generated_at,
    served_at:data.served_at, cache_age_seconds:0});
  if (news && (news.fingerprint !== ctx.news_fingerprint || instant(news.as_of) > at)) fail();
  if (!news && ctx.news_fingerprint !== null) fail();
  for (const f of ctx.frames) {
    if (frames.has(f.timeframe) || f.as_of && instant(f.as_of) > at) fail();
    frames.add(f.timeframe);
    const a = parseAnalysis({...JSON.parse(f.analysis_json), generated_at:data.generated_at,
      served_at:data.served_at, cache_age_seconds:0});
    if (a.input_id !== f.input_id || a.source !== ctx.source || a.symbol !== ctx.symbol || a.timeframe !== f.timeframe) fail();
    for (const indicator of f.indicators) if (indicator.value !== null && !Number.isFinite(Number(indicator.value))) fail();
    for (const p of f.patterns) {
      if (p.confirmed_at && instant(p.confirmed_at) > at || instant(p.detected_at) > at) fail();
      if (p.status === 'CONFIRMED' && !p.confirmed_at) fail();
      for (const pivot of p.points) if (instant(pivot.confirmed_at) > at) fail();
    }
  }
  for (const level of ctx.key_levels) {
    if (!Number.isFinite(Number(level.price)) || level.confirmed_at && instant(level.confirmed_at) > at) fail();
    if (level.status === 'CONFIRMED' && !level.confirmed_at) fail();
  }
  for (const c of ev.candidates) {
    const needsNews = ['STRAT05', 'STRAT06'].includes(c.strategy_id);
    const dependencyId = needsNews ? ctx.id : ctx.market_context_id;
    if (needsNews && !news) fail();
    if (candidates.has(c.id) || !profiles.has(c.profile_id) || c.context_id !== dependencyId ||
        instant(c.detected_at) > at || c.confirmed_at && instant(c.confirmed_at) > at) fail();
    candidates.add(c.id);
    if (!needsNews && (c.news_provenance || c.evidence.some(e=>e.code==='NEWS'))) fail();
    if (c.news_provenance) {
      const provenance=c.news_provenance;
      if (provenance.context_fingerprint!==ctx.news_fingerprint || provenance.source!==news?.source ||
          instant(provenance.as_of)>at) fail();
      for (const e of provenance.event_vintages) {
        if (e.source!==news?.source || instant(e.available_at)>at ||
            e.actual!==null && (!e.released_at || instant(e.released_at)>at)) fail();
      }
    }
    if (c.status === 'READY' && (!c.plan || c.direction === 'NO_TRADE' || c.conflicts.length ||
        c.missing_conditions.length || instant(c.expires_at) <= at)) fail();
    if (needsNews && ctx.mode === 'ACTUAL' && news?.source_mode !== 'LIVE' && c.status === 'READY') fail();
    if (c.plan) {
      const p=c.plan, low=Number(p.entry_lower), high=Number(p.entry_upper), stop=Number(p.stop_loss);
      if (p.candidate_id !== c.id || p.context_id !== c.context_id || p.direction !== c.direction ||
          ![low,high,stop].every(Number.isFinite) || low > high || stop <= 0 || p.targets.length < 2 ||
          !(p.direction === 'LONG' ? stop < low : stop > high)) fail();
      for (const t of p.targets) if (!(p.direction === 'LONG' ? Number(t.price) > high : Number(t.price) < low) ||
          !Number.isFinite(Number(t.rr)) || Number(t.rr) <= 0) fail();
    }
  }
  return data;
}
