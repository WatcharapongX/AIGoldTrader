'use client';

import React from 'react';
import { PERFORMANCE_READINESS_ITEMS } from './contracts';
import { READINESS_STATE_TH } from './thai';

export function PerformanceReadinessPanel() {
  return (
    <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 shadow-lg space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-2">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
              <span>Performance Readiness Matrix</span>
              <span className="text-xs font-normal text-gray-400">
                (เมทริกซ์ความพร้อมของโมดูลเพื่อสร้างรายงานผลการเทรด)
              </span>
            </h2>
            <p className="text-xs text-gray-400">
              สถานะองค์ประกอบที่จำเป็นสำหรับเครื่องยนต์ Performance Engine ในอนาคต
            </p>
          </div>
        </div>

        <div className="text-xs text-gray-400">
          ความคืบหน้าภาพรวมระบบ: <strong className="text-amber-400">4 / 11 องค์ประกอบพร้อมใช้งาน</strong>
        </div>
      </div>

      {/* Grid of Readiness Items */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {PERFORMANCE_READINESS_ITEMS.map((item) => {
          const cfg = READINESS_STATE_TH[item.status];
          return (
            <div
              key={item.name}
              className="p-3.5 rounded-lg bg-slate-950/60 border border-slate-800 flex flex-col justify-between"
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-1">
                  <span className="text-xs font-bold text-gray-200">{item.name}</span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400 border border-slate-700 font-mono">
                    {item.phase}
                  </span>
                </div>
                <div className="text-[11px] text-gray-400 mb-2">{item.nameTh}</div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className={`px-2 py-0.5 rounded text-[11px] font-bold border ${cfg.border} ${cfg.bg} ${cfg.text}`}>
                    {cfg.label}
                  </span>
                  <span className="text-[10px] font-mono text-gray-400">{item.status}</span>
                </div>
                <p className="text-[10px] text-slate-400 leading-relaxed border-t border-slate-900 pt-2">
                  {item.detailsTh}
                </p>
              </div>
            </div>
          );
        })}
      </div>

      {/* Roadmap & Prerequisite Callout */}
      <div className="p-4 rounded-lg bg-slate-900/60 border border-slate-800 text-xs text-gray-300 leading-relaxed">
        <div className="font-semibold text-gray-200 mb-1 flex items-center gap-2">
          <span>แผนลำดับการพัฒนาเพื่อรองรับ Real Trading Performance (Development Sequence):</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-2 text-[11px]">
          <div className="p-2.5 rounded bg-slate-950/50 border border-slate-800">
            <span className="font-bold text-indigo-400">1. Phase 7 — OMS & Execution:</span>
            <p className="text-gray-400 mt-0.5">ติดตั้ง Paper Order Ledger, Position Lifecycle, Order Execution</p>
          </div>
          <div className="p-2.5 rounded bg-slate-950/50 border border-slate-800">
            <span className="font-bold text-amber-400">2. Phase 8 — Trade Journal:</span>
            <p className="text-gray-400 mt-0.5">บันทึก Closed Trades Ledger และเปิดใช้งาน Performance Engine คำนวณ Win Rate จริง</p>
          </div>
          <div className="p-2.5 rounded bg-slate-950/50 border border-slate-800">
            <span className="font-bold text-emerald-400">3. Phase 9 — Backtest Engine:</span>
            <p className="text-gray-400 mt-0.5">ประเมินกลยุทธ์ย้อนหลังกับชุดข้อมูลแท่งเทียน W1/D1/H1/M5</p>
          </div>
        </div>
      </div>
    </div>
  );
}
