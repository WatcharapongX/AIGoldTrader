'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '@/lib/api';
import { parseStatus } from '@/features/chart/contracts';
import { parseCalendar, parseNews } from '@/features/news/contracts';
import {
  parseAccountSnapshot,
  parseKillSwitch,
  parsePortfolioRisk,
  parseRiskDecisions,
  parseRiskPolicy,
} from '@/features/risk/contracts';
import { parseStrategy } from '@/features/strategy/contracts';
import type { HealthResponse, ReadyResponse, SystemStatusResponse } from '@/types';
import type { Quote } from '@/types/market.generated';
import type { NewsResponse } from '@/types/news.generated';
import type { StrategyResponse } from '@/types/strategy.generated';
import {
  buildCsv,
  buildJsonExport,
  downloadTextArtifact,
  parseCandidateList,
  reportFilename,
  type ExportColumn,
  type ExportRow,
  type ReportExportMetadata,
  type ReportStatus,
} from './contracts';

type ReportId = 'system' | 'market' | 'candidates' | 'evaluations' | 'risk' | 'calendar' | 'macro' | 'operational' | 'ai' | 'execution';
type LoadPhase = 'idle' | 'loading' | 'ready' | 'error';

interface ReportDefinition {
  id: ReportId;
  title: string;
  subtitle: string;
  defaultStatus: ReportStatus;
  endpoint: string;
  drilldown?: string;
}

interface ReportPayload {
  status: ReportStatus;
  columns: ExportColumn[];
  rows: ExportRow[];
  facts: Array<{ label: string; value: string }>;
  source: string;
  mode: string;
  dataAsOf: string | null;
  coverage: string;
  limitations: string[];
}

interface ReportState {
  phase: LoadPhase;
  data: ReportPayload | null;
  error: string | null;
  loadedAt: string | null;
}

const REPORTS: ReportDefinition[] = [
  { id: 'system', title: 'System Health', subtitle: 'Backend, DB, Redis และ subsystem ทั้งหมด', defaultStatus: 'AVAILABLE', endpoint: '/healthz · /readyz · /system/status' },
  { id: 'market', title: 'Market & Data', subtitle: 'สถานะ provider, quote และ freshness', defaultStatus: 'AVAILABLE', endpoint: '/market/status · /market/quote', drilldown: '/trading' },
  { id: 'candidates', title: 'Strategy Candidates', subtitle: 'Candidate ที่ตรวจพบ สูงสุด 100 รายการ', defaultStatus: 'AVAILABLE', endpoint: '/trade-candidates?limit=100', drilldown: '/signals' },
  { id: 'evaluations', title: 'Strategy Evaluations', subtitle: 'Operational evaluation snapshots ไม่ใช่ backtest', defaultStatus: 'AVAILABLE', endpoint: '/strategy/evaluations?limit=25', drilldown: '/backtesting' },
  { id: 'risk', title: 'Risk Decisions', subtitle: 'Decision, account, portfolio, policy และ Kill Switch', defaultStatus: 'AVAILABLE', endpoint: '/risk/*', drilldown: '/risk' },
  { id: 'calendar', title: 'Economic Calendar', subtitle: 'เหตุการณ์ช่วง 7 วันแบบ point-in-time', defaultStatus: 'AVAILABLE', endpoint: '/calendar/economic', drilldown: '/calendar' },
  { id: 'macro', title: 'Macro Context', subtitle: 'บริบทข่าวเชิงพรรณนา ไม่ใช่ Trading Signal', defaultStatus: 'AVAILABLE', endpoint: '/news/context', drilldown: '/scanner' },
  { id: 'operational', title: 'Operational Analytics', subtitle: 'กิจกรรม Candidate, Evaluation และ Risk', defaultStatus: 'PARTIAL', endpoint: 'bounded operational endpoints', drilldown: '/analytics' },
  { id: 'ai', title: 'AI Report History', subtitle: 'ยังไม่มี durable AI report history', defaultStatus: 'UNAVAILABLE', endpoint: 'NO REPORT DATASET', drilldown: '/analysis' },
  { id: 'execution', title: 'Executed Trading Performance', subtitle: 'ยังไม่มี order/trade/position ledger', defaultStatus: 'NOT IMPLEMENTED', endpoint: 'NO EXECUTION DATASET', drilldown: '/analytics' },
];

const EMPTY_STATE: ReportState = { phase: 'idle', data: null, error: null, loadedAt: null };
const INITIAL_STATES = Object.fromEntries(REPORTS.map((report) => [report.id, { ...EMPTY_STATE }])) as Record<ReportId, ReportState>;
INITIAL_STATES.system = { ...EMPTY_STATE, phase: 'loading' };

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : 'ไม่สามารถโหลดรายงานได้';
}

function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'N/A';
  if (typeof value === 'boolean') return value ? 'YES' : 'NO';
  return String(value);
}

function formatTime(value: string | null): string {
  if (!value) return 'N/A';
  const time = Date.parse(value);
  return Number.isFinite(time)
    ? new Intl.DateTimeFormat('th-TH', { dateStyle: 'medium', timeStyle: 'medium', timeZone: 'Asia/Bangkok' }).format(time)
    : value;
}

