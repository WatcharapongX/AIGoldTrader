'use client';

import React from 'react';
import type { AIAnalysisResult, AgentAgreement, DirectionalBias, EvidenceStrength } from '@/types/ai.generated';

interface MetaControllerCardProps {
  result?: AIAnalysisResult | null;
  isLoading?: boolean;
  isOutdated?: boolean;
  outdatedReason?: string;
}

function biasBadge(bias?: DirectionalBias) {
  switch (bias) {
    case 'LONG':
      return (
        <span className="px-2.5 py-1 text-xs font-bold rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
          ▲ SYNTHESIS: LONG (ขาขึ้น)
        </span>
      );
    case 'SHORT':
      return (
        <span className="px-2.5 py-1 text-xs font-bold rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">
          ▼ SYNTHESIS: SHORT (ขาลง)
        </span>
      );
    case 'NEUTRAL':
      return (
        <span className="px-2.5 py-1 text-xs font-bold rounded bg-gray-500/20 text-gray-300 border border-gray-500/40">
          ◆ SYNTHESIS: NEUTRAL (เป็นกลาง)
        </span>
      );
    default:
      return (
        <span className="px-2.5 py-1 text-xs font-bold rounded bg-gray-600/20 text-gray-400 border border-gray-600/40">
          ● SYNTHESIS: NO BIAS
        </span>
      );
  }
}

function agreementBadge(agreement?: AgentAgreement) {
  switch (agreement) {
    case 'HIGH':
      return <span className="text-emerald-400 font-semibold">● เห็นพ้องสูง (HIGH)</span>;
    case 'MEDIUM':
      return <span className="text-amber-400 font-medium">◐ เห็นพ้องปานกลาง (MEDIUM)</span>;
    case 'LOW':
      return <span className="text-gray-400">○ เห็นพ้องต่ำ (LOW)</span>;
    case 'CONFLICTING':
      return <span className="text-rose-400 font-bold animate-pulse">⚠ ขัดแย้งกัน (CONFLICTING)</span>;
    default:
      return <span className="text-gray-500">—</span>;
  }
}

function strengthBadge(strength?: EvidenceStrength) {
  switch (strength) {
    case 'STRONG':
      return <span className="text-emerald-400 font-semibold">● หนักแน่น (STRONG)</span>;
    case 'MODERATE':
      return <span className="text-amber-400 font-medium">◐ ปานกลาง (MODERATE)</span>;
    case 'WEAK':
      return <span className="text-gray-400">○ เบาบาง (WEAK)</span>;
    default:
      return <span className="text-gray-500">✕ ไม่เพียงพอ</span>;
  }
}

