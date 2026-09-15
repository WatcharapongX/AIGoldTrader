'use client';

import React from 'react';
import type { ExtendedAccountSnapshot } from './contracts';
import { calculateSnapshotDrawdown } from './contracts';
import {
  ACCOUNT_SOURCE_TH,
  formatBangkokTime,
  formatCurrency,
  formatPercent,
} from './thai';

interface AccountSnapshotCardProps {
  account: ExtendedAccountSnapshot | null;
  isLoading: boolean;
  error: string | null;
}

export function AccountSnapshotCard({
  account,
  isLoading,
  error,
}: AccountSnapshotCardProps) {
  if (isLoading) {
    return (
      <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 animate-pulse">
        <div className="h-5 bg-slate-800 rounded w-1/4 mb-4" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="h-16 bg-slate-800/60 rounded" />
          <div className="h-16 bg-slate-800/60 rounded" />
          <div className="h-16 bg-slate-800/60 rounded" />
          <div className="h-16 bg-slate-800/60 rounded" />
        </div>
      </div>
    );
  }

  if (error || !account) {
    return (
      <div className="bg-[#0f172a] border border-rose-900/40 rounded-xl p-5">
        <div className="flex items-center gap-2 text-rose-400 font-semibold mb-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>ไม่สามารถโหลดข้อมูล Account Snapshot ได้</span>
        </div>
        <p className="text-sm text-gray-400">
          {error || 'ไม่พบข้อมูลบัญชีหรือบริการปิดการเชื่อมต่อ — ตรวจสอบระบบความเสี่ยง'}
        </p>
      </div>
    );
  }

  const drawdown = calculateSnapshotDrawdown(account.equity, account.peak_equity);
  const sourceLabel = ACCOUNT_SOURCE_TH[account.source] || account.source;

  return (
    <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 shadow-lg">
      {/* Card Header with Badges */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 mb-4 border-b border-slate-800 gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 10h18M7 15h1m4 0h1m-7 4h12a3 3 0 003-3V8a3 3 0 00-3-3H6a3 3 0 00-3 3v8a3 3 0 003 3z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
              <span>Account Snapshot</span>
              <span className="text-xs font-normal text-gray-400">
                (ID: {account.account_id})
              </span>
            </h2>
            <div className="flex items-center gap-2 text-xs text-gray-400 mt-0.5">
              <span>แหล่งที่มา:</span>
              <span className="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[11px] border border-slate-700">
                {account.source} ({sourceLabel})
              </span>
            </div>
          </div>
        </div>

        {/* Status badges */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span className="px-2.5 py-1 rounded bg-yellow-500/15 text-yellow-400 border border-yellow-500/30 font-semibold">
            {account.trading_mode}
          </span>
          {account.cooldown_until && (
            <span className="px-2.5 py-1 rounded bg-rose-500/20 text-rose-400 border border-rose-500/40">
              Cooldown จนถึง: {formatBangkokTime(account.cooldown_until)}
            </span>
          )}
          <span className="text-gray-400 text-[11px]">
            เวอร์ชันสถานะ: v{account.state_version}
          </span>
        </div>
      </div>

      {/* Primary Financial Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        {/* Balance */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5">
          <div className="text-xs text-gray-400 font-medium">Balance (ยอดคงเหลือ)</div>
          <div className="text-xl font-bold text-gray-100 font-mono mt-1">
            {formatCurrency(account.balance)}
          </div>
          <div className="text-[11px] text-gray-400 mt-1">
            *เป็นค่าพอร์ตจำลอง ไม่ใช่กำไรที่แท้จริง
          </div>
        </div>

        {/* Equity */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5">
          <div className="text-xs text-gray-400 font-medium">Equity (มูลค่าพอร์ตสุทธิ)</div>
          <div className="text-xl font-bold text-amber-400 font-mono mt-1">
            {formatCurrency(account.equity)}
          </div>
          <div className="text-[11px] text-gray-400 mt-1">
            Peak: {formatCurrency(account.peak_equity)}
          </div>
        </div>

        {/* Free Margin */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5">
          <div className="text-xs text-gray-400 font-medium">Free Margin (หลักประกันคงเหลือ)</div>
          <div className="text-xl font-bold text-gray-100 font-mono mt-1">
            {account.free_margin != null ? formatCurrency(account.free_margin) : 'N/A'}
          </div>
          <div className="text-[11px] text-gray-400 mt-1">
            {account.free_margin != null ? 'คำนวณจากยอดมาร์จิ้น' : 'ไม่มี Position ถือครอง'}
          </div>
        </div>

        {/* Current Snapshot Drawdown */}
        <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-3.5">
          <div className="text-xs text-gray-400 font-medium flex items-center justify-between">
            <span>CURRENT ACCOUNT SNAPSHOT DRAWDOWN</span>
          </div>
          <div className="text-xl font-bold text-gray-200 font-mono mt-1">
            {drawdown.displayPct}
          </div>
          <div className="text-[11px] text-amber-400/80 mt-1">
            *(Peak vs Equity ปัจจุบัน — ไม่ใช่ Max Drawdown จากการเทรด)
          </div>
        </div>
      </div>

      {/* Secondary Row: Realized P&L, Floating P&L, Open Positions */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {/* Daily Realized PnL */}
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-lg p-3">
          <div className="text-xs text-gray-400">Daily Realized P&L (กำไรรับรู้รายวัน)</div>
          <div className="text-base font-semibold text-gray-200 font-mono mt-0.5">
            {formatCurrency(account.daily_realized_pnl)}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">
            {Number(account.daily_realized_pnl) === 0 ? 'ยังไม่มี Execute Trade Records' : 'ตามรายงานบัญชี'}
          </div>
        </div>

        {/* Weekly Realized PnL */}
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-lg p-3">
          <div className="text-xs text-gray-400">Weekly Realized P&L (กำไรรับรู้รายสัปดาห์)</div>
          <div className="text-base font-semibold text-gray-200 font-mono mt-0.5">
            {formatCurrency(account.weekly_realized_pnl)}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">
            {Number(account.weekly_realized_pnl) === 0 ? 'ยังไม่มี Execute Trade Records' : 'ตามรายงานบัญชี'}
          </div>
        </div>

        {/* Floating PnL */}
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-lg p-3">
          <div className="text-xs text-gray-400">Floating P&L (กำไรขาดทุนที่ยังไม่ปิด)</div>
          <div className="text-base font-semibold text-gray-200 font-mono mt-0.5">
            {account.floating_pnl != null ? formatCurrency(account.floating_pnl) : 'N/A'}
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">
            {account.floating_pnl != null ? 'จาก Position เปิดอยู่' : 'N/A / ไม่มีข้อมูล Position'}
          </div>
        </div>

        {/* Open Positions Count */}
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-lg p-3">
          <div className="text-xs text-gray-400">Open Positions (จำนวนออเดอร์ที่เปิด)</div>
          <div className="text-base font-semibold text-gray-200 font-mono mt-0.5">
            {account.open_positions_count} ออเดอร์
          </div>
          <div className="text-[11px] text-slate-400 mt-0.5">
            {account.open_positions_count === 0 ? 'ไม่มี Position ถือครอง (ระบบยังไม่รองรับ)' : 'ตาม Snapshot'}
          </div>
        </div>
      </div>

      {/* Account Risk & Operational Metadata */}
      <div className="flex flex-wrap items-center justify-between pt-3 border-t border-slate-800 text-xs text-gray-400 gap-2">
        <div className="flex items-center gap-4">
          <span>ความเสี่ยงเปิด (Open Risk): <strong className="text-gray-200 font-mono">{formatPercent(account.open_risk_pct)}</strong></span>
          <span>ความเสี่ยงที่จองไว้ (Reserved): <strong className="text-gray-200 font-mono">{formatPercent(account.reserved_risk_pct)}</strong></span>
          <span>แพ้ติดต่อกัน (Consecutive Losses): <strong className="text-gray-200 font-mono">{account.consecutive_losses}</strong></span>
        </div>
        <div className="text-[11px] text-gray-400">
          Snapshot As-Of: {formatBangkokTime(account.as_of)}
        </div>
      </div>
    </div>
  );
}