function parseSystemStatus(value: unknown): SystemStatusResponse {
  if (!value || typeof value !== 'object') throw new Error('Invalid system status payload');
  const row = value as Record<string, unknown>;
  if (typeof row.as_of !== 'string' || typeof row.trading_mode !== 'string' || typeof row.live_auto_trading !== 'boolean' || !row.modules || typeof row.modules !== 'object') {
    throw new Error('Invalid system status payload');
  }
  return value as SystemStatusResponse;
}

function parseQuote(value: unknown): Quote | null {
  if (value === null) return null;
  if (!value || typeof value !== 'object') throw new Error('Invalid quote payload');
  const row = value as Record<string, unknown>;
  if (typeof row.symbol !== 'string' || typeof row.timestamp !== 'string' || typeof row.bid !== 'string' || typeof row.ask !== 'string' || typeof row.source !== 'string') {
    throw new Error('Invalid quote payload');
  }
  return value as Quote;
}

function isRejected<T>(result: PromiseSettledResult<T>): result is PromiseRejectedResult {
  return result.status === 'rejected';
}

function staticUnavailable(id: 'ai' | 'execution'): ReportPayload {
  const execution = id === 'execution';
  const metrics = execution
    ? ['Total Executed Trades', 'Win Rate', 'Profit Factor', 'Net P&L', 'Expectancy', 'Maximum Drawdown', 'Sharpe Ratio', 'Equity Curve', 'Monthly P&L']
    : ['AI advisory history', 'AI decision audit trail', 'AI outcome attribution'];
  return {
    status: execution ? 'NOT IMPLEMENTED' : 'UNAVAILABLE',
    columns: [{ key: 'metric', label: 'Metric' }, { key: 'value', label: 'Value' }, { key: 'reason', label: 'Reason' }],
    rows: metrics.map((metric) => ({ metric, value: 'N/A', reason: execution ? 'ไม่มี execution ledger' : 'ไม่มี durable AI report dataset' })),
    facts: [{ label: 'สถานะข้อมูล', value: execution ? 'NOT IMPLEMENTED' : 'NOT AVAILABLE' }, { label: 'ค่าทดแทน', value: 'ไม่ใช้ 0 หรือ 0%' }],
    source: 'ไม่มีแหล่งข้อมูลที่เชื่อถือได้',
    mode: 'REPORTING ONLY',
    dataAsOf: null,
    coverage: 'ไม่มีข้อมูลประวัติที่คำนวณ metric นี้ได้',
    limitations: ['ระบบไม่สร้าง trade, P&L, win rate, profit factor หรือ AI history ขึ้นเอง', 'ค่า N/A หมายถึงไม่พร้อมใช้งาน ไม่ใช่ศูนย์'],
  };
}

async function loadSystemReport(): Promise<ReportPayload> {
  const results = await Promise.allSettled([api.healthz(), api.readyz(), api.get('/system/status')]);
  const health = results[0].status === 'fulfilled' ? results[0].value as HealthResponse : null;
  const ready = results[1].status === 'fulfilled' ? results[1].value as ReadyResponse : null;
  const system = results[2].status === 'fulfilled' ? parseSystemStatus(results[2].value) : null;
  if (!health && !ready && !system) throw new Error('System health endpoints ไม่พร้อมใช้งานทั้งหมด');
  const rows: ExportRow[] = [];
  if (system) for (const [key, module] of Object.entries(system.modules)) rows.push({ module: key, state: module.state, detail: module.detail_th, updated_at: module.updated_at });
  if (health) rows.push({ module: 'healthz', state: health.status.toUpperCase(), detail: `${health.app} · ${health.env}`, updated_at: null });
  if (ready) rows.push({ module: 'readyz', state: ready.status.toUpperCase(), detail: `database=${ready.checks.database}; redis=${valueText(ready.checks.redis)}`, updated_at: null });
  const failures = results.filter(isRejected).length;
  return {
    status: failures ? 'PARTIAL' : 'AVAILABLE',
    columns: [{ key: 'module', label: 'Module' }, { key: 'state', label: 'State' }, { key: 'detail', label: 'Detail' }, { key: 'updated_at', label: 'Updated At' }],
    rows,
    facts: [
      { label: 'Trading Mode', value: system?.trading_mode ?? health?.trading_mode ?? 'N/A' },
      { label: 'Live Auto Trading', value: valueText(system?.live_auto_trading ?? health?.live_auto_trading) },
      { label: 'AI Provider', value: system?.ai_status_label ?? 'N/A' },
      { label: 'Readiness', value: ready?.status.toUpperCase() ?? 'UNAVAILABLE' },
    ],
    source: 'AIGoldTrader runtime APIs', mode: system?.trading_mode ?? health?.trading_mode ?? 'UNKNOWN', dataAsOf: system?.as_of ?? null,
    coverage: `${rows.length} module/status records · ${failures} endpoint failure(s)`,
    limitations: failures ? ['บาง health endpoint ไม่ตอบสนอง แต่ผลจาก endpoint อื่นยังแสดงตามจริง'] : [],
  };
}

