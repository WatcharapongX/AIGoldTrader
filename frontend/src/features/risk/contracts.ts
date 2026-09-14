/**
 * Phase 5 Risk Engine & Portfolio Risk contracts and strict runtime validators.
 */

export type ResourceStatus = 'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE';

export interface RiskPolicyData {
  version: string;
  max_risk_per_trade_pct: string;
  min_risk_per_trade_pct: string;
  max_account_risk_pct: string;
  max_symbol_risk_pct: string;
  max_directional_risk_pct: string;
  max_concurrent_trades: number;
  daily_loss_limit_pct: string;
  weekly_loss_limit_pct: string;
  max_drawdown_pct: string;
  cooldown_consecutive_losses: number;
  max_spread_absolute: string;
  news_high_impact_blackout_pre_minutes: number;
  news_high_impact_pre_minutes: number;
  news_high_impact_post_minutes: number;
  news_blackout_minutes?: number;
  news_reduction_window_minutes?: number;
  news_reduction_factor: string;
  reservation_ttl_seconds: number;
}

export interface KillSwitchData {
  state: 'ACTIVE' | 'INACTIVE' | 'UNKNOWN';
  trigger_type: string;
  reason_th: string;
  activated_at: string;
  activated_by: string;
  cleared_at: string | null;
  cleared_by: string | null;
  policy_version: string;
}

export interface RiskReservationData {
  id: string;
  decision_id: string;
  account_id: string;
  profile_id: string;
  symbol: string;
  direction: 'LONG' | 'SHORT';
  risk_pct: string;
  risk_amount: string;
  position_size: string;
  status: string;
  reserved_at: string;
  reserved_until: string;
}

export interface PortfolioRiskData {
  account_id: string;
  account_source: string;
  as_of: string;
  open_risk_pct: string;
  reserved_risk_pct: string;
  total_risk_pct: string;
  max_account_risk_pct: string;
  available_risk_pct: string;
  symbol_risk_pct: Record<string, string>;
  directional_risk_pct: Record<'LONG' | 'SHORT', string>;
  active_reservations: RiskReservationData[];
  active_reservations_count: number;
  kill_switch_active: boolean;
  kill_switch_state: KillSwitchData | null;
  daily_loss_pct: string;
  weekly_loss_pct: string;
  drawdown_pct: string;
  in_cooldown: boolean;
  cooldown_until: string | null;
}

export interface MarketProvenanceData {
  source: string;
  mode: string;
  quote_timestamp: string;
  quote_bid: string;
  quote_ask: string;
  quote_spread: string;
  is_stale: boolean;
}

export interface NewsRiskProvenanceData {
  news_state: string;
  in_blackout: boolean;
  in_pre_news_window: boolean;
  in_post_news_window: boolean;
  event_ids: string[];
  description_th: string;
}

export interface RiskDecisionData {
  id: string;
  candidate_id: string;
  plan_id: string;
  strategy_id: string;
  strategy_version: string;
  profile_id: string;
  symbol: string;
  direction: 'LONG' | 'SHORT';
  decision: 'APPROVED' | 'REDUCED' | 'BLOCKED';
  requested_risk_pct: string;
  approved_risk_pct: string;
  requested_risk_amount: string;
  approved_risk_amount: string;
  position_size: string;
  entry_lower: string;
  entry_upper: string;
  stop_loss: string;
  stop_distance: string;
  portfolio_exposure_before: string;
  portfolio_exposure_after: string;
  account_snapshot_id: string;
  symbol_specification_id: string;
  policy_version: string;
  as_of: string;
  expires_at: string;
  dependency_fingerprint: string;
  reasons_th: string[];
  warnings_th: string[];
  blocked_reasons_th: string[];
  market_provenance: MarketProvenanceData | null;
  news_provenance: NewsRiskProvenanceData | null;
  news_risk_provenance: NewsRiskProvenanceData | null;
}

export class RiskContractError extends Error {
  constructor(message: string = 'Invalid risk contract') {
    super(message);
    this.name = 'RiskContractError';
  }
}

function fail(msg: string = 'Contract validation failed'): never {
  throw new RiskContractError(msg);
}

export function parseInstant(value: unknown): number {
  if (typeof value !== 'string') return fail('Timestamp must be string');
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
    return fail('Timestamp not ISO 8601');
  }
  const time = Date.parse(value);
  if (!Number.isFinite(time)) return fail('Invalid date');
  return time;
}

function isNumericStringOrNumber(value: unknown): boolean {
  if (typeof value === 'number') return Number.isFinite(value);
  if (typeof value === 'string') {
    return value.trim().length > 0 && Number.isFinite(Number(value));
  }
  return false;
}

