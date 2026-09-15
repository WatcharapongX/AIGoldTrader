'use client';

import React from 'react';
import type { PortfolioRiskData } from '@/features/risk/contracts';
import { formatBangkokTime, formatCurrency, formatPercent } from './thai';

interface PortfolioRiskCardProps {
  portfolio: PortfolioRiskData | null;
  isLoading: boolean;
  error: string | null;
}

export function PortfolioRiskCard({
  portfolio,
  isLoading,
  error,
}: PortfolioRiskCardProps) {
  if (isLoading) {
    return (
      <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 animate-pulse">
        <div className="h-5 bg-slate-800 rounded w-1/4 mb-4" />
        <div className="h-24 bg-slate-800/60 rounded mb-4" />
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="h-16 bg-slate-800/60 rounded" />
          <div className="h-16 bg-slate-800/60 rounded" />
          <div className="h-16 bg-slate-800/60 rounded" />
          <div className="h-16 bg-slate-800/60 rounded" />
        </div>
      </div>
    );
  }

  if (error || !portfolio) {
    return (
      <div className="bg-[#0f172a] border border-rose-900/40 rounded-xl p-5">
        <div className="flex items-center gap-2 text-rose-400 font-semibold mb-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>ไม่สามารถโหลดข้อมูล Portfolio Risk ได้</span>
        </div>
        <p className="text-sm text-gray-400">
          {error || 'ไม่พบข้อมูลความเสี่ยงพอร์ตโฟลิโอหรือระบบคำนวณปิดปรับปรุง'}
        </p>
      </div>
    );
  }

  const totalRisk = Number(portfolio.total_risk_pct) || 0;
  const maxRisk = Number(portfolio.max_account_risk_pct) || 6.0;
  const usedRiskPctOfMax = maxRisk > 0 ? Math.min(100, Math.max(0, (totalRisk / maxRisk) * 100)) : 0;

  return (
    <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 shadow-lg">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 mb-4 border-b border-slate-800 gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
              <span>Portfolio Risk & Capacity</span>
              <span className="text-xs font-normal text-gray-400">
                (การใช้โควต้าความเสี่ยงพอร์ต)
              </span>
            </h2>
            <p className="text-xs text-gray-400">
              ติดตามการใช้ความเสี่ยงรวมและการจองโควต้า — นี่คือการจัดสรรความเสี่ยง ไม่ใช่ผลตอบแทน P&L
            </p>
          </div>
        </div>

        {/* Kill Switch & Cooldown Status */}
        <div className="flex items-center gap-2">
          {portfolio.kill_switch_active ? (
            <span className="px-3 py-1 rounded-full bg-rose-500/20 text-rose-400 border border-rose-500/40 text-xs font-bold flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
              KILL SWITCH: ACTIVE (บล็อกการเทรด)
            </span>
          ) : (
            <span className="px-3 py-1 rounded-full bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 text-xs font-medium flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              KILL SWITCH: NORMAL (ระบบพร้อมทำงาน)
            </span>
          )}
        </div>
      </div>

      {/* Visual Risk Capacity Utilization Bar */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-lg p-4 mb-5">
        <div className="flex justify-between items-center text-xs mb-2">
          <div className="flex items-center gap-2">
            <span className="text-gray-300 font-semibold">การใช้ความเสี่ยงของพอร์ต (Risk Capacity Utilization):</span>
            <span className="text-amber-400 font-mono font-bold">
              {formatPercent(portfolio.total_risk_pct)} / {formatPercent(portfolio.max_account_risk_pct)}
            </span>
          </div>
          <div className="text-gray-400 font-mono">
            โควต้าว่างคงเหลือ (Available): <strong className="text-emerald-400">{formatPercent(portfolio.available_risk_pct)}</strong>
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-slate-800 rounded-full h-3.5 overflow-hidden flex">
          <div
            className={`h-full transition-all duration-500 ${
              usedRiskPctOfMax > 85 ? 'bg-rose-500' : usedRiskPctOfMax > 50 ? 'bg-amber-500' : 'bg-indigo-500'
            }`}
            style={{ width: `${usedRiskPctOfMax}%` }}
          />
          <div
            className="h-full bg-emerald-500/40 transition-all duration-500"
            style={{ width: `${100 - usedRiskPctOfMax}%` }}
          />
        </div>

        <div className="flex justify-between text-[11px] text-gray-400 mt-2">
          <span>0.00% (เริ่มต้น)</span>
          <span>ใช้ไป {usedRiskPctOfMax.toFixed(1)}% ของขีดจำกัดสูงสุด</span>
          <span>ขีดจำกัดสูงสุด {formatPercent(portfolio.max_account_risk_pct)}</span>
        </div>
      </div>

      {/* Metric Breakdown Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        {/* Open Risk */}
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-lg p-3">
          <div className="text-xs text-gray-400">Open Risk % (ความเสี่ยง Position เปิด)</div>
          <div className="text-lg font-bold text-gray-100 font-mono mt-0.5">
            {formatPercent(portfolio.open_risk_pct)}
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            *จาก Position ที่ถือครองจริงในพอร์ต
          </div>
        </div>

        {/* Reserved Risk */}
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-lg p-3">
          <div className="text-xs text-gray-400">Reserved Risk % (ความเสี่ยงที่จองไว้)</div>
          <div className="text-lg font-bold text-amber-400 font-mono mt-0.5">
            {formatPercent(portfolio.reserved_risk_pct)}
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            {portfolio.active_reservations_count} โควต้าที่อนุมัติรอออกคำสั่ง
          </div>
        </div>

        {/* Directional LONG Risk */}
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-lg p-3">
          <div className="text-xs text-gray-400">Directional: LONG Risk %</div>
          <div className="text-lg font-bold text-emerald-400 font-mono mt-0.5">
            {formatPercent(portfolio.directional_risk_pct?.LONG)}
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            โควต้าฝั่งซื้อ (LONG Exposure)
          </div>
        </div>

        {/* Directional SHORT Risk */}
        <div className="bg-slate-900/50 border border-slate-800/80 rounded-lg p-3">
          <div className="text-xs text-gray-400">Directional: SHORT Risk %</div>
          <div className="text-lg font-bold text-rose-400 font-mono mt-0.5">
            {formatPercent(portfolio.directional_risk_pct?.SHORT)}
          </div>
          <div className="text-[11px] text-gray-400 mt-0.5">
            โควต้าฝั่งขาย (SHORT Exposure)
          </div>
        </div>
      </div>

      {/* Active Reservations Section */}
      <div className="bg-slate-900/40 border border-slate-800/80 rounded-lg p-3.5">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-gray-200">
              Active Risk Reservations (โควต้าความเสี่ยงที่จองไว้):
            </span>
            <span className="px-2 py-0.5 rounded bg-slate-800 text-amber-400 font-mono text-xs font-bold border border-slate-700">
              {portfolio.active_reservations_count} รายการ
            </span>
          </div>
          <span className="text-[11px] text-amber-400/90 font-medium">
            *Reservation ≠ Executed Position (การจองโควต้าไม่ใช่การเปิดออเดอร์)
          </span>
        </div>

        {portfolio.active_reservations && portfolio.active_reservations.length > 0 ? (
          <div className="space-y-2 mt-2">
            {portfolio.active_reservations.map((res) => (
              <div
                key={res.id}
                className="flex flex-col sm:flex-row sm:items-center justify-between p-2.5 rounded bg-slate-950/60 border border-slate-800 text-xs gap-2"
              >
                <div className="flex items-center gap-2.5 font-mono">
                  <span
                    className={`px-1.5 py-0.5 rounded font-bold ${
                      res.direction === 'LONG'
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                    }`}
                  >
                    {res.direction}
                  </span>
                  <span className="text-gray-200 font-semibold">{res.symbol}</span>
                  <span className="text-gray-400">ID: {res.id.slice(0, 12)}...</span>
                  <span className="text-gray-400">ขนาด: {res.position_size} lots</span>
                </div>

                <div className="flex items-center gap-3 text-[11px] font-mono text-gray-400">
                  <span>ความเสี่ยง: <strong className="text-amber-400">{formatPercent(res.risk_pct)}</strong> ({formatCurrency(res.risk_amount)})</span>
                  <span>หมดอายุ: {formatBangkokTime(res.reserved_until)}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="py-3 text-center text-xs text-gray-400 bg-slate-950/40 rounded border border-dashed border-slate-800">
            ไม่มี Active Risk Reservation ในขณะนี้ (ไม่มีโควต้าที่ถูกล็อกไว้)
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex justify-between items-center pt-3 mt-3 border-t border-slate-800/80 text-[11px] text-gray-400">
        <span>Drawdown Policy Limit: {formatPercent(portfolio.drawdown_pct)} | Daily Loss Limit: {formatPercent(portfolio.daily_loss_pct)}</span>
        <span>Portfolio As-Of: {formatBangkokTime(portfolio.as_of)}</span>
      </div>
    </div>
  );
}