async function loadMarketReport(): Promise<ReportPayload> {
  const results = await Promise.allSettled([api.get('/market/status'), api.get('/market/quote')]);
  const status = results[0].status === 'fulfilled' ? parseStatus(results[0].value) : null;
  const quote = results[1].status === 'fulfilled' ? parseQuote(results[1].value) : null;
  if (!status && !quote) throw new Error('Market status และ quote ไม่พร้อมใช้งาน');
  const rows: ExportRow[] = [{
    symbol: quote?.symbol ?? status?.provider_symbol ?? 'XAUUSD', provider: status?.source ?? quote?.source ?? null,
    mode: status?.mode ?? quote?.mode ?? null, connection: status?.status ?? quote?.status ?? null,
    market_state: status?.market_state ?? null, bid: quote?.bid ?? null, ask: quote?.ask ?? null,
    spread: quote?.spread ?? null, quote_at: quote?.timestamp ?? status?.last_quote ?? null,
    stale_after_seconds: status?.stale_after_seconds ?? null, last_candle: status?.last_candle ?? null,
    history_complete: status?.history_complete ?? null,
    history_counts: status?.history_counts ? JSON.stringify(status.history_counts) : null,
  }];
  const stale = status?.status === 'STALE' || quote?.status === 'STALE';
  const failures = results.filter(isRejected).length;
  return {
    status: stale ? 'STALE' : failures ? 'PARTIAL' : 'AVAILABLE',
    columns: Object.keys(rows[0]).map((key) => ({ key, label: key.replaceAll('_', ' ').toUpperCase() })), rows,
    facts: [{ label: 'Provider', value: status?.source ?? quote?.source ?? 'N/A' }, { label: 'Connection', value: status?.status ?? quote?.status ?? 'N/A' }, { label: 'History Complete', value: valueText(status?.history_complete) }, { label: 'Historical Coverage', value: status?.history_counts ? JSON.stringify(status.history_counts) : 'N/A' }, { label: 'Subscriptions', value: valueText(status?.subscriptions) }],
    source: status?.source ?? quote?.source ?? 'market API', mode: status?.mode ?? quote?.mode ?? 'UNKNOWN',
    dataAsOf: quote?.timestamp ?? status?.last_quote ?? status?.server_time ?? null,
    coverage: `status + latest quote + provider history counts${failures ? ' · partial endpoint failure' : ''}`,
    limitations: quote ? [] : ['ไม่มี latest quote; แสดงเฉพาะ provider status'],
  };
}

async function loadCandidatesReport(): Promise<ReportPayload> {
  const candidates = parseCandidateList(await api.get('/trade-candidates?limit=100'));
  const rows: ExportRow[] = candidates.map((item) => ({
    id: item.id, detected_at: item.detected_at, symbol: item.symbol, strategy_id: item.strategy_id,
    strategy_version: item.strategy_version ?? null, profile_id: item.profile_id, direction: item.direction,
    state: item.status, evidence_score: item.score, evidence_count: item.evidence.length,
    missing_conditions: item.missing_conditions.join(' | '), conflicts: item.conflicts.join(' | '),
    confirmed_at: item.confirmed_at, expires_at: item.expires_at, context_id: item.context_id,
  }));
  return {
    status: 'AVAILABLE', columns: Object.keys(rows[0] ?? { id: '' }).map((key) => ({ key, label: key.replaceAll('_', ' ').toUpperCase() })), rows,
    facts: [{ label: 'Candidate Count', value: String(rows.length) }, { label: 'READY', value: String(candidates.filter((c) => c.status === 'READY').length) }, { label: 'NO_TRADE', value: String(candidates.filter((c) => c.status === 'NO_TRADE').length) }, { label: 'ความหมาย', value: 'Candidate ≠ Executed Trade' }],
    source: '/trade-candidates', mode: 'ANALYSIS ONLY', dataAsOf: candidates[0]?.detected_at ?? null,
    coverage: `ล่าสุดสูงสุด 100 รายการ; ได้รับ ${rows.length} รายการ`,
    limitations: ['Evidence Score ไม่ใช่ win probability', 'การกรองทำใน browser ภายในชุดข้อมูลที่โหลดเท่านั้น'],
  };
}

async function loadEvaluationsReport(): Promise<ReportPayload> {
  const raw = await api.get('/strategy/evaluations?limit=25');
  if (!Array.isArray(raw) || raw.length > 25) throw new Error('Invalid evaluations payload');
  const evaluations = raw.map(parseStrategy);
  const rows: ExportRow[] = evaluations.map((item: StrategyResponse) => ({
    evaluation_id: item.evaluation.id, identity_version: item.evaluation.identity_version ?? null,
    scope: item.evaluation.scope ?? 'LEGACY', symbol: item.evaluation.context.symbol,
    context_mode: item.evaluation.context.mode, context_as_of: item.evaluation.context.as_of,
    config_id: item.evaluation.context.config_id, engine_version: item.evaluation.context.engine_version ?? null,
    strategies: item.evaluation.strategies.map((strategy) => `${strategy.id}@${strategy.version ?? 'unknown'}`).join(' | '),
    profiles: item.evaluation.profiles.map((profile) => profile.id).join(' | '), candidate_count: item.evaluation.candidates.length,
    adaptive_status: item.evaluation.adaptive_status ?? null, generated_at: item.generated_at, served_at: item.served_at, stale: item.stale,
  }));
  return {
    status: evaluations.some((item) => item.stale) ? 'STALE' : 'AVAILABLE',
    columns: Object.keys(rows[0] ?? { evaluation_id: '' }).map((key) => ({ key, label: key.replaceAll('_', ' ').toUpperCase() })), rows,
    facts: [{ label: 'Snapshots', value: String(rows.length) }, { label: 'Candidate References', value: String(evaluations.reduce((sum, item) => sum + item.evaluation.candidates.length, 0)) }, { label: 'ประเภท', value: 'Historical Evaluation Activity' }, { label: 'Backtest', value: 'NO · NOT A BACKTEST' }],
    source: '/strategy/evaluations', mode: 'ANALYSIS ONLY', dataAsOf: evaluations[0]?.evaluation.context.as_of ?? null,
    coverage: `ล่าสุดสูงสุด 25 evaluation snapshots; ได้รับ ${rows.length}`,
    limitations: ['เป็น operational snapshots ไม่ใช่ผลทดสอบย้อนหลังหรือ performance'],
  };
}

