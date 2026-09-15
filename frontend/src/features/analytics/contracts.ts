/**
 * Phase 8 Performance & Analytics contracts and descriptive analytical parsers.
 *
 * Strict product invariants:
 * - Never fabricates executed trading metrics (Win Rate, Net P&L, Profit Factor, Expectancy, Sharpe, Max Drawdown).
 * - Never substitutes 0 or 0% for missing execution datasets.
 * - Clearly separates Candidate/Risk Analytical Activity from Executed Trading Performance.
 * - Computes truthful descriptive aggregations without altering business logic.
 */

import type { SetupCandidate, StrategyResponse } from '@/types/strategy.generated';
import type { RiskDecisionData } from '@/features/risk/contracts';

export type CanonicalCandidateState =
  | 'DETECTED'
  | 'WAITING_CONFIRMATION'
  | 'READY'
  | 'BLOCKED_CONTEXT'
  | 'NO_TRADE'
  | 'INVALIDATED'
  | 'EXPIRED'
  | 'SUPERSEDED';

export const CANONICAL_CANDIDATE_STATES: CanonicalCandidateState[] = [
  'DETECTED',
  'WAITING_CONFIRMATION',
  'READY',
  'BLOCKED_CONTEXT',
  'NO_TRADE',
  'INVALIDATED',
  'EXPIRED',
  'SUPERSEDED',
];

export interface ExtendedAccountSnapshot {
  id: string;
  account_id: string;
  balance: string;
  equity: string;
  free_margin: string | null;
  daily_realized_pnl: string;
  weekly_realized_pnl: string;
  floating_pnl: string | null;
  peak_equity: string;
  open_risk_pct: string;
  reserved_risk_pct: string;
  consecutive_losses: number;
  last_loss_at: string | null;
  cooldown_until: string | null;
  open_positions_count: number;
  state_version: number;
  state_updated_at: string | null;
  observed_at: string | null;
  trading_mode: string;
  source: string;
  as_of: string;
}

export function parseExtendedAccountSnapshot(raw: unknown): ExtendedAccountSnapshot {
  if (!raw || typeof raw !== 'object') {
    throw new Error('Account snapshot must be an object');
  }
  const d = raw as Record<string, unknown>;
  return {
    id: String(d.id || ''),
    account_id: String(d.account_id || 'default_paper_account'),
    balance: String(d.balance ?? '0.00'),
    equity: String(d.equity ?? '0.00'),
    free_margin: d.free_margin != null ? String(d.free_margin) : null,
    daily_realized_pnl: String(d.daily_realized_pnl ?? '0.00'),
    weekly_realized_pnl: String(d.weekly_realized_pnl ?? '0.00'),
    floating_pnl: d.floating_pnl != null ? String(d.floating_pnl) : null,
    peak_equity: String(d.peak_equity ?? d.equity ?? '0.00'),
    open_risk_pct: String(d.open_risk_pct ?? '0.0000'),
    reserved_risk_pct: String(d.reserved_risk_pct ?? '0.0000'),
    consecutive_losses: Number(d.consecutive_losses || 0),
    last_loss_at: d.last_loss_at != null ? String(d.last_loss_at) : null,
    cooldown_until: d.cooldown_until != null ? String(d.cooldown_until) : null,
    open_positions_count: Number(d.open_positions_count || 0),
    state_version: Number(d.state_version || 1),
    state_updated_at: d.state_updated_at != null ? String(d.state_updated_at) : null,
    observed_at: d.observed_at != null ? String(d.observed_at) : null,
    trading_mode: String(d.trading_mode || 'PAPER'),
    source: String(d.source || 'CONFIGURED_PAPER'),
    as_of: String(d.as_of || new Date().toISOString()),
  };
}

export interface SnapshotDrawdownResult {
  drawdownPct: number;
  displayPct: string;
  isAvailable: boolean;
}

/**
 * Calculates current account snapshot drawdown: (peak_equity - equity) / peak_equity.
 * Strictly labeled CURRENT ACCOUNT SNAPSHOT DRAWDOWN, never historical Max Drawdown.
 */
