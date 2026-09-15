'use client';

import React from 'react';
import { label } from './thai';

interface MacroBiasCardProps {
  macroBias:
    | 'USD_STRONG_POSITIVE'
    | 'USD_POSITIVE'
    | 'USD_NEUTRAL'
    | 'USD_NEGATIVE'
    | 'USD_STRONG_NEGATIVE'
    | 'CONFLICTING'
    | 'UNKNOWN';
  macroStrength: 'STRONG' | 'MODERATE' | 'MIXED' | 'UNKNOWN';
  newsRegime?: string;
  releaseStatus?: string;
  dataQuality?: 'COMPLETE' | 'PARTIAL' | 'CONFLICT' | 'UNAVAILABLE';
  multipleEventRisk?: boolean;
  calendarState?: 'AVAILABLE' | 'CALENDAR_UNAVAILABLE';
}

export function MacroBiasCard({
  macroBias,
  macroStrength,
  newsRegime = 'UNKNOWN',
  releaseStatus = 'UNAVAILABLE',
  dataQuality = 'UNAVAILABLE',
  multipleEventRisk = false,
  calendarState = 'CALENDAR_UNAVAILABLE',
}: MacroBiasCardProps) {
  // Determine color styling based on bias
  const isPositive = macroBias === 'USD_STRONG_POSITIVE' || macroBias === 'USD_POSITIVE';
  const isNegative = macroBias === 'USD_STRONG_NEGATIVE' || macroBias === 'USD_NEGATIVE';
  const isConflicting = macroBias === 'CONFLICTING';
  const isNeutral = macroBias === 'USD_NEUTRAL';

  const biasBadgeColor = isPositive
    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
    : isNegative
    ? 'bg-rose-500/20 text-rose-300 border-rose-500/40'
    : isConflicting
    ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
    : isNeutral
    ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
    : 'bg-gray-500/20 text-gray-300 border-gray-500/40';

  const strengthBadgeColor =
    macroStrength === 'STRONG'
      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
      : macroStrength === 'MODERATE'
      ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
      : 'bg-gray-500/20 text-gray-300 border-gray-500/40';

  return (
    <div
      data-testid="macro-bias-card"
      className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4 relative overflow-hidden"
    >
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800 pb-3">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
          <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
            ภาพรวมดอลลาร์สหรัฐและสภาวะมหภาค (USD Macro Bias &amp; Strength)
          </h3>
        </div>

        {/* Macro Bias != Trading Signal Badge */}
        <span
          data-testid="macro-bias-not-signal"
          className="px-2.5 py-0.5 rounded font-mono text-[10px] font-bold bg-amber-500/10 text-amber-300 border border-amber-500/30"
        >
          MACRO BIAS ≠ TRADING SIGNAL
        </span>
      </div>

      {/* Main Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {/* 1. Macro Bias */}
        <div className="p-3.5 bg-black/40 rounded-xl border border-white/5 space-y-1.5 flex flex-col justify-between">
          <div>
            <span className="text-[10px] uppercase font-mono text-gray-400 block">
              ทิศทางมหภาคดอลลาร์ (Macro Bias)
            </span>
            <strong
              data-testid="macro-bias-value"
              className={`text-base sm:text-lg font-bold font-mono px-2 py-0.5 rounded border inline-block mt-1 ${biasBadgeColor}`}
            >
              {macroBias}
            </strong>
          </div>
          <p className="text-xs text-gray-300">
            {label(macroBias)}
          </p>
        </div>

        {/* 2. Macro Strength */}
        <div className="p-3.5 bg-black/40 rounded-xl border border-white/5 space-y-1.5 flex flex-col justify-between">
          <div>
            <span className="text-[10px] uppercase font-mono text-gray-400 block">
              ความชัดเจนของหลักฐาน (Strength)
            </span>
            <strong
              data-testid="macro-strength-value"
              className={`text-base sm:text-lg font-bold font-mono px-2 py-0.5 rounded border inline-block mt-1 ${strengthBadgeColor}`}
            >
              {macroStrength}
            </strong>
          </div>
          <p className="text-xs text-gray-300">
            ระดับ: {label(macroStrength)}
          </p>
        </div>

        {/* 3. News Regime & Release Status */}
        <div className="p-3.5 bg-black/40 rounded-xl border border-white/5 space-y-1.5 flex flex-col justify-between text-xs font-mono">
          <div>
            <span className="text-[10px] uppercase text-gray-400 block">
              สภาวะช่วงข่าว (News Regime)
            </span>
            <div className="flex items-center gap-1.5 mt-1">
              <strong data-testid="news-regime-value" className="text-blue-300 font-bold">
                {newsRegime}
              </strong>
              <span className="text-[10px] text-gray-400">({label(newsRegime)})</span>
            </div>
          </div>
          <div className="pt-1.5 border-t border-white/5 text-[11px] text-gray-400 flex items-center justify-between">
            <span>สถานะประกาศ:</span>
            <span data-testid="release-status-value" className="text-amber-300 font-semibold">
              {label(releaseStatus)}
            </span>
          </div>
        </div>

        {/* 4. Data Quality & Calendar State */}
        <div className="p-3.5 bg-black/40 rounded-xl border border-white/5 space-y-1.5 flex flex-col justify-between text-xs font-mono">
          <div>
            <span className="text-[10px] uppercase text-gray-400 block">
              คุณภาพข้อมูล (Data Quality)
            </span>
            <strong
              data-testid="data-quality-value"
              className={`text-sm font-bold block mt-1 ${
                dataQuality === 'COMPLETE'
                  ? 'text-emerald-400'
                  : dataQuality === 'CONFLICT'
                  ? 'text-rose-400 font-black animate-pulse'
                  : 'text-amber-400'
              }`}
            >
              {dataQuality} ({label(dataQuality)})
            </strong>
          </div>
          <div className="pt-1.5 border-t border-white/5 text-[11px] text-gray-400 flex items-center justify-between">
            <span>สถานะปฏิทิน:</span>
            <span
              data-testid="calendar-state-value"
              className={calendarState === 'AVAILABLE' ? 'text-emerald-400' : 'text-rose-400'}
            >
              {calendarState === 'AVAILABLE' ? 'พร้อมใช้งาน' : 'ไม่พร้อมใช้งาน'}
            </span>
          </div>
        </div>
      </div>

      {/* Multiple Event Risk Alert Banner */}
      {multipleEventRisk && (
        <div
          data-testid="multiple-event-risk-alert"
          className="p-3 bg-amber-500/20 border border-amber-500/40 rounded-lg flex items-center gap-2.5 text-xs text-amber-200"
        >
          <span className="text-lg shrink-0">⚠️</span>
          <div>
            <strong>แจ้งเตือนความเสี่ยงสะสม (Multiple Event Risk):</strong>
            <span className="ml-1">
              มีหลายเหตุการณ์สำคัญซ้อนกันในช่วงเวลาใกล้เคียงกัน ผลกระทบต่อตลาดอาจขัดแย้งกัน หรือเกิดแรงเหวี่ยงสองทิศทาง (Whipsaw)
            </span>
          </div>
        </div>
      )}

      {/* Explanatory Disclaimer Strip */}
      <div className="p-3 bg-black/30 rounded-lg border border-white/5 text-xs text-gray-400 font-mono space-y-1">
        <p>
          <strong className="text-gray-300">คำชี้แจงด้านบริบท: </strong>
          {macroBias === 'CONFLICTING'
            ? 'ตัวเลขในชุดข่าวให้ผลลัพธ์ต่างกัน รวมถึงการปรับข้อมูลเดิม จึงยังสรุปทิศทางไม่ได้'
            : macroBias === 'UNKNOWN'
            ? 'ผลประกาศยังไม่ครบ หรือทิศทางต้องตีความตามบริบท เช่น เงินเฟ้อและนโยบายดอกเบี้ย'
            : isPositive
            ? 'ตัวเลขเศรษฐกิจโดยรวมออกมาดีกว่าคาด สนับสนุนดอลลาร์สหรัฐ (USD Positive Context)'
            : isNegative
            ? 'ตัวเลขเศรษฐกิจโดยรวมออกมาต่ำกว่าคาด กดดันดอลลาร์สหรัฐ (USD Negative Context)'
            : 'ตัวเลขเศรษฐกิจออกมาใกล้เคียงกับที่คาดการณ์ไว้ (Neutral Context)'}
        </p>
        <p className="text-[11px] text-amber-300/80">
          * ภาพรวม USD เป็นเพียงบริบท ไม่ใช่คำสั่งซื้อหรือขายทอง (Context Only — No Direct XAUUSD Signal)
        </p>
      </div>
    </div>
  );
}