async function loadRiskReport(): Promise<ReportPayload> {
  const results = await Promise.allSettled([
    api.get('/risk/decisions?limit=50'), api.get('/risk/account'), api.get('/risk/portfolio'), api.get('/risk/policy'), api.get('/risk/kill-switch'),
  ]);
  const decisions = results[0].status === 'fulfilled' ? parseRiskDecisions(results[0].value) : [];
  const account = results[1].status === 'fulfilled' ? parseAccountSnapshot(results[1].value) : null;
  const portfolio = results[2].status === 'fulfilled' ? parsePortfolioRisk(results[2].value) : null;
  const policy = results[3].status === 'fulfilled' ? parseRiskPolicy(results[3].value) : null;
  const killSwitch = results[4].status === 'fulfilled' ? parseKillSwitch(results[4].value) : null;
  if (results.every(isRejected)) throw new Error('Risk endpoints ไม่พร้อมใช้งานทั้งหมด');
  const rows: ExportRow[] = decisions.map((item) => ({
    id: item.id, as_of: item.as_of, candidate_id: item.candidate_id, strategy_id: item.strategy_id, profile_id: item.profile_id,
    symbol: item.symbol, direction: item.direction, decision: item.decision, requested_risk_pct: item.requested_risk_pct,
    approved_risk_pct: item.approved_risk_pct, requested_risk_amount: item.requested_risk_amount,
    approved_risk_amount: item.approved_risk_amount, position_size: item.position_size,
    exposure_before: item.portfolio_exposure_before, exposure_after: item.portfolio_exposure_after,
    reasons: item.reasons_th.join(' | '), warnings: item.warnings_th.join(' | '), blocked_reasons: item.blocked_reasons_th.join(' | '),
    market_source: item.market_provenance?.source ?? null, market_mode: item.market_provenance?.mode ?? null,
    news_state: item.news_provenance?.news_state ?? null, policy_version: item.policy_version,
  }));
  const failures = results.filter(isRejected).length;
  return {
    status: failures ? 'PARTIAL' : 'AVAILABLE', columns: Object.keys(rows[0] ?? { id: '' }).map((key) => ({ key, label: key.replaceAll('_', ' ').toUpperCase() })), rows,
    facts: [
      { label: 'Risk Decisions', value: String(decisions.length) }, { label: 'Account Source', value: account?.source ?? 'UNAVAILABLE' },
      { label: 'Portfolio Risk', value: portfolio ? `${portfolio.total_risk_pct}%` : 'UNAVAILABLE' },
      { label: 'Active Reservations', value: portfolio ? `${portfolio.active_reservations_count} (≠ positions)` : 'UNAVAILABLE' },
      { label: 'Policy', value: policy?.version ?? 'UNAVAILABLE' }, { label: 'Kill Switch', value: killSwitch?.state ?? 'UNAVAILABLE' },
    ],
    source: 'Risk Engine APIs', mode: account?.trading_mode ?? 'UNKNOWN', dataAsOf: portfolio?.as_of ?? account?.as_of ?? decisions[0]?.as_of ?? null,
    coverage: `ล่าสุดสูงสุด 50 decisions; ได้รับ ${rows.length} · ${5 - failures}/5 endpoints`,
    limitations: failures ? ['บาง risk endpoint ไม่พร้อม; แสดงส่วนที่โหลดสำเร็จโดยไม่แทนค่าข้อมูลที่ขาด'] : [],
  };
}

function calendarWindow(): string {
  const now = Date.now();
  const start = new Date(now - 86400000).toISOString();
  const end = new Date(now + 6 * 86400000).toISOString();
  return `start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&relevant_only=false`;
}

async function loadCalendarReport(): Promise<ReportPayload> {
  const calendar = parseCalendar(await api.get(`/calendar/economic?${calendarWindow()}`));
  const rows: ExportRow[] = calendar.events.map((item) => ({
    id: item.id, scheduled_at: item.scheduled_at, event_name: item.event_name, event_code: item.event_code,
    country: item.country, currency: item.currency, category: item.category, impact: item.impact, status: item.status,
    actual: item.actual, forecast: item.forecast, previous: item.previous, revised_previous: item.revised_previous ?? null,
    unit: item.unit, source: item.source, source_mode: item.source_mode, revision_version: item.revision_version,
    available_at: item.available_at, updated_at: item.updated_at,
  }));
  return {
    status: calendar.state === 'CALENDAR_UNAVAILABLE' ? 'UNAVAILABLE' : calendar.truncated ? 'PARTIAL' : 'AVAILABLE',
    columns: Object.keys(rows[0] ?? { id: '' }).map((key) => ({ key, label: key.replaceAll('_', ' ').toUpperCase() })), rows,
    facts: [{ label: 'Events', value: String(rows.length) }, { label: 'Source Mode', value: calendar.source_mode }, { label: 'Calendar State', value: calendar.state }, { label: 'Truncated', value: valueText(calendar.truncated) }],
    source: calendar.source, mode: calendar.source_mode, dataAsOf: calendar.as_of,
    coverage: `ช่วง 7 วัน สูงสุด 200 events${calendar.truncated ? ' · ผลลัพธ์ถูกตัด' : ''}`,
    limitations: ['แสดงเฉพาะ vintage ที่รู้ได้ ณ as_of; ไม่ใช้ข้อมูลอนาคต'],
  };
}

