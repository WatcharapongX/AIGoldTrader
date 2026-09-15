'use client';

import React, { useState } from 'react';
import type {
  AgentAnalysisResult,
  CanonicalAgentId,
  DirectionalBias,
  EvidenceStrength,
} from '@/types/ai.generated';
import { CANONICAL_AGENT_METADATA } from '@/types/ai.generated';

interface AIAgentCardProps {
  agentId: CanonicalAgentId;
  result?: AgentAnalysisResult;
  isLoading?: boolean;
}

function biasBadge(bias?: DirectionalBias) {
  switch (bias) {
    case 'LONG':
      return <span className="px-2 py-0.5 text-[11px] font-bold rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">LONG · ขาขึ้น</span>;
    case 'SHORT':
      return <span className="px-2 py-0.5 text-[11px] font-bold rounded bg-rose-500/15 text-rose-400 border border-rose-500/30">SHORT · ขาลง</span>;
    case 'NEUTRAL':
      return <span className="px-2 py-0.5 text-[11px] font-medium rounded bg-gray-500/15 text-gray-300 border border-gray-500/30">NEUTRAL · เป็นกลาง</span>;
    default:
      return <span className="px-2 py-0.5 text-[11px] font-medium rounded bg-gray-500/10 text-gray-400 border border-gray-600/20">NO BIAS</span>;
  }
}

function strengthBadge(strength?: EvidenceStrength) {
  switch (strength) {
    case 'STRONG':
      return <span className="text-[11px] text-emerald-400 font-semibold">● หนักแน่น (STRONG)</span>;
    case 'MODERATE':
      return <span className="text-[11px] text-amber-400 font-medium">◐ ปานกลาง (MODERATE)</span>;
    case 'WEAK':
      return <span className="text-[11px] text-gray-400">○ เบาบาง (WEAK)</span>;
    case 'INSUFFICIENT':
    default:
      return <span className="text-[11px] text-gray-500">✕ ไม่เพียงพอ</span>;
  }
}

