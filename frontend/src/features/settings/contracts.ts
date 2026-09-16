export type CredentialState = 'CONFIGURED' | 'MISSING' | 'NOT_REQUIRED' | 'NOT_EXPOSED';

export interface SafeConfiguration {
  as_of: string;
  authority: 'SERVER_CONFIGURATION';
  restart_required: boolean;
  trading: {
    mode: string;
    live_auto_trading: boolean;
    broker_execution: 'NONE';
    account_provenance: 'CONFIGURED_PAPER' | 'UNAVAILABLE';
  };
  market: {
    provider: 'simulated' | 'mt5';
    account_mode: 'DEMO' | 'LIVE';
    configured_symbol: string | null;
    server_timezone: string;
    poll_seconds: number;
    stale_after_seconds: number;
    archive_real_ticks: boolean;
    terminal: CredentialState;
    account_validation: CredentialState;
    server_validation: CredentialState;
    provenance: 'SIMULATED' | 'DEMO' | 'LIVE';
  };
  news: {
    provider: 'fixture' | 'unavailable' | 'xoomar' | 'forex_factory';
    poll_seconds: number;
    stale_after_seconds: number;
    provenance: 'FIXTURE' | 'LIVE' | 'UNAVAILABLE';
  };
  ai: {
    mode: 'fixture' | 'external';
    provider_type: 'fixture' | 'openai_compatible';
    credential: CredentialState;
    endpoint: 'DEFAULT_PROVIDER' | 'CUSTOM_ENDPOINT_CONFIGURED';
    model_mapping: Record<string, string>;
    max_concurrent_provider_calls: number;
    queue_timeout_seconds: number;
    provenance: 'FIXTURE' | 'EXTERNAL';
  };
  infrastructure: { environment: string; redis_enabled: boolean };
  session: { access_token_minutes: number; refresh_session_days: number };
}

export interface RuntimeModule { state: string; detail_th: string; updated_at: string }
export interface SystemStatus {
  as_of: string;
  trading_mode: string;
  live_auto_trading: boolean;
  ai_mode: string;
  ai_status_label: string;
  modules: Record<string, RuntimeModule>;
}
export interface MarketStatus {
  source: string;
  mode: string;
  status: string;
  last_quote: string | null;
  server_time: string;
  stale_after_seconds: number;
  detail: string;
  history_counts: Record<string, number>;
  history_complete: boolean;
  provider_symbol: string | null;
  last_candle: string | null;
}
export interface NewsStatus {
  source: string;
  source_mode: string;
  state: string;
  poll_seconds: number;
  last_sync_at: string | null;
  provider_updated_at: string | null;
  detail_th: string;
}
export interface RiskPolicy {
  version: string;
  max_risk_per_trade_pct: string | number;
  min_risk_per_trade_pct: string | number;
  max_account_risk_pct: string | number;
  max_symbol_risk_pct: string | number;
  max_directional_risk_pct: string | number;
  max_concurrent_trades: number;
  daily_loss_limit_pct: string | number;
  weekly_loss_limit_pct: string | number;
  max_drawdown_pct: string | number;
  max_spread_multiplier: string | number;
  max_spread_absolute: string | number;
  quote_freshness_seconds: number;
  account_freshness_seconds: number;
  news_high_impact_blackout_pre_minutes: number;
  news_high_impact_pre_minutes: number;
  news_high_impact_post_minutes: number;
  reservation_ttl_seconds: number;
}
export interface StrategyDefinition {
  id: string; name: string; version: string; category: string; styles: string[];
  required_context: string[]; minimum_bars: number; description_th: string;
}
export interface TraderProfile {
  id: string; name: string; description_th: string; style: string; enabled: boolean;
  allowed_strategies: string[]; execution_mode: string;
  timeframe_map: { context: string; bias: string; setup: string; trigger: string; minimum_bars: number };
}
export interface KillSwitchStatus { state: string; reason_th: string }

export class SettingsContractError extends Error {
  constructor() { super('Invalid Settings response contract'); }
}
function fail(): never { throw new SettingsContractError(); }
function record(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return fail();
  return value as Record<string, unknown>;
}
function exact(value: unknown, keys: readonly string[]): Record<string, unknown> {
  const data = record(value);
  const actual = Object.keys(data).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) fail();
  return data;
}
function text(value: unknown): string { if (typeof value !== 'string') return fail(); return value; }
function optionalText(value: unknown): string | null { if (value === null) return null; return text(value); }
function finite(value: unknown): number { if (typeof value !== 'number' || !Number.isFinite(value)) return fail(); return value; }
function bool(value: unknown): boolean { if (typeof value !== 'boolean') return fail(); return value; }
function literal<T extends string>(value: unknown, values: readonly T[]): T {
  if (typeof value !== 'string' || !values.includes(value as T)) return fail();
  return value as T;
}
function instant(value: unknown): string {
  const result = text(value);
  if (!Number.isFinite(Date.parse(result))) fail();
  return result;
}
function textList(value: unknown, maximum = 100): string[] {
  if (!Array.isArray(value) || value.length > maximum) return fail();
  return value.map(text);
}
function scalar(value: unknown): string | number {
  if (typeof value === 'string') return value;
  return finite(value);
}