function macroPayload(news: NewsResponse): ReportPayload {
  const rows: ExportRow[] = [
    { field: 'news_regime', value: news.news_regime }, { field: 'macro_bias', value: news.macro_bias },
    { field: 'macro_strength', value: news.macro_strength }, { field: 'trade_policy_state', value: news.trade_policy_state },
    { field: 'spread_state', value: news.spread_state }, { field: 'volatility_state', value: news.volatility_state },
    { field: 'data_quality', value: news.data_quality ?? null }, { field: 'reason_codes', value: news.reason_codes.join(' | ') },
  ];
  for (const [strategyId, eligibility] of Object.entries(news.strategy_eligibility)) {
    rows.push({ field: `strategy_eligibility.${strategyId}`, value: eligibility });
  }
  return {
    status: news.calendar_state === 'CALENDAR_UNAVAILABLE' ? 'PARTIAL' : 'AVAILABLE',
    columns: [{ key: 'field', label: 'FIELD' }, { key: 'value', label: 'VALUE' }], rows,
    facts: [{ label: 'Macro Bias', value: news.macro_bias }, { label: 'Strength', value: news.macro_strength }, { label: 'News Regime', value: news.news_regime }, { label: 'Trade Policy', value: news.trade_policy_state }],
    source: news.source, mode: news.source_mode, dataAsOf: news.as_of,
    coverage: `${news.events.length} known events · ${Object.keys(news.strategy_eligibility).length} strategy eligibility states`,
    limitations: ['Macro Bias เป็นบริบทเชิงพรรณนา ไม่ใช่ Trading Signal หรือคำแนะนำให้ส่งคำสั่งซื้อขาย'],
  };
}

async function loadOperationalReport(): Promise<ReportPayload> {
  const results = await Promise.allSettled([
    api.get('/trade-candidates?limit=100'), api.get('/strategy/evaluations?limit=25'), api.get('/risk/decisions?limit=50'), api.get('/risk/account'), api.get('/risk/portfolio'),
  ]);
  if (results.every(isRejected)) throw new Error('Operational data endpoints ไม่พร้อมใช้งานทั้งหมด');
  const candidates = results[0].status === 'fulfilled' ? parseCandidateList(results[0].value) : [];
  const evaluations = results[1].status === 'fulfilled' && Array.isArray(results[1].value) ? results[1].value.map(parseStrategy) : [];
  const decisions = results[2].status === 'fulfilled' ? parseRiskDecisions(results[2].value) : [];
  const account = results[3].status === 'fulfilled' ? parseAccountSnapshot(results[3].value) : null;
  const portfolio = results[4].status === 'fulfilled' ? parsePortfolioRisk(results[4].value) : null;
  const rows: ExportRow[] = [
    { metric: 'candidate_count', value: candidates.length, scope: 'latest 100 maximum', interpretation: 'Candidates, not trades' },
    { metric: 'ready_candidate_count', value: candidates.filter((item) => item.status === 'READY').length, scope: 'loaded candidates', interpretation: 'READY state, not execution' },
    { metric: 'evaluation_snapshot_count', value: evaluations.length, scope: 'latest 25 maximum', interpretation: 'NOT A BACKTEST' },
    { metric: 'risk_decision_count', value: decisions.length, scope: 'latest 50 maximum', interpretation: 'Decisions, not trades' },
    { metric: 'active_risk_reservations', value: portfolio?.active_reservations_count ?? null, scope: 'current portfolio snapshot', interpretation: 'Reservations ≠ positions' },
    { metric: 'account_source', value: account?.source ?? null, scope: 'current account snapshot', interpretation: 'Source-provenanced' },
    { metric: 'executed_trade_count', value: null, scope: 'no ledger', interpretation: 'NOT AVAILABLE' },
  ];
  const failures = results.filter(isRejected).length;
  return {
    status: 'PARTIAL', columns: [{ key: 'metric', label: 'METRIC' }, { key: 'value', label: 'VALUE' }, { key: 'scope', label: 'COVERAGE' }, { key: 'interpretation', label: 'INTERPRETATION' }], rows,
    facts: [{ label: 'Candidate Activity', value: String(candidates.length) }, { label: 'Evaluation Activity', value: String(evaluations.length) }, { label: 'Risk Decisions', value: String(decisions.length) }, { label: 'Executed Performance', value: 'NOT AVAILABLE' }],
    source: 'Candidate + Strategy + Risk APIs', mode: account?.trading_mode ?? 'ANALYSIS ONLY', dataAsOf: portfolio?.as_of ?? account?.as_of ?? null,
    coverage: `bounded operational datasets · ${5 - failures}/5 endpoints`,
    limitations: ['Operational activity ไม่ใช่ trading performance', 'ไม่มี executed trade ledger จึงไม่คำนวณ P&L, win rate หรือ equity curve'],
  };
}

