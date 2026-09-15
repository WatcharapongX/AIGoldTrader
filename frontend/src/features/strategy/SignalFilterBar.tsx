'use client';

import React from 'react';
import type { StrategyDefinition, TraderProfile } from '@/types/strategy.generated';
import { label } from './thai';

export type CandidateTab = 'CURRENT' | 'HISTORY';

export type CanonicalStateFilter =
  | 'ALL'
  | 'READY'
  | 'WAITING_CONFIRMATION'
  | 'DETECTED'
  | 'BLOCKED_CONTEXT'
  | 'NO_TRADE'
  | 'INVALIDATED'
  | 'EXPIRED'
  | 'SUPERSEDED';

interface SignalFilterBarProps {
  activeTab: CandidateTab;
  onSelectTab: (tab: CandidateTab) => void;
  stateFilter: CanonicalStateFilter;
  onSelectState: (state: CanonicalStateFilter) => void;
  strategyFilter: string;
  onSelectStrategy: (strategyId: string) => void;
  profileFilter: string;
  onSelectProfile: (profileId: string) => void;
  directionFilter: string;
  onSelectDirection: (direction: string) => void;
  strategies: StrategyDefinition[];
  profiles: TraderProfile[];
  searchQuery: string;
  onSearchChange: (query: string) => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}

const CANONICAL_STATES: readonly CanonicalStateFilter[] = [
  'ALL',
  'READY',
  'WAITING_CONFIRMATION',
  'DETECTED',
  'BLOCKED_CONTEXT',
  'NO_TRADE',
  'INVALIDATED',
  'EXPIRED',
  'SUPERSEDED',
] as const;

export function SignalFilterBar({
  activeTab,
  onSelectTab,
  stateFilter,
  onSelectState,
  strategyFilter,
  onSelectStrategy,
  profileFilter,
  onSelectProfile,
  directionFilter,
  onSelectDirection,
  strategies,
  profiles,
  searchQuery,
  onSearchChange,
  onRefresh,
  isRefreshing,
}: SignalFilterBarProps) {
  return (
    <div
      data-testid="signal-filter-bar"
      className="bg-[#0e1726] border border-gray-800 rounded-xl p-4 space-y-3.5"
    >
      {/* Top Bar: View Tabs & Refresh Button */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-gray-800">
        <div className="flex items-center gap-2" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'CURRENT'}
            onClick={() => onSelectTab('CURRENT')}
            className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 ${
              activeTab === 'CURRENT'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            <span>⚡</span>
            <span>CURRENT EVALUATION (รอบประเมินปัจจุบัน)</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'HISTORY'}
            onClick={() => onSelectTab('HISTORY')}
            className={`px-4 py-1.5 text-xs font-bold rounded-lg transition-colors flex items-center gap-1.5 ${
              activeTab === 'HISTORY'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5 border border-transparent'
            }`}
          >
            <span>📚</span>
            <span>CANDIDATE HISTORY (ประวัติบันทึกย้อนหลัง)</span>
          </button>
        </div>

        <button
          type="button"
          onClick={onRefresh}
          disabled={isRefreshing}
          className="px-3 py-1.5 bg-white/10 hover:bg-white/15 disabled:opacity-50 text-gray-300 hover:text-white text-xs font-medium rounded-lg border border-white/10 transition-colors flex items-center gap-1.5 self-start sm:self-auto"
        >
          <span className={isRefreshing ? 'animate-spin' : ''}>🔄</span>
          <span>{isRefreshing ? 'กำลังโหลด…' : 'รีเฟรชข้อมูล'}</span>
        </button>
      </div>

      {/* State Filter Chips (Canonical Enum Buttons) */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
        <span className="text-gray-400 text-[11px] shrink-0 mr-1 font-semibold">สถานะ:</span>
        {CANONICAL_STATES.map((st) => (
          <button
            key={st}
            type="button"
            onClick={() => onSelectState(st)}
            className={`px-2.5 py-1 rounded-md text-[11px] font-mono font-bold whitespace-nowrap transition-colors border ${
              stateFilter === st
                ? st === 'READY'
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50'
                  : st === 'WAITING_CONFIRMATION'
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
                  : st === 'BLOCKED_CONTEXT'
                  ? 'bg-orange-500/20 text-orange-300 border-orange-500/50'
                  : 'bg-blue-500/20 text-blue-300 border-blue-500/50'
                : 'bg-black/30 text-gray-400 hover:text-gray-200 border-white/5'
            }`}
          >
            {st} {st !== 'ALL' ? `(${label(st)})` : ''}
          </button>
        ))}
      </div>

      {/* Dropdown Filters & Search Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 text-xs">
        {/* Strategy Filter */}
        <div>
          <label htmlFor="strategy-filter" className="text-gray-400 block text-[11px] mb-1">
            กลยุทธ์ (Strategy):
          </label>
          <select
            id="strategy-filter"
            value={strategyFilter}
            onChange={(e) => onSelectStrategy(e.target.value)}
            className="w-full bg-black/40 text-gray-200 border border-gray-700 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500"
          >
            <option value="ALL">ทุกกลยุทธ์ (STRAT01 – STRAT06)</option>
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.id})
              </option>
            ))}
          </select>
        </div>

        {/* Profile Filter */}
        <div>
          <label htmlFor="profile-filter" className="text-gray-400 block text-[11px] mb-1">
            โปรไฟล์ผู้เทรด (Trader Profile):
          </label>
          <select
            id="profile-filter"
            value={profileFilter}
            onChange={(e) => onSelectProfile(e.target.value)}
            className="w-full bg-black/40 text-gray-200 border border-gray-700 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500"
          >
            <option value="ALL">ทุกโปรไฟล์ (7 Profiles)</option>
            {profiles.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name} · {label(p.style)}
              </option>
            ))}
          </select>
        </div>

        {/* Direction Filter */}
        <div>
          <label htmlFor="direction-filter" className="text-gray-400 block text-[11px] mb-1">
            ทิศทาง (Direction):
          </label>
          <select
            id="direction-filter"
            value={directionFilter}
            onChange={(e) => onSelectDirection(e.target.value)}
            className="w-full bg-black/40 text-gray-200 border border-gray-700 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500"
          >
            <option value="ALL">ทุกทิศทาง</option>
            <option value="LONG">ฝั่งซื้อ (LONG)</option>
            <option value="SHORT">ฝั่งขาย (SHORT)</option>
            <option value="NO_TRADE">ยังไม่มีทิศทาง (NO_TRADE)</option>
          </select>
        </div>

        {/* Search Input */}
        <div>
          <label htmlFor="signal-search" className="text-gray-400 block text-[11px] mb-1">
            ค้นหา (ID / Context):
          </label>
          <input
            id="signal-search"
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="พิมพ์รหัส ID..."
            className="w-full bg-black/40 text-gray-200 border border-gray-700 rounded-lg px-2.5 py-1.5 focus:outline-none focus:border-amber-500 font-mono"
          />
        </div>
      </div>
    </div>
  );
}
