'use client';

import React from 'react';
import type { NewsResponse } from '@/types/news.generated';
import { label } from './thai';

interface NewsRiskSummaryProps {
  newsContext: NewsResponse | null;
  loading: boolean;
  error: string | null;
}

export function NewsRiskSummary({ newsContext, loading, error }: NewsRiskSummaryProps) {
  if (loading && !newsContext) {
    return (
      <div data-testid="news-risk-loading" className="p-4 bg-[#0e1726] border border-gray-800 rounded-xl text-center text-xs text-gray-400">
        กำลังโหลดข้อมูลบริบทความเสี่ยงข่าว (Loading News Risk Context)...
      </div>
    );
  }

  if (error && !newsContext) {
    return (
      <div data-testid="news-risk-error" className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs">
        {error}
      </div>
    );
  }

  if (!newsContext) return null;

  const policy = newsContext.trade_policy_state;
  const regime = newsContext.news_regime;

  return (
    <div
      data-testid="news-risk-summary"
      className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4"
    >
      {/* 1. Header & Canonical Trade Policy */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800 pb-3">
        <div>
          <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
            นโยบายและสภาวะความเสี่ยงข่าว (News Risk &amp; Trade Policy)
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            สภาวะความเสี่ยงมหภาคตามการวิเคราะห์ของ News Engine แบบ Point-in-Time
          </p>
        </div>

        {/* Policy != Kill Switch Clarification */}
        <span className="text-[10px] font-mono text-gray-400 px-2 py-0.5 rounded bg-black/40 border border-white/5">
          POLICY ≠ KILL SWITCH
        </span>
      </div>

      {/* 2. Key Metrics Grid: Trade Policy, News Regime, Macro Bias, Data Quality */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* Trade Policy State Card */}
        <div
          data-testid="trade-policy-state"
          className={`p-3.5 rounded-xl border flex flex-col justify-between space-y-2 ${
            policy === 'INFORMATIONAL'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : policy === 'CAUTION'
              ? 'bg-amber-500/10 border-amber-500/30 text-amber-300'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
          }`}
        >
          <div>
            <span className="text-[10px] uppercase font-mono block opacity-80">
              นโยบายการเทรด (Trade Policy)
            </span>
            <strong className="text-base font-bold font-mono block mt-0.5">
              {policy}
            </strong>
          </div>
          <p className="text-xs">
            {policy === 'INFORMATIONAL'
              ? '● ปกติ / ใช้ประกอบบริบท'
              : policy === 'CAUTION'
              ? '⚠️ ต้องระมัดระวังความผันผวน'
              : '🛑 จำกัดการเทรดตามนโยบายข่าว'}
          </p>
        </div>

        {/* News Regime Card */}
        <div
          data-testid="news-regime-state"
          className="p-3.5 bg-black/30 border border-white/5 rounded-xl flex flex-col justify-between space-y-2"
        >
          <div>
            <span className="text-[10px] uppercase font-mono text-gray-400 block">
              สภาวะช่วงข่าว (News Regime)
            </span>
            <strong className="text-base font-bold font-mono text-blue-300 block mt-0.5">
              {regime}
            </strong>
          </div>
          <p className="text-xs text-gray-300">
            {label(regime)}
          </p>
        </div>

        {/* Macro Bias Card */}
        <div
          data-testid="macro-bias-state"
          className="p-3.5 bg-black/30 border border-white/5 rounded-xl flex flex-col justify-between space-y-2"
        >
          <div>
            <span className="text-[10px] uppercase font-mono text-gray-400 block">
              ทิศทางมหภาคดอลลาร์ (Macro Bias)
            </span>
            <strong className="text-base font-bold font-mono text-amber-300 block mt-0.5">
              {newsContext.macro_bias}
            </strong>
          </div>
          <p className="text-xs text-gray-300">
            {label(newsContext.macro_bias)} ({newsContext.macro_strength})
          </p>
        </div>

        {/* Market Conditions (Spread & Volatility) */}
        <div className="p-3.5 bg-black/30 border border-white/5 rounded-xl flex flex-col justify-between space-y-2 text-xs font-mono">
          <div>
            <span className="text-[10px] uppercase text-gray-400 block">
              สเปรดและความผันผวน
            </span>
            <div className="flex items-center justify-between mt-1">
              <span className="text-gray-300">SPREAD:</span>
              <strong className="text-amber-300">{newsContext.spread_state}</strong>
            </div>
            <div className="flex items-center justify-between mt-0.5">
              <span className="text-gray-300">VOLATILITY:</span>
              <strong className="text-purple-300">{newsContext.volatility_state}</strong>
            </div>
          </div>
          <div className="text-[11px] text-gray-400 pt-1 border-t border-white/5 flex justify-between">
            <span>DATA QUALITY:</span>
            <strong className="text-emerald-400">{newsContext.data_quality || 'COMPLETE'}</strong>
          </div>
        </div>
      </div>

      {/* 3. Multiple Event Risk Alert */}
      {newsContext.multiple_event_risk && (
        <div
          data-testid="multiple-event-risk-banner"
          className="p-3 bg-amber-500/15 border border-amber-500/40 rounded-lg flex items-center gap-2.5 text-xs text-amber-200"
        >
          <span className="text-base">⚠️</span>
          <span>
            <strong>แจ้งเตือนความเสี่ยงสะสม:</strong> มีข่าวสำคัญหลายรายการในช่วงเวลาเดียวกัน (Multiple Event Risk) ตลาดอาจเกิดแรงกระชากสองทิศทาง (Whipsaw)
          </span>
        </div>
      )}

      {/* 4. Semantic Disclaimers */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between text-[11px] text-gray-400 pt-1 border-t border-gray-800 font-mono gap-2">
        <span>* Macro Bias ≠ Trading Signal: การวิเคราะห์ปัจจัยพื้นฐานไม่ออกคำสั่งเทรดทองคำโดยอัตโนมัติ</span>
        <span>Calendar State: {newsContext.calendar_state}</span>
      </div>
    </div>
  );
}