async function fetchReport(id: ReportId): Promise<ReportPayload> {
  if (id === 'system') return loadSystemReport();
  if (id === 'market') return loadMarketReport();
  if (id === 'candidates') return loadCandidatesReport();
  if (id === 'evaluations') return loadEvaluationsReport();
  if (id === 'risk') return loadRiskReport();
  if (id === 'calendar') return loadCalendarReport();
  if (id === 'macro') return macroPayload(parseNews(await api.get('/news/context')));
  if (id === 'operational') return loadOperationalReport();
  return staticUnavailable(id);
}

const STATUS_STYLE: Record<ReportStatus, string> = {
  AVAILABLE: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-300',
  PARTIAL: 'border-amber-400/30 bg-amber-400/10 text-amber-200',
  STALE: 'border-orange-400/30 bg-orange-400/10 text-orange-200',
  UNAVAILABLE: 'border-rose-400/30 bg-rose-400/10 text-rose-200',
  'NOT IMPLEMENTED': 'border-slate-500/40 bg-slate-500/10 text-slate-300',
};

function StatusBadge({ status }: { status: ReportStatus }) {
  return <span className={`inline-flex rounded-full border px-2 py-1 text-[10px] font-semibold tracking-wide ${STATUS_STYLE[status]}`}>{status}</span>;
}

