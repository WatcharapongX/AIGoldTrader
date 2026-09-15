'use client';

import React from 'react';
import { label } from './thai';

interface StrategyNewsEligibilityProps {
  eligibility?: Record<string, 'ALLOWED' | 'CAUTION' | 'BLOCKED' | 'WAITING' | 'ELIGIBLE'>;
}

export function StrategyNewsEligibility({ eligibility = {} }: StrategyNewsEligibilityProps) {
  const strat05 = eligibility['STRAT05'] || 'ELIGIBLE';
  const strat06 = eligibility['STRAT06'] || 'ELIGIBLE';

  const badgeClass = (status: string) => {
    switch (status) {
      case 'ALLOWED':
      case 'ELIGIBLE':
        return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40';
      case 'CAUTION':
      case 'WAITING':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40';
      case 'BLOCKED':
      default:
        return 'bg-rose-500/20 text-rose-300 border-rose-500/40';
    }
  };

  return (
    <div
      data-testid="strategy-news-eligibility"
      className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800 pb-3">
        <div>
          <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
            ความพร้อมของกลยุทธ์ตามสภาวะข่าว (Strategy News Eligibility)
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            การประเมินสิทธิ์และข้อจำกัดของกลยุทธ์ที่เกี่ยวข้องกับข่าวเศรษฐกิจ
          </p>
        </div>
        <span className="text-[10px] font-mono text-gray-400">
          News Engine Governed
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* STRAT05: Post-News Momentum */}
        <div
          data-testid="eligibility-STRAT05"
          className="p-4 bg-black/30 border border-white/5 rounded-xl space-y-2.5"
        >
          <div className="flex items-center justify-between gap-2">
            <div>
              <span className="text-xs font-mono font-bold text-amber-300">STRAT05</span>
              <h4 className="text-sm font-bold text-white">Post-News Momentum</h4>
            </div>
            <span
              className={`px-2.5 py-1 text-xs font-mono font-bold rounded border ${badgeClass(
                strat05
              )}`}
            >
              {strat05}
            </span>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            {label(strat05)}: ติดตามแรงส่งทิศทางเดียวหลังการประกาศตัวเลขจริงเมื่อ Macro Alignment สอดคล้องกับโครงสร้างราคา
          </p>
        </div>

        {/* STRAT06: Post-News Liquidity Reversal */}
        <div
          data-testid="eligibility-STRAT06"
          className="p-4 bg-black/30 border border-white/5 rounded-xl space-y-2.5"
        >
          <div className="flex items-center justify-between gap-2">
            <div>
              <span className="text-xs font-mono font-bold text-amber-300">STRAT06</span>
              <h4 className="text-sm font-bold text-white">Post-News Liquidity Reversal</h4>
            </div>
            <span
              className={`px-2.5 py-1 text-xs font-mono font-bold rounded border ${badgeClass(
                strat06
              )}`}
            >
              {strat06}
            </span>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            {label(strat06)}: รอการกวาดสภาพคล่องและกลับเข้าระดับเดิมหลังข่าวแรง พร้อมยืนยัน CHoCH / MSS กรอบเล็ก
          </p>
        </div>
      </div>

      {/* Market-Driven STRAT01–STRAT04 Clarification */}
      <div className="p-3 bg-black/40 border border-white/5 rounded-lg flex items-start gap-2.5 text-xs text-gray-300">
        <span className="text-emerald-400 font-bold shrink-0">ℹ️</span>
        <div>
          <strong className="text-emerald-300">STRAT01–STRAT04 (Market-Driven Playbooks):</strong>
          <span className="text-gray-400 block mt-0.5">
            กลยุทธ์ SMC, Trend Pullback, Breakout Retest และ Range Mean Reversion เป็นระบบวิเคราะห์โครงสร้างราคาทางเทคนิค
            <strong className="text-gray-300 font-normal"> ข่าวเศรษฐกิจไม่เปลี่ยน Signal Identity หรือโครงสร้าง Setup Evidence Score ของกลุ่มนี้</strong>
          </span>
        </div>
      </div>
    </div>
  );
}
