'use client';

import React, { useState, useMemo } from 'react';
import Link from 'next/link';
import type { SetupCandidate, StrategyDefinition, StrategyResponse, TraderProfile } from '@/types/strategy.generated';
import { utc } from './thai';

interface EvaluationsTabProps {
  currentEvaluation: StrategyResponse | null;
  historicalEvaluations: StrategyResponse[];
  candidates: SetupCandidate[];
  strategies: StrategyDefinition[];
  profiles: TraderProfile[];
  loadingCurrent: boolean;
  loadingHistory: boolean;
  loadingCandidates: boolean;
  error: string | null;
  historyError?: string | null;
  candidatesError?: string | null;
}

const CANONICAL_STATES = [
  'READY',
  'WAITING_CONFIRMATION',
  'DETECTED',
  'BLOCKED_CONTEXT',
  'NO_TRADE',
  'INVALIDATED',
  'EXPIRED',
  'SUPERSEDED',
] as const;

export function EvaluationsTab({
  currentEvaluation,
  historicalEvaluations,
  candidates,
  strategies,
  profiles,
  loadingCurrent,
  loadingHistory,
  loadingCandidates,
  error,
  historyError,
  candidatesError,
}: EvaluationsTabProps) {
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);

  // Canonical state counts for current evaluation
  const currentCandidates = useMemo(
    () => currentEvaluation?.evaluation?.candidates || [],
    [currentEvaluation?.evaluation?.candidates]
  );
  const stateCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const st of CANONICAL_STATES) {
      counts[st] = 0;
    }
    for (const c of currentCandidates) {
      if (counts[c.status] !== undefined) {
        counts[c.status]++;
      } else {
        counts[c.status] = 1;
      }
    }
    return counts;
  }, [currentCandidates]);

  // Selected historical snapshot
  const selectedSnapshot = useMemo(() => {
    if (!selectedSnapshotId) return null;
    return (
      historicalEvaluations.find(
        (h) => h.evaluation.id === selectedSnapshotId || h.generated_at === selectedSnapshotId
      ) || null
    );
  }, [selectedSnapshotId, historicalEvaluations]);

  // Candidate descriptive statistics from real trade_candidates history
  const candidateStats = useMemo(() => {
    const byStrategy: Record<string, number> = {};
    const byProfile: Record<string, number> = {};
    const byState: Record<string, number> = {};
    const byDirection: Record<string, number> = { LONG: 0, SHORT: 0, NO_TRADE: 0 };

    for (const c of candidates) {
      byStrategy[c.strategy_id] = (byStrategy[c.strategy_id] || 0) + 1;
      byProfile[c.profile_id] = (byProfile[c.profile_id] || 0) + 1;
      byState[c.status] = (byState[c.status] || 0) + 1;
      if (byDirection[c.direction] !== undefined) {
        byDirection[c.direction]++;
      }
    }

    return {
      total: candidates.length,
      byStrategy,
      byProfile,
      byState,
      byDirection,
    };
  }, [candidates]);

  return (
    <div data-testid="evaluations-tab" className="space-y-8">
      {/* 1. CURRENT EVALUATION SECTION */}
      <section className="space-y-4" aria-label="Current Strategy Evaluation">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800 pb-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              <h3 className="text-sm font-bold text-white uppercase tracking-wider">
                ผลการประเมินรอบปัจจุบัน (Current Evaluation Snapshot)
              </h3>
            </div>
            <p className="text-xs text-gray-400 mt-0.5">
              สถานะล่าสุดของ Strategy Engine ตามข้อมูลตลาดและแท่งเทียนที่ปิดแล้ว
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href="/signals"
              className="px-3 py-1 bg-amber-500/20 text-amber-300 hover:bg-amber-500/30 text-xs font-semibold rounded-lg border border-amber-500/40 transition-colors"
            >
              ไปยังหน้า Trading Signals →
            </Link>
          </div>
        </div>

        {loadingCurrent ? (
          <div data-testid="current-eval-loading" className="p-8 text-center text-gray-400 text-sm">
            กำลังโหลดผลการประเมินปัจจุบัน...
          </div>
        ) : error && !currentEvaluation ? (
          <div data-testid="current-eval-error" className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs">
            {error}
          </div>
        ) : currentEvaluation ? (
          <div className="space-y-4">
            {/* Meta Strip */}
            <div className="p-4 bg-[#0e1726] border border-gray-800 rounded-xl grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 text-xs font-mono">
              <div>
                <span className="text-[10px] text-gray-400 block">AS OF (UTC)</span>
                <strong className="text-gray-200">
                  {utc(currentEvaluation.evaluation.context.as_of)}
                </strong>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 block">SOURCE / MODE</span>
                <span className="text-amber-300 font-bold">
                  {currentEvaluation.evaluation.context.source} · {currentEvaluation.evaluation.context.mode}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 block">CURRENT SESSION</span>
                <strong className="text-blue-300">
                  {currentEvaluation.evaluation.context.current_session}
                </strong>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 block">CONFIG ID</span>
                <span className="text-gray-400 truncate block">
                  {currentEvaluation.evaluation.context.config_id.slice(0, 12)}…
                </span>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 block">ENGINE VERSION</span>
                <strong className="text-gray-200">
                  {currentEvaluation.evaluation.context.engine_version || 'UNAVAILABLE'}
                </strong>
              </div>
              <div>
                <span className="text-[10px] text-gray-400 block">FRESHNESS</span>
                <span
                  className={`font-bold ${
                    currentEvaluation.stale ? 'text-rose-400' : 'text-emerald-400'
                  }`}
                >
                  {currentEvaluation.stale ? 'STALE' : 'FRESH'}
                </span>
              </div>
            </div>

            {/* Canonical State Counters */}
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
              {CANONICAL_STATES.map((st) => {
                const count = stateCounts[st] || 0;
                const isReady = st === 'READY';
                const isBlocked = st === 'BLOCKED_CONTEXT';

                return (
                  <div
                    key={st}
                    className={`p-2.5 rounded-lg border text-center font-mono ${
                      isReady && count > 0
                        ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                        : isBlocked && count > 0
                        ? 'bg-orange-500/15 border-orange-500/40 text-orange-300'
                        : 'bg-[#0e1726] border-gray-800 text-gray-400'
                    }`}
                  >
                    <span className="text-[9px] block uppercase truncate" title={st}>
                      {st}
                    </span>
                    <strong className="text-lg font-bold block mt-0.5">{count}</strong>
                  </div>
                );
              })}
            </div>

            {/* Current Candidates Result Matrix */}
            <div className="rounded-xl border border-gray-800 bg-[#0e1726] overflow-hidden">
              <div className="p-3 bg-[#121c2e] border-b border-gray-800 flex items-center justify-between">
                <span className="text-xs font-bold text-white uppercase tracking-wider">
                  รายการประเมินสัญญาณปัจจุบัน ({currentCandidates.length} Candidates)
                </span>
                <span className="text-[11px] font-mono text-gray-400">
                  Setup Evidence Score (ไม่ใช่ Win Rate)
                </span>
              </div>

              {currentCandidates.length === 0 ? (
                <div className="p-6 text-center text-gray-400 text-xs italic">
                  ยังไม่พบ Setup Candidate ในรอบการประเมินนี้
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs font-mono">
                    <thead className="bg-black/30 text-gray-400 border-b border-gray-800">
                      <tr>
                        <th className="p-2.5">กลยุทธ์</th>
                        <th className="p-2.5">โปรไฟล์</th>
                        <th className="p-2.5">ฝั่ง (Direction)</th>
                        <th className="p-2.5">สถานะ (Canonical State)</th>
                        <th className="p-2.5 text-center">Evidence Score</th>
                        <th className="p-2.5 text-center">Trade Plan</th>
                        <th className="p-2.5 text-right">หมดอายุ (Expires UTC)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800/60 text-gray-300">
                      {currentCandidates.map((c) => {
                        const strat = strategies.find((s) => s.id === c.strategy_id);
                        const prof = profiles.find((p) => p.id === c.profile_id);

                        return (
                          <tr key={c.id} className="hover:bg-white/5 transition-colors">
                            <td className="p-2.5 font-bold text-white">
                              {strat?.name || c.strategy_id}
                              <span className="text-[10px] text-gray-400 block font-normal">
                                {c.strategy_id}
                              </span>
                            </td>
                            <td className="p-2.5 text-gray-300">
                              {prof?.name || c.profile_id}
                            </td>
                            <td className="p-2.5">
                              <span
                                className={`font-bold ${
                                  c.direction === 'LONG'
                                    ? 'text-emerald-400'
                                    : c.direction === 'SHORT'
                                    ? 'text-rose-400'
                                    : 'text-gray-400'
                                }`}
                              >
                                {c.direction}
                              </span>
                            </td>
                            <td className="p-2.5">
                              <span
                                className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                                  c.status === 'READY'
                                    ? 'bg-emerald-500/20 text-emerald-300'
                                    : c.status === 'WAITING_CONFIRMATION'
                                    ? 'bg-amber-500/20 text-amber-300'
                                    : c.status === 'BLOCKED_CONTEXT'
                                    ? 'bg-orange-500/20 text-orange-300'
                                    : 'bg-gray-800 text-gray-400'
                                }`}
                              >
                                {c.status}
                              </span>
                            </td>
                            <td className="p-2.5 text-center">
                              <strong className="text-amber-300 font-bold">
                                {c.score} <span className="text-[10px] text-gray-400">/ 100</span>
                              </strong>
                            </td>
                            <td className="p-2.5 text-center">
                              {c.plan ? (
                                <span className="text-emerald-400 font-bold">AVAILABLE</span>
                              ) : (
                                <span className="text-gray-500">—</span>
                              )}
                            </td>
                            <td className="p-2.5 text-right text-gray-400">
                              {utc(c.expires_at)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ) : null}
      </section>

      {/* 2. HISTORICAL EVALUATION SNAPSHOTS (EXPLICITLY NOT A BACKTEST) */}
      <section className="space-y-4" aria-label="Historical Evaluation Snapshots">
        <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-xl space-y-2">
          <div className="flex items-center gap-2">
            <span className="text-base">🕒</span>
            <h3 className="text-sm font-bold text-blue-300">
              ประวัติผลการประเมินกลยุทธ์ (Historical Evaluation Snapshots)
            </h3>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            ตารางนี้แสดงประวัติผลการประเมินที่ถูกบันทึกไว้ในฐานข้อมูล ณ รอบเวลาในอดีต (Audit Snapshots)
            <strong className="text-blue-400 block mt-1">
              * ข้อชี้แจงสำคัญ: หน้านี้ไม่ใช่ผลการจำลองการเทรดย้อนหลัง (Backtest) ไม่มีการคำนวณกำไร/ขาดทุน (P&amp;L) หรือการจับคู่ Order Execution ใดๆ ทั้งสิ้น
            </strong>
          </p>
        </div>

        {loadingHistory ? (
          <div data-testid="history-eval-loading" className="p-8 text-center text-gray-400 text-sm">
            กำลังโหลดประวัติผลการประเมิน...
          </div>
        ) : historyError ? (
          <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs">
            UNAVAILABLE: {historyError}
          </div>
        ) : historicalEvaluations.length === 0 ? (
          <div data-testid="history-empty" className="p-8 bg-[#0e1726] border border-gray-800 rounded-xl text-center text-gray-400 text-xs">
            <span className="text-2xl block mb-2">📂</span>
            <p className="font-semibold text-gray-300">ยังไม่มีประวัติการประเมินกลยุทธ์ (No Evaluation History Stored)</p>
            <p className="text-[11px] text-gray-400 mt-1">
              เมื่อระบบ Strategy Engine ทำการประเมินรอบถัดไป ข้อมูล Snapshot จะถูกบันทึกลงฐานข้อมูลโดยอัตโนมัติ
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="overflow-x-auto rounded-xl border border-gray-800 bg-[#0e1726]">
              <table className="w-full text-left text-xs font-mono">
                <thead className="bg-[#121c2e] text-gray-300 uppercase border-b border-gray-800">
                  <tr>
                    <th className="p-3">จุดเวลาประเมิน (As Of UTC)</th>
                    <th className="p-3">เวลาที่บันทึก (Generated UTC)</th>
                    <th className="p-3">แหล่งข้อมูล (Source)</th>
                    <th className="p-3 text-center">ผู้สมัคร (Candidates)</th>
                    <th className="p-3 text-center">READY</th>
                    <th className="p-3 text-center">BLOCKED</th>
                    <th className="p-3">Config ID</th>
                    <th className="p-3 text-right">เลือกตรวจ</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60 text-gray-300">
                  {historicalEvaluations.map((h, idx) => {
                    const candList = h.evaluation.candidates || [];
                    const readyCount = candList.filter((c) => c.status === 'READY').length;
                    const blockedCount = candList.filter((c) => c.status === 'BLOCKED_CONTEXT').length;
                    const isSelected = selectedSnapshotId === (h.evaluation.id || h.generated_at);

                    return (
                      <tr
                        key={h.evaluation.id || h.generated_at || idx}
                        className={`transition-colors cursor-pointer ${
                          isSelected ? 'bg-amber-500/10' : 'hover:bg-white/5'
                        }`}
                        onClick={() => setSelectedSnapshotId(h.evaluation.id || h.generated_at)}
                      >
                        <td className="p-3 font-semibold text-white">
                          {utc(h.evaluation.context.as_of)}
                        </td>
                        <td className="p-3 text-gray-400">
                          {utc(h.generated_at)}
                        </td>
                        <td className="p-3 text-gray-300">
                          {h.evaluation.context.source}
                        </td>
                        <td className="p-3 text-center font-bold text-gray-200">
                          {candList.length}
                        </td>
                        <td className="p-3 text-center">
                          <span className="text-emerald-400 font-bold">{readyCount}</span>
                        </td>
                        <td className="p-3 text-center">
                          <span className="text-orange-400 font-bold">{blockedCount}</span>
                        </td>
                        <td className="p-3 text-gray-400 truncate max-w-[120px]">
                          {h.evaluation.context.config_id.slice(0, 10)}…
                        </td>
                        <td className="p-3 text-right">
                          <button
                            type="button"
                            className="px-2.5 py-1 text-[11px] rounded bg-white/5 hover:bg-white/10 text-amber-300 border border-white/10"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedSnapshotId(h.evaluation.id || h.generated_at);
                            }}
                          >
                            {isSelected ? 'กำลังดู' : 'ดูรายละเอียด'}
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            {/* Selected Snapshot Inspector Drawer */}
            {selectedSnapshot && (
              <div
                data-testid="snapshot-detail"
                className="p-5 bg-[#121c2e] border border-amber-500/30 rounded-xl space-y-4"
              >
                <div className="flex items-center justify-between border-b border-gray-800 pb-3">
                  <div>
                    <h4 className="text-sm font-bold text-amber-300">
                      รายละเอียด Snapshot ประวัติย้อนหลัง
                    </h4>
                    <p className="text-xs text-gray-400 font-mono">
                      As Of: {utc(selectedSnapshot.evaluation.context.as_of)} · ID: {selectedSnapshot.evaluation.id}
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setSelectedSnapshotId(null)}
                    className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded bg-black/30"
                  >
                    ปิด (Close)
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs font-mono">
                  <div className="p-3 bg-black/40 rounded-lg border border-white/5">
                    <span className="text-gray-400 block text-[10px]">CANDIDATES TOTAL</span>
                    <strong className="text-white text-base">
                      {selectedSnapshot.evaluation.candidates.length}
                    </strong>
                  </div>
                  <div className="p-3 bg-black/40 rounded-lg border border-white/5">
                    <span className="text-gray-400 block text-[10px]">CURRENT SESSION</span>
                    <strong className="text-blue-400 text-base">
                      {selectedSnapshot.evaluation.context.current_session}
                    </strong>
                  </div>
                  <div className="p-3 bg-black/40 rounded-lg border border-white/5">
                    <span className="text-gray-400 block text-[10px]">RECORD AS OF</span>
                    <strong className="text-gray-300 text-xs">
                      {utc(selectedSnapshot.evaluation.context.as_of)}
                    </strong>
                  </div>
                </div>

                {/* Candidate List of Selected Snapshot */}
                <div className="space-y-2">
                  <span className="text-xs font-bold text-gray-300 block">
                    ผู้สมัครที่พบใน Snapshot นี้ ({selectedSnapshot.evaluation.candidates.length}):
                  </span>
                  <div className="space-y-1.5 max-h-56 overflow-y-auto pr-1">
                    {selectedSnapshot.evaluation.candidates.map((cand) => (
                      <div
                        key={cand.id}
                        className="p-2.5 bg-black/30 rounded border border-white/5 flex items-center justify-between text-xs font-mono"
                      >
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-amber-300">{cand.strategy_id}</span>
                          <span className="text-gray-400">({cand.profile_id})</span>
                          <span className="font-bold text-white">{cand.direction}</span>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className="text-amber-400">Score: {cand.score} / 100</span>
                          <span className="px-2 py-0.5 rounded bg-white/5 text-[10px] text-gray-300">
                            {cand.status}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {/* 3. CANDIDATE DESCRIPTIVE STATISTICS (REAL DATA ONLY) */}
      <section className="space-y-4" aria-label="Candidate Statistics">
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div>
            <h3 className="text-sm font-bold text-white uppercase tracking-wider">
              สถิติเชิงพรรณนาของผู้สมัครสัญญาณ (Candidate Descriptive Statistics)
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              ความถี่การตรวจพบเงื่อนไขของสัญญาณในประวัติระบบ (ข้อมูลจริงจาก /api/trade-candidates)
            </p>
          </div>
          <span className="text-xs font-mono text-gray-400">
            รวม {candidatesError ? 'UNAVAILABLE' : candidateStats.total} บันทึก
          </span>
        </div>

        {loadingCandidates ? (
          <div data-testid="candidates-stats-loading" className="p-8 text-center text-gray-400 text-sm">
            กำลังคำนวณสถิติสัญญาณ...
          </div>
        ) : candidatesError ? (
          <div className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs">
            UNAVAILABLE: {candidatesError}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* By Strategy */}
              <div className="p-4 bg-[#0e1726] border border-gray-800 rounded-xl space-y-2">
                <span className="text-xs font-bold text-amber-300 block uppercase">
                  ตามกลยุทธ์ (By Strategy)
                </span>
                <div className="space-y-1 text-xs font-mono">
                  {strategies.map((s) => (
                    <div key={s.id} className="flex justify-between py-0.5 border-b border-white/5">
                      <span className="text-gray-300">{s.id}:</span>
                      <strong className="text-white">
                        {candidateStats.byStrategy[s.id] || 0}
                      </strong>
                    </div>
                  ))}
                </div>
              </div>

              {/* By Profile */}
              <div className="p-4 bg-[#0e1726] border border-gray-800 rounded-xl space-y-2">
                <span className="text-xs font-bold text-blue-300 block uppercase">
                  ตามโปรไฟล์ (By Profile)
                </span>
                <div className="space-y-1 text-xs font-mono">
                  {profiles.map((p) => (
                    <div key={p.id} className="flex justify-between py-0.5 border-b border-white/5">
                      <span className="text-gray-300 truncate max-w-[120px]">{p.name}:</span>
                      <strong className="text-white">
                        {candidateStats.byProfile[p.id] || 0}
                      </strong>
                    </div>
                  ))}
                </div>
              </div>

              {/* By Direction */}
              <div className="p-4 bg-[#0e1726] border border-gray-800 rounded-xl space-y-2">
                <span className="text-xs font-bold text-emerald-300 block uppercase">
                  ตามฝั่ง (By Direction)
                </span>
                <div className="space-y-1 text-xs font-mono">
                  <div className="flex justify-between py-0.5 border-b border-white/5">
                    <span className="text-emerald-400">LONG (ซื้อ):</span>
                    <strong className="text-white">{candidateStats.byDirection.LONG}</strong>
                  </div>
                  <div className="flex justify-between py-0.5 border-b border-white/5">
                    <span className="text-rose-400">SHORT (ขาย):</span>
                    <strong className="text-white">{candidateStats.byDirection.SHORT}</strong>
                  </div>
                  <div className="flex justify-between py-0.5 border-b border-white/5">
                    <span className="text-gray-400">NO_TRADE (ไม่มีทิศทาง):</span>
                    <strong className="text-white">{candidateStats.byDirection.NO_TRADE}</strong>
                  </div>
                </div>
              </div>

              {/* By Canonical State */}
              <div className="p-4 bg-[#0e1726] border border-gray-800 rounded-xl space-y-2">
                <span className="text-xs font-bold text-purple-300 block uppercase">
                  ตามสถานะ (By State)
                </span>
                <div className="space-y-1 text-xs font-mono max-h-36 overflow-y-auto">
                  {CANONICAL_STATES.map((st) => (
                    <div key={st} className="flex justify-between py-0.5 border-b border-white/5">
                      <span className="text-gray-400 text-[11px] truncate">{st}:</span>
                      <strong className="text-white">{candidateStats.byState[st] || 0}</strong>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="p-3 bg-black/30 rounded-lg border border-white/5 text-[11px] text-gray-400 italic">
              * ข้อมูลสถิติเชิงพรรณนาข้างต้นแสดงเฉพาะความถี่ของการเกิดสัญญาณ (Detection Frequency) ในประวัติฐานข้อมูล ไม่ใช่อัตราความแม่นยำ (Win Rate), Profit Factor, Sharpe Ratio หรือผลตอบแทนย้อนหลังใดๆ เนื่องจากระบบยังไม่มีการส่งคำสั่งซื้อขายจริงหรือการทำ Backtest Fill Simulation
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