export function AIAgentCard({ agentId, result, isLoading }: AIAgentCardProps) {
  const meta = CANONICAL_AGENT_METADATA[agentId];
  const [expanded, setExpanded] = useState(false);

  if (isLoading) {
    return (
      <div className="bg-[#0e1726]/80 border border-gray-800 rounded-lg p-4 animate-pulse flex flex-col justify-between min-h-[220px]">
        <div>
          <div className="flex items-center justify-between pb-3 border-b border-gray-800">
            <div className="flex items-center gap-2">
              <span className="text-lg">{meta.icon}</span>
              <div>
                <h4 className="text-sm font-bold text-white">{meta.nameTh}</h4>
                <p className="text-[10px] text-gray-400 font-mono">{agentId}</p>
              </div>
            </div>
            <span className="text-xs text-amber-400 font-medium">กำลังวิเคราะห์…</span>
          </div>
          <p className="text-xs text-gray-400 mt-3">{meta.descriptionTh}</p>
        </div>
        <div className="h-4 bg-gray-800 rounded mt-4 w-3/4" />
      </div>
    );
  }

  if (!result) {
    return (
      <div className="bg-[#0e1726]/60 border border-gray-800/80 rounded-lg p-4 flex flex-col justify-between min-h-[200px]">
        <div>
          <div className="flex items-center justify-between pb-3 border-b border-gray-800/80">
            <div className="flex items-center gap-2">
              <span className="text-lg opacity-80">{meta.icon}</span>
              <div>
                <h4 className="text-sm font-semibold text-gray-200">{meta.nameTh}</h4>
                <p className="text-[10px] text-gray-400 font-mono">{agentId}</p>
              </div>
            </div>
            <span className="text-[11px] px-2 py-0.5 rounded bg-gray-800 text-gray-400 font-mono">
              WAITING
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-3 leading-relaxed">{meta.descriptionTh}</p>
        </div>
        <div className="text-[11px] text-gray-400 mt-4 pt-2 border-t border-gray-800/60 flex items-center justify-between">
          <span>รอการประเมินจาก Candidate</span>
          <span className="font-mono text-[10px]">AI AGENT</span>
        </div>
      </div>
    );
  }

  const isDegraded = result.status === 'DEGRADED';
  const isUnavailable = result.status === 'UNAVAILABLE';
  const isReady = result.status === 'READY';

  return (
    <div
      data-testid={`agent-card-${agentId}`}
      className={`rounded-lg border transition-colors p-4 flex flex-col justify-between ${
        isUnavailable
          ? 'bg-rose-950/20 border-rose-900/40'
          : isDegraded
          ? 'bg-amber-950/20 border-amber-900/40'
          : 'bg-[#0e1726] border-gray-800 hover:border-gray-700'
      }`}
    >
      <div>
        {/* Card Header */}
        <div className="flex items-start justify-between pb-2.5 border-b border-gray-800/80 gap-2">
          <div className="flex items-center gap-2">
            <span className="text-lg">{meta.icon}</span>
            <div>
              <div className="flex items-center gap-1.5">
                <h4 className="text-sm font-bold text-white">{meta.nameTh}</h4>
                <span className="text-[10px] text-gray-400 font-mono">({agentId})</span>
              </div>
              <p className="text-[11px] text-gray-400">{meta.descriptionTh}</p>
            </div>
          </div>
          <div className="flex flex-col items-end gap-1">
            <span
              className={`text-[10px] px-2 py-0.5 rounded font-mono font-bold uppercase ${
                isReady
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                  : isDegraded
                  ? 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
                  : 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
              }`}
            >
              {result.status}
            </span>
            {biasBadge(result.directional_bias)}
          </div>
        </div>

        {/* Evidence Strength */}
        <div className="mt-2.5 flex items-center justify-between text-xs">
          <span className="text-gray-400">น้ำหนักหลักฐาน:</span>
          {strengthBadge(result.evidence_strength)}
        </div>

        {/* Thai Summary */}
        <p className="mt-2.5 text-xs text-gray-200 leading-relaxed bg-black/20 p-2.5 rounded border border-white/5">
          {result.summary_th || 'ไม่มีคำอธิบายสรุป'}
        </p>

        {/* Supporting Factors */}
        {result.supporting_factors_th.length > 0 && (
          <div className="mt-2.5">
            <p className="text-[11px] font-semibold text-emerald-400 mb-1 flex items-center gap-1">
              <span>✓</span>
              <span>ปัจจัยสนับสนุน:</span>
            </p>
            <ul className="text-[11px] text-gray-300 space-y-0.5 list-disc list-inside">
              {result.supporting_factors_th.map((factor, idx) => (
                <li key={idx} className="leading-tight">
                  {factor}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Conflicting Factors */}
        {result.conflicting_factors_th.length > 0 && (
          <div className="mt-2.5">
            <p className="text-[11px] font-semibold text-amber-400 mb-1 flex items-center gap-1">
              <span>⚠</span>
              <span>ปัจจัยขัดแย้ง:</span>
            </p>
            <ul className="text-[11px] text-amber-200/80 space-y-0.5 list-disc list-inside">
              {result.conflicting_factors_th.map((factor, idx) => (
                <li key={idx} className="leading-tight">
                  {factor}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Warnings */}
        {result.warnings_th.length > 0 && (
          <div className="mt-2">
            <p className="text-[11px] font-semibold text-rose-400 mb-1">ข้อควรระวัง:</p>
            <ul className="text-[11px] text-rose-300/80 space-y-0.5 list-disc list-inside">
              {result.warnings_th.map((warning, idx) => (
                <li key={idx} className="leading-tight">
                  {warning}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Missing Context */}
        {result.missing_context_th.length > 0 && (
          <div className="mt-2">
            <p className="text-[11px] font-medium text-gray-400 mb-0.5">บริบทที่ขาดหาย:</p>
            <p className="text-[11px] text-gray-400 italic">
              {result.missing_context_th.join(', ')}
            </p>
          </div>
        )}
      </div>

      {/* Provenance & Technical Footer */}
      <div className="mt-3 pt-2 border-t border-gray-800/60">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="text-[10px] text-gray-400 hover:text-gray-200 flex items-center justify-between w-full font-mono"
        >
          <span>
            {expanded ? '▲ ย่อข้อมูลระบบ' : '▼ รายละเอียด Provenance / Schema'}
          </span>
          <span className="uppercase">
            {result.execution_provenance?.provider_type || result.provider_provenance}
          </span>
        </button>

        {expanded && (
          <dl className="mt-2 text-[10px] text-gray-400 grid grid-cols-2 gap-x-2 gap-y-1 bg-black/40 p-2 rounded border border-white/5 font-mono">
            <div>
              <dt className="text-gray-400">Provider:</dt>
              <dd className="text-gray-300">
                {result.execution_provenance?.provider_id || result.provider_provenance}
              </dd>
            </div>
            <div>
              <dt className="text-gray-400">Model:</dt>
              <dd className="text-gray-300 truncate">
                {result.execution_provenance?.model_used || 'fixture-v1'}
              </dd>
            </div>
            <div>
              <dt className="text-gray-400">Prompt Ver:</dt>
              <dd className="text-gray-300">{result.prompt_version}</dd>
            </div>
            <div>
              <dt className="text-gray-400">Total Tokens:</dt>
              <dd className="text-gray-300">
                {result.token_usage?.total_tokens ?? '—'}
              </dd>
            </div>
            <div className="col-span-2">
              <dt className="text-gray-400">Generated UTC:</dt>
              <dd className="text-gray-400 truncate">
                {new Date(result.generated_at).toISOString()}
              </dd>
            </div>
          </dl>
        )}
      </div>
    </div>
  );
}
