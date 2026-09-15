'use client';

import React from 'react';
import type { EvaluationActivitySummary } from './contracts';
import { formatBangkokTime } from './thai';

interface EvaluationActivityPanelProps {
  summary: EvaluationActivitySummary | null;
  isLoading: boolean;
  error: string | null;
}

export function EvaluationActivityPanel({
  summary,
  isLoading,
  error,
}: EvaluationActivityPanelProps) {
  if (isLoading) {
    return (
      <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 animate-pulse">
        <div className="h-5 bg-slate-800 rounded w-1/3 mb-4" />
        <div className="h-40 bg-slate-800/40 rounded" />
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
          <span>ไม่สามารถโหลดข้อมูล Historical Evaluation Activity ได้</span>
        </div>
        <p className="text-sm text-gray-400">{error}</p>
      </div>
    );
  }

  if (!summary || summary.totalEvaluations === 0) {
    return (
      <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-8 text-center">
        <div className="w-12 h-12 rounded-full bg-slate-800 flex items-center justify-center mx-auto mb-3 text-gray-400">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h3 className="text-base font-semibold text-gray-200">ยังไม่มี Strategy Evaluation History</h3>
        <p className="text-xs text-gray-400 max-w-md mx-auto mt-1">
          ยังไม่มี Snapshot รอบการประเมินกลยุทธ์ถูกบันทึกไว้ในฐานข้อมูล
        </p>
      </div>
    );
  }

  // Find max candidate count across items for bar chart scaling
  const maxCandidates = Math.max(1, ...summary.items.map((it) => it.candidateCount));

  return (
    <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 shadow-lg space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-2">
        <div>
          <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
            <span>Historical Evaluation Activity</span>
            <span className="text-xs font-normal text-gray-400">
              (ประวัติรอบการประเมินกลยุทธ์เชิงปฏิบัติการ)
            </span>
          </h2>
          <div className="text-xs text-gray-400 mt-0.5">
            {summary.coverageNotice}
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-amber-400 bg-amber-500/10 border border-amber-500/30 px-3 py-1 rounded-lg">
            NOT A BACKTEST (ไม่ใช่ผลทดสอบย้อนหลัง)
          </span>
        </div>
      </div>

      {/* Activity Timeline Bar Chart */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3 text-xs">
          <span className="font-semibold text-gray-200">
            Activity Timeline (Candidates per Evaluation):
          </span>
          <div className="flex items-center gap-4 text-[11px]">
            <span className="flex items-center gap-1.5 text-gray-400">
              <span className="w-2.5 h-2.5 rounded-sm bg-slate-600" /> รวม (Total)
            </span>
            <span className="flex items-center gap-1.5 text-emerald-400">
              <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /> READY
            </span>
            <span className="flex items-center gap-1.5 text-rose-400">
              <span className="w-2.5 h-2.5 rounded-sm bg-rose-500" /> BLOCKED
            </span>
          </div>
        </div>

        {/* Visual Columns */}
        <div className="flex items-end gap-1.5 h-32 pt-4 px-2 pb-2 bg-slate-950/60 rounded border border-slate-800 overflow-x-auto">
          {summary.items.slice(0, 25).reverse().map((it, idx) => {
            const heightPct = Math.round((it.candidateCount / maxCandidates) * 100);
            const readyPct = it.candidateCount > 0 ? (it.readyCount / it.candidateCount) * 100 : 0;
            const blockedPct = it.candidateCount > 0 ? (it.blockedCount / it.candidateCount) * 100 : 0;

            return (
              <div
                key={idx}
                className="flex-1 min-w-[20px] max-w-[40px] flex flex-col items-center justify-end h-full group relative"
              >
                {/* Tooltip on hover */}
                <div className="absolute bottom-full mb-2 hidden group-hover:flex flex-col p-2 bg-slate-900 border border-slate-700 text-white rounded shadow-xl text-[10px] whitespace-nowrap z-20 pointer-events-none">
                  <span className="font-bold">{formatBangkokTime(it.asOf)}</span>
                  <span>Candidates: {it.candidateCount}</span>
                  <span className="text-emerald-400">READY: {it.readyCount}</span>
                  <span className="text-rose-400">BLOCKED: {it.blockedCount}</span>
                  <span className="text-gray-400 font-mono text-[9px]">{it.configId.slice(0, 12)}</span>
                </div>

                {/* Stacked bar */}
                <div
                  className="w-full rounded-t overflow-hidden bg-slate-800 flex flex-col justify-end"
                  style={{ height: `${Math.max(8, heightPct)}%` }}
                >
                  <div className="bg-rose-500/80 w-full" style={{ height: `${blockedPct}%` }} />
                  <div className="bg-emerald-500 w-full" style={{ height: `${readyPct}%` }} />
                </div>
                <span className="text-[9px] text-gray-400 font-mono mt-1">
                  #{idx + 1}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Evaluations Table */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-200">
            Recent Evaluation Records (ตารางประวัติรอบการประเมิน 25 รายการล่าสุด)
          </h3>
          <span className="text-[11px] text-gray-400">
            แสดงข้อมูลตามเวลา As-Of จริง
          </span>
        </div>

        <div className="overflow-x-auto max-h-64 overflow-y-auto">
          <table className="w-full text-xs text-left">
            <thead className="sticky top-0 bg-slate-950 text-gray-400 border-b border-slate-800 font-mono text-[11px]">
              <tr>
                <th className="py-2 px-3">วันเวลา As-Of (Bangkok)</th>
                <th className="py-2 px-3 text-right">Candidates</th>
                <th className="py-2 px-3 text-right">READY</th>
                <th className="py-2 px-3 text-right">BLOCKED</th>
                <th className="py-2 px-3">Config ID</th>
                <th className="py-2 px-3 text-center">สถานะ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-gray-300 font-mono">
              {summary.items.map((it, idx) => (
                <tr key={idx} className="hover:bg-slate-800/30">
                  <td className="py-2 px-3 text-gray-200">{formatBangkokTime(it.asOf)}</td>
                  <td className="py-2 px-3 text-right font-bold text-gray-100">{it.candidateCount}</td>
                  <td className="py-2 px-3 text-right text-emerald-400 font-semibold">{it.readyCount}</td>
                  <td className="py-2 px-3 text-right text-rose-400">{it.blockedCount}</td>
                  <td className="py-2 px-3 text-gray-400 text-[11px] font-mono">{it.configId.slice(0, 16)}...</td>
                  <td className="py-2 px-3 text-center">
                    {it.isStale ? (
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-amber-500/20 text-amber-400 border border-amber-500/30">
                        STALE SNAPSHOT
                      </span>
                    ) : (
                      <span className="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                        ACTIVE
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
