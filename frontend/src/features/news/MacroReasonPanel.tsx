'use client';

import React from 'react';
import { reasonDesc } from './thai';

interface MacroReasonPanelProps {
  tradePolicyState?: 'INFORMATIONAL' | 'CAUTION' | 'RESTRICTED';
  reasonCodes?: string[];
}

export function MacroReasonPanel({
  tradePolicyState = 'INFORMATIONAL',
  reasonCodes = [],
}: MacroReasonPanelProps) {
  const policyColor =
    tradePolicyState === 'INFORMATIONAL'
      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
      : tradePolicyState === 'CAUTION'
      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
      : 'bg-rose-500/20 text-rose-300 border-rose-500/40 font-bold';

  return (
    <div
      data-testid="macro-reason-panel"
      className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4"
    >
      {/* 1. Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800 pb-3">
        <div>
          <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
            นโยบายการเทรดและเหตุผลของระบบ (Trade Policy &amp; Reason Codes)
          </h3>
          <p className="text-xs text-gray-400 font-mono mt-0.5">
            การกำหนดขอบเขตนโยบายความเสี่ยงและรหัสเหตุผลที่ประเมินโดย News Engine
          </p>
        </div>

        {/* Policy != Kill Switch Clarification */}
        <span className="text-[10px] font-mono text-gray-400 px-2 py-0.5 rounded bg-black/40 border border-white/5">
          POLICY ≠ RISK ENGINE KILL SWITCH
        </span>
      </div>

      {/* 2. Trade Policy Card */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between p-4 bg-black/30 rounded-xl border border-white/5 gap-3">
        <div>
          <span className="text-[10px] uppercase font-mono text-gray-400 block">
            สภาวะนโยบายข่าว (Trade Policy State)
          </span>
          <div className="flex items-center gap-2 mt-1">
            <strong
              data-testid="trade-policy-state-badge"
              className={`text-sm sm:text-base font-bold font-mono px-2.5 py-0.5 rounded border ${policyColor}`}
            >
              {tradePolicyState}
            </strong>
            <span className="text-xs text-gray-300">
              ({tradePolicyState === 'INFORMATIONAL'
                ? 'ปกติ / ใช้ประกอบบริบท'
                : tradePolicyState === 'CAUTION'
                ? 'ต้องระมัดระวังความผันผวน'
                : 'จำกัดสิทธิ์การเทรดตามนโยบายข่าว'})
            </span>
          </div>
        </div>

        <p className="text-xs text-gray-400 font-mono max-w-sm text-left sm:text-right">
          นโยบายข่าวเป็นข้อจำกัดเชิงมหภาค ไม่แก้ไขค่าความเสี่ยงหรือพอร์ตโฟลิโอของ Risk Engine
        </p>
      </div>

      {/* 3. Reason Codes */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
            รหัสเหตุผลของระบบ (Active Reason Codes)
          </h4>
          <span className="text-[10px] font-mono text-gray-400">
            {reasonCodes.length} รายการ
          </span>
        </div>

        {reasonCodes.length === 0 ? (
          <div className="p-3 bg-black/20 rounded-lg border border-white/5 text-center text-xs text-gray-500 font-mono">
            ไม่มีรหัสเหตุผลที่ถูกกระตุ้นในสภาวะปัจจุบัน (No Active Reason Codes)
          </div>
        ) : (
          <div className="flex flex-wrap gap-2">
            {reasonCodes.map((code) => (
              <div
                key={code}
                className="p-2.5 bg-black/40 rounded-lg border border-white/10 flex flex-col space-y-1 font-mono text-xs"
              >
                <div className="flex items-center gap-2">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                  <strong className="text-amber-300 font-bold">{reasonDesc(code)}</strong>
                </div>
                <span className="text-[10px] text-gray-400 pl-3.5">
                  Raw Code: <code className="text-gray-300">{code}</code>
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