const CREDENTIALS = ['CONFIGURED', 'MISSING', 'NOT_REQUIRED', 'NOT_EXPOSED'] as const;

export function parseSafeConfiguration(value: unknown): SafeConfiguration {
  const root = exact(value, ['as_of','authority','restart_required','trading','market','news','ai','infrastructure','session']);
  const trading = exact(root.trading, ['mode','live_auto_trading','broker_execution','account_provenance']);
  const market = exact(root.market, ['provider','account_mode','configured_symbol','server_timezone','poll_seconds','stale_after_seconds','archive_real_ticks','terminal','account_validation','server_validation','provenance']);
  const news = exact(root.news, ['provider','poll_seconds','stale_after_seconds','provenance']);
  const ai = exact(root.ai, ['mode','provider_type','credential','endpoint','model_mapping','max_concurrent_provider_calls','queue_timeout_seconds','provenance']);
  const infrastructure = exact(root.infrastructure, ['environment','redis_enabled']);
  const session = exact(root.session, ['access_token_minutes','refresh_session_days']);
  const mapping = record(ai.model_mapping);
  if (Object.keys(mapping).length > 20 || Object.values(mapping).some(item => typeof item !== 'string')) fail();
  return {
    as_of: instant(root.as_of), authority: literal(root.authority, ['SERVER_CONFIGURATION']), restart_required: bool(root.restart_required),
    trading: {
      mode: text(trading.mode), live_auto_trading: bool(trading.live_auto_trading),
      broker_execution: literal(trading.broker_execution, ['NONE']),
      account_provenance: literal(trading.account_provenance, ['CONFIGURED_PAPER','UNAVAILABLE']),
    },
    market: {
      provider: literal(market.provider, ['simulated','mt5']), account_mode: literal(market.account_mode, ['DEMO','LIVE']),
      configured_symbol: optionalText(market.configured_symbol), server_timezone: text(market.server_timezone),
      poll_seconds: finite(market.poll_seconds), stale_after_seconds: finite(market.stale_after_seconds),
      archive_real_ticks: bool(market.archive_real_ticks), terminal: literal(market.terminal, CREDENTIALS),
      account_validation: literal(market.account_validation, CREDENTIALS), server_validation: literal(market.server_validation, CREDENTIALS),
      provenance: literal(market.provenance, ['SIMULATED','DEMO','LIVE']),
    },
    news: {
      provider: literal(news.provider, ['fixture','unavailable','xoomar','forex_factory']),
      poll_seconds: finite(news.poll_seconds), stale_after_seconds: finite(news.stale_after_seconds),
      provenance: literal(news.provenance, ['FIXTURE','LIVE','UNAVAILABLE']),
    },
    ai: {
      mode: literal(ai.mode, ['fixture','external']), provider_type: literal(ai.provider_type, ['fixture','openai_compatible']),
      credential: literal(ai.credential, CREDENTIALS), endpoint: literal(ai.endpoint, ['DEFAULT_PROVIDER','CUSTOM_ENDPOINT_CONFIGURED']),
      model_mapping: mapping as Record<string,string>, max_concurrent_provider_calls: finite(ai.max_concurrent_provider_calls),
      queue_timeout_seconds: finite(ai.queue_timeout_seconds), provenance: literal(ai.provenance, ['FIXTURE','EXTERNAL']),
    },
    infrastructure: { environment: text(infrastructure.environment), redis_enabled: bool(infrastructure.redis_enabled) },
    session: { access_token_minutes: finite(session.access_token_minutes), refresh_session_days: finite(session.refresh_session_days) },
  };
}

