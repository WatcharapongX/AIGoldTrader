'use client';

import React, { useState } from 'react';
import type { AIAnalysisResult } from '@/types/ai.generated';
import { CANONICAL_AGENT_IDS } from '@/types/ai.generated';
import { MetaControllerCard } from './MetaControllerCard';
import { AIAgentCard } from './AIAgentCard';
import type { SubsystemStatus } from '@/types';

interface AIAgentAdvisoryPanelProps {
  result?: AIAnalysisResult | null;
  isLoading?: boolean;
  isOutdated?: boolean;
  outdatedReason?: string;
  aiSystemStatus?: SubsystemStatus | null;
}

export function AIAgentAdvisoryPanel({
  result,
  isLoading,
  isOutdated,
  outdatedReason,
  aiSystemStatus,
}: AIAgentAdvisoryPanelProps) {
  const [activeTab, setActiveTab] = useState<'agents' | 'conflicts' | 'evidence'>('agents');

  const isFixture =
    aiSystemStatus?.state === 'FIXTURE_READY' ||
    result?.provider_provenance === 'fixture' ||
    result?.execution_provenance?.provider_type === 'fixture';

  return (
    <section
      data-testid="ai-advisory-panel"
      className="space-y-4"
      aria-label="AI Advisory Analysis Panel"
    >
      {/* High-Visibility Advisory Authority Banner */}
      <div className="p-4 bg-gradient-to-r from-amber-500/10 via-purple-500/10 to-blue-500/10 border border-amber-500/30 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-md">
        <div className="flex items-start gap-3">
          <span className="text-2xl mt-0.5">🤖</span>
          <div>
            <div className="flex items-center gap-2">
              <span className="px-2 py-0.5 text-[10px] font-bold uppercase rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                AI ADVISORY ONLY
              </span>
              <span className="text-xs font-bold text-white tracking-wide">
                Multi-Agent Analytical Advisory System
              </span>
            </div>
            <p className="text-xs text-gray-300 mt-1 leading-relaxed">
              AI ใช้เพื่อช่วยอธิบายและตรวจสอบบริบท ไม่สามารถส่งคำสั่งซื้อขาย เปลี่ยน Risk หรือ Override Kill Switch ได้
            </p>
          </div>
        </div>

        {/* Provider Status Pill */}
        <div className="flex flex-col items-start md:items-end gap-1 shrink-0">
          <div className="flex items-center gap-2">
            <span
              className={`text-xs px-2.5 py-1 rounded font-mono font-bold flex items-center gap-1.5 ${
                isFixture
                  ? 'bg-purple-500/20 text-purple-300 border border-purple-500/40'
                  : aiSystemStatus?.state === 'EXTERNAL_READY'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  : 'bg-gray-800 text-gray-300 border border-gray-700'
              }`}
            >
              <span className="w-2 h-2 rounded-full bg-current animate-pulse" />
              <span>
                {isFixture
                  ? 'FIXTURE ADVISORY'
                  : aiSystemStatus?.state || 'AI SUBSYSTEM'}
              </span>
            </span>
          </div>
          <span className="text-[10px] text-gray-400 font-mono">
            {isFixture
              ? 'OFFLINE DETERMINISTIC TEST PROVIDER'
              : aiSystemStatus?.detail_th || 'ระบบวิเคราะห์พร้อมใช้งาน'}
          </span>
        </div>
      </div>

      {/* Meta Controller Synthesis (Separated and Above the 6 Agents) */}
      <MetaControllerCard
        result={result}
        isLoading={isLoading}
        isOutdated={isOutdated}
        outdatedReason={outdatedReason}
      />

      {/* Sub-Navigation Tabs */}
      <div className="flex items-center justify-between border-b border-gray-800 pb-2">
        <div className="flex items-center gap-2" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'agents'}
            onClick={() => setActiveTab('agents')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 ${
              activeTab === 'agents'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            <span>👥</span>
            <span>6 Analytical Agents</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'conflicts'}
            onClick={() => setActiveTab('conflicts')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 ${
              activeTab === 'conflicts'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            <span>⚡</span>
            <span>ข้อขัดแย้งในการวิเคราะห์ ({result?.conflicts_th.length || 0})</span>
          </button>

          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'evidence'}
            onClick={() => setActiveTab('evidence')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors flex items-center gap-1.5 ${
              activeTab === 'evidence'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
            }`}
          >
            <span>📋</span>
            <span>หลักฐานสำคัญ ({result?.key_evidence_th.length || 0})</span>
          </button>
        </div>

        <span className="text-[11px] text-gray-400 font-mono hidden sm:inline">
          ARCHITECTURE: 6 AGENTS + 1 META
        </span>
      </div>

      {/* Tab Content: 6 Analytical Agents Grid */}
      {activeTab === 'agents' && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {CANONICAL_AGENT_IDS.map((agentId) => (
            <AIAgentCard
              key={agentId}
              agentId={agentId}
              result={result?.agent_results?.[agentId]}
              isLoading={isLoading}
            />
          ))}
        </div>
      )}

      {/* Tab Content: Conflicts Panel */}
      {activeTab === 'conflicts' && (
        <div className="bg-[#0e1726] border border-gray-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-gray-800">
            <h4 className="text-sm font-bold text-white flex items-center gap-2">
              <span>⚡</span>
              <span>ข้อขัดแย้งระหว่างเอเจนต์ในการประเมิน (Agent Conflicts)</span>
            </h4>
            <span className="text-xs text-gray-400 font-mono">
              {result?.conflicts_th.length || 0} CONFLICTS DETECTED
            </span>
          </div>

          {!result ? (
            <p className="text-xs text-gray-400 italic py-4 text-center">
              ยังไม่มีข้อมูลการวิเคราะห์ กรุณากดปุ่ม &ldquo;วิเคราะห์ด้วย AI&rdquo;
            </p>
          ) : result.conflicts_th.length === 0 ? (
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-emerald-300 text-xs text-center">
              ✓ ไม่พบข้อขัดแย้งระหว่าง 6 Analytical Agents — การประเมินทุกมิติไปในทิศทางสอดคล้องกัน
            </div>
          ) : (
            <div className="space-y-2">
              {result.conflicts_th.map((conflict, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-amber-500/10 border border-amber-500/25 rounded-lg text-xs text-amber-200 flex items-start gap-2.5"
                >
                  <span className="text-amber-400 font-bold mt-0.5">⚠</span>
                  <span className="leading-relaxed">{conflict}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Tab Content: Key Evidence Summary */}
      {activeTab === 'evidence' && (
        <div className="bg-[#0e1726] border border-gray-800 rounded-xl p-5 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-gray-800">
            <h4 className="text-sm font-bold text-white flex items-center gap-2">
              <span>📋</span>
              <span>หลักฐานสำคัญที่ใช้สังเคราะห์ Thesis (Key Evidence)</span>
            </h4>
            <span className="text-xs text-gray-400 font-mono">
              {result?.key_evidence_th.length || 0} PIECES OF EVIDENCE
            </span>
          </div>

          {!result ? (
            <p className="text-xs text-gray-400 italic py-4 text-center">
              ยังไม่มีข้อมูลการวิเคราะห์ กรุณากดปุ่ม &ldquo;วิเคราะห์ด้วย AI&rdquo;
            </p>
          ) : result.key_evidence_th.length === 0 ? (
            <p className="text-xs text-gray-400 italic py-4 text-center">
              ไม่มีหลักฐานสำคัญบันทึกไว้ในผลการวิเคราะห์
            </p>
          ) : (
            <div className="space-y-2">
              {result.key_evidence_th.map((item, idx) => (
                <div
                  key={idx}
                  className="p-3 bg-black/30 border border-white/5 rounded-lg text-xs text-gray-200 flex items-start gap-2.5"
                >
                  <span className="text-emerald-400 font-bold mt-0.5">✓</span>
                  <span className="leading-relaxed">{item}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </section>
  );
}
