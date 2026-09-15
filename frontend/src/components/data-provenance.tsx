import React from 'react';

export type DataCondition = 'FRESH' | 'PARTIAL' | 'STALE' | 'CONFLICT' | 'DEGRADED' | 'UNAVAILABLE';

export function provenanceLabel(mode?: string | null): string {
  switch (mode?.toUpperCase()) {
    case 'LIVE': return 'REAL MARKET DATA · LIVE';
    case 'DEMO': return 'MT5 DEMO · REAL MARKET DATA';
    case 'SIMULATED': return 'SIMULATED · NOT LIVE MARKET DATA';
    case 'REPLAY': return 'REPLAY · HISTORICAL';
    case 'FIXTURE': return 'FIXTURE · TEST DATA';
    case 'PAPER': return 'CONFIGURED PAPER';
    case 'DERIVED': return 'DERIVED';
    case 'ACTUAL': return 'AUTHORITATIVE ANALYSIS';
    case 'NOT IMPLEMENTED': return 'NOT IMPLEMENTED';
    default: return 'UNAVAILABLE';
  }
}

const conditionClass: Record<DataCondition, string> = {
  FRESH: 'border-emerald-500/30 bg-emerald-500/15 text-emerald-300',
  PARTIAL: 'border-amber-500/30 bg-amber-500/15 text-amber-300',
  STALE: 'border-amber-500/30 bg-amber-500/15 text-amber-300',
  CONFLICT: 'border-rose-500/30 bg-rose-500/15 text-rose-300',
  DEGRADED: 'border-orange-500/30 bg-orange-500/15 text-orange-300',
  UNAVAILABLE: 'border-gray-700 bg-gray-800 text-gray-400',
};

export function DataProvenanceBadge({ mode }: { mode?: string | null }) {
  return <span className="rounded border border-blue-500/30 bg-blue-500/15 px-2 py-0.5 text-[10px] font-bold text-blue-300">{provenanceLabel(mode)}</span>;
}

export function DataConditionBadge({ condition }: { condition: DataCondition }) {
  return <span className={`rounded border px-2 py-0.5 text-[10px] font-bold ${conditionClass[condition]}`}>{condition}</span>;
}

export function DataProvenanceLine({ source, mode, condition, asOf, derivedFrom }: {
  source?: string | null;
  mode?: string | null;
  condition: DataCondition;
  asOf?: string | null;
  derivedFrom?: string | null;
}) {
  return <div className="flex flex-wrap items-center gap-2 text-[10px] font-mono text-gray-400">
    <DataProvenanceBadge mode={mode} />
    <DataConditionBadge condition={condition} />
    <span>Source: {source || 'UNAVAILABLE'}</span>
    <span>As of: {asOf || 'UNAVAILABLE'}</span>
    {derivedFrom && <span>Derived from: {derivedFrom}</span>}
  </div>;
}