export function parseRiskPolicy(raw: unknown): RiskPolicyData {
  if (!raw || typeof raw !== 'object') fail('Policy must be object');
  const d = raw as Record<string, unknown>;
  if (typeof d.version !== 'string' || !d.version.startsWith('risk-policy-')) fail('Invalid policy version');
  if (!isNumericStringOrNumber(d.max_risk_per_trade_pct)) fail('Invalid max_risk_per_trade_pct');
  if (!isNumericStringOrNumber(d.min_risk_per_trade_pct)) fail('Invalid min_risk_per_trade_pct');
  if (!isNumericStringOrNumber(d.max_account_risk_pct)) fail('Invalid max_account_risk_pct');
  if (!isNumericStringOrNumber(d.max_symbol_risk_pct)) fail('Invalid max_symbol_risk_pct');
  if (!isNumericStringOrNumber(d.max_directional_risk_pct)) fail('Invalid max_directional_risk_pct');
  if (typeof d.max_concurrent_trades !== 'number' || d.max_concurrent_trades <= 0) fail('Invalid max_concurrent_trades');

  if (d.news_high_impact_blackout_pre_minutes === undefined || d.news_high_impact_blackout_pre_minutes === null || !Number.isFinite(Number(d.news_high_impact_blackout_pre_minutes))) {
    fail('Invalid news_high_impact_blackout_pre_minutes');
  }
  if (d.news_high_impact_pre_minutes === undefined || d.news_high_impact_pre_minutes === null || !Number.isFinite(Number(d.news_high_impact_pre_minutes))) {
    fail('Invalid news_high_impact_pre_minutes');
  }
  if (d.news_high_impact_post_minutes === undefined || d.news_high_impact_post_minutes === null || !Number.isFinite(Number(d.news_high_impact_post_minutes))) {
    fail('Invalid news_high_impact_post_minutes');
  }
  if (!isNumericStringOrNumber(d.news_reduction_factor)) {
    fail('Invalid news_reduction_factor');
  }

  const blackoutPre = Number(d.news_high_impact_blackout_pre_minutes);
  const preMinutes = Number(d.news_high_impact_pre_minutes);
  const postMinutes = Number(d.news_high_impact_post_minutes);

  return {
    version: d.version,
    max_risk_per_trade_pct: String(d.max_risk_per_trade_pct),
    min_risk_per_trade_pct: String(d.min_risk_per_trade_pct),
    max_account_risk_pct: String(d.max_account_risk_pct),
    max_symbol_risk_pct: String(d.max_symbol_risk_pct),
    max_directional_risk_pct: String(d.max_directional_risk_pct),
    max_concurrent_trades: d.max_concurrent_trades,
    daily_loss_limit_pct: String(d.daily_loss_limit_pct),
    weekly_loss_limit_pct: String(d.weekly_loss_limit_pct),
    max_drawdown_pct: String(d.max_drawdown_pct),
    cooldown_consecutive_losses: Number(d.cooldown_consecutive_losses),
    max_spread_absolute: String(d.max_spread_absolute),
    news_high_impact_blackout_pre_minutes: blackoutPre,
    news_high_impact_pre_minutes: preMinutes,
    news_high_impact_post_minutes: postMinutes,
    news_blackout_minutes: blackoutPre,
    news_reduction_window_minutes: preMinutes,
    news_reduction_factor: String(d.news_reduction_factor),
    reservation_ttl_seconds: Number(d.reservation_ttl_seconds),
  };
}

export function parseKillSwitch(raw: unknown): KillSwitchData {
  if (!raw || typeof raw !== 'object') fail('Kill switch must be object');
  const d = raw as Record<string, unknown>;
  if (d.state !== 'ACTIVE' && d.state !== 'INACTIVE' && d.state !== 'UNKNOWN') fail('Invalid kill switch state');
  if (typeof d.trigger_type !== 'string') fail('Invalid trigger_type');
  if (typeof d.reason_th !== 'string') fail('Invalid reason_th');
  parseInstant(d.activated_at);
  if (d.cleared_at !== null && d.cleared_at !== undefined) parseInstant(d.cleared_at);

  return {
    state: d.state as 'ACTIVE' | 'INACTIVE' | 'UNKNOWN',
    trigger_type: d.trigger_type,
    reason_th: d.reason_th,
    activated_at: String(d.activated_at),
    activated_by: String(d.activated_by),
    cleared_at: d.cleared_at ? String(d.cleared_at) : null,
    cleared_by: d.cleared_by ? String(d.cleared_by) : null,
    policy_version: String(d.policy_version),
  };
}

