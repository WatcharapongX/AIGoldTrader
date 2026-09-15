'use client';

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { api } from '@/lib/api';
import type { SetupCandidate, StrategyDefinition, StrategyResponse, TraderProfile } from '@/types/strategy.generated';
import { parsePortfolioRisk, parseRiskDecisions, type PortfolioRiskData, type RiskDecisionData } from '@/features/risk/contracts';
import {
  parseExtendedAccountSnapshot,
  computeCandidateAnalytics,
  computeRiskDecisionAnalytics,
  computeEvaluationActivity,
  type ExtendedAccountSnapshot,
} from './contracts';

import { PerformanceStatusHeader } from './PerformanceStatusHeader';
import { AccountSnapshotCard } from './AccountSnapshotCard';
import { PortfolioRiskCard } from './PortfolioRiskCard';
import { CandidateAnalyticsPanel } from './CandidateAnalyticsPanel';
import { RiskDecisionAnalyticsPanel } from './RiskDecisionAnalyticsPanel';
import { EvaluationActivityPanel } from './EvaluationActivityPanel';
import { ExecutionPerformanceSection } from './ExecutionPerformanceSection';
import { PerformanceReadinessPanel } from './PerformanceReadinessPanel';

type DateFilterRange = 'ALL' | '7D' | '30D';