export function parseSystemStatus(value: unknown): SystemStatus {
  const data = record(value); const modules = record(data.modules); const parsed: Record<string, RuntimeModule> = {};
  for (const [key, item] of Object.entries(modules)) {
    const moduleStatus = record(item); parsed[key] = { state: text(moduleStatus.state), detail_th: text(moduleStatus.detail_th), updated_at: instant(moduleStatus.updated_at) };
  }
  return { as_of: instant(data.as_of), trading_mode: text(data.trading_mode), live_auto_trading: bool(data.live_auto_trading), ai_mode: text(data.ai_mode), ai_status_label: text(data.ai_status_label), modules: parsed };
}
export function parseMarketStatus(value: unknown): MarketStatus {
  const data = record(value); const counts = record(data.history_counts); const history: Record<string,number> = {};
  for (const [key,item] of Object.entries(counts)) history[key] = finite(item);
  return { source:text(data.source), mode:text(data.mode), status:text(data.status), last_quote:optionalText(data.last_quote), server_time:instant(data.server_time), stale_after_seconds:finite(data.stale_after_seconds), detail:text(data.detail), history_counts:history, history_complete:bool(data.history_complete), provider_symbol:optionalText(data.provider_symbol), last_candle:optionalText(data.last_candle) };
}
export function parseNewsStatus(value: unknown): NewsStatus {
  const data=record(value); return { source:text(data.source), source_mode:text(data.source_mode), state:text(data.state), poll_seconds:finite(data.poll_seconds), last_sync_at:optionalText(data.last_sync_at), provider_updated_at:optionalText(data.provider_updated_at), detail_th:text(data.detail_th) };
}
export function parseRiskPolicy(value: unknown): RiskPolicy {
  const d=record(value); return {
    version:text(d.version), max_risk_per_trade_pct:scalar(d.max_risk_per_trade_pct), min_risk_per_trade_pct:scalar(d.min_risk_per_trade_pct),
    max_account_risk_pct:scalar(d.max_account_risk_pct), max_symbol_risk_pct:scalar(d.max_symbol_risk_pct), max_directional_risk_pct:scalar(d.max_directional_risk_pct),
    max_concurrent_trades:finite(d.max_concurrent_trades), daily_loss_limit_pct:scalar(d.daily_loss_limit_pct), weekly_loss_limit_pct:scalar(d.weekly_loss_limit_pct), max_drawdown_pct:scalar(d.max_drawdown_pct),
    max_spread_multiplier:scalar(d.max_spread_multiplier), max_spread_absolute:scalar(d.max_spread_absolute), quote_freshness_seconds:finite(d.quote_freshness_seconds), account_freshness_seconds:finite(d.account_freshness_seconds),
    news_high_impact_blackout_pre_minutes:finite(d.news_high_impact_blackout_pre_minutes), news_high_impact_pre_minutes:finite(d.news_high_impact_pre_minutes), news_high_impact_post_minutes:finite(d.news_high_impact_post_minutes), reservation_ttl_seconds:finite(d.reservation_ttl_seconds),
  };
}
export function parseStrategies(value: unknown): StrategyDefinition[] {
  if (!Array.isArray(value) || value.length > 20) return fail();
  return value.map(item=>{ const d=record(item); return { id:text(d.id), name:text(d.name), version:text(d.version), category:text(d.category), styles:textList(d.styles,10), required_context:textList(d.required_context,20), minimum_bars:finite(d.minimum_bars), description_th:text(d.description_th) }; });
}
export function parseProfiles(value: unknown): TraderProfile[] {
  if (!Array.isArray(value) || value.length > 20) return fail();
  return value.map(item=>{ const d=record(item); const t=record(d.timeframe_map); return { id:text(d.id), name:text(d.name), description_th:text(d.description_th), style:text(d.style), enabled:bool(d.enabled), allowed_strategies:textList(d.allowed_strategies,20), execution_mode:text(d.execution_mode), timeframe_map:{ context:text(t.context), bias:text(t.bias), setup:text(t.setup), trigger:text(t.trigger), minimum_bars:finite(t.minimum_bars) } }; });
}
export function parseKillSwitch(value: unknown): KillSwitchStatus {
  const d=record(value); return { state:text(d.state), reason_th:text(d.reason_th) };
}

export const UI_PREFERENCES_KEY = 'aigoldtrader.ui-preferences.v1';
export interface UiPreferences { language: 'th'; timezone: 'Asia/Bangkok' | 'UTC'; density: 'comfortable' | 'compact'; default_timeframe: 'M5' | 'M15' | 'H1' }
export const DEFAULT_UI_PREFERENCES: UiPreferences = { language:'th', timezone:'Asia/Bangkok', density:'comfortable', default_timeframe:'M15' };
export function parseUiPreferences(value: unknown): UiPreferences {
  try {
    const d=exact(value,['language','timezone','density','default_timeframe']);
    return { language:literal(d.language,['th']), timezone:literal(d.timezone,['Asia/Bangkok','UTC']), density:literal(d.density,['comfortable','compact']), default_timeframe:literal(d.default_timeframe,['M5','M15','H1']) };
  } catch { return { ...DEFAULT_UI_PREFERENCES }; }
}