export function ReportsScreen() {
  const [selected, setSelected] = useState<ReportId>('system');
  const [states, setStates] = useState<Record<ReportId, ReportState>>(INITIAL_STATES);
  const [refreshKey, setRefreshKey] = useState(0);
  const [filters, setFilters] = useState({ strategy: '', profile: '', state: '', direction: '', symbol: '', date: '', impact: '' });
  const requestSequence = useRef<Record<ReportId, number>>({ system: 0, market: 0, candidates: 0, evaluations: 0, risk: 0, calendar: 0, macro: 0, operational: 0, ai: 0, execution: 0 });
  const definition = REPORTS.find((report) => report.id === selected)!;
  const state = states[selected];

  useEffect(() => {
    const sequence = ++requestSequence.current[selected];
    void fetchReport(selected).then(
      (data) => {
        if (requestSequence.current[selected] !== sequence) return;
        setStates((current) => ({ ...current, [selected]: { phase: 'ready', data, error: null, loadedAt: new Date().toISOString() } }));
      },
      (error) => {
        if (requestSequence.current[selected] !== sequence) return;
        setStates((current) => ({ ...current, [selected]: { ...current[selected], phase: 'error', error: errorText(error), loadedAt: new Date().toISOString() } }));
      },
    );
  }, [selected, refreshKey]);

  function selectReport(id: ReportId) {
    if (id === selected) return;
    setFilters({ strategy: '', profile: '', state: '', direction: '', symbol: '', date: '', impact: '' });
    setStates((current) => ({ ...current, [id]: { ...current[id], phase: 'loading', error: null } }));
    setSelected(id);
  }

  function refreshReport() {
    setStates((current) => ({
      ...current,
      [selected]: { ...current[selected], phase: 'loading', error: null },
    }));
    setRefreshKey((key) => key + 1);
  }

  const visibleRows = useMemo(() => {
    const rows = state.data?.rows ?? [];
    return rows.filter((row) => {
      if (filters.strategy && row.strategy_id !== filters.strategy) return false;
      if (filters.profile && row.profile_id !== filters.profile) return false;
      if (filters.state && row.state !== filters.state && row.decision !== filters.state && row.status !== filters.state) return false;
      if (filters.direction && row.direction !== filters.direction) return false;
      if (filters.symbol && !String(row.symbol ?? '').toLowerCase().includes(filters.symbol.toLowerCase())) return false;
      if (filters.impact && row.impact !== filters.impact) return false;
      if (filters.date) {
        const timestamp = String(row.detected_at ?? row.scheduled_at ?? row.as_of ?? row.context_as_of ?? '');
        if (!timestamp.startsWith(filters.date)) return false;
      }
      return true;
    });
  }, [filters, state.data]);

  const options = (key: string) => Array.from(new Set((state.data?.rows ?? []).map((row) => String(row[key] ?? '')).filter(Boolean))).sort();

  function exportReport(extension: 'csv' | 'json') {
    if (!state.data || !visibleRows.length) return;
    const metadata: ReportExportMetadata = {
      report_type: selected, generated_at: new Date().toISOString(), data_as_of: state.data.dataAsOf,
      source: state.data.source, mode: state.data.mode, coverage: state.data.coverage,
      filters: Object.fromEntries(Object.entries(filters).filter(([, value]) => value)),
    };
    const content = extension === 'csv' ? buildCsv(state.data.columns, visibleRows) : buildJsonExport(metadata, visibleRows);
    downloadTextArtifact(reportFilename(selected, extension), content, extension === 'csv' ? 'text/csv' : 'application/json');
  }

  const status = state.phase === 'error' ? 'UNAVAILABLE' : state.data?.status ?? definition.defaultStatus;

  return (
    <main className="mx-auto min-w-0 max-w-[1680px] space-y-5 p-4 text-slate-200 sm:p-6 lg:p-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-[10px] font-semibold uppercase tracking-[0.24em] text-amber-300/80">FC-09 · Reporting only</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-white sm:text-3xl">Reports Workspace</h1>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">รายงานจากข้อมูลจริงที่ระบบมี พร้อม provenance, coverage และข้อจำกัดชัดเจน ไม่มีการสร้าง trade หรือ performance metric ทดแทน</p>
        </div>
        <div className="rounded-lg border border-amber-400/25 bg-amber-400/10 px-4 py-3 text-right text-xs text-amber-100">
          <div className="font-semibold">REPORTING ONLY · NO ORDER ACTIONS</div>
          <div className="mt-1 text-amber-200/70">Report generation never sends orders</div>
        </div>
      </header>

      <section aria-label="Report Center" className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {REPORTS.map((report) => {
          const current = states[report.id];
          const cardStatus: ReportStatus = current.phase === 'error' ? 'UNAVAILABLE' : current.data?.status ?? report.defaultStatus;
          return (
            <button key={report.id} type="button" onClick={() => selectReport(report.id)} aria-pressed={selected === report.id}
              className={`min-h-36 rounded-xl border p-4 text-left transition ${selected === report.id ? 'border-amber-400/60 bg-amber-400/[0.08]' : 'border-slate-700/70 bg-[#101722] hover:border-slate-500'}`}>
              <div className="flex items-start justify-between gap-2"><span className="text-sm font-semibold text-slate-100">{report.title}</span><StatusBadge status={cardStatus} /></div>
              <p className="mt-3 text-xs leading-5 text-slate-400">{report.subtitle}</p>
              <p className="mt-3 break-words font-mono text-[10px] text-slate-500">{report.endpoint}</p>
            </button>
          );
        })}
      </section>

      <section className="overflow-hidden rounded-xl border border-slate-700/70 bg-[#0e1621]">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-700/60 p-4 sm:p-5">
          <div>
            <div className="flex flex-wrap items-center gap-3"><h2 className="text-lg font-semibold text-white">{definition.title}</h2><StatusBadge status={status} /></div>
            <p className="mt-1 text-xs text-slate-400">{definition.subtitle}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={refreshReport} disabled={state.phase === 'loading'} className="rounded-md border border-slate-600 px-3 py-2 text-xs hover:bg-slate-800 disabled:opacity-50">{state.phase === 'loading' ? 'กำลังโหลด…' : 'Refresh'}</button>
            <button type="button" onClick={() => exportReport('csv')} disabled={!visibleRows.length || state.phase !== 'ready'} className="rounded-md border border-emerald-500/40 px-3 py-2 text-xs text-emerald-300 disabled:opacity-40">Export CSV</button>
            <button type="button" onClick={() => exportReport('json')} disabled={!visibleRows.length || state.phase !== 'ready'} className="rounded-md border border-sky-500/40 px-3 py-2 text-xs text-sky-300 disabled:opacity-40">Export JSON</button>
            <button type="button" disabled title="PDF export is not implemented" className="rounded-md border border-slate-700 px-3 py-2 text-xs text-slate-500">PDF · NOT IMPLEMENTED</button>
          </div>
        </div>

        {state.phase === 'loading' && !state.data && <div className="grid min-h-56 place-items-center p-8 text-sm text-amber-200" role="status">กำลังโหลด {definition.title} จากแหล่งข้อมูลจริง…</div>}
        {state.phase === 'error' && <div className="m-5 rounded-lg border border-rose-500/30 bg-rose-500/10 p-5" role="alert"><div className="font-semibold text-rose-200">UNAVAILABLE</div><p className="mt-2 text-sm text-rose-100/80">{state.error}</p><p className="mt-2 text-xs text-slate-400">ข้อผิดพลาดนี้จำกัดอยู่ที่รายงานหมวดนี้ รายงานหมวดอื่นยังเปิดได้ตามปกติ</p></div>}

        {state.data && (
          <div className="space-y-5 p-4 sm:p-5" aria-live="polite">
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 xl:grid-cols-6">
              {state.data.facts.map((fact) => <div key={fact.label} className="min-w-0 rounded-lg border border-slate-700/60 bg-slate-900/50 p-3"><div className="text-[10px] uppercase tracking-wide text-slate-500">{fact.label}</div><div className="mt-2 break-words text-sm font-semibold text-slate-100">{fact.value}</div></div>)}
            </div>

            {(selected === 'candidates' || selected === 'risk' || selected === 'calendar') && (
              <div className="flex flex-wrap gap-2 rounded-lg border border-slate-700/50 bg-slate-900/30 p-3" aria-label="Report filters">
                {selected === 'candidates' && <><FilterSelect label="Strategy" value={filters.strategy} values={options('strategy_id')} onChange={(strategy) => setFilters((f) => ({ ...f, strategy }))} /><FilterSelect label="Profile" value={filters.profile} values={options('profile_id')} onChange={(profile) => setFilters((f) => ({ ...f, profile }))} /><FilterSelect label="State" value={filters.state} values={options('state')} onChange={(stateValue) => setFilters((f) => ({ ...f, state: stateValue }))} /><FilterSelect label="Direction" value={filters.direction} values={options('direction')} onChange={(direction) => setFilters((f) => ({ ...f, direction }))} /></>}
                {selected === 'risk' && <FilterSelect label="Decision" value={filters.state} values={options('decision')} onChange={(stateValue) => setFilters((f) => ({ ...f, state: stateValue }))} />}
                {selected === 'calendar' && <><FilterSelect label="Impact" value={filters.impact} values={options('impact')} onChange={(impact) => setFilters((f) => ({ ...f, impact }))} /><FilterSelect label="Status" value={filters.state} values={options('status')} onChange={(stateValue) => setFilters((f) => ({ ...f, state: stateValue }))} /></>}
                {(selected === 'candidates' || selected === 'risk') && <input aria-label="Symbol filter" placeholder="Symbol" value={filters.symbol} onChange={(event) => setFilters((f) => ({ ...f, symbol: event.target.value }))} className="min-w-28 rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-xs outline-none focus:border-amber-400" />}
                <input aria-label="Date filter" type="date" value={filters.date} onChange={(event) => setFilters((f) => ({ ...f, date: event.target.value }))} className="rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-xs outline-none focus:border-amber-400" />
                <button type="button" onClick={() => setFilters({ strategy: '', profile: '', state: '', direction: '', symbol: '', date: '', impact: '' })} className="rounded-md border border-slate-600 px-3 py-2 text-xs">ล้างตัวกรอง</button>
              </div>
            )}

            <div className="hidden max-w-full overflow-auto rounded-lg border border-slate-700/60 lg:block">
              <table className="w-full min-w-max border-collapse text-left text-xs">
                <thead className="sticky top-0 bg-slate-900 text-[10px] uppercase tracking-wide text-slate-400"><tr>{state.data.columns.map((column) => <th key={column.key} className="border-b border-slate-700 px-3 py-3 font-medium">{column.label}</th>)}</tr></thead>
                <tbody>{visibleRows.map((row, index) => <tr key={`${selected}-${index}`} className="border-b border-slate-800/80 align-top hover:bg-white/[0.02]">{state.data!.columns.map((column) => <td key={column.key} className="max-w-80 whitespace-pre-wrap break-words px-3 py-3 text-slate-300">{valueText(row[column.key])}</td>)}</tr>)}</tbody>
              </table>
            </div>
            <div className="grid gap-3 lg:hidden">{visibleRows.map((row, index) => <article key={`${selected}-card-${index}`} className="rounded-lg border border-slate-700/60 bg-slate-900/40 p-4">{state.data!.columns.map((column) => <div key={column.key} className="grid grid-cols-[minmax(90px,0.8fr)_minmax(0,1.4fr)] gap-3 border-b border-slate-800 py-2 last:border-0"><span className="text-[10px] uppercase text-slate-500">{column.label}</span><span className="break-words text-xs text-slate-200">{valueText(row[column.key])}</span></div>)}</article>)}</div>
            {!visibleRows.length && <div className="rounded-lg border border-dashed border-slate-700 p-8 text-center text-sm text-slate-400">ไม่มี record ใน coverage/ตัวกรองที่เลือก — ระบบไม่สร้างข้อมูลตัวอย่างทดแทน</div>}

            <div className="grid gap-3 border-t border-slate-700/60 pt-4 text-xs text-slate-400 md:grid-cols-2 xl:grid-cols-4">
              <Meta label="Data as of" value={formatTime(state.data.dataAsOf)} /><Meta label="Report loaded" value={formatTime(state.loadedAt)} /><Meta label="Source / Mode" value={`${state.data.source} · ${state.data.mode}`} /><Meta label="Coverage" value={state.data.coverage} />
            </div>
            {state.data.limitations.length > 0 && <div className="rounded-lg border border-amber-500/25 bg-amber-500/[0.06] p-4"><h3 className="text-xs font-semibold text-amber-200">ข้อจำกัดและความหมายของข้อมูล</h3><ul className="mt-2 list-disc space-y-1 pl-5 text-xs leading-5 text-slate-400">{state.data.limitations.map((item) => <li key={item}>{item}</li>)}</ul></div>}
            {definition.drilldown && <Link href={definition.drilldown} className="inline-flex rounded-md border border-amber-400/35 px-3 py-2 text-xs text-amber-200 hover:bg-amber-400/10">เปิด workspace ต้นทาง → {definition.drilldown}</Link>}
          </div>
        )}
      </section>

      <footer className="rounded-lg border border-slate-700/60 bg-slate-900/40 p-4 text-xs leading-5 text-slate-400">
        <strong className="text-slate-200">Data Truthfulness:</strong> Null แยกจาก zero, Candidate/Risk Decision/Reservation ไม่ใช่ Executed Trade, Evaluation Activity ไม่ใช่ Backtest และ export มีเฉพาะฟิลด์รายงานที่กำหนดไว้โดยไม่รวม token หรือข้อมูลรับรองใด ๆ
      </footer>
    </main>
  );
}

function FilterSelect({ label, value, values, onChange }: { label: string; value: string; values: string[]; onChange: (value: string) => void }) {
  return <label className="grid gap-1 text-[10px] uppercase text-slate-500"><span>{label}</span><select value={value} onChange={(event) => onChange(event.target.value)} className="min-w-32 rounded-md border border-slate-600 bg-slate-950 px-3 py-2 text-xs normal-case text-slate-200 outline-none focus:border-amber-400"><option value="">ทั้งหมด</option>{values.map((item) => <option key={item} value={item}>{item}</option>)}</select></label>;
}

function Meta({ label, value }: { label: string; value: string }) {
  return <div className="min-w-0"><div className="text-[10px] uppercase tracking-wide text-slate-500">{label}</div><div className="mt-1 break-words text-slate-300">{value}</div></div>;
}
