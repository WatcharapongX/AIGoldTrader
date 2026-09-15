'use client';

import React from 'react';
import type { ReactionWindow } from '@/types/news.generated';
import { label, numeric } from './thai';

interface MarketReactionPanelProps {
  reactionState?: string;
  reactionWindows?: ReactionWindow[];
  spreadState?: 'SPREAD_NORMAL' | 'SPREAD_ELEVATED' | 'SPREAD_EXTREME' | 'UNAVAILABLE';
  currentSpread?: string | null;
  baselineSpread?: string | null;
  spreadRatio?: string | null;
  volatilityState?: 'NORMAL' | 'ELEVATED' | 'EXTREME' | 'UNAVAILABLE';
  sourceMode?: string;
}

export function MarketReactionPanel({
  reactionState = 'REACTION_UNAVAILABLE',
  reactionWindows = [],
  spreadState = 'SPREAD_NORMAL',
  currentSpread,
  baselineSpread,
  spreadRatio,
  volatilityState = 'NORMAL',
  sourceMode = 'LIVE',
}: MarketReactionPanelProps) {
  // Classification badge helper
  const getClassificationBadge = (cls?: string) => {
    if (!cls) return null;
    let color = 'bg-gray-500/20 text-gray-300 border-gray-500/40';
    if (cls === 'STRONG_DIRECTIONAL' || cls === 'BREAKOUT') {
      color = 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 font-bold';
    } else if (cls === 'WHIPSAW' || cls === 'LIQUIDITY_SWEEP_REVERSAL' || cls === 'FAILED_BREAKOUT') {
      color = 'bg-amber-500/20 text-amber-300 border-amber-500/40 font-bold';
    } else if (cls === 'MUTED') {
      color = 'bg-blue-500/20 text-blue-300 border-blue-500/40';
    }

    return (
      <span className={`px-2 py-0.5 rounded text-[10px] font-mono border ${color}`}>
        {cls} ({label(cls)})
      </span>
    );
  };

  return (
    <div
      data-testid="market-reaction-panel"
      className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-5"
    >
      {/* 1. Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-500 animate-pulse" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              ปฏิกิริยาราคาทองคำ สเปรด และความผันผวน (XAUUSD Market Reaction)
            </h3>
          </div>
          <p className="text-xs text-gray-400 font-mono mt-1">
            การวัดผลเชิงสถิติจากการเคลื่อนที่ของแท่งเทียน M1 จริงหลังช่วงประกาศข่าว
          </p>
        </div>

        {/* Reaction State Badge */}
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-gray-400 uppercase">สถานะปฏิกิริยา:</span>
          <span
            data-testid="reaction-state-badge"
            className={`px-2.5 py-1 text-xs font-mono font-bold rounded border ${
              reactionState === 'READY'
                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                : reactionState === 'WAITING'
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                : 'bg-gray-500/20 text-gray-300 border-gray-500/40'
            }`}
          >
            {reactionState} ({label(reactionState)})
          </span>
        </div>
      </div>

      {/* 2. Spread & Volatility Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 font-mono text-xs">
        {/* Spread State */}
        <div
          data-testid="spread-state-card"
          className="p-3.5 bg-black/30 rounded-xl border border-white/5 space-y-1.5"
        >
          <span className="text-[10px] uppercase text-gray-400 block">
            สภาวะสเปรด (Spread State)
          </span>
          <div className="flex items-center justify-between">
            <strong
              className={`text-sm font-bold ${
                spreadState === 'SPREAD_NORMAL'
                  ? 'text-emerald-400'
                  : spreadState === 'SPREAD_ELEVATED'
                  ? 'text-amber-400'
                  : 'text-rose-400 font-black'
              }`}
            >
              {spreadState}
            </strong>
            <span className="text-gray-300 text-[11px]">
              {label(spreadState)}
            </span>
          </div>
          <div className="pt-1.5 border-t border-white/5 text-[11px] text-gray-400 flex items-center justify-between">
            <span>อัตราส่วนต่อฐาน:</span>
            <span className="text-white font-bold">
              {spreadRatio != null
                ? `${Number(spreadRatio).toFixed(2)}x`
                : 'ไม่มีข้อมูลย้อนหลังเพียงพอ'}
            </span>
          </div>
          {(currentSpread || baselineSpread) && (
            <div className="text-[10px] text-gray-500 flex justify-between">
              <span>ปัจจุบัน: {currentSpread || '—'}</span>
              <span>ฐาน: {baselineSpread || '—'}</span>
            </div>
          )}
        </div>

        {/* Volatility State */}
        <div
          data-testid="volatility-state-card"
          className="p-3.5 bg-black/30 rounded-xl border border-white/5 space-y-1.5"
        >
          <span className="text-[10px] uppercase text-gray-400 block">
            สภาวะความผันผวน (Volatility State)
          </span>
          <div className="flex items-center justify-between">
            <strong
              className={`text-sm font-bold ${
                volatilityState === 'NORMAL'
                  ? 'text-emerald-400'
                  : volatilityState === 'ELEVATED'
                  ? 'text-amber-400'
                  : 'text-rose-400 font-black'
              }`}
            >
              {volatilityState}
            </strong>
            <span className="text-gray-300 text-[11px]">
              {label(volatilityState)}
            </span>
          </div>
          <div className="pt-1.5 border-t border-white/5 text-[11px] text-gray-400">
            <span>การกระจายตัวของราคาเทียบค่าเฉลี่ยปกติ</span>
          </div>
        </div>

        {/* Market Source */}
        <div className="p-3.5 bg-black/30 rounded-xl border border-white/5 space-y-1.5 sm:col-span-2 lg:col-span-1">
          <span className="text-[10px] uppercase text-gray-400 block">
            แหล่งข้อมูลตลาด (Market Source)
          </span>
          <strong className="text-sm font-bold text-amber-300 block">
            {sourceMode === 'LIVE' ? 'XAUUSD Real Tick Data' : 'XAUUSD Fixture Data'}
          </strong>
          <div className="pt-1.5 border-t border-white/5 text-[11px] text-gray-400">
            <span>แท่งเทียน M1 ประเมินผลแบบปิดแท่ง (No Incomplete Interpolation)</span>
          </div>
        </div>
      </div>

      {/* 3. Reaction Windows Cards (T+1m, T+5m, T+15m) */}
      <div className="space-y-2">
        <h4 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
          หน้าต่างเวลาสังเกตการณ์ปฏิกิริยาราคา (Reaction Windows)
        </h4>

        {reactionWindows.length === 0 ? (
          <div className="p-4 bg-black/20 rounded-lg border border-white/5 text-center text-xs text-gray-400 font-mono">
            ไม่มีหน้าต่างเวลาที่กำลังประเมิน
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 font-mono">
            {reactionWindows.map((w) => {
              const minutes = Math.round(w.seconds / 60);
              const isReady = w.status === 'READY';
              const isWaiting = w.status === 'WAITING';

              return (
                <div
                  key={w.seconds}
                  data-testid={`reaction-window-${w.seconds}`}
                  className={`p-3.5 rounded-xl border space-y-2.5 flex flex-col justify-between ${
                    isReady
                      ? 'bg-black/40 border-white/10'
                      : 'bg-black/20 border-white/5 opacity-80'
                  }`}
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <span className="text-sm font-bold text-white">
                        T+{minutes} นาที ({w.seconds}s)
                      </span>
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                          isReady
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                            : isWaiting
                            ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                            : 'bg-gray-500/20 text-gray-400 border border-gray-500/30'
                        }`}
                      >
                        {w.status}
                      </span>
                    </div>

                    {isReady ? (
                      <div className="space-y-2 mt-2">
                        {/* Return % & Classification */}
                        <div className="flex items-baseline justify-between">
                          <span className="text-xs text-gray-400">ผลตอบแทน:</span>
                          <strong
                            className={`text-base font-bold ${
                              w.return_percent && Number(w.return_percent) > 0
                                ? 'text-emerald-400'
                                : w.return_percent && Number(w.return_percent) < 0
                                ? 'text-rose-400'
                                : 'text-gray-300'
                            }`}
                          >
                            {w.return_percent != null
                              ? `${Number(w.return_percent) > 0 ? '+' : ''}${numeric(
                                  w.return_percent
                                )}%`
                              : '—'}
                          </strong>
                        </div>

                        {w.classification && (
                          <div className="pt-1">
                            {getClassificationBadge(w.classification)}
                          </div>
                        )}

                        {/* Price range & metrics */}
                        <div className="text-[11px] text-gray-300 pt-2 border-t border-white/5 space-y-1">
                          {(w.price_before || w.price_after) && (
                            <div className="flex justify-between text-gray-400">
                              <span>ราคา:</span>
                              <span className="text-white">
                                {w.price_before || '—'} → {w.price_after || '—'}
                              </span>
                            </div>
                          )}
                          {w.move_atr && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">Move ATR:</span>
                              <span className="text-amber-300">{w.move_atr}</span>
                            </div>
                          )}
                          {w.range_atr && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">Range ATR:</span>
                              <span className="text-purple-300">{w.range_atr}</span>
                            </div>
                          )}
                          {w.tick_activity_ratio && (
                            <div className="flex justify-between">
                              <span className="text-gray-400">Tick Ratio:</span>
                              <span className="text-blue-300">{w.tick_activity_ratio}x</span>
                            </div>
                          )}
                        </div>
                      </div>
                    ) : isWaiting ? (
                      <p className="text-xs text-amber-300/80 mt-2">
                        ⏳ กำลังรอแท่งเทียน M1 ปิดครบ {minutes} นาทีหลังเวลาประกาศ
                      </p>
                    ) : (
                      <p className="text-xs text-gray-500 mt-2">
                        ℹ️ ข้อมูลราคายังไม่เพียงพอสำหรับวัดปฏิกิริยา (Reaction Unavailable)
                      </p>
                    )}
                  </div>

                  <span className="text-[10px] text-gray-500 pt-1 border-t border-white/5 block">
                    Cutoff: {w.cutoff ? w.cutoff.slice(11, 19) + ' UTC' : '—'}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* 4. Semantic Disclaimers */}
      <div className="p-3.5 bg-black/30 rounded-xl border border-white/5 text-xs text-gray-400 font-mono space-y-1">
        <p className="text-gray-300 font-semibold">
          ⚖️ ข้อสังเกตเชิงสถิติ (Correlation vs Causation):
        </p>
        <p>
          ปฏิกิริยาราคาที่สังเกตได้หลังช่วงประกาศเป็นผลการเคลื่อนไหวเชิงประจักษ์ของตลาด (Observed Market Reaction)
          <strong className="text-gray-200"> ไม่ได้พิสูจน์ความสัมพันธ์เชิงสาเหตุว่าข่าวเป็นปัจจัยเดียวที่ทำให้ราคาเคลื่อนไหว</strong>
        </p>
        {sourceMode === 'FIXTURE' && (
          <p className="text-amber-400/90 pt-1 border-t border-white/5">
            * ชุดข้อมูลนี้ทำงานในโหมด FIXTURE / DEMO — ปฏิกิริยาราคาในชุดสาธิตไม่ได้สะท้อนหรือพิสูจน์ผลกระทบจากข่าวจริงในตลาด
          </p>
        )}
      </div>
    </div>
  );
}