export function parseReservation(raw: unknown): RiskReservationData {
  if (!raw || typeof raw !== 'object') fail('Reservation must be object');
  const d = raw as Record<string, unknown>;
  if (typeof d.id !== 'string') fail('Invalid id');
  if (typeof d.decision_id !== 'string') fail('Invalid decision_id');
  if (typeof d.symbol !== 'string') fail('Invalid symbol');
  if (d.direction !== 'LONG' && d.direction !== 'SHORT') fail('Invalid direction');
  if (!isNumericStringOrNumber(d.risk_pct)) fail('Invalid risk_pct');
  if (!isNumericStringOrNumber(d.position_size)) fail('Invalid position_size');
  parseInstant(d.reserved_at);
  parseInstant(d.reserved_until);

  return {
    id: d.id,
    decision_id: d.decision_id,
    account_id: String(d.account_id),
    profile_id: String(d.profile_id),
    symbol: d.symbol,
    direction: d.direction as 'LONG' | 'SHORT',
    risk_pct: String(d.risk_pct),
    risk_amount: String(d.risk_amount),
    position_size: String(d.position_size),
    status: String(d.status),
    reserved_at: String(d.reserved_at),
    reserved_until: String(d.reserved_until),
  };
}

export function parsePortfolioRisk(raw: unknown): PortfolioRiskData {
  if (!raw || typeof raw !== 'object') fail('Portfolio risk must be object');
  const d = raw as Record<string, unknown>;

  if (typeof d.account_id !== 'string' || !d.account_id) fail('Invalid account_id');
  if (typeof d.account_source !== 'string' || !d.account_source) fail('Invalid account_source');
  parseInstant(d.as_of);

  if (!isNumericStringOrNumber(d.open_risk_pct)) fail('Invalid open_risk_pct');
  if (!isNumericStringOrNumber(d.reserved_risk_pct)) fail('Invalid reserved_risk_pct');
  if (!isNumericStringOrNumber(d.total_risk_pct)) fail('Invalid total_risk_pct');
  if (!isNumericStringOrNumber(d.max_account_risk_pct)) fail('Invalid max_account_risk_pct');
  if (!isNumericStringOrNumber(d.available_risk_pct)) fail('Invalid available_risk_pct');

  if (!d.symbol_risk_pct || typeof d.symbol_risk_pct !== 'object' || Array.isArray(d.symbol_risk_pct)) {
    fail('Invalid symbol_risk_pct');
  }

  if (!d.directional_risk_pct || typeof d.directional_risk_pct !== 'object' || Array.isArray(d.directional_risk_pct)) {
    fail('Invalid directional_risk_pct');
  }
  const directional = d.directional_risk_pct as Record<string, unknown>;
  if (!isNumericStringOrNumber(directional.LONG) || !isNumericStringOrNumber(directional.SHORT)) {
    fail('directional_risk_pct must contain LONG and SHORT numbers');
  }

  if (!Array.isArray(d.active_reservations)) fail('active_reservations must be array');
  const reservations = d.active_reservations.map(parseReservation);

  if (typeof d.active_reservations_count !== 'number') fail('Invalid active_reservations_count');
  if (typeof d.kill_switch_active !== 'boolean') fail('Invalid kill_switch_active');

  if (!isNumericStringOrNumber(d.daily_loss_pct)) fail('Invalid daily_loss_pct');
  if (!isNumericStringOrNumber(d.weekly_loss_pct)) fail('Invalid weekly_loss_pct');
  if (!isNumericStringOrNumber(d.drawdown_pct)) fail('Invalid drawdown_pct');
  if (typeof d.in_cooldown !== 'boolean') fail('Invalid in_cooldown');
  if (d.cooldown_until !== null && d.cooldown_until !== undefined) {
    parseInstant(d.cooldown_until);
  }

  return {
    account_id: String(d.account_id),
    account_source: String(d.account_source),
    as_of: String(d.as_of),
    open_risk_pct: String(d.open_risk_pct),
    reserved_risk_pct: String(d.reserved_risk_pct),
    total_risk_pct: String(d.total_risk_pct),
    max_account_risk_pct: String(d.max_account_risk_pct),
    available_risk_pct: String(d.available_risk_pct),
    symbol_risk_pct: d.symbol_risk_pct as Record<string, string>,
    directional_risk_pct: {
      LONG: String(directional.LONG),
      SHORT: String(directional.SHORT),
    },
    active_reservations: reservations,
    active_reservations_count: d.active_reservations_count,
    kill_switch_active: d.kill_switch_active,
    kill_switch_state: d.kill_switch_state ? parseKillSwitch(d.kill_switch_state) : null,
    daily_loss_pct: String(d.daily_loss_pct),
    weekly_loss_pct: String(d.weekly_loss_pct),
    drawdown_pct: String(d.drawdown_pct),
    in_cooldown: d.in_cooldown,
    cooldown_until: d.cooldown_until ? String(d.cooldown_until) : null,
  };
}

