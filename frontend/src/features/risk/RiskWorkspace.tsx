'use client';

import React, { useEffect, useState, useCallback } from 'react';
import { api } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import {
  parseKillSwitch,
  parsePortfolioRisk,
  parseRiskDecisions,
  parseRiskPolicy,
  type KillSwitchData,
  type PortfolioRiskData,
  type ResourceStatus,
  type RiskDecisionData,
  type RiskPolicyData,
} from './contracts';

export function RiskWorkspace() {
  const { user } = useAuthStore();
  const isAdmin = user?.role === 'ADMIN';

  // Per-resource data and status authority
  const [policy, setPolicy] = useState<RiskPolicyData | null>(null);
  const [policyStatus, setPolicyStatus] = useState<ResourceStatus>('LOADING');
  const [policyLastSuccessAt, setPolicyLastSuccessAt] = useState<Date | null>(null);

  const [portfolio, setPortfolio] = useState<PortfolioRiskData | null>(null);
  const [portfolioStatus, setPortfolioStatus] = useState<ResourceStatus>('LOADING');
  const [portfolioLastSuccessAt, setPortfolioLastSuccessAt] = useState<Date | null>(null);

  const [killSwitch, setKillSwitch] = useState<KillSwitchData | null>(null);
  const [killSwitchStatus, setKillSwitchStatus] = useState<ResourceStatus>('LOADING');
  const [killSwitchLastSuccessAt, setKillSwitchLastSuccessAt] = useState<Date | null>(null);

  const [decisions, setDecisions] = useState<RiskDecisionData[]>([]);
  const [decisionsStatus, setDecisionsStatus] = useState<ResourceStatus>('LOADING');
  const [decisionsLastSuccessAt, setDecisionsLastSuccessAt] = useState<Date | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Kill Switch Action Modal
  const [modalMode, setModalMode] = useState<'ACTIVATE' | 'CLEAR' | null>(null);
  const [actionReason, setActionReason] = useState('');
  const [actionPending, setActionPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Expanded decision details
  const [expandedDecisionId, setExpandedDecisionId] = useState<string | null>(null);

  const [refresh, setRefresh] = useState(0);

  const fetchResources = useCallback(async () => {
    const errors: string[] = [];

    const [policyRes, portfolioRes, killSwitchRes, decisionsRes] = await Promise.allSettled([
      api.get('/risk/policy'),
      api.get('/risk/portfolio'),
      api.get('/risk/kill-switch'),
      api.get('/risk/decisions?limit=20'),
    ]);

    // 1. Policy
    if (policyRes.status === 'fulfilled') {
      try {
        const parsed = parseRiskPolicy(policyRes.value);
        setPolicy(parsed);
        setPolicyStatus('READY');
        setPolicyLastSuccessAt(new Date());
      } catch (e) {
        errors.push(`Policy Error: ${(e as Error).message}`);
        setPolicyStatus((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
      }
    } else {
      errors.push(`Policy Unreachable: ${(policyRes.reason as Error).message}`);
      setPolicyStatus((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
    }

    // 2. Portfolio
    if (portfolioRes.status === 'fulfilled') {
      try {
        const parsed = parsePortfolioRisk(portfolioRes.value);
        setPortfolio(parsed);
        setPortfolioStatus('READY');
        setPortfolioLastSuccessAt(new Date());
      } catch (e) {
        errors.push(`Portfolio Error: ${(e as Error).message}`);
        setPortfolioStatus((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
      }
    } else {
      errors.push(`Portfolio Unreachable: ${(portfolioRes.reason as Error).message}`);
      setPortfolioStatus((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
    }

    // 3. Kill Switch
    if (killSwitchRes.status === 'fulfilled') {
      try {
        const parsed = parseKillSwitch(killSwitchRes.value);
        setKillSwitch(parsed);
        setKillSwitchStatus('READY');
        setKillSwitchLastSuccessAt(new Date());
      } catch (e) {
        errors.push(`Kill Switch Error: ${(e as Error).message}`);
        setKillSwitchStatus((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
      }
    } else {
      errors.push(`Kill Switch Unreachable: ${(killSwitchRes.reason as Error).message}`);
      setKillSwitchStatus((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
    }

    // 4. Decisions
    if (decisionsRes.status === 'fulfilled') {
      try {
        const parsed = parseRiskDecisions(decisionsRes.value);
        setDecisions(parsed);
        setDecisionsStatus('READY');
        setDecisionsLastSuccessAt(new Date());
      } catch (e) {
        errors.push(`Decisions Error: ${(e as Error).message}`);
        setDecisionsStatus((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
      }
    } else {
      errors.push(`Decisions Unreachable: ${(decisionsRes.reason as Error).message}`);
      setDecisionsStatus((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
    }

    if (errors.length > 0) {
      setError(errors.join(' | '));
    } else {
      setError(null);
    }
  }, []);

  useEffect(() => {
    const timer = setInterval(() => {
      setRefresh((v) => v + 1);
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      await fetchResources();
    } finally {
      setLoading(false);
    }
  }, [fetchResources]);

  useEffect(() => {
    let active = true;
    const runPoll = async () => {
      await fetchResources();
      if (active) setLoading(false);
    };
    void runPoll();
    return () => {
      active = false;
    };
  }, [refresh, fetchResources]);

  const handleKillSwitchAction = async () => {
    if (!actionReason.trim()) {
      setActionError('กรุณากรอกเหตุผล');
      return;
    }
    setActionPending(true);
    setActionError(null);
    try {
      if (modalMode === 'ACTIVATE') {
        await api.post('/risk/kill-switch/activate', { reason_th: actionReason.trim() });
      } else {
        await api.post('/risk/kill-switch/clear', { reason_th: actionReason.trim() });
      }
      setModalMode(null);
      setActionReason('');
      await loadData();
    } catch (err) {
      setActionError((err as Error).message || 'เกิดข้อผิดพลาดในการดำเนินการ Kill Switch');
    } finally {
      setActionPending(false);
    }
  };

  const isKillSwitchNotReady = killSwitchStatus !== 'READY';
  const isKillSwitchUnknown = isKillSwitchNotReady || !killSwitch || killSwitch?.state === 'UNKNOWN';
  const isKillSwitchActive = !isKillSwitchUnknown && killSwitch?.state === 'ACTIVE';

  // Portfolio budget calculation
  const hasPortfolio = portfolioStatus === 'READY' && !!portfolio;
  const isPortfolioStale = portfolioStatus === 'STALE' && !!portfolio;
  const hasPolicy = policyStatus === 'READY' && !!policy;

  const totalRiskPct = (hasPortfolio || isPortfolioStale) && portfolio ? Number(portfolio.total_risk_pct) : null;
  const maxAccountRiskPct = (hasPortfolio || isPortfolioStale) && portfolio
    ? Number(portfolio.max_account_risk_pct)
    : (hasPolicy || policyStatus === 'STALE') && policy
    ? Number(policy.max_account_risk_pct)
    : null;
  const availableRiskPct = (hasPortfolio || isPortfolioStale) && portfolio ? Number(portfolio.available_risk_pct) : null;
  const budgetUsageRatio = (totalRiskPct !== null && maxAccountRiskPct !== null && maxAccountRiskPct > 0)
    ? Math.min(100, Math.max(0, (totalRiskPct / maxAccountRiskPct) * 100))
    : 0;

  return (
    <div className="space-y-6">
      {/* 1. SAFETY & INVARIANCE BOUNDARY BANNER */}
      <div className="bg-amber-950/40 border border-amber-500/40 rounded-xl p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs md:text-sm">
        <div className="flex items-center space-x-3">
          <span className="text-xl">🛡️</span>
          <div>
            <div className="font-bold text-amber-300 flex items-center gap-2">
              <span>TRADING SAFETY ENFORCEMENT</span>
              <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-400 font-mono text-[11px] border border-amber-500/30">
                PAPER MODE
              </span>
              <span className="px-2 py-0.5 rounded bg-red-500/20 text-red-400 font-mono text-[11px] border border-red-500/30">
                LIVE_AUTO_TRADING=OFF
              </span>
            </div>
            <p className="text-gray-300 mt-0.5 text-xs">
              ระบบนี้ทำการประเมินความเสี่ยงและจัดสรรงบประมาณเชิงวิเคราะห์เท่านั้น ไม่อนุญาตให้มีการส่งคำสั่งซื้อขายจริง (Execution Disabled)
            </p>
          </div>
        </div>
        <button
          onClick={loadData}
          className="self-start md:self-auto px-3 py-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-700 text-xs transition"
        >
          {loading ? 'กำลังโหลด...' : '🔄 รีเฟรชข้อมูล'}
        </button>
      </div>

      {error && (
        <div className="bg-amber-950/40 border border-amber-500/50 text-amber-200 text-xs p-3 rounded-xl flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <span>⚠️</span>
            <span>{error}</span>
          </div>
          <span className="text-[10px] text-amber-400/80 font-mono">FAIL-CLOSED ACTIVATED</span>
        </div>
      )}

      {/* 2. EMERGENCY KILL SWITCH HERO BANNER */}
      <div
        className={`rounded-xl border p-6 transition-all ${
          isKillSwitchUnknown
            ? 'bg-amber-950/40 border-amber-500/60 shadow-lg shadow-amber-950/50'
            : isKillSwitchActive
            ? 'bg-red-950/40 border-red-500/60 shadow-lg shadow-red-950/50'
            : 'bg-emerald-950/20 border-emerald-500/30'
        }`}
      >
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-start md:items-center space-x-4">
            <div
              className={`w-14 h-14 rounded-2xl flex items-center justify-center text-3xl shrink-0 ${
                isKillSwitchUnknown
                  ? 'bg-amber-500/20 border border-amber-500/40 animate-pulse'
                  : isKillSwitchActive
                  ? 'bg-red-500/20 border border-red-500/40 animate-pulse'
                  : 'bg-emerald-500/20 border border-emerald-500/30'
              }`}
            >
              {isKillSwitchUnknown ? '⚠️' : isKillSwitchActive ? '🚨' : '🟢'}
            </div>
            <div>
              <div className="flex items-center space-x-3">
                <h2 className="text-xl font-bold text-white">Emergency Kill Switch</h2>
                <span
                  className={`px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider ${
                    isKillSwitchUnknown
                      ? 'bg-amber-500 text-gray-950'
                      : isKillSwitchActive
                      ? 'bg-red-500 text-white'
                      : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  }`}
                >
                  {killSwitchStatus === 'UNAVAILABLE'
                    ? 'UNAVAILABLE (ไม่สามารถตรวจสอบสถานะได้ - Fail Closed)'
                    : killSwitchStatus === 'STALE'
                    ? 'STALE (ข้อมูลล้าสมัย - Fail Closed)'
                    : isKillSwitchUnknown
                    ? 'UNKNOWN (ไม่สามารถตรวจสอบสถานะได้ - Fail Closed)'
                    : isKillSwitchActive
                    ? 'ACTIVE (ปิดระบบฉุกเฉิน)'
                    : 'INACTIVE (ระบบพร้อมทำงาน)'}
                </span>
              </div>
              <p className="text-sm text-gray-300 mt-1">
                {killSwitchStatus === 'UNAVAILABLE'
                  ? 'ระบบปฏิเสธคำสั่งทั้งหมดเนื่องจากไม่สามารถเชื่อมต่อฐานข้อมูลสถานะความปลอดภัยได้ (Fail-Closed)'
                  : killSwitchStatus === 'STALE'
                  ? `ระบบปฏิเสธคำสั่งเนื่องจากข้อมูลความปลอดภัยล่าสุด (${killSwitchLastSuccessAt ? killSwitchLastSuccessAt.toLocaleTimeString('th-TH') : 'ไม่ระบุ'}) อาจล้าสมัย`
                  : isKillSwitchUnknown
                  ? `ระบบปฏิเสธคำสั่งทั้งหมดเนื่องจากไม่สามารถยืนยันสถานะ Kill Switch ได้ (Fail-Closed): ${killSwitch?.reason_th || 'ฐานข้อมูลยังไม่พร้อม'}`
                  : isKillSwitchActive
                  ? `ระบบถูกระงับ: ${killSwitch?.reason_th || 'ไม่สามารถทำการประเมินแผนการเทรดได้'}`
                  : 'ระบบทำงานปกติ ไม่มีการเปิดสวิตช์ฉุกเฉิน คำสั่งประเมินความเสี่ยงสามารถดำเนินการได้ตามเกณฑ์ที่กำหนด'}
              </p>
              {(isKillSwitchActive || isKillSwitchUnknown) && killSwitch && (
                <div className="flex flex-wrap gap-4 mt-2 text-xs text-gray-400">
                  <span>ผู้สั่งการ: <strong className="text-gray-200">{killSwitch.activated_by}</strong></span>
                  <span>สาเหตุ: <strong className="text-red-300">{killSwitch.trigger_type}</strong></span>
                  <span>เวลาบันทึก: <strong className="text-gray-200">{new Date(killSwitch.activated_at).toLocaleString('th-TH')}</strong></span>
                  {killSwitchLastSuccessAt && (
                    <span>ซิงค์สำเร็จล่าสุด: <strong className="text-amber-300">{killSwitchLastSuccessAt.toLocaleTimeString('th-TH')}</strong></span>
                  )}
                </div>
              )}
            </div>
          </div>

          <div className="flex flex-col items-end gap-2">
            {isAdmin ? (
              isKillSwitchActive ? (
                <button
                  onClick={() => { setModalMode('CLEAR'); setActionReason(''); }}
                  className="px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-medium text-sm transition shadow-lg shadow-emerald-950 flex items-center gap-2"
                >
                  <span>🔓</span>
                  <span>ปลดล็อค Kill Switch</span>
                </button>
              ) : (
                <button
                  onClick={() => { setModalMode('ACTIVATE'); setActionReason(''); }}
                  className="px-5 py-2.5 rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium text-sm transition shadow-lg shadow-red-950 flex items-center gap-2"
                >
                  <span>⚠️</span>
                  <span>เปิด Kill Switch ฉุกเฉิน</span>
                </button>
              )
            ) : (
              <span className="text-xs text-gray-400 italic">
                🔒 เฉพาะผู้ดูแลระบบ (Admin) เท่านั้นที่สามารถควบคุม Kill Switch
              </span>
            )}
          </div>
        </div>
      </div>

      {/* 3. PORTFOLIO RISK BUDGET OVERVIEW (GAUGES & METRICS) */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Account Capacity Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h3 className="text-sm font-semibold text-gray-300">เพดานความเสี่ยงบัญชี (Account Risk)</h3>
              <span className="text-[10px] text-gray-500 font-mono">
                Source: {portfolio?.account_source || 'UNAVAILABLE'}
                {portfolioLastSuccessAt && ` · ${portfolioLastSuccessAt.toLocaleTimeString('th-TH')}`}
              </span>
            </div>
            <span
              className={`text-xs px-2 py-0.5 rounded font-mono ${
                portfolioStatus === 'READY'
                  ? 'bg-gray-800 text-gray-400'
                  : portfolioStatus === 'STALE'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : 'bg-red-500/20 text-red-300 border border-red-500/30'
              }`}
            >
              {portfolioStatus === 'READY'
                ? `Max ${maxAccountRiskPct !== null ? `${maxAccountRiskPct.toFixed(2)}%` : 'UNKNOWN'}`
                : portfolioStatus === 'STALE'
                ? 'STALE'
                : 'UNAVAILABLE'}
            </span>
          </div>

          <div className="space-y-4">
            <div>
              <div className="flex justify-between text-sm mb-1">
                <span className="text-gray-400">ความเสี่ยงรวมปัจจุบัน:</span>
                <span
                  className={`font-mono font-bold ${
                    portfolioStatus !== 'READY'
                      ? 'text-amber-400'
                      : totalRiskPct !== null && maxAccountRiskPct !== null && totalRiskPct > maxAccountRiskPct * 0.8
                      ? 'text-red-400'
                      : 'text-emerald-400'
                  }`}
                >
                  {portfolioStatus === 'UNAVAILABLE'
                    ? 'UNAVAILABLE'
                    : totalRiskPct !== null
                    ? `${totalRiskPct.toFixed(2)}%`
                    : 'UNAVAILABLE'}
                </span>
              </div>
              <div className="w-full bg-gray-800 h-3 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    portfolioStatus !== 'READY'
                      ? 'bg-amber-600/70'
                      : budgetUsageRatio > 80
                      ? 'bg-red-500'
                      : budgetUsageRatio > 50
                      ? 'bg-amber-500'
                      : 'bg-emerald-500'
                  }`}
                  style={{ width: `${portfolioStatus === 'UNAVAILABLE' ? 0 : budgetUsageRatio}%` }}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2 text-xs border-t border-gray-800/80">
              <div>
                <span className="text-gray-500 block">คงเหลือที่อนุญาต (Available):</span>
                <span className={`font-mono font-bold text-sm ${portfolioStatus === 'READY' ? 'text-gray-200' : 'text-amber-300'}`}>
                  {portfolioStatus === 'UNAVAILABLE' ? 'UNAVAILABLE' : availableRiskPct !== null ? `${availableRiskPct.toFixed(2)}%` : 'UNAVAILABLE'}
                </span>
              </div>
              <div>
                <span className="text-gray-500 block">จองไว้ล่วงหน้า (Reserved):</span>
                <span className="font-mono font-bold text-amber-400 text-sm">
                  {portfolioStatus === 'UNAVAILABLE' ? 'UNAVAILABLE' : (hasPortfolio || isPortfolioStale) && portfolio ? `${Number(portfolio.reserved_risk_pct).toFixed(2)}%` : 'UNAVAILABLE'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Directional Gross Risk */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-300">ความเสี่ยงตามทิศทาง (Gross Directional)</h3>
            <span
              className={`text-[11px] px-2 py-0.5 rounded ${
                portfolioStatus === 'READY'
                  ? 'text-gray-400 bg-gray-800'
                  : 'text-amber-300 bg-amber-500/20 border border-amber-500/30'
              }`}
            >
              {portfolioStatus === 'READY' ? 'ไม่หักล้างกัน (Gross)' : portfolioStatus}
            </span>
          </div>

          <div className="space-y-3">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-emerald-400 font-medium">LONG Exposure</span>
                <span className="font-mono text-gray-200">
                  {portfolioStatus === 'UNAVAILABLE'
                    ? 'UNAVAILABLE'
                    : (hasPortfolio || isPortfolioStale) && portfolio
                    ? `${Number(portfolio.directional_risk_pct?.LONG || '0').toFixed(2)}%`
                    : 'UNAVAILABLE'}{' '}
                  / {hasPolicy && policy ? `${Number(policy.max_directional_risk_pct).toFixed(2)}%` : 'UNKNOWN'}
                </span>
              </div>
              <div className="w-full bg-gray-800 h-2 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${portfolioStatus === 'READY' ? 'bg-emerald-500' : 'bg-gray-600'}`}
                  style={{
                    width: `${portfolioStatus === 'READY' && portfolio && policy ? Math.min(100, (Number(portfolio.directional_risk_pct?.LONG || '0') / Number(policy.max_directional_risk_pct)) * 100) : 0}%`,
                  }}
                />
              </div>
            </div>

            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-rose-400 font-medium">SHORT Exposure</span>
                <span className="font-mono text-gray-200">
                  {portfolioStatus === 'UNAVAILABLE'
                    ? 'UNAVAILABLE'
                    : (hasPortfolio || isPortfolioStale) && portfolio
                    ? `${Number(portfolio.directional_risk_pct?.SHORT || '0').toFixed(2)}%`
                    : 'UNAVAILABLE'}{' '}
                  / {hasPolicy && policy ? `${Number(policy.max_directional_risk_pct).toFixed(2)}%` : 'UNKNOWN'}
                </span>
              </div>
              <div className="w-full bg-gray-800 h-2 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${portfolioStatus === 'READY' ? 'bg-rose-500' : 'bg-gray-600'}`}
                  style={{
                    width: `${portfolioStatus === 'READY' && portfolio && policy ? Math.min(100, (Number(portfolio.directional_risk_pct?.SHORT || '0') / Number(policy.max_directional_risk_pct)) * 100) : 0}%`,
                  }}
                />
              </div>
            </div>

            <div className="pt-2 text-[11px] text-gray-400 border-t border-gray-800/80">
              สัญลักษณ์หลัก: <strong className="text-gray-200">XAUUSD</strong> (
              {portfolioStatus === 'UNAVAILABLE'
                ? 'UNAVAILABLE'
                : (hasPortfolio || isPortfolioStale) && portfolio
                ? `${Number(portfolio.symbol_risk_pct?.XAUUSD || '0').toFixed(2)}%`
                : 'UNAVAILABLE'}{' '}
              ความเสี่ยงสะสม)
            </div>
          </div>
        </div>

        {/* Account Loss Guardrails */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-semibold text-gray-300">มาตรวัดความเสียหาย (Loss Guardrails)</h3>
            <span
              className={`text-xs px-2 py-0.5 rounded font-medium ${
                portfolioStatus !== 'READY'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                  : portfolio?.in_cooldown
                  ? 'bg-red-500/20 text-red-400 border border-red-500/30'
                  : 'bg-emerald-500/20 text-emerald-400'
              }`}
            >
              {portfolioStatus === 'READY'
                ? portfolio?.in_cooldown
                  ? 'อยู่ในช่วง Cooldown'
                  : 'ปกติ'
                : portfolioStatus === 'STALE'
                ? 'ข้อมูลล้าสมัย (STALE)'
                : 'UNAVAILABLE'}
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div className="bg-gray-800/60 p-3 rounded-lg border border-gray-800">
              <span className="text-gray-400 block mb-1">ขาดทุนรายวัน:</span>
              <span className="font-mono font-bold text-gray-200 text-sm">
                {portfolioStatus === 'UNAVAILABLE' ? 'UNAVAILABLE' : (hasPortfolio || isPortfolioStale) && portfolio ? `${Number(portfolio.daily_loss_pct).toFixed(2)}%` : 'UNAVAILABLE'}
              </span>
              <span className="text-[10px] text-gray-500 block">เพดาน: {policy ? `${policy.daily_loss_limit_pct}%` : 'UNKNOWN'}</span>
            </div>

            <div className="bg-gray-800/60 p-3 rounded-lg border border-gray-800">
              <span className="text-gray-400 block mb-1">ขาดทุนรายสัปดาห์:</span>
              <span className="font-mono font-bold text-gray-200 text-sm">
                {portfolioStatus === 'UNAVAILABLE' ? 'UNAVAILABLE' : (hasPortfolio || isPortfolioStale) && portfolio ? `${Number(portfolio.weekly_loss_pct).toFixed(2)}%` : 'UNAVAILABLE'}
              </span>
              <span className="text-[10px] text-gray-500 block">เพดาน: {policy ? `${policy.weekly_loss_limit_pct}%` : 'UNKNOWN'}</span>
            </div>

            <div className="col-span-2 bg-gray-800/60 p-3 rounded-lg border border-gray-800 flex justify-between items-center">
              <div>
                <span className="text-gray-400 block">Current Snapshot Drawdown:</span>
                <span className="text-[10px] text-gray-500">เพดานสูงสุด: {policy ? `${policy.max_drawdown_pct}%` : 'UNKNOWN'}</span>
              </div>
              <span className="font-mono font-bold text-gray-100 text-base">
                {portfolioStatus === 'UNAVAILABLE' ? 'UNAVAILABLE' : (hasPortfolio || isPortfolioStale) && portfolio ? `${Number(portfolio.drawdown_pct).toFixed(2)}%` : 'UNAVAILABLE'}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* 4. ACTIVE RISK RESERVATIONS TABLE */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <h3 className="font-semibold text-gray-200">การจองงบประมาณความเสี่ยงที่เปิดอยู่ (Active Risk Reservations)</h3>
            <span
              className={`px-2 py-0.5 rounded-full text-xs font-mono border ${
                portfolioStatus === 'READY'
                  ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                  : portfolioStatus === 'STALE'
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  : 'bg-red-500/20 text-red-300 border-red-500/30'
              }`}
            >
              {portfolioStatus === 'READY' && portfolio
                ? `${portfolio.active_reservations_count} รายการ`
                : portfolioStatus === 'STALE' && portfolio
                ? `STALE (${portfolio.active_reservations_count} รายการ)`
                : 'UNAVAILABLE'}
            </span>
          </div>
          <span className="text-xs text-gray-400">
            หมดอายุอัตโนมัติเมื่อครบกำหนด (TTL: {policy ? `${policy.reservation_ttl_seconds}s` : 'UNKNOWN'})
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-800/50 text-gray-400 font-medium border-b border-gray-800">
              <tr>
                <th className="px-6 py-3">Reservation ID</th>
                <th className="px-6 py-3">Profile ID</th>
                <th className="px-6 py-3">Symbol</th>
                <th className="px-6 py-3">ทิศทาง</th>
                <th className="px-6 py-3">ความเสี่ยง (%)</th>
                <th className="px-6 py-3">วงเงิน ($)</th>
                <th className="px-6 py-3">ขนาดสัญญา (Lots)</th>
                <th className="px-6 py-3">หมดอายุ (Reserved Until)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50 text-gray-300">
              {portfolio?.active_reservations && portfolio.active_reservations.length > 0 ? (
                portfolio.active_reservations.map((res) => (
                  <tr key={res.id} className="hover:bg-gray-800/30 transition">
                    <td className="px-6 py-3 font-mono text-gray-400">{res.id}</td>
                    <td className="px-6 py-3 font-medium text-gray-200">{res.profile_id}</td>
                    <td className="px-6 py-3 font-bold text-amber-400">{res.symbol}</td>
                    <td className="px-6 py-3">
                      <span
                        className={`px-2 py-0.5 rounded font-bold ${
                          res.direction === 'LONG'
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-rose-500/20 text-rose-400'
                        }`}
                      >
                        {res.direction}
                      </span>
                    </td>
                    <td className="px-6 py-3 font-mono text-amber-300 font-bold">{Number(res.risk_pct).toFixed(2)}%</td>
                    <td className="px-6 py-3 font-mono">${Number(res.risk_amount).toFixed(2)}</td>
                    <td className="px-6 py-3 font-mono font-bold text-gray-100">{res.position_size} lot</td>
                    <td className="px-6 py-3 font-mono text-gray-400">
                      {new Date(res.reserved_until).toLocaleTimeString('th-TH')}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={8} className="px-6 py-8 text-center text-gray-500">
                    {portfolioStatus === 'READY'
                      ? 'ไม่มีงบประมาณความเสี่ยงที่ถูกจองค้างไว้ในขณะนี้ (No active reservations)'
                      : portfolioStatus === 'STALE'
                      ? 'ข้อมูลการจองล่าสุดอาจล้าสมัย กรุณารีเฟรชเพื่อยืนยัน (Data Stale)'
                      : 'ไม่สามารถยืนยันข้อมูลการจองความเสี่ยงได้ (Fail-Closed)'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 5. RECENT RISK DECISIONS TABLE */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-800 flex items-center justify-between">
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-semibold text-gray-200">ประวัติการประเมินความเสี่ยงล่าสุด (Risk Decisions Audit)</h3>
              {decisionsStatus === 'STALE' && (
                <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 text-[10px] font-mono border border-amber-500/30">
                  STALE
                </span>
              )}
              {decisionsStatus === 'UNAVAILABLE' && (
                <span className="px-2 py-0.5 rounded bg-red-500/20 text-red-300 text-[10px] font-mono border border-red-500/30">
                  UNAVAILABLE
                </span>
              )}
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              บันทึกการตัดสินใจที่เป็น Immutable และผลลัพธ์คำอธิบายภาษาไทยตามเกณฑ์ Fail-Closed
              {decisionsLastSuccessAt && ` · ซิงค์ล่าสุด ${decisionsLastSuccessAt.toLocaleTimeString('th-TH')}`}
            </p>
          </div>
          <span className="text-xs font-mono text-gray-500">แสดงสูงสุด 20 รายการ</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-gray-800/50 text-gray-400 font-medium border-b border-gray-800">
              <tr>
                <th className="px-6 py-3">Decision ID</th>
                <th className="px-6 py-3">ผลการประเมิน</th>
                <th className="px-6 py-3">Profile / Strategy</th>
                <th className="px-6 py-3">Symbol / Dir</th>
                <th className="px-6 py-3">ขนาดที่อนุมัติ</th>
                <th className="px-6 py-3">ระยะ Stop Loss</th>
                <th className="px-6 py-3">เวลาประเมิน</th>
                <th className="px-6 py-3 text-right">รายละเอียด</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/50 text-gray-300">
              {decisions.length > 0 ? (
                decisions.map((dec) => {
                  const isExpanded = expandedDecisionId === dec.id;
                  return (
                    <React.Fragment key={dec.id}>
                      <tr
                        onClick={() => setExpandedDecisionId(isExpanded ? null : dec.id)}
                        className="hover:bg-gray-800/40 cursor-pointer transition"
                      >
                        <td className="px-6 py-3 font-mono text-gray-400">{dec.id.slice(0, 16)}...</td>
                        <td className="px-6 py-3">
                          <span
                            className={`px-2.5 py-1 rounded-full font-bold text-[11px] ${
                              dec.decision === 'APPROVED'
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : dec.decision === 'REDUCED'
                                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                : 'bg-red-500/20 text-red-400 border border-red-500/30'
                            }`}
                          >
                            {dec.decision}
                          </span>
                        </td>
                        <td className="px-6 py-3">
                          <div className="font-medium text-gray-200">{dec.profile_id}</div>
                          <div className="text-[10px] text-gray-500 font-mono">{dec.strategy_id}</div>
                        </td>
                        <td className="px-6 py-3">
                          <div className="font-bold text-amber-400">{dec.symbol}</div>
                          <span
                            className={`font-semibold text-[10px] ${
                              dec.direction === 'LONG' ? 'text-emerald-400' : 'text-rose-400'
                            }`}
                          >
                            {dec.direction}
                          </span>
                        </td>
                        <td className="px-6 py-3 font-mono">
                          {dec.decision === 'BLOCKED' ? (
                            <span className="text-gray-500">0.00 lot (0.00%)</span>
                          ) : (
                            <div>
                              <strong className="text-gray-100">{dec.position_size} lot</strong>
                              <span className="text-gray-400 block text-[10px]">
                                ({Number(dec.approved_risk_pct).toFixed(2)}% / ${Number(dec.approved_risk_amount).toFixed(2)})
                              </span>
                            </div>
                          )}
                        </td>
                        <td className="px-6 py-3 font-mono text-gray-400">
                          {Number(dec.stop_distance).toFixed(2)} pts
                          <span className="block text-[10px] text-gray-500">SL: {Number(dec.stop_loss).toFixed(2)}</span>
                        </td>
                        <td className="px-6 py-3 font-mono text-gray-400">
                          {new Date(dec.as_of).toLocaleTimeString('th-TH')}
                        </td>
                        <td className="px-6 py-3 text-right">
                          <span className="text-amber-400 hover:text-amber-300 font-medium">
                            {isExpanded ? '▲ ซ่อน' : '▼ ดูเหตุผล'}
                          </span>
                        </td>
                      </tr>

                      {/* Expandable Decision Details */}
                      {isExpanded && (
                        <tr className="bg-gray-950/60 border-y border-gray-800">
                          <td colSpan={8} className="px-6 py-4">
                            <div className="space-y-3">
                              {/* Thai Reasons */}
                              {dec.reasons_th && dec.reasons_th.length > 0 && (
                                <div>
                                  <h5 className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider mb-1">
                                    เหตุผลการอนุมัติ / คำอธิบาย:
                                  </h5>
                                  <ul className="list-disc list-inside text-xs text-gray-300 space-y-0.5">
                                    {dec.reasons_th.map((r, i) => (
                                      <li key={i}>{r}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {/* Blocked Reasons */}
                              {dec.blocked_reasons_th && dec.blocked_reasons_th.length > 0 && (
                                <div>
                                  <h5 className="text-[11px] font-semibold text-red-400 uppercase tracking-wider mb-1">
                                    เหตุผลที่ปฏิเสธ (Blocked Reasons):
                                  </h5>
                                  <ul className="list-disc list-inside text-xs text-red-300 space-y-0.5">
                                    {dec.blocked_reasons_th.map((r, i) => (
                                      <li key={i}>{r}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {/* Warnings */}
                              {dec.warnings_th && dec.warnings_th.length > 0 && (
                                <div>
                                  <h5 className="text-[11px] font-semibold text-amber-400 uppercase tracking-wider mb-1">
                                    คำเตือน (Warnings):
                                  </h5>
                                  <ul className="list-disc list-inside text-xs text-amber-200 space-y-0.5">
                                    {dec.warnings_th.map((r, i) => (
                                      <li key={i}>{r}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {/* Provenance Tags */}
                              <div className="flex flex-wrap gap-3 pt-2 text-[11px] border-t border-gray-800 text-gray-400">
                                <span>Policy: <strong className="text-gray-200">{dec.policy_version}</strong></span>
                                <span>Candidate ID: <strong className="text-gray-200">{dec.candidate_id}</strong></span>
                                {dec.news_risk_provenance && (
                                  <span>
                                    สถานะข่าว: <strong className="text-amber-300">{dec.news_risk_provenance.description_th}</strong>
                                  </span>
                                )}
                                {dec.market_provenance && (
                                  <span>
                                    Quote Source: <strong className="text-gray-200">{dec.market_provenance.source}</strong> (Spread: {dec.market_provenance.quote_spread})
                                  </span>
                                )}
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })
              ) : (
                <tr>
                  <td colSpan={8} className="px-6 py-8 text-center text-gray-500">
                    {decisionsStatus === 'UNAVAILABLE'
                      ? 'ไม่สามารถโหลดประวัติการประเมินความเสี่ยงได้ (UNAVAILABLE)'
                      : 'ยังไม่มีประวัติการประเมินความเสี่ยง (No risk decisions recorded)'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 6. RISK POLICY PARAMETERS (READ-ONLY) */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="font-semibold text-gray-200">นโยบายความเสี่ยงที่ใช้งานอยู่ (Active Risk Policy)</h3>
              <span
                className={`text-[10px] px-2 py-0.5 rounded font-mono border ${
                  policyStatus === 'READY'
                    ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
                    : policyStatus === 'STALE'
                    ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                    : 'bg-red-500/20 text-red-300 border-red-500/30'
                }`}
              >
                {policyStatus}
              </span>
            </div>
            <span className="text-xs text-gray-400 font-mono">
              Version: {policy?.version || 'N/A'}
              {policyLastSuccessAt && ` · ซิงค์ล่าสุด ${policyLastSuccessAt.toLocaleTimeString('th-TH')}`}
            </span>
          </div>
          <span className="px-2.5 py-1 rounded bg-gray-800 text-gray-400 text-xs">
            กำหนดค่าผ่าน Server Configuration (Read-Only)
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 text-xs">
          <div className="bg-gray-800/40 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-500 block mb-1">ความเสี่ยงสูงสุดต่อไม้</span>
            <span className="font-mono font-bold text-gray-200 text-sm">{policy ? `${policy.max_risk_per_trade_pct}%` : 'UNKNOWN'}</span>
          </div>
          <div className="bg-gray-800/40 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-500 block mb-1">ความเสี่ยงขั้นต่ำต่อไม้</span>
            <span className="font-mono font-bold text-gray-200 text-sm">{policy ? `${policy.min_risk_per_trade_pct}%` : 'UNKNOWN'}</span>
          </div>
          <div className="bg-gray-800/40 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-500 block mb-1">เพดานรวมของบัญชี</span>
            <span className="font-mono font-bold text-gray-200 text-sm">{policy ? `${policy.max_account_risk_pct}%` : 'UNKNOWN'}</span>
          </div>
          <div className="bg-gray-800/40 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-500 block mb-1">เพดานความเสี่ยงต่อทิศทาง</span>
            <span className="font-mono font-bold text-gray-200 text-sm">{policy ? `${policy.max_directional_risk_pct}%` : 'UNKNOWN'}</span>
          </div>
          <div className="bg-gray-800/40 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-500 block mb-1">จำนวนคำสั่งเปิดพร้อมกันสูงสุด</span>
            <span className="font-mono font-bold text-gray-200 text-sm">{policy ? `${policy.max_concurrent_trades} ไม้` : 'UNKNOWN'}</span>
          </div>
          <div className="bg-gray-800/40 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-500 block mb-1">ช่วงห้ามเทรดก่อนข่าว (Blackout)</span>
            <span className="font-mono font-bold text-gray-200 text-sm">{policy ? `${policy.news_blackout_minutes} นาที` : 'UNKNOWN'}</span>
          </div>
          <div className="bg-gray-800/40 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-500 block mb-1">ช่วงปรับลดความเสี่ยงก่อนข่าว</span>
            <span className="font-mono font-bold text-gray-200 text-sm">{policy ? `${policy.news_reduction_window_minutes} นาที (ลดเหลือ ${(Number(policy.news_reduction_factor) * 100).toFixed(0)}%)` : 'UNKNOWN'}</span>
          </div>
          <div className="bg-gray-800/40 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-500 block mb-1">สเปรดสูงสุดที่ยอมรับได้</span>
            <span className="font-mono font-bold text-gray-200 text-sm">{policy ? policy.max_spread_absolute : 'UNKNOWN'}</span>
          </div>
        </div>
      </div>

      {/* ACTION MODAL (ACTIVATE / CLEAR KILL SWITCH) */}
      {modalMode && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <div className="bg-gray-900 border border-gray-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-center space-x-3">
              <span className="text-2xl">{modalMode === 'ACTIVATE' ? '🚨' : '🔓'}</span>
              <h3 className="text-lg font-bold text-white">
                {modalMode === 'ACTIVATE' ? 'ยืนยันการเปิด Kill Switch ฉุกเฉิน' : 'ยืนยันการปลดล็อค Kill Switch'}
              </h3>
            </div>

            <p className="text-sm text-gray-300">
              {modalMode === 'ACTIVATE'
                ? 'การเปิด Kill Switch จะปฏิเสธคำสั่งประเมินความเสี่ยงทั้งหมดทันที เพื่อความปลอดภัยของพอร์ตโฟลิโอ'
                : 'การปลดล็อค Kill Switch จะคืนสิทธิ์ให้ระบบกลับมาประเมินความเสี่ยงตามนโยบายปกติ'}
            </p>

            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                ระบุเหตุผล (ภาษาไทยสำหรับ Audit Trail) <span className="text-red-400">*</span>
              </label>
              <textarea
                value={actionReason}
                onChange={(e) => setActionReason(e.target.value)}
                placeholder={modalMode === 'ACTIVATE' ? 'เช่น ตรวจพบความผันผวนสูงผิดปกติ หรือการขาดทุนต่อเนื่อง' : 'เช่น สภาวะตลาดกลับสู่ระดับปกติแล้ว'}
                rows={3}
                className="w-full bg-gray-950 border border-gray-700 rounded-lg p-3 text-sm text-gray-100 placeholder-gray-500 focus:outline-none focus:border-amber-500"
              />
            </div>

            {actionError && (
              <div className="text-xs text-red-400 bg-red-950/40 p-2 rounded border border-red-800">
                {actionError}
              </div>
            )}

            <div className="flex justify-end space-x-3 pt-2">
              <button
                onClick={() => setModalMode(null)}
                disabled={actionPending}
                className="px-4 py-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm transition"
              >
                ยกเลิก
              </button>
              <button
                onClick={handleKillSwitchAction}
                disabled={actionPending}
                className={`px-4 py-2 rounded-lg text-white text-sm font-medium transition ${
                  modalMode === 'ACTIVATE'
                    ? 'bg-red-600 hover:bg-red-500 shadow-lg shadow-red-950'
                    : 'bg-emerald-600 hover:bg-emerald-500 shadow-lg shadow-emerald-950'
                }`}
              >
                {actionPending ? 'กำลังบันทึก...' : modalMode === 'ACTIVATE' ? 'เปิด Kill Switch' : 'ปลดล็อคระบบ'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
