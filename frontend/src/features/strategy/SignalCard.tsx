'use client';

import React from 'react';
import type { SetupCandidate, StrategyDefinition, TraderProfile } from '@/types/strategy.generated';
import { label, utc } from './thai';

interface SignalCardProps {
  candidate: SetupCandidate;
  isSelected: boolean;
  onSelect: (id: string) => void;
  strategy?: StrategyDefinition;
  profile?: TraderProfile;
}

function stateBadge(status: SetupCandidate['status']) {
  switch (status) {
    case 'READY':
      return (
        <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
          READY · ผ่านเกณฑ์
        </span>
      );
    case 'WAITING_CONFIRMATION':
      return (
        <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
          WAITING_CONFIRMATION · รอยืนยัน
        </span>
      );
    case 'DETECTED':
      return (
        <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-blue-500/20 text-blue-300 border border-blue-500/40">
          DETECTED · ตรวจพบเงื่อนไข
        </span>
      );
    case 'BLOCKED_CONTEXT':
      return (
        <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-orange-500/20 text-orange-300 border border-orange-500/40">
          BLOCKED_CONTEXT · ติดเงื่อนไขบริบท
        </span>
      );
    case 'INVALIDATED':
      return (
        <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">
          INVALIDATED · เงื่อนไขใช้ไม่ได้
        </span>
      );
    case 'EXPIRED':
      return (
        <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-gray-500/20 text-gray-400 border border-gray-600/30">
          EXPIRED · หมดอายุ
        </span>
      );
    case 'SUPERSEDED':
      return (
        <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
          SUPERSEDED · มีรอบใหม่แทนที่
        </span>
      );
    case 'NO_TRADE':
    default:
      return (
        <span className="px-2 py-0.5 text-[10px] font-mono font-medium rounded bg-gray-700/40 text-gray-400 border border-gray-700">
          NO_TRADE · ยังไม่พบโอกาส
        </span>
      );
  }
}

function directionBadge(dir: SetupCandidate['direction']) {
  switch (dir) {
    case 'LONG':
      return (
        <span className="px-2 py-0.5 text-[11px] font-bold rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
          ▲ LONG
        </span>
      );
    case 'SHORT':
      return (
        <span className="px-2 py-0.5 text-[11px] font-bold rounded bg-rose-500/20 text-rose-400 border border-rose-500/30">
          ▼ SHORT
        </span>
      );
    case 'NO_TRADE':
    default:
      return (
        <span className="px-2 py-0.5 text-[11px] font-medium rounded bg-gray-800 text-gray-400 border border-gray-700">
          — NO TRADE
        </span>
      );
  }
}

export function SignalCard({
  candidate,
  isSelected,
  onSelect,
  strategy,
  profile,
}: SignalCardProps) {
  const hasPlan = Boolean(candidate.plan);
  const isExpired = candidate.status === 'EXPIRED';

  return (
    <div
      data-testid={`signal-card-${candidate.id}`}
      role="button"
      tabIndex={0}
      onClick={() => onSelect(candidate.id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onSelect(candidate.id);
        }
      }}
      className={`p-4 rounded-xl border text-left transition-all cursor-pointer space-y-3 ${
        isSelected
          ? 'bg-amber-500/10 border-amber-500/50 shadow-lg shadow-amber-500/5 ring-1 ring-amber-500/30'
          : 'bg-[#0e1726] border-gray-800 hover:border-gray-700 hover:bg-[#121c2e]'
      }`}
    >
      {/* Top Row: State Badge + Direction Badge */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          {stateBadge(candidate.status)}
          {directionBadge(candidate.direction)}
        </div>

        {/* Setup Evidence Score */}
        <div className="text-right">
          <span className="text-[10px] text-gray-400 block">Setup Evidence Score</span>
          <strong className="text-sm font-bold font-mono text-amber-300">
            {candidate.score} <span className="text-xs text-gray-400 font-normal">/ 100</span>
          </strong>
        </div>
      </div>

      {/* Main Info: Strategy & Profile */}
      <div>
        <div className="flex items-baseline justify-between gap-2">
          <h4 className="text-sm font-bold text-white tracking-wide truncate">
            {strategy?.name || candidate.strategy_id}
          </h4>
          <span className="text-[11px] font-mono text-gray-400 font-semibold shrink-0">
            {candidate.strategy_id}
          </span>
        </div>
        <p className="text-xs text-gray-400 mt-0.5 flex items-center gap-1.5">
          <span>{profile?.name || candidate.profile_id}</span>
          {profile?.style && (
            <span className="text-[10px] px-1.5 py-0.2 rounded bg-black/40 text-gray-400 border border-white/5">
              {label(profile.style)}
            </span>
          )}
        </p>
      </div>

      {/* Trade Plan Geometry Highlights (if available) */}
      {candidate.plan ? (
        <div className="p-2.5 bg-black/30 rounded-lg border border-white/5 text-xs font-mono grid grid-cols-3 gap-2 text-center">
          <div>
            <span className="text-[10px] text-gray-400 block">ENTRY LOWER</span>
            <strong className="text-gray-200">${Number(candidate.plan.entry_lower).toFixed(2)}</strong>
          </div>
          <div>
            <span className="text-[10px] text-gray-400 block">STOP LOSS</span>
            <strong className="text-rose-400">${Number(candidate.plan.stop_loss).toFixed(2)}</strong>
          </div>
          <div>
            <span className="text-[10px] text-gray-400 block">TARGET TP1</span>
            <strong className="text-emerald-400">
              {candidate.plan.targets[0] ? `$${Number(candidate.plan.targets[0].price).toFixed(2)}` : '—'}
            </strong>
          </div>
        </div>
      ) : (
        <div className="text-[11px] text-gray-400 italic bg-black/20 p-2 rounded border border-white/5">
          {candidate.missing_conditions.length > 0
            ? `รอเงื่อนไข: ${candidate.missing_conditions[0]}`
            : 'ไม่มี Trade Plan Geometry ที่กำหนด'}
        </div>
      )}

      {/* Footer Timestamps */}
      <div className="flex flex-wrap items-center justify-between text-[10px] text-gray-400 pt-2 border-t border-gray-800/60 font-mono gap-1">
        <span>ตรวจพบ: {utc(candidate.detected_at)}</span>
        <div className="flex items-center gap-2">
          {hasPlan && (
            <span className="text-amber-400/80 font-bold">SUGGESTION AVAILABLE</span>
          )}
          {isExpired && (
            <span className="text-gray-400 uppercase font-semibold">EXPIRED</span>
          )}
        </div>
      </div>
    </div>
  );
}
