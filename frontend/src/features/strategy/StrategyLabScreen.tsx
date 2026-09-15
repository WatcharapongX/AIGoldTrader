'use client';

import React, { useState, useEffect } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type {
  SetupCandidate,
  StrategyDefinition,
  StrategyResponse,
  TraderProfile,
} from '@/types/strategy.generated';
import { StrategyCatalogTab } from './StrategyCatalogTab';
import { TraderProfilesTab } from './TraderProfilesTab';
import { EvaluationsTab } from './EvaluationsTab';
import { BacktestReadinessTab } from './BacktestReadinessTab';

type TabKey = 'STRATEGIES' | 'PROFILES' | 'EVALUATIONS' | 'BACKTEST';

interface MarketProviderInfo {
  source: string;
  mode: string;
  status: string;
}

export function StrategyLabScreen() {
  const [activeTab, setActiveTab] = useState<TabKey>('STRATEGIES');
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);

  // Data states
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([]);
  const [profiles, setProfiles] = useState<TraderProfile[]>([]);
  const [currentEval, setCurrentEval] = useState<StrategyResponse | null>(null);
  const [evaluations, setEvaluations] = useState<StrategyResponse[]>([]);
  const [candidates, setCandidates] = useState<SetupCandidate[]>([]);
  const [provider, setProvider] = useState<MarketProviderInfo | null>(null);

  // Loading and error states
  const [loadingStrategies, setLoadingStrategies] = useState(true);
  const [loadingProfiles, setLoadingProfiles] = useState(true);
  const [loadingCurrent, setLoadingCurrent] = useState(true);
  const [loadingEvaluations, setLoadingEvaluations] = useState(true);
  const [loadingCandidates, setLoadingCandidates] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch all domain data from authoritative endpoints
  useEffect(() => {
    let active = true;
    const abort = new AbortController();

    const fetchAllData = async () => {
      setIsRefreshing(true);
      setError(null);

      // 1. Fetch Market Status
      try {
        const rawStatus = (await api.get('/market/status', { signal: abort.signal })) as {
          provider?: { source?: string; mode?: string; status?: string };
        };
        if (active && rawStatus?.provider) {
          setProvider({
            source: rawStatus.provider.source || 'mt5_demo_iux',
            mode: rawStatus.provider.mode || 'DEMO',
            status: rawStatus.provider.status || 'CONNECTED',
          });
        }
      } catch {
        // Fallback provider
        if (active) {
          setProvider({ source: 'mt5_demo_iux', mode: 'DEMO', status: 'CONNECTED' });
        }
      }

      // 2. Fetch Strategies Catalog (GET /api/strategies)
      try {
        setLoadingStrategies(true);
        const strats = (await api.get('/strategies', { signal: abort.signal })) as StrategyDefinition[];
        if (active) {
          setStrategies(Array.isArray(strats) ? strats : []);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : 'โหลดกลยุทธ์ไม่สำเร็จ');
        }
      } finally {
        if (active) setLoadingStrategies(false);
      }

      // 3. Fetch Trader Profiles (GET /api/trader-profiles)
      try {
        setLoadingProfiles(true);
        const profs = (await api.get('/trader-profiles', { signal: abort.signal })) as TraderProfile[];
        if (active) {
          setProfiles(Array.isArray(profs) ? profs : []);
        }
      } catch {
        // Graceful handling
      } finally {
        if (active) setLoadingProfiles(false);
      }

      // 4. Fetch Current Strategy Context (GET /api/strategy/context)
      try {
        setLoadingCurrent(true);
        const currentResp = (await api.get('/strategy/context', { signal: abort.signal })) as StrategyResponse;
        if (active && currentResp?.evaluation) {
          setCurrentEval(currentResp);
        }
      } catch {
        // Graceful handling
      } finally {
        if (active) setLoadingCurrent(false);
      }

      // 5. Fetch Historical Evaluations (GET /api/strategy/evaluations?limit=25)
      try {
        setLoadingEvaluations(true);
        const evalsResp = (await api.get('/strategy/evaluations?limit=25', { signal: abort.signal })) as StrategyResponse[];
        if (active) {
          setEvaluations(Array.isArray(evalsResp) ? evalsResp : []);
        }
      } catch {
        if (active) setEvaluations([]);
      } finally {
        if (active) setLoadingEvaluations(false);
      }

      // 6. Fetch Candidates History (GET /api/trade-candidates?limit=100)
      try {
        setLoadingCandidates(true);
        const cands = (await api.get('/trade-candidates?limit=100', { signal: abort.signal })) as SetupCandidate[];
        if (active) {
          setCandidates(Array.isArray(cands) ? cands : []);
        }
      } catch {
        if (active) setCandidates([]);
      } finally {
        if (active) {
          setLoadingCandidates(false);
          setIsRefreshing(false);
        }
      }
    };

    void fetchAllData();

    return () => {
      active = false;
      abort.abort();
    };
  }, [refreshTrigger]);

  // Derived metrics for summary cards
  const currentCandidatesList = currentEval?.evaluation?.candidates || [];
  const readyCount = currentCandidatesList.filter((c) => c.status === 'READY').length;

  return (
    <div className="strategy-lab-workspace space-y-6">
      {/* 1. Workspace Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
            <p className="tracking-widest text-xs font-semibold text-gray-400 uppercase font-mono">
              STRATEGY LAB &amp; DETERMINISTIC PLAYBOOK WORKBENCH
            </p>
          </div>
          <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight mt-1">
            Strategy Lab
          </h1>
          <p className="text-xs text-gray-400 mt-0.5">
            กลยุทธ์ การประเมินย้อนหลัง และความพร้อมของ Backtest (STRAT01–06, Profiles, Snapshots &amp; Readiness)
          </p>
        </div>

        {/* Action / Badges */}
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/trading"
            className="text-xs text-gray-400 hover:text-amber-400 flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[#121c2e] border border-gray-800 transition-colors"
          >
            <span>←</span>
            <span>Market Overview</span>
          </Link>
          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded-md border border-emerald-500/20 font-mono">
            PAPER MODE · EXECUTION DISABLED
          </span>
        </div>
      </div>

      {/* 2. Cross-Module Navigation Pills */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 text-xs font-mono">
        <span className="text-gray-500 shrink-0">Quick Nav:</span>
        <Link
          href="/signals"
          className="px-2.5 py-1 rounded bg-black/40 text-amber-300 hover:bg-white/5 border border-white/10 shrink-0 transition-colors"
        >
          ⚡ Trading Signals →
        </Link>
        <Link
          href="/analysis"
          className="px-2.5 py-1 rounded bg-black/40 text-blue-300 hover:bg-white/5 border border-white/10 shrink-0 transition-colors"
        >
          📐 Market Analysis →
        </Link>
        <Link
          href="/trading"
          className="px-2.5 py-1 rounded bg-black/40 text-purple-300 hover:bg-white/5 border border-white/10 shrink-0 transition-colors"
        >
          📈 Market Overview →
        </Link>
        <Link
          href="/calendar"
          className="px-2.5 py-1 rounded bg-black/40 text-emerald-300 hover:bg-white/5 border border-white/10 shrink-0 transition-colors"
        >
          📅 Economic Calendar →
        </Link>
        <Link
          href="/risk"
          className="px-2.5 py-1 rounded bg-black/40 text-rose-300 hover:bg-white/5 border border-white/10 shrink-0 transition-colors"
        >
          🛡️ Risk Management →
        </Link>
      </div>

      {/* 3. Summary KPI Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 font-mono">
        {/* Active Strategies */}
        <div className="p-3.5 bg-[#0e1726] border border-gray-800 rounded-xl">
          <span className="text-[10px] text-gray-400 block uppercase">กลยุทธ์ในระบบ</span>
          <strong className="text-xl font-bold text-white block mt-0.5">
            {loadingStrategies ? '…' : `${strategies.length} Strategies`}
          </strong>
          <span className="text-[10px] text-emerald-400">STRAT01–STRAT06</span>
        </div>

        {/* Trader Profiles */}
        <div className="p-3.5 bg-[#0e1726] border border-gray-800 rounded-xl">
          <span className="text-[10px] text-gray-400 block uppercase">โปรไฟล์ผู้เทรด</span>
          <strong className="text-xl font-bold text-blue-400 block mt-0.5">
            {loadingProfiles ? '…' : `${profiles.length} Profiles`}
          </strong>
          <span className="text-[10px] text-gray-400">4 Trading Styles</span>
        </div>

        {/* Current Candidates */}
        <div className="p-3.5 bg-[#0e1726] border border-gray-800 rounded-xl">
          <span className="text-[10px] text-gray-400 block uppercase">ผู้สมัครรอบปัจจุบัน</span>
          <strong className="text-xl font-bold text-amber-300 block mt-0.5">
            {loadingCurrent ? '…' : currentCandidatesList.length}
          </strong>
          <span className="text-[10px] text-emerald-400 font-semibold">
            READY: {readyCount} รายการ
          </span>
        </div>

        {/* Historical Evaluations */}
        <div className="p-3.5 bg-[#0e1726] border border-gray-800 rounded-xl">
          <span className="text-[10px] text-gray-400 block uppercase">ประวัติ SNAPSHOTS</span>
          <strong className="text-xl font-bold text-purple-400 block mt-0.5">
            {loadingEvaluations ? '…' : evaluations.length}
          </strong>
          <span className="text-[10px] text-gray-400">Stored Audits</span>
        </div>

        {/* Backtest Engine Status */}
        <div className="p-3.5 bg-[#0e1726] border border-amber-500/30 rounded-xl col-span-2 sm:col-span-1">
          <span className="text-[10px] text-amber-400 block uppercase font-bold">BACKTEST ENGINE</span>
          <strong className="text-sm font-bold text-amber-300 block mt-1">
            PENDING PHASE 9
          </strong>
          <span className="text-[10px] text-gray-400 block">NOT IMPLEMENTED</span>
        </div>
      </div>

      {/* 4. Tab Navigation & Refresh Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-800 pb-2">
        <div className="flex items-center gap-1 overflow-x-auto">
          <button
            type="button"
            data-testid="tab-strategies"
            onClick={() => setActiveTab('STRATEGIES')}
            className={`px-4 py-2 text-xs font-bold rounded-lg transition-all font-mono whitespace-nowrap ${
              activeTab === 'STRATEGIES'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            STRATEGIES (แคตตาล็อกกลยุทธ์)
          </button>

          <button
            type="button"
            data-testid="tab-profiles"
            onClick={() => setActiveTab('PROFILES')}
            className={`px-4 py-2 text-xs font-bold rounded-lg transition-all font-mono whitespace-nowrap ${
              activeTab === 'PROFILES'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            PROFILES (โปรไฟล์ผู้เทรด)
          </button>

          <button
            type="button"
            data-testid="tab-evaluations"
            onClick={() => setActiveTab('EVALUATIONS')}
            className={`px-4 py-2 text-xs font-bold rounded-lg transition-all font-mono whitespace-nowrap ${
              activeTab === 'EVALUATIONS'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            EVALUATIONS (ผลประเมินย้อนหลัง)
          </button>

          <button
            type="button"
            data-testid="tab-backtest"
            onClick={() => setActiveTab('BACKTEST')}
            className={`px-4 py-2 text-xs font-bold rounded-lg transition-all font-mono whitespace-nowrap ${
              activeTab === 'BACKTEST'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            BACKTEST (ความพร้อม Backtest)
          </button>
        </div>

        {/* Refresh button & Source */}
        <div className="flex items-center gap-2 self-end sm:self-auto">
          {provider && (
            <span className="text-[11px] font-mono text-gray-400 hidden lg:inline">
              Source: {provider.source} ({provider.mode})
            </span>
          )}
          <button
            type="button"
            data-testid="refresh-btn"
            onClick={() => setRefreshTrigger((v) => v + 1)}
            disabled={isRefreshing}
            className="px-3 py-1.5 bg-[#121c2e] hover:bg-white/10 text-gray-300 rounded-lg text-xs font-mono border border-gray-800 transition-colors flex items-center gap-1.5"
          >
            <span className={isRefreshing ? 'animate-spin' : ''}>↻</span>
            <span>{isRefreshing ? 'กำลังซิงค์…' : 'รีเฟรช'}</span>
          </button>
        </div>
      </div>

      {/* 5. Active Tab Workspace Content */}
      <div className="strategy-lab-content">
        {activeTab === 'STRATEGIES' && (
          <StrategyCatalogTab
            strategies={strategies}
            loading={loadingStrategies}
            error={error}
            strategyConfigJson={currentEval?.evaluation?.context?.strategy_config_json}
          />
        )}

        {activeTab === 'PROFILES' && (
          <TraderProfilesTab
            profiles={profiles}
            loading={loadingProfiles}
            error={error}
            strategies={strategies}
          />
        )}

        {activeTab === 'EVALUATIONS' && (
          <EvaluationsTab
            currentEvaluation={currentEval}
            historicalEvaluations={evaluations}
            candidates={candidates}
            strategies={strategies}
            profiles={profiles}
            loadingCurrent={loadingCurrent}
            loadingHistory={loadingEvaluations}
            loadingCandidates={loadingCandidates}
            error={error}
          />
        )}

        {activeTab === 'BACKTEST' && (
          <BacktestReadinessTab context={currentEval?.evaluation?.context} />
        )}
      </div>
    </div>
  );
}
