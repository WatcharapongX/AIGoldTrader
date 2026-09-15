'use client';

import React from 'react';
import type { RiskDecisionAnalyticsSummary } from './contracts';
import {
  RISK_DECISION_COLORS,
  RISK_DECISION_TH,
  formatCurrency,
  formatPercent,
} from './thai';

interface RiskDecisionAnalyticsPanelProps {
  summary: RiskDecisionAnalyticsSummary | null;
  isLoading: boolean;
  error: string | null;
}

export function RiskDecisionAnalyticsPanel({
  summary,
  isLoading,
  error,
}: RiskDecisionAnalyticsPanelProps) {
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
          <span>ไม่สามารถโหลดข้อมูล Risk Decision Analytics ได้</span>
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
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h3 className="text-base font-semibold text-gray-200">ยังไม่มีประวัติ Risk Decision</h3>
        <p className="text-xs text-gray-400 max-w-md mx-auto mt-1">
          ยังไม่มีการส่งคำขอประเมินความเสี่ยงเข้าสู่ Risk Engine ในระบบ
        </p>
      </div>
    );
  }

  return (
    <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 shadow-lg space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-2">
        <div>
          <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
            <span>Risk Decision Analytics</span>
            <span className="text-xs font-normal text-gray-400">
              (การวิเคราะห์ผลการพิจารณาความเสี่ยง)
            </span>
          </h2>
          <div className="text-xs text-gray-400 mt-0.5">
            {summary.coverageNotice}
          </div>
        </div>

        <div className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-3 py-1 rounded-lg">
          *Risk Decision ≠ Executed Trades (การพิจารณาความเสี่ยงไม่ใช่ผลการเทรด)
        </div>
      </div>

      {/* Decision Status Breakdown Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* APPROVED */}
        <div className={`p-4 rounded-xl border ${RISK_DECISION_COLORS.APPROVED.border} ${RISK_DECISION_COLORS.APPROVED.bg}`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-emerald-400">APPROVED</span>
            <span className="text-xs font-semibold text-emerald-500 font-mono">
              {summary.byDecision.APPROVED.pct}%
            </span>
          </div>
          <div className="text-2xl font-bold text-emerald-300 font-mono mt-1.5">
            {summary.byDecision.APPROVED.count}
          </div>
          <div className="text-[11px] text-emerald-400/80 mt-1">
            {RISK_DECISION_TH.APPROVED}
          </div>
        </div>

        {/* REDUCED */}
        <div className={`p-4 rounded-xl border ${RISK_DECISION_COLORS.REDUCED.border} ${RISK_DECISION_COLORS.REDUCED.bg}`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-amber-400">REDUCED</span>
            <span className="text-xs font-semibold text-amber-500 font-mono">
              {summary.byDecision.REDUCED.pct}%
            </span>
          </div>
          <div className="text-2xl font-bold text-amber-300 font-mono mt-1.5">
            {summary.byDecision.REDUCED.count}
          </div>
          <div className="text-[11px] text-amber-400/80 mt-1">
            {RISK_DECISION_TH.REDUCED}
          </div>
        </div>

        {/* BLOCKED */}
        <div className={`p-4 rounded-xl border ${RISK_DECISION_COLORS.BLOCKED.border} ${RISK_DECISION_COLORS.BLOCKED.bg}`}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-rose-400">BLOCKED</span>
            <span className="text-xs font-semibold text-rose-500 font-mono">
              {summary.byDecision.BLOCKED.pct}%
            </span>
          </div>
          <div className="text-2xl font-bold text-rose-300 font-mono mt-1.5">
            {summary.byDecision.BLOCKED.count}
          </div>
          <div className="text-[11px] text-rose-400/80 mt-1">
            {RISK_DECISION_TH.BLOCKED}
          </div>
        </div>
      </div>

      {/* Requested vs Approved Risk Metrics */}
      <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-gray-200">
            Requested vs Approved Risk Comparison (การเปรียบเทียบความเสี่ยงที่ขอ vs ที่อนุมัติ)
          </h3>
          <span className="text-[11px] text-gray-400">
            การปรับลดขนาดความเสี่ยงตามนโยบาย Risk Policy
          </span>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <div className="text-xs text-gray-400">Avg Requested Risk %</div>
            <div className="text-lg font-bold text-gray-200 font-mono mt-0.5">
              {summary.avgRequestedRiskPct != null ? formatPercent(summary.avgRequestedRiskPct) : 'N/A'}
            </div>
            <div className="text-[11px] text-gray-400 mt-0.5">ความเสี่ยงเฉลี่ยที่ขอ</div>
          </div>

          <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <div className="text-xs text-gray-400">Avg Approved Risk %</div>
            <div className="text-lg font-bold text-emerald-400 font-mono mt-0.5">
              {summary.avgApprovedRiskPct != null ? formatPercent(summary.avgApprovedRiskPct) : 'N/A'}
            </div>
            <div className="text-[11px] text-emerald-500/80 mt-0.5">ความเสี่ยงเฉลี่ยที่อนุมัติ</div>
          </div>

          <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <div className="text-xs text-gray-400">Total Requested Risk Amount</div>
            <div className="text-lg font-bold text-gray-200 font-mono mt-0.5">
              {formatCurrency(summary.totalRequestedRiskAmount)}
            </div>
            <div className="text-[11px] text-gray-400 mt-0.5">ยอดเงินความเสี่ยงที่ขอรวม</div>
          </div>

          <div className="p-3 bg-slate-950/60 rounded-lg border border-slate-800">
            <div className="text-xs text-gray-400">Total Approved Risk Amount</div>
            <div className="text-lg font-bold text-indigo-400 font-mono mt-0.5">
              {formatCurrency(summary.totalApprovedRiskAmount)}
            </div>
            <div className="text-[11px] text-indigo-400/80 mt-0.5">ยอดเงินความเสี่ยงที่อนุมัติรวม</div>
          </div>
        </div>
      </div>

      {/* Top Block Reasons & Warnings */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Top Block Reasons */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-200">
              Top Block Reasons (สาเหตุหลักที่ถูกปฏิเสธความเสี่ยง)
            </h3>
            <span className="text-[11px] text-rose-400 font-mono">จาก blocked_reasons_th</span>
          </div>

          {summary.topBlockedReasons.length > 0 ? (
            <div className="space-y-2">
              {summary.topBlockedReasons.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-2 rounded bg-rose-500/5 border border-rose-500/20 text-xs"
                >
                  <span className="text-gray-300 line-clamp-1">{item.reason}</span>
                  <span className="font-mono font-bold text-rose-400 ml-2 px-1.5 py-0.5 rounded bg-rose-500/20">
                    {item.count} ครั้ง
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-4 text-center text-xs text-gray-400 bg-slate-950/40 rounded border border-dashed border-slate-800">
              ไม่มีการบล็อกความเสี่ยงในชุดข้อมูลที่บันทึก
            </div>
          )}
        </div>

        {/* Top Warnings */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-200">
              Risk Warnings (คำเตือนความเสี่ยงที่เกิดขึ้น)
            </h3>
            <span className="text-[11px] text-amber-400 font-mono">จาก warnings_th</span>
          </div>

          {summary.topWarnings.length > 0 ? (
            <div className="space-y-2">
              {summary.topWarnings.map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-center justify-between p-2 rounded bg-amber-500/5 border border-amber-500/20 text-xs"
                >
                  <span className="text-gray-300 line-clamp-1">{item.warning}</span>
                  <span className="font-mono font-bold text-amber-400 ml-2 px-1.5 py-0.5 rounded bg-amber-500/20">
                    {item.count} ครั้ง
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div className="py-4 text-center text-xs text-gray-400 bg-slate-950/40 rounded border border-dashed border-slate-800">
              ไม่มีคำเตือนความเสี่ยงในชุดข้อมูลที่บันทึก
            </div>
          )}
        </div>
      </div>

      {/* Decisions by Strategy and Direction */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Decisions by Strategy */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-200">
              Risk Decisions by Strategy (การตัดสินใจแยกตามกลยุทธ์)
            </h3>
            <span className="text-[11px] text-gray-400">อนุมัติ / ลดขนาด / บล็อก</span>
          </div>

          <div className="space-y-2">
            {Object.keys(summary.byStrategy).sort().map((stratId) => {
              const st = summary.byStrategy[stratId];
              return (
                <div
                  key={stratId}
                  className="flex items-center justify-between p-2 rounded bg-slate-950/50 border border-slate-800/80 text-xs"
                >
                  <span className="font-bold text-gray-200 font-mono">{stratId}</span>
                  <div className="flex items-center gap-3 font-mono text-[11px]">
                    <span className="text-emerald-400">App: {st.approved}</span>
                    <span className="text-amber-400">Red: {st.reduced}</span>
                    <span className="text-rose-400">Blk: {st.blocked}</span>
                    <span className="text-gray-400 font-bold">({st.total})</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Decisions by Direction */}
        <div className="bg-slate-900/60 border border-slate-800 rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-200">
              Risk Decisions by Direction (การตัดสินใจแยกตามฝั่งเทรด)
            </h3>
            <span className="text-[11px] text-gray-400">LONG vs SHORT</span>
          </div>

          <div className="space-y-2">
            {(['LONG', 'SHORT'] as const).map((dir) => {
              const d = summary.byDirection[dir];
              return (
                <div
                  key={dir}
                  className="flex items-center justify-between p-3 rounded bg-slate-950/50 border border-slate-800/80 text-xs"
                >
                  <span
                    className={`font-bold font-mono px-2 py-0.5 rounded ${
                      dir === 'LONG'
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                    }`}
                  >
                    {dir}
                  </span>
                  <div className="flex items-center gap-4 font-mono text-xs">
                    <span className="text-emerald-400">อนุมัติ: {d.approved}</span>
                    <span className="text-amber-400">ปรับลด: {d.reduced}</span>
                    <span className="text-rose-400">บล็อก: {d.blocked}</span>
                    <span className="text-gray-200 font-bold">รวม: {d.total}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
