'use client';

import React from 'react';
import type { StructureContext } from '@/types/news.generated';
import { bangkok, label } from './thai';

interface StructureConfirmationCardProps {
  structure?: StructureContext;
}

export function StructureConfirmationCard({ structure }: StructureConfirmationCardProps) {
  if (!structure) {
    return (
      <div
        data-testid="structure-confirmation-card"
        className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl text-center text-xs text-gray-400 font-mono"
      >
        ไม่มีข้อมูลการยืนยันโครงสร้างตลาด
      </div>
    );
  }

  const status = structure.status;
  const statusColor =
    status === 'ALIGNED'
      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
      : status === 'CONFLICTING'
      ? 'bg-rose-500/20 text-rose-300 border-rose-500/40 font-bold'
      : status === 'WAITING'
      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
      : 'bg-gray-500/20 text-gray-300 border-gray-500/40';

  const refEntries = Object.entries(structure.references || {});

  return (
    <div
      data-testid="structure-confirmation-card"
      className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-5"
    >
      {/* 1. Header & Status */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              การยืนยันจากโครงสร้างตลาด (Market Structure Confirmation)
            </h3>
          </div>
          <p className="text-xs text-gray-400 font-mono mt-1">
            การตรวจสอบความสอดคล้องระหว่างปฏิกิริยาราคากับโครงสร้าง Smart Money Concepts (BOS, CHoCH, MSS, Liquidity)
          </p>
        </div>

        {/* Structure Status Badge */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-gray-400 uppercase">สถานะโครงสร้าง:</span>
          <span
            data-testid="structure-status-badge"
            className={`px-3 py-1 text-xs font-mono font-bold rounded border ${statusColor}`}
          >
            {status} ({label(status)})
          </span>
        </div>
      </div>

      {/* 2. Structural References Grid */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
            วัตถุโครงสร้างที่ตรวจพบใน Snapshot (Structural References)
          </h4>
          <span className="text-[10px] font-mono text-gray-400">
            {refEntries.length} รายการ
          </span>
        </div>

        {refEntries.length === 0 ? (
          <div className="p-3 bg-black/30 rounded-lg border border-white/5 text-center text-xs text-gray-400 font-mono">
            ยังไม่มีวัตถุโครงสร้างที่บันทึกไว้ใน snapshot ของการประเมินนี้
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5 font-mono text-xs">
            {refEntries.map(([key, val]) => (
              <div
                key={key}
                className="p-2.5 bg-black/40 rounded-lg border border-white/5 flex items-center justify-between"
              >
                <span className="text-amber-300 font-bold">{key}</span>
                <span className="text-gray-300">{val}</span>
              </div>
            ))}
          </div>
        )}

        {/* Absence Means Unknown Note */}
        <p className="text-[11px] text-gray-400 font-mono italic">
          * วัตถุที่ไม่อยู่ใน snapshot = ยังไม่ทราบสถานะ (NOT_INCLUDED_UNKNOWN) ไม่ถือว่าโครงสร้างนั้นถูกยกเลิก (Absence means Unknown, not Invalidated)
        </p>
      </div>

      {/* 3. Upstream Provenance */}
      <div className="p-3 bg-black/30 rounded-lg border border-white/5 text-xs font-mono space-y-1.5 text-gray-400">
        <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
          <span>
            ขอบเขตเวลา: {bangkok(structure.upstream_window_start)} ถึง {bangkok(structure.upstream_as_of)}
          </span>
          <span>
            Algorithm: {structure.upstream_algorithm_version || 'v1.2.0'}
          </span>
        </div>
        {(structure.upstream_input_id || structure.upstream_config_id) && (
          <div className="flex flex-wrap items-center justify-between gap-2 text-[10px] text-gray-500 pt-1 border-t border-white/5">
            <span>Input ID: {structure.upstream_input_id || '—'}</span>
            <span>Config ID: {structure.upstream_config_id || '—'}</span>
          </div>
        )}
      </div>

      {/* 4. Explainability Flow Diagram */}
      <div className="p-4 bg-black/40 rounded-xl border border-white/5 space-y-2">
        <h4 className="text-[11px] font-bold text-gray-300 uppercase tracking-wider font-mono">
          กระบวนการวิเคราะห์และตรวจสอบร่วม (Explainability Flow)
        </h4>
        <div className="flex flex-wrap items-center gap-1.5 text-[11px] font-mono text-gray-300">
          <span className="px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
            1. ECONOMIC RELEASE
          </span>
          <span className="text-gray-500">→</span>
          <span className="px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
            2. SURPRISE / REVISION
          </span>
          <span className="text-gray-500">→</span>
          <span className="px-2 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/30">
            3. USD MACRO BIAS
          </span>
          <span className="text-gray-500">→</span>
          <span className="px-2 py-0.5 rounded bg-pink-500/20 text-pink-300 border border-pink-500/30">
            4. XAUUSD REACTION
          </span>
          <span className="text-gray-500">→</span>
          <span className="px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
            5. STRUCTURE CONFIRMATION
          </span>
          <span className="text-gray-500">→</span>
          <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            6. TRADE POLICY &amp; ELIGIBILITY
          </span>
        </div>
        <p className="text-[10px] text-gray-500 font-mono">
          * แผนภาพแสดงขั้นตอนการเชื่อมโยงข้อมูลเชิงเหตุผล — ไม่มีการสร้างคะแนนสังเคราะห์ (No Synthetic Confluence Score) และไม่มีการส่งคำสั่งซื้อขายอัตโนมัติ
        </p>
      </div>
    </div>
  );
}