export function calculateSnapshotDrawdown(
  equityStr: string | number,
  peakEquityStr: string | number
): SnapshotDrawdownResult {
  const equity = Number(equityStr);
  const peak = Number(peakEquityStr);

  if (!Number.isFinite(equity) || !Number.isFinite(peak) || peak <= 0) {
    return { drawdownPct: 0, displayPct: 'N/A', isAvailable: false };
  }

  if (peak <= equity) {
    return { drawdownPct: 0, displayPct: '0.00%', isAvailable: true };
  }

  const dd = ((peak - equity) / peak) * 100;
  return {
    drawdownPct: dd,
    displayPct: `${dd.toFixed(2)}%`,
    isAvailable: true,
  };
}

export interface CandidateStrategyStat {
  strategyId: string;
  count: number;
  readyCount: number;
  blockedCount: number;
  avgEvidenceScore: number | null;
  directions: {
    LONG: number;
    SHORT: number;
    NO_TRADE: number;
  };
}

export interface CandidateAnalyticsSummary {
  total: number;
  byState: Record<CanonicalCandidateState, number>;
  byStatePct: Record<CanonicalCandidateState, number>;
  byStrategy: Record<string, CandidateStrategyStat>;
  byProfile: Record<string, number>;
  byDirection: {
    LONG: { count: number; pct: number };
    SHORT: { count: number; pct: number };
    NO_TRADE: { count: number; pct: number };
  };
  planCount: number;
  avgEvidenceScore: number | null;
  coverageNotice: string;
}

export function computeCandidateAnalytics(
  candidates: SetupCandidate[],
  maxLoaded: number = 100
): CandidateAnalyticsSummary {
  const total = candidates.length;
  const byState: Record<CanonicalCandidateState, number> = {
    DETECTED: 0,
    WAITING_CONFIRMATION: 0,
    READY: 0,
    BLOCKED_CONTEXT: 0,
    NO_TRADE: 0,
    INVALIDATED: 0,
    EXPIRED: 0,
    SUPERSEDED: 0,
  };

  const byStrategy: Record<string, CandidateStrategyStat> = {};
  const byProfile: Record<string, number> = {};
  const byDirection = {
    LONG: { count: 0, pct: 0 },
    SHORT: { count: 0, pct: 0 },
    NO_TRADE: { count: 0, pct: 0 },
  };

  let planCount = 0;
  let evidenceScoreSum = 0;
  let evidenceScoreCount = 0;

  const strategyScores: Record<string, { sum: number; count: number }> = {};

  for (const c of candidates) {
    // State counts
    const st = c.status as CanonicalCandidateState;
    if (st in byState) {
      byState[st] += 1;
    }

    // Direction counts
    const dir = c.direction as 'LONG' | 'SHORT' | 'NO_TRADE';
    if (dir === 'LONG' || dir === 'SHORT' || dir === 'NO_TRADE') {
      byDirection[dir].count += 1;
    }

    // Profile counts
    const prof = c.profile_id || 'UNKNOWN_PROFILE';
    byProfile[prof] = (byProfile[prof] || 0) + 1;

    // Strategy counts
    const strat = c.strategy_id || 'UNKNOWN_STRATEGY';
    if (!byStrategy[strat]) {
      byStrategy[strat] = {
        strategyId: strat,
        count: 0,
        readyCount: 0,
        blockedCount: 0,
        avgEvidenceScore: null,
        directions: { LONG: 0, SHORT: 0, NO_TRADE: 0 },
      };
      strategyScores[strat] = { sum: 0, count: 0 };
    }
    byStrategy[strat].count += 1;
    if (st === 'READY') byStrategy[strat].readyCount += 1;
    if (st === 'BLOCKED_CONTEXT') byStrategy[strat].blockedCount += 1;
    if (dir === 'LONG') byStrategy[strat].directions.LONG += 1;
    if (dir === 'SHORT') byStrategy[strat].directions.SHORT += 1;
    if (dir === 'NO_TRADE') byStrategy[strat].directions.NO_TRADE += 1;

    // Plan & Evidence scores
    if (c.plan) {
      planCount += 1;
      const score = Number(c.plan.score);
      if (Number.isFinite(score)) {
        evidenceScoreSum += score;
        evidenceScoreCount += 1;
        strategyScores[strat].sum += score;
        strategyScores[strat].count += 1;
      }
    }
  }

  // Calculate percentages
  const byStatePct: Record<CanonicalCandidateState, number> = {
    DETECTED: 0,
    WAITING_CONFIRMATION: 0,
    READY: 0,
    BLOCKED_CONTEXT: 0,
    NO_TRADE: 0,
    INVALIDATED: 0,
    EXPIRED: 0,
    SUPERSEDED: 0,
  };

  if (total > 0) {
    for (const key of CANONICAL_CANDIDATE_STATES) {
      byStatePct[key] = Math.round((byState[key] / total) * 1000) / 10;
    }
    byDirection.LONG.pct = Math.round((byDirection.LONG.count / total) * 1000) / 10;
    byDirection.SHORT.pct = Math.round((byDirection.SHORT.count / total) * 1000) / 10;
    byDirection.NO_TRADE.pct = Math.round((byDirection.NO_TRADE.count / total) * 1000) / 10;
  }

  // Strategy average scores
  for (const strat of Object.keys(byStrategy)) {
    const s = strategyScores[strat];
    if (s && s.count > 0) {
      byStrategy[strat].avgEvidenceScore = Math.round((s.sum / s.count) * 100) / 100;
    }
  }

  const avgEvidenceScore =
    evidenceScoreCount > 0 ? Math.round((evidenceScoreSum / evidenceScoreCount) * 100) / 100 : null;

  return {
    total,
    byState,
    byStatePct,
    byStrategy,
    byProfile,
    byDirection,
    planCount,
    avgEvidenceScore,
    coverageNotice: `แสดงข้อมูลจาก Candidate ล่าสุด ${total} รายการ (จำกัดสูงสุด ${maxLoaded})`,
  };
}

