'use client';

import React from 'react';
import { formatBangkokTime } from './thai';

interface PerformanceStatusHeaderProps {
  lastUpdated: Date | null;
  isRefreshing: boolean;
  onRefresh: () => void;
  tradingMode?: string;
  sourceMode?: string;
}

export function PerformanceStatusHeader({
  lastUpdated,
  isRefreshing,
  onRefresh,
  tradingMode = 'PAPER',
}: PerformanceStatusHeaderProps) {
  return (
    <div className="bg-[#0f172a]/90 border border-slate-800 rounded-xl p-5 mb-6 backdrop-blur-md shadow-lg">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        {/* Title & Subtitle */}
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-100 tracking-tight">
              Performance & Analytics
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
              ผลการดำเนินงานและการวิเคราะห์
            </span>
          </div>
          <p className="text-sm text-gray-400 mt-1">
            ภาพรวมการวิเคราะห์กลยุทธ์, การตัดสินใจความเสี่ยง, และความพร้อมของระบบ — แยกส่วนชัดเจนจากการเทรดจริง
          </p>
        </div>

        {/* Action Controls & Badges */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Paper Mode & Execution Disabled */}
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 text-xs font-medium">
            <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse" />
            <span>TRADING MODE: {tradingMode}</span>
            <span className="text-yellow-600">|</span>
            <span className="font-semibold text-yellow-300">EXECUTION DISABLED</span>
          </div>

          {/* Scope Badge */}
          <div className="px-3 py-1.5 rounded-lg bg-blue-500/10 border border-blue-500/30 text-blue-400 text-xs font-medium">
            SCOPE: ANALYSIS / STRATEGY / RISK ONLY
          </div>

          {/* Executed Trades Unavailable Badge */}
          <div className="px-3 py-1.5 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400 text-xs font-medium">
            EXECUTED TRADES: NOT AVAILABLE
          </div>

          {/* Backtest Not Implemented Badge */}
          <div className="px-3 py-1.5 rounded-lg bg-zinc-800 border border-zinc-700 text-zinc-400 text-xs font-medium">
            BACKTEST: NOT IMPLEMENTED
          </div>

          {/* Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-gray-300 hover:text-white border border-slate-700 text-xs font-medium transition disabled:opacity-50"
          >
            <svg
              className={`w-3.5 h-3.5 ${isRefreshing ? 'animate-spin' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
              />
            </svg>
            <span>{isRefreshing ? 'กำลังโหลด...' : 'รีเฟรช'}</span>
          </button>
        </div>
      </div>

      {/* As-Of Timestamp Bar */}
      <div className="mt-4 pt-3 border-t border-slate-800/80 flex flex-wrap items-center justify-between text-xs text-gray-400 gap-2">
        <div className="flex items-center gap-2">
          <span className="text-gray-400">ข้อมูลอัปเดตล่าสุด:</span>
          <span className="text-gray-300 font-mono">
            {lastUpdated ? formatBangkokTime(lastUpdated.toISOString()) : 'ยังไม่ได้โหลด'} (Asia/Bangkok · UTC+7)
          </span>
        </div>
        <div className="text-gray-400 text-[11px]">
          *ข้อมูลสถิติเป็นการวิเคราะห์เชิงพฤติกรรม (Operational Activity) ไม่ใช่ผลกำไรขาดทุนจากการเทรดจริง
        </div>
      </div>
    </div>
  );
}
