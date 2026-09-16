'use client';

import React, { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { StrategyWorkspace } from '@/features/strategy/StrategyWorkspace';
import { AnalysisPrimitive } from '@/features/analysis/primitive';
import { SignalSummaryHeader } from '@/features/strategy/SignalSummaryHeader';
import {
  SignalFilterBar,
  type CandidateTab,
  type CanonicalStateFilter,
} from '@/features/strategy/SignalFilterBar';
import { SignalCard } from '@/features/strategy/SignalCard';
import { SignalDetailPanel } from '@/features/strategy/SignalDetailPanel';
import { api } from '@/lib/api';
import { parseStatus, timeframes } from '@/features/chart/contracts';
import { parseKillSwitch, parseRiskDecisions, type KillSwitchData, type RiskDecisionData } from '@/features/risk/contracts';
import type { MarketDataStatus, Timeframe } from '@/types/market.generated';
import type {
  SetupCandidate,
  StrategyDefinition,
  StrategyResponse,
  TraderProfile,
} from '@/types/strategy.generated';

export function TradingSignalsScreen({ initialCandidateId = null }: { initialCandidateId?: string | null }) {
  const [timeframe, setTimeframe] = useState<Timeframe>('M5');
  const [provider, setProvider] = useState<MarketDataStatus | null>(null);
  const [primitive] = useState(() => new AnalysisPrimitive());
  const [revision, setRevision] = useState('initial');
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(true);

  // Strategy & Candidate Data
  const [strategyResponse, setStrategyResponse] = useState<StrategyResponse | null>(null);
  const [historyCandidates, setHistoryCandidates] = useState<SetupCandidate[]>([]);
  const [strategies, setStrategies] = useState<StrategyDefinition[]>([]);
  const [profiles, setProfiles] = useState<TraderProfile[]>([]);
  const [killSwitch, setKillSwitch] = useState<KillSwitchData | null>(null);
  const [riskDecisions, setRiskDecisions] = useState<RiskDecisionData[]>([]);

  // Selected candidate state (persists across reloads)
  const [selectedId, setSelectedId] = useState<string>('');
  const [candidateLinkPending, setCandidateLinkPending] = useState(Boolean(initialCandidateId));
  const [candidateLinkNotice, setCandidateLinkNotice] = useState('');

  // Filters
  const [activeTab, setActiveTab] = useState<CandidateTab>('CURRENT');
  const [stateFilter, setStateFilter] = useState<CanonicalStateFilter>('ALL');
  const [strategyFilter, setStrategyFilter] = useState<string>('ALL');
  const [profileFilter, setProfileFilter] = useState<string>('ALL');
  const [directionFilter, setDirectionFilter] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');

  // 1. Initial & recurring market status
  useEffect(() => {
    const abort = new AbortController();
    const fetchStatus = async () => {
      try {
        const status = parseStatus(await api.get('/market/status', { signal: abort.signal }));
        setProvider(status);
        setRevision(`rev-${status.source}-${Date.now()}`);
      } catch {
        // Safe fallback
      }
    };
    void fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => {
      abort.abort();
      clearInterval(interval);
    };
  }, []);

  // 2. Fetch authoritative candidates, strategies, profiles, risk decisions, kill switch
  useEffect(() => {
    let active = true;
    const abort = new AbortController();

    const fetchAllData = async () => {
      setIsRefreshing(true);
      try {
        // Current Strategy Context
        try {
          const strat = (await api.get('/strategy/context', { signal: abort.signal })) as StrategyResponse;
          if (active) setStrategyResponse(strat);
        } catch {}

        // Persisted Candidates History
        try {
          const hist = (await api.get('/trade-candidates?limit=50', { signal: abort.signal })) as SetupCandidate[];
          if (active && Array.isArray(hist)) {
            setHistoryCandidates(hist);
          }
        } catch {}

        // Strategies List
        try {
          const strats = (await api.get('/strategies', { signal: abort.signal })) as StrategyDefinition[];
          if (active && Array.isArray(strats)) {
            setStrategies(strats);
          }
        } catch {}

        // Trader Profiles List
        try {
          const profs = (await api.get('/trader-profiles', { signal: abort.signal })) as TraderProfile[];
          if (active && Array.isArray(profs)) {
            setProfiles(profs);
          }
        } catch {}

        // Kill Switch
        try {
          const rawKs = await api.get('/risk/kill-switch', { signal: abort.signal });
          if (active) setKillSwitch(parseKillSwitch(rawKs));
        } catch {}

        // Risk Decisions
        try {
          const rawDecisions = await api.get('/risk/decisions?limit=50', { signal: abort.signal });
          const parsed = parseRiskDecisions(rawDecisions);
          if (active && Array.isArray(parsed)) {
            setRiskDecisions(parsed);
          }
        } catch {}
      } finally {
        if (active) setIsRefreshing(false);
      }
    };

    void fetchAllData();

    return () => {
      active = false;
      abort.abort();
    };
  }, [refreshTrigger]);

  // Determine current active pool of candidates based on tab
  const currentCandidates = useMemo(() => strategyResponse?.evaluation?.candidates || [], [strategyResponse]);
  const baseCandidates = activeTab === 'CURRENT' ? currentCandidates : historyCandidates;

  useEffect(() => {
    const timer = window.setTimeout(() => setCandidateLinkPending(Boolean(initialCandidateId)), 0);
    return () => window.clearTimeout(timer);
  }, [initialCandidateId]);

  useEffect(() => {
    if (!candidateLinkPending || !initialCandidateId || isRefreshing) return;
    const timer = window.setTimeout(() => {
      const current = currentCandidates.find((candidate) => candidate.id === initialCandidateId);
      const historical = historyCandidates.find((candidate) => candidate.id === initialCandidateId);
      if (current || historical) {
        setActiveTab(current ? 'CURRENT' : 'HISTORY');
        setStateFilter('ALL');
        setStrategyFilter('ALL');
        setProfileFilter('ALL');
        setDirectionFilter('ALL');
        setSearchQuery('');
        setSelectedId(initialCandidateId);
        setCandidateLinkNotice('');
      } else {
        setCandidateLinkNotice('ไม่พบ Candidate ที่ระบุในข้อมูล authoritative; ไม่ได้สร้างข้อมูลทดแทน');
      }
      setCandidateLinkPending(false);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [candidateLinkPending, initialCandidateId, isRefreshing, currentCandidates, historyCandidates]);

  // Filtered candidate list
  const filteredCandidates = useMemo(() => {
    return baseCandidates
      .filter((c) => {
        // State Filter
        if (stateFilter !== 'ALL' && c.status !== stateFilter) return false;
        // Strategy Filter
        if (strategyFilter !== 'ALL' && c.strategy_id !== strategyFilter) return false;
        // Profile Filter
        if (profileFilter !== 'ALL' && c.profile_id !== profileFilter) return false;
        // Direction Filter
        if (directionFilter !== 'ALL' && c.direction !== directionFilter) return false;
        // Search Query
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase().trim();
          const matchesId = c.id.toLowerCase().includes(q);
          const matchesStrategy = c.strategy_id.toLowerCase().includes(q);
          const matchesSymbol = c.symbol.toLowerCase().includes(q);
          if (!matchesId && !matchesStrategy && !matchesSymbol) return false;
        }
        return true;
      })
      .sort((a, b) => Date.parse(b.detected_at) - Date.parse(a.detected_at)); // Newest first
  }, [baseCandidates, stateFilter, strategyFilter, profileFilter, directionFilter, searchQuery]);

  // Selected candidate resolution (keep selected if exists; otherwise pick first)
  const selectedCandidate = useMemo(() => {
    if (selectedId) {
      const found = filteredCandidates.find((c) => c.id === selectedId) || baseCandidates.find((c) => c.id === selectedId);
      if (found) return found;
    }
    return filteredCandidates[0] || null;
  }, [selectedId, filteredCandidates, baseCandidates]);

  // Active strategy & profile metadata for selected candidate
  const selectedStrategy = strategies.find((s) => s.id === selectedCandidate?.strategy_id);
  const selectedProfile = profiles.find((p) => p.id === selectedCandidate?.profile_id);

  return (
    <div className="trading-workspace space-y-6">
      {candidateLinkNotice && <div role="alert" className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">{candidateLinkNotice}</div>}
      {/* Header with Market Overview Link and Paper Mode Badge */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
            <p className="market-eyebrow tracking-widest text-xs font-semibold text-gray-400">
              RULE-BASED TRADING SIGNALS &amp; STRATEGY EVALUATION
            </p>
          </div>
          <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight mt-1">
            Trading Signals
          </h1>
          <p className="text-xs text-gray-400 mt-0.5">
            ระบบคัดกรองและประเมินสัญญาณเทรดทองคำตาม 7 โปรไฟล์ผู้เทรด พร้อมกฎเกณฑ์ Setup Scoring และแผน Entry / SL / TP
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/trading"
            className="px-3 py-1.5 bg-white/10 hover:bg-white/15 text-gray-300 hover:text-white text-xs font-medium rounded-md border border-white/10 transition-colors flex items-center gap-1"
          >
            <span>←</span>
            <span>Market Overview</span>
          </Link>
          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded-md border border-emerald-500/20 font-mono">
            PAPER MODE · EXECUTION DISABLED
          </span>
        </div>
      </div>

      {/* 1. Signal Summary & Status Header */}
      <SignalSummaryHeader
        candidates={baseCandidates}
        provider={provider}
        killSwitch={killSwitch}
        asOf={strategyResponse?.evaluation?.context?.as_of}
        isStale={strategyResponse?.stale}
      />

      {/* 2. Signal Filter & Tab Bar */}
      <SignalFilterBar
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        stateFilter={stateFilter}
        onSelectState={setStateFilter}
        strategyFilter={strategyFilter}
        onSelectStrategy={setStrategyFilter}
        profileFilter={profileFilter}
        onSelectProfile={setProfileFilter}
        directionFilter={directionFilter}
        onSelectDirection={setDirectionFilter}
        strategies={strategies}
        profiles={profiles}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onRefresh={() => setRefreshTrigger((v) => v + 1)}
        isRefreshing={isRefreshing}
      />

      {/* 3. Operational Signal Grid: Candidate List (Left) & Detail Panel (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Candidate List Column */}
        <div className="lg:col-span-5 space-y-3">
          <div className="flex items-center justify-between px-1">
            <span className="text-xs font-bold text-gray-300 uppercase tracking-wider">
              {activeTab === 'CURRENT' ? 'รอบประเมินปัจจุบัน' : 'ประวัติบันทึกย้อนหลัง'} ({filteredCandidates.length})
            </span>
            <span className="text-[11px] font-mono text-gray-400">
              เรียงลำดับ: ล่าสุดก่อน (Newest first)
            </span>
          </div>

          {filteredCandidates.length === 0 ? (
            <div
              data-testid="no-candidates-filtered"
              className="p-8 bg-[#0e1726] border border-gray-800 rounded-xl text-center text-gray-400 text-xs space-y-2"
            >
              <span className="text-2xl block">🔍</span>
              <p className="font-semibold text-gray-300">
                {activeTab === 'CURRENT'
                  ? 'ยังไม่พบ Setup ที่ผ่านเกณฑ์ในรอบนี้'
                  : 'ยังไม่มีประวัติ Candidate ที่ตรงกับตัวกรอง'}
              </p>
              <p className="text-[11px] text-gray-400">
                ลองปรับเปลี่ยนตัวกรองสถานะ, กลยุทธ์ หรือโปรไฟล์ผู้เทรด
              </p>
            </div>
          ) : (
            <div className="space-y-2.5 max-h-[720px] overflow-y-auto pr-1">
              {filteredCandidates.map((cand) => {
                const strat = strategies.find((s) => s.id === cand.strategy_id);
                const prof = profiles.find((p) => p.id === cand.profile_id);
                return (
                  <SignalCard
                    key={cand.id}
                    candidate={cand}
                    isSelected={selectedCandidate?.id === cand.id}
                    onSelect={(id) => setSelectedId(id)}
                    strategy={strat}
                    profile={prof}
                  />
                );
              })}
            </div>
          )}
        </div>

        {/* Selected Candidate Detail Panel */}
        <div className="lg:col-span-7">
          <SignalDetailPanel
            candidate={selectedCandidate}
            strategy={selectedStrategy}
            profile={selectedProfile}
            killSwitch={killSwitch}
            riskDecisions={riskDecisions}
          />
        </div>
      </div>

      {/* Timeframe Bar */}
      <div className="bg-[#101925] border border-[#253044] rounded-xl p-4 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-gray-300">กรอบเวลาที่กำลังประเมิน:</span>
          <div className="timeframes" role="group" aria-label="Timeframe">
            {timeframes.map((tf) => (
              <button key={tf} aria-pressed={timeframe === tf} onClick={() => setTimeframe(tf)}>
                {tf}
              </button>
            ))}
          </div>
        </div>
        <span className="text-xs text-gray-400">
          แหล่งข้อมูลราคา: <b className="text-amber-400 font-mono">{provider?.source || 'UNKNOWN'}</b>
        </span>
      </div>

      {/* Strategy Workspace Component (Full Engine & Multi-Timeframe Context) */}
      <StrategyWorkspace
        timeframe={timeframe}
        source={provider?.source || 'UNKNOWN'}
        revision={revision}
        primitive={primitive}
      />
    </div>
  );
}
