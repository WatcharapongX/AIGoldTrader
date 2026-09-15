'use client';

import React from 'react';
import type { SetupCandidate } from '@/types/strategy.generated';
import type { KillSwitchData } from '@/features/risk/contracts';
import type { MarketDataStatus } from '@/types/market.generated';
import { providerLabel } from '@/features/chart/contracts';

interface SignalSummaryHeaderProps {
  candidates: SetupCandidate[];
  provider: MarketDataStatus | null;
  killSwitch: KillSwitchData | null;
  asOf?: string;
  isStale?: boolean;
}

export function SignalSummaryHeader({
  candidates,
  provider,
  killSwitch,
  asOf,
  isStale,
}: SignalSummaryHeaderProps) {
  const readyCount = candidates.filter((c) => c.status === 'READY').length;
  const waitingCount = candidates.filter((c) => c.status === 'WAITING_CONFIRMATION').length;
  const blockedCount = candidates.filter((c) => c.status === 'BLOCKED_CONTEXT').length;
  const closedCount = candidates.filter(
    (c) => c.status === 'INVALIDATED' || c.status === 'EXPIRED' || c.status === 'SUPERSEDED'
  ).length;

  const isKillActive = killSwitch?.state === 'ACTIVE';

  return (
    <section
      data-testid="signal-summary-header"
      className="bg-[#0e1726] border border-gray-800 rounded-xl p-5 space-y-4"
      aria-label="Signal Summary and Telemetry"
    >
      {/* Top Telemetry Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-gray-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 animate-pulse" />
            <h2 className="text-base font-bold text-white tracking-wide">
              Deterministic Signal Command Center
            </h2>
            <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
              PHASE 4 · STRATEGY ENGINE
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            ประเมินโอกาสเทรดตามกฎกลยุทธ์เชิงคณิตศาสตร์ (SMC, Trend, Pattern) ร่วมกับ 7 โปรไฟล์ผู้เทรด
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          <div className="px-2.5 py-1 rounded bg-black/40 border border-white/10 font-mono text-gray-300">
            ◈ {providerLabel(provider)}
          </div>
          <div
            className={`px-2.5 py-1 rounded font-mono font-bold border ${
              isKillActive
                ? 'bg-rose-500/20 text-rose-300 border-rose-500/40 animate-pulse'
                : 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
            }`}
          >
            KILL SWITCH: {isKillActive ? 'ACTIVE (BLOCKED)' : 'NORMAL (CLEAR)'}
          </div>
          <div className="px-2.5 py-1 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-semibold font-mono">
            PAPER · EXECUTION DISABLED
          </div>
        </div>
      </div>

      {/* Metric Counters Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        {/* Total Candidates */}
        <div className="p-3 bg-black/30 rounded-lg border border-white/5">
          <span className="text-gray-400 text-[11px] block">CANDIDATES ทั้งหมด</span>
          <strong className="text-xl font-bold font-mono text-white mt-1 block">
            {candidates.length}
          </strong>
          <small className="text-gray-400 text-[10px] block">รายการในหน่วยความจำ</small>
        </div>

        {/* READY */}
        <div className="p-3 bg-emerald-950/20 rounded-lg border border-emerald-500/30">
          <span className="text-emerald-400 font-semibold text-[11px] block flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>READY (พร้อมเสนอแผน)</span>
          </span>
          <strong className="text-xl font-bold font-mono text-emerald-300 mt-1 block">
            {readyCount}
          </strong>
          <small className="text-emerald-400/70 text-[10px] block">ผ่านเกณฑ์ตามกฎกลยุทธ์</small>
        </div>

        {/* WAITING_CONFIRMATION */}
        <div className="p-3 bg-amber-950/20 rounded-lg border border-amber-500/30">
          <span className="text-amber-400 font-semibold text-[11px] block flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span>WAITING CONFIRMATION</span>
          </span>
          <strong className="text-xl font-bold font-mono text-amber-300 mt-1 block">
            {waitingCount}
          </strong>
          <small className="text-amber-400/70 text-[10px] block">รอการยืนยันราคาปิด</small>
        </div>

        {/* BLOCKED_CONTEXT */}
        <div className="p-3 bg-orange-950/20 rounded-lg border border-orange-500/30">
          <span className="text-orange-400 font-semibold text-[11px] block flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-orange-400" />
            <span>BLOCKED CONTEXT</span>
          </span>
          <strong className="text-xl font-bold font-mono text-orange-300 mt-1 block">
            {blockedCount}
          </strong>
          <small className="text-orange-400/70 text-[10px] block">ติดเงื่อนไขข่าวหรือสเปรด</small>
        </div>

        {/* CLOSED / EXPIRED */}
        <div className="p-3 bg-black/20 rounded-lg border border-white/5">
          <span className="text-gray-400 text-[11px] block">CLOSED / EXPIRED</span>
          <strong className="text-xl font-bold font-mono text-gray-400 mt-1 block">
            {closedCount}
          </strong>
          <small className="text-gray-400 text-[10px] block">หมดอายุหรือถูกแทนที่</small>
        </div>
      </div>

      {/* Freshness & Stale Banner */}
      {isStale && (
        <div
          data-testid="signal-stale-banner"
          className="p-3 bg-amber-500/15 border border-amber-500/30 rounded-lg text-amber-300 text-xs flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <span className="font-bold">⚠ STALE CONTEXT:</span>
            <span>ข้อมูลราคาล้าสมัยหรือขาดการเชื่อมต่อชั่วคราว รอข้อมูลแท่งใหม่ก่อนพิจารณา Setup</span>
          </div>
          <span className="text-[10px] font-mono uppercase bg-amber-500/20 px-2 py-0.5 rounded">
            WAITING FRESH CANDLE
          </span>
        </div>
      )}

      {/* Metadata Footnote */}
      <div className="flex flex-wrap items-center justify-between text-[11px] text-gray-400 pt-1 border-t border-gray-800/60 font-mono">
        <span>ข้อมูลล่าสุด ณ เวลา UTC: {asOf ? new Date(asOf).toISOString() : 'กำลังโหลด…'}</span>
        <span>RULE EVIDENCE SCORE · NOT A PROFIT PROBABILITY</span>
      </div>
    </section>
  );
}