export function parseRiskDecision(raw: unknown): RiskDecisionData {
  if (!raw || typeof raw !== 'object') fail('Risk decision must be object');
  const d = raw as Record<string, unknown>;
  if (typeof d.id !== 'string') fail('Invalid decision id');
  if (typeof d.candidate_id !== 'string') fail('Invalid candidate_id');
  if (d.decision !== 'APPROVED' && d.decision !== 'REDUCED' && d.decision !== 'BLOCKED') {
    fail('Invalid decision status');
  }
  if (d.direction !== 'LONG' && d.direction !== 'SHORT') fail('Invalid direction');
  parseInstant(d.as_of);
  parseInstant(d.expires_at);

  return {
    id: d.id,
    candidate_id: d.candidate_id,
    plan_id: String(d.plan_id),
    strategy_id: String(d.strategy_id),
    strategy_version: String(d.strategy_version),
    profile_id: String(d.profile_id),
    symbol: String(d.symbol),
    direction: d.direction as 'LONG' | 'SHORT',
    decision: d.decision as 'APPROVED' | 'REDUCED' | 'BLOCKED',
    requested_risk_pct: String(d.requested_risk_pct),
    approved_risk_pct: String(d.approved_risk_pct),
    requested_risk_amount: String(d.requested_risk_amount),
    approved_risk_amount: String(d.approved_risk_amount),
    position_size: String(d.position_size),
    entry_lower: String(d.entry_lower),
    entry_upper: String(d.entry_upper),
    stop_loss: String(d.stop_loss),
    stop_distance: String(d.stop_distance),
    portfolio_exposure_before: String(d.portfolio_exposure_before),
    portfolio_exposure_after: String(d.portfolio_exposure_after),
    account_snapshot_id: String(d.account_snapshot_id),
    symbol_specification_id: String(d.symbol_specification_id),
    policy_version: String(d.policy_version),
    as_of: String(d.as_of),
    expires_at: String(d.expires_at),
    dependency_fingerprint: String(d.dependency_fingerprint || ''),
    reasons_th: Array.isArray(d.reasons_th) ? d.reasons_th.map(String) : [],
    warnings_th: Array.isArray(d.warnings_th) ? d.warnings_th.map(String) : [],
    blocked_reasons_th: Array.isArray(d.blocked_reasons_th) ? d.blocked_reasons_th.map(String) : [],
    market_provenance: d.market_provenance ? (d.market_provenance as MarketProvenanceData) : null,
    news_provenance: (d.news_provenance || d.news_risk_provenance) ? ((d.news_provenance || d.news_risk_provenance) as NewsRiskProvenanceData) : null,
    news_risk_provenance: (d.news_provenance || d.news_risk_provenance) ? ((d.news_provenance || d.news_risk_provenance) as NewsRiskProvenanceData) : null,
  };
}

export function parseRiskDecisions(raw: unknown): RiskDecisionData[] {
  if (!Array.isArray(raw)) fail('Decisions must be array');
  return raw.map(parseRiskDecision);
}

export function parseAccountSnapshot(raw: unknown): import('@/types').AccountSnapshotData {
  if (!raw || typeof raw !== 'object') fail('Account snapshot must be object');
  const d = raw as Record<string, unknown>;
  return {
    id: String(d.id || ''),
    account_id: String(d.account_id || ''),
    balance: String(d.balance ?? '0.00'),
    equity: String(d.equity ?? '0.00'),
    free_margin: d.free_margin != null ? String(d.free_margin) : null,
    daily_realized_pnl: String(d.daily_realized_pnl ?? '0.00'),
    weekly_realized_pnl: String(d.weekly_realized_pnl ?? '0.00'),
    floating_pnl: d.floating_pnl != null ? String(d.floating_pnl) : null,
    peak_equity: String(d.peak_equity ?? d.equity ?? '0.00'),
    open_risk_pct: String(d.open_risk_pct ?? '0.00'),
    reserved_risk_pct: String(d.reserved_risk_pct ?? '0.00'),
    consecutive_losses: Number(d.consecutive_losses || 0),
    trading_mode: String(d.trading_mode || 'PAPER'),
    source: String(d.source || 'CONFIGURED_PAPER'),
    as_of: String(d.as_of || new Date().toISOString()),
  };
}
