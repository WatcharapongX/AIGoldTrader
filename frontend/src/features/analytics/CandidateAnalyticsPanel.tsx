'use client';

import React from 'react';
import type { StrategyDefinition, TraderProfile } from '@/types/strategy.generated';
import type { CandidateAnalyticsSummary } from './contracts';
import { CANONICAL_CANDIDATE_STATES } from './contracts';
import {
  CANDIDATE_STATE_COLORS,
  CANDIDATE_STATE_TH,
} from './thai';

interface CandidateAnalyticsPanelProps {
  summary: CandidateAnalyticsSummary | null;
  strategies: StrategyDefinition[];
  profiles: TraderProfile[];
  isLoading: boolean;
  error: string | null;
}

export function CandidateAnalyticsPanel({
  summary,
  strategies,
  profiles,
  isLoading,
  error,
}: CandidateAnalyticsPanelProps) {
  if (isLoading) {
    return (
      <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 animate-pulse">
        <div className="h-5 bg-slate-800 rounded w-1/3 mb-4" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
          <div className="h-16 bg-slate-800/60 rounded" />
          <div className="h-16 bg-slate-800/60 rounded" />
          <div className="h-16 bg-slate-800/60 rounded" />
          <div className="h-16 bg-slate-800/60 rounded" />
        </div>
        <div className="h-32 bg-slate-800/40 rounded" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-[#0f172a] border border-rose-900/40 rounded-xl p-5">
        <div className="flex items-center gap-2 text-rose-400 font-semibold mb-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>ไม่สามารถโหลดข้อมูล Candidate Analytics ได้</span>
        </div>
        <p className="text-sm text-gray-400">{error}</p>
      </div>
    );
  }

  if (!summary || summary.total === 0) {
    return (
      <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-8 text-center">
        <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-3 text-gray-400">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
          </svg>
        </div>
        <h3 className="text-base font-semibold text-gray-200">ยังไม่มี Candidate สำหรับวิเคราะห์</h3>
        <p className="text-xs text-gray-400 max-w-md mx-auto mt-1">
          ระบบยังไม่พบประวัติ Trade Candidate ในรอบเวลาปัจจุบัน หรือเครื่องยนต์ Strategy ยังไม่มีข้อมูลการตรวจจับ
        </p>
      </div>
    );
  }

  // Create strategy lookup dictionary
  const strategyNameMap = new Map<string, string>();
  for (const s of strategies) {
    strategyNameMap.set(s.id, s.name);
  }

  // Create profile lookup dictionary
  const profileNameMap = new Map<string, string>();
  for (const p of profiles) {
    profileNameMap.set(p.id, p.name);
  }

  return (
    <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 shadow-lg space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-2">
        <div>
          <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
            <span>Candidate Analytics</span>
            <span className="text-xs font-normal text-gray-400">
              (สถิติเชิงพรรณนาของการตรวจจับสัญญาณ)
            </span>
          </h2>
          <div className="text-xs text-gray-400 mt-0.5">
            {summary.coverageNotice}
          </div>
        </div>

        <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-3 py-1 rounded-lg">
          *Candidate Count ≠ Total Trades (Candidate ไม่ใช่คำสั่งเทรดจริง)
        </div>
      </div>

      {/* Top Aggregation Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {/* Total Candidates */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5">
          <div className="text-xs text-gray-400">Total Candidates (จำนวนที่ตรวจพบ)</div>
          <div className="text-2xl font-bold text-gray-100 font-mono mt-1">
            {summary.total}
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            ชุดข้อมูล Candidate ทั้งหมดที่บันทึก
          </div>
        </div>

        {/* Ready Candidates */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5">
          <div className="text-xs text-gray-400">READY Candidates (มีแผนพร้อม)</div>
          <div className="text-2xl font-bold text-emerald-400 font-mono mt-1">
            {summary.byState.READY}
            <span className="text-xs text-emerald-500/80 ml-2 font-normal">
              ({summary.byStatePct.READY}%)
            </span>
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            มี Trade Plan และผ่านเกณฑ์เทคนิค
          </div>
        </div>

        {/* Average Evidence Score */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5">
          <div className="text-xs text-gray-400">Average Setup Evidence Score</div>
          <div className="text-2xl font-bold text-amber-400 font-mono mt-1">
            {summary.avgEvidenceScore != null ? summary.avgEvidenceScore.toFixed(2) : 'N/A'}
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            *คะแนนตรวจพบหลักฐาน (ไม่ใช่ Win Probability)
          </div>
        </div>

        {/* Trade Plan Available */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5">
          <div className="text-xs text-gray-400">Plan Availability (มีแผนเข้าเทรด)</div>
          <div className="text-2xl font-bold text-indigo-400 font-mono mt-1">
            {summary.planCount}
            <span className="text-xs text-indigo-400/80 ml-2 font-normal">
              ({Math.round((summary.planCount / summary.total) * 1000) / 10}%)
            </span>
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            มี Entry/SL/TP ครบถ้วน
          </div>
        </div>
      </div>

      {/* Candidate State Distribution (Canonical States) */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-200">
            Candidate State Distribution (การกระจายตัวตามสถานะ Canonical)
          </h3>
          <span className="text-[11px] text-gray-400">
            *คำนวณจากเปอร์เซ็นต์ของบันทึก Candidate ทั้งหมด (ไม่ใช่ Win Rate)
          </span>
        </div>

        {/* Horizontal Stacked Bar */}
        <div className="w-full bg-slate-800 rounded-full h-3 overflow-hidden flex mb-4">
          {CANONICAL_CANDIDATE_STATES.map((st) => {
            const pct = summary.byStatePct[st];
            if (pct <= 0) return null;
            const colorClass =
              st === 'READY'
                ? 'bg-emerald-500'
                : st === 'BLOCKED_CONTEXT'
                ? 'bg-rose-500'
                : st === 'WAITING_CONFIRMATION'
                ? 'bg-yellow-500'
                : st === 'DETECTED'
                ? 'bg-blue-500'
                : st === 'EXPIRED'
                ? 'bg-amber-500'
                : st === 'SUPERSEDED'
                ? 'bg-purple-500'
                : 'bg-slate-600';
            return (
              <div
                key={st}
                className={`h-full ${colorClass} transition-all`}
                style={{ width: `${pct}%` }}
                title={`${st}: ${summary.byState[st]} (${pct}%)`}
              />
            );
          })}
        </div>

        {/* State Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
          {CANONICAL_CANDIDATE_STATES.map((st) => {
            const count = summary.byState[st];
            const pct = summary.byStatePct[st];
            const cfg = CANDIDATE_STATE_COLORS[st];
            return (
              <div
                key={st}
                className={`p-2.5 rounded-lg border ${cfg.border} ${cfg.bg} flex flex-col justify-between`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-xs font-bold ${cfg.text}`}>{st}</span>
                  <span className="text-xs font-mono font-bold text-gray-200">{count}</span>
                </div>
                <div className="flex items-center justify-between mt-1 text-[11px] text-gray-400">
                  <span>{CANDIDATE_STATE_TH[st]}</span>
                  <span className="font-mono">{pct}%</span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Direction Distribution & Profiles */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Direction Distribution */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-200">
              Setup Direction Frequency (ความถี่ฝั่งการเข้าเทรด)
            </h3>
            <span className="text-[11px] text-gray-400">LONG vs SHORT vs NO_TRADE</span>
          </div>

          <div className="grid grid-cols-3 gap-2 text-center mb-3">
            {/* LONG */}
            <div className="p-3 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
              <div className="text-xs font-bold text-emerald-400">LONG</div>
              <div className="text-lg font-bold text-gray-100 font-mono mt-0.5">
                {summary.byDirection.LONG.count}
              </div>
              <div className="text-[11px] text-emerald-500/80 font-mono">
                {summary.byDirection.LONG.pct}%
              </div>
            </div>

            {/* SHORT */}
            <div className="p-3 rounded-lg bg-rose-500/10 border border-rose-500/20">
              <div className="text-xs font-bold text-rose-400">SHORT</div>
              <div className="text-lg font-bold text-gray-100 font-mono mt-0.5">
                {summary.byDirection.SHORT.count}
              </div>
              <div className="text-[11px] text-rose-500/80 font-mono">
                {summary.byDirection.SHORT.pct}%
              </div>
            </div>

            {/* NO_TRADE */}
            <div className="p-3 rounded-lg bg-slate-800/60 border border-slate-700">
              <div className="text-xs font-bold text-slate-400">NO_TRADE</div>
              <div className="text-lg font-bold text-gray-100 font-mono mt-0.5">
                {summary.byDirection.NO_TRADE.count}
              </div>
              <div className="text-[11px] text-slate-400 font-mono">
                {summary.byDirection.NO_TRADE.pct}%
              </div>
            </div>
          </div>

          <div className="text-[11px] text-gray-400 bg-slate-950/40 p-2 rounded border border-slate-800">
            *ความถี่ของฝั่ง LONG หรือ SHORT เป็นเพียงสถิติการเกิด Setup จากอัลกอริทึม ไม่ได้สะท้อนถึงแนวโน้มกำไร (Profitable Bias) หรือความแม่นยำ
          </div>
        </div>

        {/* Trader Profile Distribution */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-200">
              Candidates by Trader Profile (การสร้างตามโปรไฟล์)
            </h3>
            <span className="text-[11px] text-gray-400">จำนวน Candidate ต่อโปรไฟล์</span>
          </div>

          <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
            {Object.entries(summary.byProfile).map(([profId, count]) => {
              const profName = profileNameMap.get(profId) || profId;
              const pct = Math.round((count / summary.total) * 1000) / 10;
              return (
                <div
                  key={profId}
                  className="flex items-center justify-between p-2 rounded bg-slate-950/50 border border-slate-800/80 text-xs"
                >
                  <div className="flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />
                    <span className="text-gray-200 font-medium">{profName}</span>
                    <span className="text-gray-400 text-[11px] font-mono">({profId})</span>
                  </div>
                  <div className="flex items-center gap-2 font-mono">
                    <span className="font-bold text-gray-100">{count}</span>
                    <span className="text-gray-400 text-[11px]">({pct}%)</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Strategy Breakdown Table */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-200">
            Strategy Candidate Activity (การกระจายตัวตามกลยุทธ์ STRAT01–STRAT06)
          </h3>
          <span className="text-[11px] text-gray-400">
            *ไม่แสดงผลกำไร/ขาดทุน เนื่องจากยังไม่มีการเทรดจริง
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead className="bg-slate-950/60 text-gray-400 border-b border-slate-800 font-mono">
              <tr>
                <th className="py-2.5 px-3">กลยุทธ์ (Strategy)</th>
                <th className="py-2.5 px-3 text-right">Candidates ทั้งหมด</th>
                <th className="py-2.5 px-3 text-right">READY</th>
                <th className="py-2.5 px-3 text-right">BLOCKED</th>
                <th className="py-2.5 px-3 text-right">Avg Setup Score</th>
                <th className="py-2.5 px-3 text-right">LONG / SHORT</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-gray-300 font-mono">
              {Object.keys(summary.byStrategy).sort().map((stratId) => {
                const s = summary.byStrategy[stratId];
                const stratName = strategyNameMap.get(stratId) || stratId;
                return (
                  <tr key={stratId} className="hover:bg-slate-800/30">
                    <td className="py-2.5 px-3 font-sans">
                      <div className="font-semibold text-gray-200">{stratId}</div>
                      <div className="text-[11px] text-gray-400">{stratName}</div>
                    </td>
                    <td className="py-2.5 px-3 text-right font-bold text-gray-100">{s.count}</td>
                    <td className="py-2.5 px-3 text-right text-emerald-400 font-semibold">{s.readyCount}</td>
                    <td className="py-2.5 px-3 text-right text-rose-400">{s.blockedCount}</td>
                    <td className="py-2.5 px-3 text-right text-amber-400 font-bold">
                      {s.avgEvidenceScore != null ? s.avgEvidenceScore.toFixed(2) : 'N/A'}
                    </td>
                    <td className="py-2.5 px-3 text-right text-slate-300">
                      <span className="text-emerald-400">{s.directions.LONG}</span>
                      <span className="text-gray-400 mx-1">/</span>
                      <span className="text-rose-400">{s.directions.SHORT}</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