export interface RiskDecisionAnalyticsSummary {
  total: number;
  byDecision: {
    APPROVED: { count: number; pct: number };
    REDUCED: { count: number; pct: number };
    BLOCKED: { count: number; pct: number };
  };
  avgRequestedRiskPct: number | null;
  avgApprovedRiskPct: number | null;
  totalRequestedRiskAmount: number;
  totalApprovedRiskAmount: number;
  reducedCount: number;
  topBlockedReasons: Array<{ reason: string; count: number }>;
  topWarnings: Array<{ warning: string; count: number }>;
  byStrategy: Record<string, { total: number; approved: number; reduced: number; blocked: number }>;
  byDirection: Record<'LONG' | 'SHORT', { total: number; approved: number; reduced: number; blocked: number }>;
  coverageNotice: string;
}

export function computeRiskDecisionAnalytics(
  decisions: RiskDecisionData[],
  maxLoaded: number = 50
): RiskDecisionAnalyticsSummary {
  const total = decisions.length;
  const byDecision = {
    APPROVED: { count: 0, pct: 0 },
    REDUCED: { count: 0, pct: 0 },
    BLOCKED: { count: 0, pct: 0 },
  };

  let reqRiskPctSum = 0;
  let reqRiskPctCount = 0;
  let appRiskPctSum = 0;
  let appRiskPctCount = 0;
  let totalReqAmount = 0;
  let totalAppAmount = 0;
  let reducedCount = 0;

  const blockedReasonMap: Record<string, number> = {};
  const warningMap: Record<string, number> = {};
  const byStrategy: Record<string, { total: number; approved: number; reduced: number; blocked: number }> = {};
  const byDirection: Record<'LONG' | 'SHORT', { total: number; approved: number; reduced: number; blocked: number }> = {
    LONG: { total: 0, approved: 0, reduced: 0, blocked: 0 },
    SHORT: { total: 0, approved: 0, reduced: 0, blocked: 0 },
  };

  for (const d of decisions) {
    // Decision status
    if (d.decision === 'APPROVED') byDecision.APPROVED.count += 1;
    else if (d.decision === 'REDUCED') {
      byDecision.REDUCED.count += 1;
      reducedCount += 1;
    } else if (d.decision === 'BLOCKED') byDecision.BLOCKED.count += 1;

    // Requested & Approved risk
    const reqPct = Number(d.requested_risk_pct);
    if (Number.isFinite(reqPct)) {
      reqRiskPctSum += reqPct;
      reqRiskPctCount += 1;
    }
    const appPct = Number(d.approved_risk_pct);
    if (Number.isFinite(appPct)) {
      appRiskPctSum += appPct;
      appRiskPctCount += 1;
    }

    const reqAmt = Number(d.requested_risk_amount);
    if (Number.isFinite(reqAmt)) totalReqAmount += reqAmt;
    const appAmt = Number(d.approved_risk_amount);
    if (Number.isFinite(appAmt)) totalAppAmount += appAmt;

    // Blocked reasons
    if (Array.isArray(d.blocked_reasons_th)) {
      for (const r of d.blocked_reasons_th) {
        if (r && typeof r === 'string') {
          blockedReasonMap[r] = (blockedReasonMap[r] || 0) + 1;
        }
      }
    }

    // Warnings
    if (Array.isArray(d.warnings_th)) {
      for (const w of d.warnings_th) {
        if (w && typeof w === 'string') {
          warningMap[w] = (warningMap[w] || 0) + 1;
        }
      }
    }

    // By Strategy
    const strat = d.strategy_id || 'UNKNOWN';
    if (!byStrategy[strat]) {
      byStrategy[strat] = { total: 0, approved: 0, reduced: 0, blocked: 0 };
    }
    byStrategy[strat].total += 1;
    if (d.decision === 'APPROVED') byStrategy[strat].approved += 1;
    else if (d.decision === 'REDUCED') byStrategy[strat].reduced += 1;
    else if (d.decision === 'BLOCKED') byStrategy[strat].blocked += 1;

    // By Direction
    const dir = d.direction as 'LONG' | 'SHORT';
    if (dir === 'LONG' || dir === 'SHORT') {
      byDirection[dir].total += 1;
      if (d.decision === 'APPROVED') byDirection[dir].approved += 1;
      else if (d.decision === 'REDUCED') byDirection[dir].reduced += 1;
      else if (d.decision === 'BLOCKED') byDirection[dir].blocked += 1;
    }
  }

  // Percentages
  if (total > 0) {
    byDecision.APPROVED.pct = Math.round((byDecision.APPROVED.count / total) * 1000) / 10;
    byDecision.REDUCED.pct = Math.round((byDecision.REDUCED.count / total) * 1000) / 10;
    byDecision.BLOCKED.pct = Math.round((byDecision.BLOCKED.count / total) * 1000) / 10;
  }

  const topBlockedReasons = Object.entries(blockedReasonMap)
    .map(([reason, count]) => ({ reason, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);

  const topWarnings = Object.entries(warningMap)
    .map(([warning, count]) => ({ warning, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5);

  return {
    total,
    byDecision,
    avgRequestedRiskPct: reqRiskPctCount > 0 ? Math.round((reqRiskPctSum / reqRiskPctCount) * 1000) / 1000 : null,
    avgApprovedRiskPct: appRiskPctCount > 0 ? Math.round((appRiskPctSum / appRiskPctCount) * 1000) / 1000 : null,
    totalRequestedRiskAmount: Math.round(totalReqAmount * 100) / 100,
    totalApprovedRiskAmount: Math.round(totalAppAmount * 100) / 100,
    reducedCount,
    topBlockedReasons,
    topWarnings,
    byStrategy,
    byDirection,
    coverageNotice: `แสดงข้อมูลจาก Risk Decision ล่าสุด ${total} รายการ (จำกัดสูงสุด ${maxLoaded})`,
  };
}

export interface EvaluationActivityItem {
  asOf: string;
  generatedAt: string;
  candidateCount: number;
  readyCount: number;
  blockedCount: number;
  configId: string;
  identityVersion: string;
  isStale: boolean;
}

export interface EvaluationActivitySummary {
  totalEvaluations: number;
  items: EvaluationActivityItem[];
  coverageNotice: string;
}

export function computeEvaluationActivity(
  evaluations: StrategyResponse[],
  maxLoaded: number = 25
): EvaluationActivitySummary {
  const items: EvaluationActivityItem[] = evaluations.map((ev) => {
    const cands = ev.evaluation?.candidates || [];
    let ready = 0;
    let blocked = 0;
    for (const c of cands) {
      if (c.status === 'READY') ready += 1;
      if (c.status === 'BLOCKED_CONTEXT') blocked += 1;
    }
    return {
      asOf: ev.evaluation?.context?.as_of || ev.generated_at,
      generatedAt: ev.generated_at,
      candidateCount: cands.length,
      readyCount: ready,
      blockedCount: blocked,
      configId: ev.evaluation?.context?.config_id || 'unknown',
      identityVersion: ev.evaluation?.identity_version || 'evaluation-1.0.0',
      isStale: Boolean(ev.stale),
    };
  });

  return {
    totalEvaluations: evaluations.length,
    items,
    coverageNotice: `แสดงข้อมูลล่าสุด ${evaluations.length} Evaluation (จำกัดสูงสุด ${maxLoaded}) — ข้อมูลกิจกรรมการประเมินเชิงปฏิบัติการ (ไม่ใช่ Backtest)`,
  };
}

export type ReadinessState = 'READY' | 'LIMITED' | 'NOT_IMPLEMENTED' | 'NOT_AVAILABLE';

export interface PerformanceReadinessItem {
  name: string;
  nameTh: string;
  status: ReadinessState;
  phase: string;
  detailsTh: string;
}

export const PERFORMANCE_READINESS_ITEMS: PerformanceReadinessItem[] = [
  {
    name: 'Candidate History',
    nameTh: 'ประวัติ Trade Candidate',
    status: 'READY',
    phase: 'Phase 4',
    detailsTh: 'บันทึกและสืบค้นผลตรวจจับ Setup Candidate จากกลยุทธ์ STRAT01–STRAT06 ได้พร้อมใช้งาน',
  },
  {
    name: 'Strategy Evaluation History',
    nameTh: 'ประวัติ Strategy Evaluation',
    status: 'LIMITED',
    phase: 'Phase 4',
    detailsTh: 'พร้อมใช้งานสำหรับ Snapshot สูงสุด 25 การประเมินล่าสุด (ไม่ครอบคลุมประวัติย้อนหลังทั้งหมด)',
  },
  {
    name: 'Risk Decision History',
    nameTh: 'ประวัติ Risk Decision',
    status: 'READY',
    phase: 'Phase 5',
    detailsTh: 'บันทึกการพิจารณาความเสี่ยง (APPROVED / REDUCED / BLOCKED) พร้อม Reason Codes และการจองโควต้า',
  },
  {
    name: 'Account Snapshot',
    nameTh: 'ภาพรวมพอร์ตและความเสี่ยงบัญชี',
    status: 'READY',
    phase: 'Phase 5',
    detailsTh: 'อ่านค่า Balance, Equity, Risk Capacity และ Drawdown เชิง Snapshot แบบ Read-Only',
  },
  {
    name: 'Paper Order Ledger',
    nameTh: 'สมุดบันทึกคำสั่ง Paper Trading',
    status: 'NOT_IMPLEMENTED',
    phase: 'Phase 7',
    detailsTh: 'ยังไม่เริ่มพัฒนา — ระบบจำลอง Order Execution และ Fill Management ในโหมด Paper',
  },
  {
    name: 'Executed Trade History',
    nameTh: 'ประวัติการเทรดที่เกิดการ Execution จริง',
    status: 'NOT_IMPLEMENTED',
    phase: 'Phase 7',
    detailsTh: 'ยังไม่มีชุดข้อมูลการจับคู่คำสั่งซื้อขายจริง (Zero Executed Trades)',
  },
  {
    name: 'Position Lifecycle',
    nameTh: 'การจัดการวงจรชีวิต Position / OMS',
    status: 'NOT_IMPLEMENTED',
    phase: 'Phase 7',
    detailsTh: 'ยังไม่มีระบบติดตามสถานะ Open / Partial Close / Closed Positions และ Real-Time P&L Tracking',
  },
  {
    name: 'Trade Journal',
    nameTh: 'สมุดบันทึกการเทรด (Trade Journal)',
    status: 'NOT_IMPLEMENTED',
    phase: 'Phase 8',
    detailsTh: 'ยังเป็น Placeholder อยู่ในเส้นทาง /journal รอเชื่อมต่อเมื่อมีข้อมูลการเทรดจริง',
  },
  {
    name: 'Backtest Results',
    nameTh: 'ผลการทดสอบกลยุทธ์ย้อนหลัง (Backtest)',
    status: 'NOT_IMPLEMENTED',
    phase: 'Phase 9',
    detailsTh: 'เครื่องยนต์ Backtest Engine ยังไม่ได้ติดตั้ง การประเมินปัจจุบันเป็นเพียง Real-Time Snapshots',
  },
  {
    name: 'Equity History',
    nameTh: 'ประวัติ Equity Curve ย้อนหลัง',
    status: 'NOT_IMPLEMENTED',
    phase: 'Phase 8',
    detailsTh: 'ยังไม่มีฐานข้อมูลบันทึก Equity Timeseries ข้อมูลกราฟจึงต้องแสดงเป็น NOT AVAILABLE',
  },
  {
    name: 'Performance Engine',
    nameTh: 'เครื่องยนต์คำนวณ Win Rate & P&L',
    status: 'NOT_IMPLEMENTED',
    phase: 'Phase 8',
    detailsTh: 'จะเปิดใช้งานเมื่อมี Executed Trade Dataset และระบบ Trade Ledger สมบูรณ์',
  },
];