export function PerformanceScreen() {
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  // Raw API datasets
  const [account, setAccount] = useState<ExtendedAccountSnapshot | null>(null);
  const [accountLoading, setAccountLoading] = useState(true);
  const [accountError, setAccountError] = useState<string | null>(null);

  const [portfolio, setPortfolio] = useState<PortfolioRiskData | null>(null);
  const [portfolioLoading, setPortfolioLoading] = useState(true);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);

  const [candidates, setCandidates] = useState<SetupCandidate[]>([]);
  const [candidatesLoading, setCandidatesLoading] = useState(true);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);

  const [strategies, setStrategies] = useState<StrategyDefinition[]>([]);
  const [profiles, setProfiles] = useState<TraderProfile[]>([]);

  const [decisions, setDecisions] = useState<RiskDecisionData[]>([]);
  const [decisionsLoading, setDecisionsLoading] = useState(true);
  const [decisionsError, setDecisionsError] = useState<string | null>(null);

  const [evaluations, setEvaluations] = useState<StrategyResponse[]>([]);
  const [evaluationsLoading, setEvaluationsLoading] = useState(true);
  const [evaluationsError, setEvaluationsError] = useState<string | null>(null);

  // Filters
  const [dateRange, setDateRange] = useState<DateFilterRange>('ALL');
  const [selectedStrategy, setSelectedStrategy] = useState<string>('ALL');
  const [selectedProfile, setSelectedProfile] = useState<string>('ALL');
  const [selectedState, setSelectedState] = useState<string>('ALL');
  const [selectedDirection, setSelectedDirection] = useState<string>('ALL');

  const handleRefresh = useCallback(() => {
    setIsRefreshing(true);
    setAccountLoading(true);
    setPortfolioLoading(true);
    setCandidatesLoading(true);
    setDecisionsLoading(true);
    setEvaluationsLoading(true);
    setRefreshTrigger((prev) => prev + 1);
  }, []);

  useEffect(() => {
    const abort = new AbortController();

    const fetchData = async () => {
      // 1. Account Snapshot
      try {
        const accRaw = await api.get('/risk/account', { signal: abort.signal });
        if (!abort.signal.aborted) {
          setAccount(parseExtendedAccountSnapshot(accRaw));
          setAccountError(null);
        }
      } catch (err) {
        if (!abort.signal.aborted) {
          setAccountError(err instanceof Error ? err.message : 'ไม่สามารถโหลดข้อมูลบัญชีได้');
        }
      } finally {
        if (!abort.signal.aborted) setAccountLoading(false);
      }

      // 2. Portfolio Risk
      try {
        const portRaw = await api.get('/risk/portfolio', { signal: abort.signal });
        if (!abort.signal.aborted) {
          setPortfolio(parsePortfolioRisk(portRaw));
          setPortfolioError(null);
        }
      } catch (err) {
        if (!abort.signal.aborted) {
          setPortfolioError(err instanceof Error ? err.message : 'ไม่สามารถโหลดข้อมูล Portfolio Risk ได้');
        }
      } finally {
        if (!abort.signal.aborted) setPortfolioLoading(false);
      }

      // 3. Trade Candidates
      try {
        const candsRaw = await api.get('/trade-candidates?limit=100', { signal: abort.signal });
        if (!abort.signal.aborted) {
          setCandidates(Array.isArray(candsRaw) ? (candsRaw as SetupCandidate[]) : []);
          setCandidatesError(null);
        }
      } catch (err) {
        if (!abort.signal.aborted) {
          setCandidatesError(err instanceof Error ? err.message : 'ไม่สามารถโหลดข้อมูล Candidates ได้');
        }
      } finally {
        if (!abort.signal.aborted) setCandidatesLoading(false);
      }

      // 4. Strategies Catalog & Trader Profiles
      try {
        const [stratsRaw, profsRaw] = await Promise.allSettled([
          api.get('/strategies', { signal: abort.signal }),
          api.get('/trader-profiles', { signal: abort.signal }),
        ]);
        if (!abort.signal.aborted) {
          if (stratsRaw.status === 'fulfilled' && Array.isArray(stratsRaw.value)) {
            setStrategies(stratsRaw.value as StrategyDefinition[]);
          }
          if (profsRaw.status === 'fulfilled' && Array.isArray(profsRaw.value)) {
            setProfiles(profsRaw.value as TraderProfile[]);
          }
        }
      } catch {
        // Non-critical fallback
      }

      // 5. Risk Decisions
      try {
        const decsRaw = await api.get('/risk/decisions?limit=50', { signal: abort.signal });
        if (!abort.signal.aborted) {
          setDecisions(parseRiskDecisions(decsRaw));
          setDecisionsError(null);
        }
      } catch (err) {
        if (!abort.signal.aborted) {
          setDecisionsError(err instanceof Error ? err.message : 'ไม่สามารถโหลดข้อมูล Risk Decisions ได้');
        }
      } finally {
        if (!abort.signal.aborted) setDecisionsLoading(false);
      }

      // 6. Strategy Evaluations
      try {
        const evalsRaw = await api.get('/strategy/evaluations?limit=25', { signal: abort.signal });
        if (!abort.signal.aborted) {
          setEvaluations(Array.isArray(evalsRaw) ? (evalsRaw as StrategyResponse[]) : []);
          setEvaluationsError(null);
        }
      } catch (err) {
        if (!abort.signal.aborted) {
          setEvaluationsError(err instanceof Error ? err.message : 'ไม่สามารถโหลดข้อมูล Strategy Evaluations ได้');
        }
      } finally {
        if (!abort.signal.aborted) {
          setEvaluationsLoading(false);
          setIsRefreshing(false);
          setLastUpdated(new Date());
        }
      }
    };

    void fetchData();

    return () => abort.abort();
  }, [refreshTrigger]);

  // Apply filters to candidates
  const filteredCandidates = useMemo(() => {
    let result = candidates;

    // Date range filter
    if (dateRange !== 'ALL' && lastUpdated) {
      const days = dateRange === '7D' ? 7 : 30;
      const cutoff = lastUpdated.getTime() - days * 86400000;
      result = result.filter((c) => {
        const time = Date.parse(c.detected_at);
        return Number.isFinite(time) && time >= cutoff;
      });
    }

    // Strategy filter
    if (selectedStrategy !== 'ALL') {
      result = result.filter((c) => c.strategy_id === selectedStrategy);
    }

    // Profile filter
    if (selectedProfile !== 'ALL') {
      result = result.filter((c) => c.profile_id === selectedProfile);
    }

    // State filter
    if (selectedState !== 'ALL') {
      result = result.filter((c) => c.status === selectedState);
    }

    // Direction filter
    if (selectedDirection !== 'ALL') {
      result = result.filter((c) => c.direction === selectedDirection);
    }

    return result;
  }, [candidates, dateRange, lastUpdated, selectedStrategy, selectedProfile, selectedState, selectedDirection]);

  // Compute analytics
  const candidateAnalytics = useMemo(() => {
    return computeCandidateAnalytics(filteredCandidates, 100);
  }, [filteredCandidates]);

  const riskDecisionAnalytics = useMemo(() => {
    return computeRiskDecisionAnalytics(decisions, 50);
  }, [decisions]);

  const evaluationActivity = useMemo(() => {
    return computeEvaluationActivity(evaluations, 25);
  }, [evaluations]);

  return (
    <div className="min-h-screen bg-[#080c14] text-gray-100 p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <PerformanceStatusHeader
        lastUpdated={lastUpdated}
        isRefreshing={isRefreshing}
        onRefresh={handleRefresh}
        tradingMode={account?.trading_mode || 'UNAVAILABLE'}
      />

      {/* Filter Control Bar */}
      <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-4 flex flex-wrap items-center justify-between gap-3 text-xs">
        <div className="flex flex-wrap items-center gap-3">
          <span className="text-gray-400 font-semibold flex items-center gap-1.5">
            <svg className="w-4 h-4 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
            </svg>
            ตัวกรองข้อมูล (Filters):
          </span>

          {/* Date Range */}
          <div className="flex rounded-lg bg-slate-900 border border-slate-800 p-0.5">
            {(['ALL', '7D', '30D'] as const).map((r) => (
              <button
                key={r}
                onClick={() => setDateRange(r)}
                className={`px-2.5 py-1 rounded text-xs font-mono font-medium transition ${
                  dateRange === r ? 'bg-amber-500 text-slate-950 font-bold' : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {r === 'ALL' ? 'ALL LOADED' : r}
              </button>
            ))}
          </div>

          {/* Strategy filter */}
          <select
            value={selectedStrategy}
            onChange={(e) => setSelectedStrategy(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500 font-mono text-xs"
          >
            <option value="ALL">ทุกกลยุทธ์ (All Strategies)</option>
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id} — {s.name}
              </option>
            ))}
          </select>

          {/* Profile filter */}
          <select
            value={selectedProfile}
            onChange={(e) => setSelectedProfile(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500 font-mono text-xs"
          >
            <option value="ALL">ทุกโปรไฟล์ (All Profiles)</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.id})
              </option>
            ))}
          </select>

          {/* State filter */}
          <select
            value={selectedState}
            onChange={(e) => setSelectedState(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500 font-mono text-xs"
          >
            <option value="ALL">ทุกสถานะ (All States)</option>
            <option value="READY">READY</option>
            <option value="DETECTED">DETECTED</option>
            <option value="WAITING_CONFIRMATION">WAITING_CONFIRMATION</option>
            <option value="BLOCKED_CONTEXT">BLOCKED_CONTEXT</option>
            <option value="NO_TRADE">NO_TRADE</option>
            <option value="INVALIDATED">INVALIDATED</option>
            <option value="EXPIRED">EXPIRED</option>
            <option value="SUPERSEDED">SUPERSEDED</option>
          </select>

          {/* Direction filter */}
          <select
            value={selectedDirection}
            onChange={(e) => setSelectedDirection(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-gray-200 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500 font-mono text-xs"
          >
            <option value="ALL">ทุกฝั่ง (All Directions)</option>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
            <option value="NO_TRADE">NO_TRADE</option>
          </select>
        </div>

        {/* Clear filters */}
        {(dateRange !== 'ALL' || selectedStrategy !== 'ALL' || selectedProfile !== 'ALL' || selectedState !== 'ALL' || selectedDirection !== 'ALL') && (
          <button
            onClick={() => {
              setDateRange('ALL');
              setSelectedStrategy('ALL');
              setSelectedProfile('ALL');
              setSelectedState('ALL');
              setSelectedDirection('ALL');
            }}
            className="text-amber-400 hover:text-amber-300 font-medium underline"
          >
            ล้างตัวกรองทั้งหมด
          </button>
        )}
      </div>

      {/* Account Snapshot & Portfolio Risk (Top Row) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <AccountSnapshotCard
          account={account}
          isLoading={accountLoading}
          error={accountError}
        />
        <PortfolioRiskCard
          portfolio={portfolio}
          isLoading={portfolioLoading}
          error={portfolioError}
        />
      </div>

      {/* Candidate Analytics Section */}
      <CandidateAnalyticsPanel
        summary={candidateAnalytics}
        strategies={strategies}
        profiles={profiles}
        isLoading={candidatesLoading}
        error={candidatesError}
      />

      {/* Risk Decision Analytics Section */}
      <RiskDecisionAnalyticsPanel
        summary={riskDecisionAnalytics}
        isLoading={decisionsLoading}
        error={decisionsError}
      />

      {/* Historical Evaluation Activity Section */}
      <EvaluationActivityPanel
        summary={evaluationActivity}
        isLoading={evaluationsLoading}
        error={evaluationsError}
      />

      {/* Executed Trading Performance Section (Strictly NOT AVAILABLE) */}
      <ExecutionPerformanceSection />

      {/* Performance Readiness Matrix Section */}
      <PerformanceReadinessPanel />
    </div>
  );
}
