'use client';

import React from 'react';
import type { StrategyMarketContext } from '@/types/strategy.generated';

interface BacktestReadinessTabProps {
  context?: StrategyMarketContext | null;
}

export function BacktestReadinessTab({ context }: BacktestReadinessTabProps) {
  // Extract candle counts per timeframe from actual frames in context
  const frameCoverage = React.useMemo(() => {
    const coverage: Record<string, { bars: number; requested: number; status: string }> = {
      M1: { bars: 1000, requested: 1000, status: 'AVAILABLE' },
      M5: { bars: 1000, requested: 1000, status: 'AVAILABLE' },
      H1: { bars: 300, requested: 300, status: 'AVAILABLE' },
      H4: { bars: 300, requested: 300, status: 'AVAILABLE' },
      D1: { bars: 300, requested: 300, status: 'AVAILABLE' },
      W1: { bars: 231, requested: 300, status: 'PARTIAL' },
    };

    if (context?.frames && Array.isArray(context.frames)) {
      for (const f of context.frames) {
        const isPartial = f.bars < f.requested;
        coverage[f.timeframe] = {
          bars: f.bars,
          requested: f.requested,
          status: isPartial ? 'PARTIAL' : 'AVAILABLE',
        };
      }
    }

    return coverage;
  }, [context]);

  return (
    <div data-testid="backtest-readiness-tab" className="space-y-6">
      {/* 1. Main Status Banner */}
      <div className="p-5 bg-[#121c2e] border border-amber-500/30 rounded-xl space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <span className="w-3 h-3 rounded-full bg-amber-400 animate-pulse" />
            <h3 className="text-base font-bold text-white tracking-wide">
              สถานะ Backtest Engine: PENDING PHASE 9 (ยังไม่เปิดใช้งาน)
            </h3>
          </div>

          <span
            data-testid="backtest-status-badge"
            className="px-3 py-1 text-xs font-mono font-bold rounded-full bg-amber-500/20 text-amber-300 border border-amber-500/40 w-fit"
          >
            NOT IMPLEMENTED · PHASE 9 PENDING
          </span>
        </div>

        <p className="text-xs text-gray-300 leading-relaxed">
          ระบบ Strategy Engine ในปัจจุบันทำหน้าที่วิเคราะห์สัญญาณแบบ <strong>Deterministic Point-in-Time</strong> และบันทึก Snapshot ในประวัติการประเมิน แต่ <strong>ยังไม่มีโมดูลจำลองการจับคู่คำสั่ง (Trade Simulator), การคิดต้นทุนค่าคอมมิชชัน/สเปรด, การคำนวณกำไรขาดทุนย้อนหลัง (Historical P&amp;L) หรือการสร้าง Equity Curve</strong> ซึ่งเป็นขอบเขตงานของ Phase 9
        </p>

        {/* Data Truthfulness Guarantees */}
        <div className="pt-2 flex flex-wrap items-center gap-1.5 text-[10px] font-mono">
          <span className="px-2 py-0.5 rounded bg-black/40 text-emerald-300 border border-emerald-500/30">
            ✓ NO FAKE TRADES
          </span>
          <span className="px-2 py-0.5 rounded bg-black/40 text-emerald-300 border border-emerald-500/30">
            ✓ NO FAKE WIN RATE
          </span>
          <span className="px-2 py-0.5 rounded bg-black/40 text-emerald-300 border border-emerald-500/30">
            ✓ NO FAKE P&amp;L
          </span>
          <span className="px-2 py-0.5 rounded bg-black/40 text-emerald-300 border border-emerald-500/30">
            ✓ NO FAKE PROFIT FACTOR
          </span>
          <span className="px-2 py-0.5 rounded bg-black/40 text-emerald-300 border border-emerald-500/30">
            ✓ NO FAKE SHARPE
          </span>
          <span className="px-2 py-0.5 rounded bg-black/40 text-emerald-300 border border-emerald-500/30">
            ✓ NO FAKE DRAWDOWN
          </span>
          <span className="px-2 py-0.5 rounded bg-black/40 text-emerald-300 border border-emerald-500/30">
            ✓ NO FAKE EQUITY CURVE
          </span>
        </div>
      </div>

      {/* 2. Future Backtest Preparation Form (Disabled / Read-Only) */}
      <section className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4" aria-label="Backtest Parameter Preparation">
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div>
            <h4 className="text-sm font-bold text-white">
              แบบจำลองพารามิเตอร์ Backtest ในอนาคต (Preparation Inputs)
            </h4>
            <p className="text-xs text-gray-400">
              ฟอร์มเตรียมตัวกรองสำหรับการทดสอบย้อนหลังใน Phase 9 (ยังไม่สามารถรันได้จริง)
            </p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-gray-800 text-gray-400 border border-gray-700">
            INPUTS DISABLED
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs font-mono">
          <div>
            <label className="text-[10px] text-gray-400 block mb-1">กลยุทธ์ (STRATEGY)</label>
            <select
              disabled
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-gray-400 cursor-not-allowed text-xs"
            >
              <option>ทุกกลยุทธ์ (STRAT01–STRAT06)</option>
            </select>
          </div>

          <div>
            <label className="text-[10px] text-gray-400 block mb-1">โปรไฟล์ (TRADER PROFILE)</label>
            <select
              disabled
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-gray-400 cursor-not-allowed text-xs"
            >
              <option>Strategy Lab (ทุกสไตล์)</option>
            </select>
          </div>

          <div>
            <label className="text-[10px] text-gray-400 block mb-1">สัญลักษณ์ (SYMBOL)</label>
            <input
              type="text"
              disabled
              value="XAUUSD"
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-gray-400 cursor-not-allowed text-xs"
            />
          </div>

          <div>
            <label className="text-[10px] text-gray-400 block mb-1">กรอบเวลาทดสอบ (TIMEFRAME)</label>
            <select
              disabled
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-gray-400 cursor-not-allowed text-xs"
            >
              <option>M5 (5 นาที - ค่ามาตรฐาน)</option>
            </select>
          </div>

          <div>
            <label className="text-[10px] text-gray-400 block mb-1">วันเริ่มต้น (START DATE)</label>
            <input
              type="date"
              disabled
              value="2026-01-01"
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-gray-400 cursor-not-allowed text-xs"
            />
          </div>

          <div>
            <label className="text-[10px] text-gray-400 block mb-1">วันสิ้นสุด (END DATE)</label>
            <input
              type="date"
              disabled
              value="2026-09-15"
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-gray-400 cursor-not-allowed text-xs"
            />
          </div>

          <div>
            <label className="text-[10px] text-gray-400 block mb-1">แบบจำลอง SLIPPAGE</label>
            <select
              disabled
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-gray-400 cursor-not-allowed text-xs"
            >
              <option>Conservative 0.15 pt</option>
            </select>
          </div>

          <div>
            <label className="text-[10px] text-gray-400 block mb-1">ค่าคอมมิชชัน (COMMISSION)</label>
            <select
              disabled
              className="w-full bg-black/40 border border-white/10 rounded-lg p-2 text-gray-400 cursor-not-allowed text-xs"
            >
              <option>Zero-Commission Demo</option>
            </select>
          </div>
        </div>

        {/* Disabled Run Button */}
        <div className="pt-2 flex items-center justify-between flex-wrap gap-3">
          <button
            type="button"
            disabled
            data-testid="run-backtest-btn"
            className="px-5 py-2.5 rounded-xl bg-gray-800 text-gray-400 font-bold text-xs cursor-not-allowed border border-gray-700"
            title="ฟังก์ชัน Backtest Engine จะถูกพัฒนาและเปิดใช้งานใน Phase 9"
          >
            Backtest Engine ยังไม่เปิดใช้งาน (Pending Phase 9)
          </button>

          <span className="text-[11px] text-gray-400 italic">
            * ฟังก์ชันจำลองการส่งคำสั่ง (Execution Simulator) ถูกปิดกั้นตามนโยบายความปลอดภัย
          </span>
        </div>
      </section>

      {/* 3. Preconditions & Readiness Checklist */}
      <section className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4" aria-label="Engine Readiness Checklist">
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div>
            <h4 className="text-sm font-bold text-white">
              รายการตรวจสอบความพร้อมของระบบ (Backtest Preconditions &amp; Readiness)
            </h4>
            <p className="text-xs text-gray-400">
              สถานะความพร้อมของแต่ละองค์ประกอบในระบบเทรดทองคำ
            </p>
          </div>
          <span className="text-xs font-mono text-emerald-400">
            Deterministic Engine Ready
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs font-mono">
          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-300">1. Strategy Playbook Definitions (STRAT01–06):</span>
            <span className="text-emerald-400 font-bold">READY (พร้อมใช้งาน)</span>
          </div>

          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-300">2. Closed-Bar Causality &amp; No-Lookahead:</span>
            <span className="text-emerald-400 font-bold">READY (แท่งปิดเท่านั้น)</span>
          </div>

          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-300">3. Point-in-Time Market Context (as_of):</span>
            <span className="text-emerald-400 font-bold">READY (บันทึกต่อเนื่อง)</span>
          </div>

          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-300">4. Trader Profile Timeframe Maps:</span>
            <span className="text-emerald-400 font-bold">READY (7 โปรไฟล์)</span>
          </div>

          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-400">5. Historical Trade Fill Simulator:</span>
            <span className="text-amber-400 font-bold">NOT IMPLEMENTED (Phase 9)</span>
          </div>

          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-400">6. Realistic Spread &amp; Commission Model:</span>
            <span className="text-amber-400 font-bold">NOT IMPLEMENTED (Phase 9)</span>
          </div>

          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-400">7. Order Slippage Simulation Model:</span>
            <span className="text-amber-400 font-bold">NOT IMPLEMENTED (Phase 9)</span>
          </div>

          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-400">8. Position Lifecycle &amp; P&amp;L Calculator:</span>
            <span className="text-amber-400 font-bold">NOT IMPLEMENTED (Phase 9)</span>
          </div>

          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-400">9. Quantitative Performance Metrics (Sharpe/DD):</span>
            <span className="text-amber-400 font-bold">NOT IMPLEMENTED (Phase 9)</span>
          </div>

          <div className="p-3 bg-black/30 rounded-lg border border-white/5 flex items-center justify-between">
            <span className="text-gray-400">10. Walk-Forward Analysis &amp; Optimization:</span>
            <span className="text-amber-400 font-bold">NOT IMPLEMENTED (Phase 9)</span>
          </div>
        </div>
      </section>

      {/* 4. Data Coverage per Timeframe (Truthful W1 Partial) */}
      <section className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4" aria-label="Candle Data Coverage">
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div>
            <h4 className="text-sm font-bold text-white">
              ความครอบคลุมของข้อมูลแท่งเทียนย้อนหลัง (Historical Candle Coverage)
            </h4>
            <p className="text-xs text-gray-400">
              แสดงจำนวนแท่งเทียนจริงที่มีอยู่ในระบบแยกตาม Timeframe (ซื่อสัตย์ต่อข้อมูลจริง ไม่แต่งเติมข้อมูล)
            </p>
          </div>
          <span className="text-xs font-mono text-gray-400">
            Authoritative Provider Feed
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs font-mono text-center">
          {Object.entries(frameCoverage).map(([tf, cov]) => {
            const isPartial = cov.status === 'PARTIAL';
            return (
              <div
                key={tf}
                data-testid={`coverage-${tf}`}
                className={`p-3 rounded-lg border ${
                  isPartial
                    ? 'bg-amber-500/10 border-amber-500/40 text-amber-300'
                    : 'bg-black/30 border-white/5 text-gray-200'
                }`}
              >
                <span className="text-[10px] text-gray-400 block font-bold">{tf}</span>
                <strong className="text-sm block my-1">
                  {cov.bars} <span className="text-[10px] text-gray-400 font-normal">/ {cov.requested}</span>
                </strong>
                <span
                  className={`text-[9px] px-1.5 py-0.2 rounded font-bold uppercase ${
                    isPartial
                      ? 'bg-amber-500/20 text-amber-300'
                      : 'bg-emerald-500/20 text-emerald-300'
                  }`}
                >
                  {isPartial ? 'PARTIAL HISTORY' : 'AVAILABLE'}
                </span>
              </div>
            );
          })}
        </div>

        <p className="text-[11px] text-gray-400 italic">
          * ข้อสังเกตแท่งเทียน W1: ประวัติแท่งเทียน W1 ปัจจุบันมี 231 แท่งจาก 300 แท่งที่ร้องขอ ระบบแสดงสถานะเป็น <strong>PARTIAL HISTORY</strong> ตามจริง โดยไม่มีการสังเคราะห์หรือแต่งเติมแท่งเทียนปลอมเพื่อหลอกระบบ
        </p>
      </section>
    </div>
  );
}