export function MetaControllerCard({
  result,
  isLoading,
  isOutdated,
  outdatedReason,
}: MetaControllerCardProps) {
  if (isLoading) {
    return (
      <div className="bg-gradient-to-r from-amber-950/20 via-[#0e1726] to-[#0e1726] border border-amber-500/30 rounded-xl p-5 animate-pulse space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <span className="w-3 h-3 rounded-full bg-amber-400 animate-ping" />
            <h3 className="text-base font-bold text-white">กำลังสังเคราะห์โดย Meta Controller…</h3>
          </div>
          <span className="text-xs text-amber-400 font-mono">PROCESSING 6 AGENTS</span>
        </div>
        <div className="h-4 bg-gray-800 rounded w-5/6" />
        <div className="h-4 bg-gray-800 rounded w-2/3" />
      </div>
    );
  }

  if (!result) {
    return (
      <div className="bg-[#0e1726]/80 border border-gray-800 rounded-xl p-5 text-center">
        <div className="flex items-center justify-center gap-2 text-gray-400 text-sm">
          <span>🧠</span>
          <span className="font-semibold text-gray-300">Meta Controller (ผู้สังเคราะห์ผลการวิเคราะห์)</span>
        </div>
        <p className="text-xs text-gray-400 mt-2 max-w-lg mx-auto leading-relaxed">
          ยังไม่ได้ทำการวิเคราะห์ กรุณากดปุ่ม &ldquo;วิเคราะห์ด้วย AI&rdquo; ด้านล่างเพื่อส่งข้อมูลให้ 6 Analytical Agents และรวบรวมข้อสรุปโดย Meta Controller
        </p>
        <p className="text-[11px] text-gray-400 mt-2 font-mono">
          ARCHITECTURE: 6 ANALYTICAL AGENTS + 1 META CONTROLLER
        </p>
      </div>
    );
  }

  const agentCount = Object.keys(result.agent_results || {}).length;
  const readyCount = Object.values(result.agent_results || {}).filter(
    (a) => a.status === 'READY',
  ).length;

  return (
    <div
      data-testid="meta-controller-card"
      className={`rounded-xl border p-5 relative overflow-hidden ${
        isOutdated
          ? 'bg-[#121620] border-amber-500/40'
          : 'bg-gradient-to-b from-[#131d2e] to-[#0e1726] border-amber-500/30 shadow-lg'
      }`}
    >
      {/* Outdated Warning Banner */}
      {isOutdated && (
        <div
          data-testid="meta-outdated-banner"
          className="mb-4 -mt-2 -mx-2 px-4 py-2 bg-amber-500/15 border border-amber-500/30 rounded-lg text-amber-300 text-xs flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <span className="text-amber-400 font-bold">⚠ OUTDATED:</span>
            <span>{outdatedReason || 'บริบท Candidate หรือ Risk มีการเปลี่ยนแปลงหลังจากวิเคราะห์'}</span>
          </div>
          <span className="text-[10px] font-mono uppercase bg-amber-500/20 px-2 py-0.5 rounded">
            กรุณาวิเคราะห์ใหม่
          </span>
        </div>
      )}

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 pb-3 border-b border-gray-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xl">🧠</span>
            <h3 className="text-base font-bold text-white tracking-wide">
              Meta Controller Thesis Synthesis
            </h3>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
              SYNTHESIZER · NOT A 7TH AGENT
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            รวบรวมข้อสรุปเชิงคุณภาพจาก 6 Analytical Agents อย่างเป็นอิสระต่อกัน (ไม่มีอำนาจส่งคำสั่ง)
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {biasBadge(result.directional_bias)}
          <span className="text-xs font-mono px-2 py-1 rounded bg-black/40 text-gray-300 border border-white/10">
            สถานะเอเจนต์: {readyCount} / {agentCount || 6} READY
          </span>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 my-3 p-3 bg-black/30 rounded-lg border border-white/5 text-xs">
        <div>
          <span className="text-gray-400 block text-[11px]">ความสอดคล้อง (Agreement):</span>
          {agreementBadge(result.agent_agreement)}
        </div>
        <div>
          <span className="text-gray-400 block text-[11px]">น้ำหนักหลักฐาน (Strength):</span>
          {strengthBadge(result.evidence_strength)}
        </div>
        <div>
          <span className="text-gray-400 block text-[11px]">สถานะ Meta:</span>
          <span className="font-mono font-bold text-gray-200">{result.status}</span>
        </div>
        <div>
          <span className="text-gray-400 block text-[11px]">ผู้ให้บริการ (Provider):</span>
          <span className="font-mono text-amber-300 truncate block">
            {result.execution_provenance?.provider_type || result.provider_provenance}
            {result.execution_provenance?.model_used ? ` · ${result.execution_provenance.model_used}` : ''}
          </span>
        </div>
      </div>

      {/* Thai Thesis Summary */}
      <div className="mt-3">
        <h4 className="text-xs font-bold text-amber-400 uppercase tracking-wider mb-1.5 flex items-center gap-1.5">
          <span>📝</span>
          <span>ข้อสรุปและสมมติฐานการเทรด (Thesis Summary)</span>
        </h4>
        <div className="p-3 bg-black/40 rounded-lg border border-white/5 text-sm text-gray-100 leading-relaxed">
          {result.summary_th || 'ไม่มีข้อสรุป'}
        </div>
      </div>

      {/* Key Evidence & Conflicts Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
        {/* Key Evidence */}
        <div className="p-3 bg-black/20 rounded-lg border border-white/5">
          <h5 className="text-xs font-semibold text-emerald-400 mb-2 flex items-center gap-1">
            <span>✓</span>
            <span>หลักฐานสำคัญ (Key Evidence):</span>
          </h5>
          {result.key_evidence_th.length > 0 ? (
            <ul className="text-xs text-gray-300 space-y-1 list-disc list-inside">
              {result.key_evidence_th.map((item, idx) => (
                <li key={idx} className="leading-snug">
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-gray-400 italic">ไม่มีหลักฐานสำคัญระบุไว้</p>
          )}
        </div>

        {/* Conflicts */}
        <div className="p-3 bg-black/20 rounded-lg border border-white/5">
          <h5 className="text-xs font-semibold text-amber-400 mb-2 flex items-center gap-1">
            <span>⚡</span>
            <span>ข้อขัดแย้งระหว่างเอเจนต์ (Conflicts):</span>
          </h5>
          {result.conflicts_th.length > 0 ? (
            <ul className="text-xs text-amber-200/90 space-y-1 list-disc list-inside">
              {result.conflicts_th.map((item, idx) => (
                <li key={idx} className="leading-snug">
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-gray-400 italic">เอเจนต์ทั้ง 6 ไม่มีข้อขัดแย้งเชิงทิศทาง</p>
          )}
        </div>
      </div>

      {/* Risk Notes & Warnings */}
      {(result.risk_notes_th.length > 0 || result.warnings_th.length > 0) && (
        <div className="mt-3 p-3 bg-rose-950/20 rounded-lg border border-rose-900/30 text-xs">
          {result.risk_notes_th.length > 0 && (
            <div className="mb-2">
              <span className="font-semibold text-rose-300 block mb-1">🛡️ ข้อสังเกตด้านความเสี่ยง:</span>
              <ul className="text-rose-200/80 space-y-0.5 list-disc list-inside">
                {result.risk_notes_th.map((note, idx) => (
                  <li key={idx}>{note}</li>
                ))}
              </ul>
            </div>
          )}
          {result.warnings_th.length > 0 && (
            <div>
              <span className="font-semibold text-amber-300 block mb-1">⚠ คำเตือน:</span>
              <ul className="text-amber-200/80 space-y-0.5 list-disc list-inside">
                {result.warnings_th.map((warn, idx) => (
                  <li key={idx}>{warn}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Meta Footer */}
      <div className="mt-3 pt-2 border-t border-gray-800/80 flex flex-wrap items-center justify-between text-[11px] text-gray-400 gap-2">
        <div className="flex items-center gap-3">
          <span>Generated UTC: {new Date(result.generated_at).toISOString()}</span>
          <span>Strategy: {result.strategy_id} ({result.strategy_version})</span>
        </div>
        <span className="font-mono text-amber-400/80 font-semibold">
          {result.execution_disclaimer}
        </span>
      </div>
    </div>
  );
}
