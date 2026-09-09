import canonical from './market-contract.generated.json';
import type { Candle, CandlePage, MarketMessage, MarketDataStatus, Quote, SymbolInfo, Timeframe } from '@/types/market.generated';

type Schema = {
  $ref?: string; anyOf?: Schema[]; enum?: unknown[]; const?: unknown; type?: string;
  properties?: Record<string, Schema>; required?: string[]; additionalProperties?: boolean | Schema;
  items?: Schema; pattern?: string; format?: string; minLength?: number; maxLength?: number;
  minimum?: number; maximum?: number; exclusiveMinimum?: number;
};
const schemas: Record<string, Schema> = canonical.schemas;
export const timeframes = canonical.timeframes as Timeframe[];
export class MarketContractError extends Error {
  constructor() { super('Invalid market data contract'); }
}
function fail(): never { throw new MarketContractError(); }
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
      if (!Array.isArray(value) || value.length > 1000) return fail();
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
function decimal(value: string): bigint {
  if (!/^\d+(?:\.\d{1,5})?$/.test(value)) return fail();
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole) * BigInt(100000) + BigInt(fraction.padEnd(5, '0'));
}
const seconds: Record<Timeframe, number> = { M1: 60, M3: 180, M5: 300, M15: 900, M30: 1800, H1: 3600, H4: 14400, D1: 86400, W1: 604800 };
function candle(value: Candle) {
  decimal(value.volume);
  const o = decimal(value.open), h = decimal(value.high), l = decimal(value.low), c = decimal(value.close);
  if (l <= BigInt(0) || h < o || h < c || h < l || l > o || l > c || (value.ask_close !== null && decimal(value.ask_close) < decimal(value.bid_close))) fail();
  const t = instant(value.open_time) / 1000, offset = value.timeframe === 'W1' ? 345600 : 0;
  if ((t - offset) % seconds[value.timeframe] !== 0) fail();
}
function quote(value: Quote) {
  const expected = value.source === 'simulated' ? 'SIMULATED' : value.source.split('_')[1].toUpperCase();
  if ((value.mode ?? 'SIMULATED') !== expected) fail();
  decimal(value.volume);
  const bid = decimal(value.bid), ask = decimal(value.ask);
  if (bid <= BigInt(0) || ask < bid || decimal(value.spread) !== ask - bid) fail();
}
export function parseSymbols(value: unknown): SymbolInfo[] {
  if (!Array.isArray(value) || value.length > 1000) return fail();
  for (const item of value) validate(schemas.SymbolInfo, item);
  return value;
}
export function parseStatus(value: unknown): MarketDataStatus {
  validate(schemas.MarketDataStatus, value);
  const status = value as MarketDataStatus;
  if (status.source === 'simulated' ? status.mode !== 'SIMULATED' :
      !['UNCONFIRMED', status.source.split('_')[1]?.toUpperCase()].includes(status.mode)) fail();
  return status;
}
export function parseCandles(value: unknown): CandlePage {
  validate(schemas.CandlePage, value);
  const page = value as CandlePage;
  let last = -Infinity;
  for (const item of page.candles) {
    candle(item);
    if (item.source !== page.candles[0].source || item.symbol !== page.candles[0].symbol ||
        item.timeframe !== page.candles[0].timeframe) fail();
    const time = instant(item.open_time);
    if (time <= last) fail();
    last = time;
  }
  return page;
}
export function parseMessage(value: unknown): MarketMessage {
  validate(schemas.MarketMessage, value);
  const message = value as MarketMessage;
  parseStatus(message.status);
  if (message.quote) { quote(message.quote); if (message.quote.symbol !== message.symbol || message.quote.source !== message.status.source) fail(); }
  let last = -Infinity;
  for (const item of message.candles) {
    candle(item);
    if (item.source !== message.status.source || item.symbol !== message.symbol || item.timeframe !== message.timeframe || instant(item.open_time) <= last) fail();
    last = instant(item.open_time);
  }
  return message;
}


export function providerLabel(status: MarketDataStatus | null): string {
  if (!status || status.mode === 'UNCONFIRMED') return 'DATA SOURCE UNCONFIRMED';
  if (status.mode === 'SIMULATED') return 'SIMULATED DATA';
  return 'REAL MARKET DATA / ' + status.mode + ' CONNECTION';
}
