'use client';

import React, { useMemo } from 'react';
import type { StrategyDefinition } from '@/types/strategy.generated';
import { label } from './thai';

interface StrategyCatalogTabProps {
  strategies: StrategyDefinition[];
  loading: boolean;
  error: string | null;
  strategyConfigJson?: string | null;
}

export function StrategyCatalogTab({
  strategies,
  loading,
  error,
  strategyConfigJson,
}: StrategyCatalogTabProps) {
  // Parse safe read-only config parameters if available
  const parsedConfig = useMemo(() => {
    if (!strategyConfigJson) return null;
    try {
      return JSON.parse(strategyConfigJson);
    } catch {
      return null;
    }
  }, [strategyConfigJson]);

  if (loading) {
    return (
      <div data-testid="catalog-loading" className="p-8 text-center text-gray-400 text-sm space-y-2">
        <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p>กำลังโหลดแคตตาล็อกกลยุทธ์ (Loading Strategy Catalog)...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="catalog-error" className="p-6 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-sm">
        <p className="font-bold">เกิดข้อผิดพลาดในการโหลดกลยุทธ์:</p>
        <p className="text-xs mt-1 text-rose-400 font-mono">{error}</p>
      </div>
    );
  }

  return (
    <div data-testid="strategy-catalog-tab" className="space-y-6">
      {/* 1. Header & News Dependency Callout */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Market-Driven Playbooks Callout */}
        <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-xl space-y-2">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
            <h4 className="text-sm font-bold text-emerald-300">
              STRAT01–STRAT04: Market-Driven Playbooks
            </h4>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            ขับเคลื่อนด้วยโครงสร้างราคาเชิงเทคนิค (SMC, Trend Continuation, Breakout Retest, Mean Reversion) และอินดิเคเตอร์เชิงปริมาณ
            <strong className="text-emerald-400 block mt-1">
              * ทิศทางและคะแนน Setup Evidence ไม่อิงตามข่าวปฏิทินเศรษฐกิจ (Independent of Macro News)
            </strong>
          </p>
        </div>

        {/* News-Aware Playbooks Callout */}
        <div className="p-4 bg-amber-500/10 border border-amber-500/30 rounded-xl space-y-2">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400" />
            <h4 className="text-sm font-bold text-amber-300">
              STRAT05–STRAT06: News-Aware Playbooks
            </h4>
          </div>
          <p className="text-xs text-gray-300 leading-relaxed">
            ออกแบบมาสำหรับสภาวะหลังการประกาศตัวเลขเศรษฐกิจจริง (Post-Release Actuals)
            <strong className="text-amber-400 block mt-1">
              * ต้องใช้ข้อมูลตัวเลขจริงที่เผยแพร่แล้ว + ทิศทาง Macro Alignment + ตรวจสอบ Spread ป้องกันความผันผวน
            </strong>
          </p>
        </div>
      </div>

      {/* 2. Strategy Catalog Cards Grid */}
      <section className="space-y-3" aria-label="Strategy Cards">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            แคตตาล็อกกลยุทธ์ทั้งหมด ({strategies.length} Strategies)
          </h3>
          <span className="text-xs text-gray-400 font-mono">
            Deterministic Rule-Based Playbooks
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {strategies.map((strat) => {
            const isNewsAware = strat.id === 'STRAT05' || strat.id === 'STRAT06';

            return (
              <div
                key={strat.id}
                data-testid={`strategy-card-${strat.id}`}
                className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4 flex flex-col justify-between hover:border-gray-700 transition-colors"
              >
                <div className="space-y-3">
                  {/* Top Bar: ID + Version + News Badge */}
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="px-2.5 py-1 text-xs font-mono font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                        {strat.id}
                      </span>
                      <span className="text-[10px] font-mono text-gray-400">
                        {strat.version || 'v1.2.1'}
                      </span>
                    </div>

                    <span
                      className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded border ${
                        isNewsAware
                          ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                          : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
                      }`}
                    >
                      {isNewsAware ? 'NEWS-AWARE' : 'MARKET-DRIVEN'}
                    </span>
                  </div>

                  {/* Name & Category */}
                  <div>
                    <h4 className="text-base font-bold text-white tracking-wide">
                      {strat.name}
                    </h4>
                    <span className="text-xs font-mono text-gray-400 block mt-0.5">
                      หมวด: {strat.category}
                    </span>
                  </div>

                  {/* Thai Description */}
                  <p className="text-xs text-gray-300 leading-relaxed bg-black/20 p-2.5 rounded-lg border border-white/5">
                    {strat.description_th}
                  </p>

                  {/* Supported Styles */}
                  <div className="space-y-1.5">
                    <span className="text-[10px] text-gray-400 uppercase font-semibold block">
                      รูปแบบการเทรดที่รองรับ (Supported Styles):
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {strat.styles.map((style) => (
                        <span
                          key={style}
                          className="px-2 py-0.5 text-[10px] font-mono rounded bg-white/5 text-gray-300 border border-white/10"
                        >
                          {label(style)}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Required Context */}
                  <div className="space-y-1.5">
                    <span className="text-[10px] text-gray-400 uppercase font-semibold block">
                      บริบทที่ต้องใช้ (Required Context):
                    </span>
                    <div className="flex flex-wrap gap-1">
                      {strat.required_context.map((ctx) => (
                        <span
                          key={ctx}
                          className="px-1.5 py-0.5 text-[10px] font-mono rounded bg-black/40 text-gray-400 border border-white/5"
                        >
                          {ctx}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {/* Footer Bar */}
                <div className="pt-3 border-t border-gray-800/80 flex items-center justify-between text-[11px] text-gray-400 font-mono">
                  <span>สถานะ: พร้อมใช้งาน</span>
                  <span>Deterministic Only</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* 3. Comparison Matrix */}
      <section className="space-y-3" aria-label="Strategy Comparison Matrix">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            ตารางเปรียบเทียบกลยุทธ์ (Strategy Comparison Matrix)
          </h3>
          <span className="text-xs text-gray-400">
            วิเคราะห์ความแตกต่างของเงื่อนไขและบริบทตลาด
          </span>
        </div>

        <div className="overflow-x-auto rounded-xl border border-gray-800 bg-[#0e1726]">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-[#121c2e] text-gray-300 uppercase border-b border-gray-800">
              <tr>
                <th className="p-3">รหัส (ID)</th>
                <th className="p-3">ชื่อกลยุทธ์</th>
                <th className="p-3">หมวดหมู่ (Category)</th>
                <th className="p-3">การพึ่งพาข่าว (News)</th>
                <th className="p-3">บริบทบังคับ (Required Context)</th>
                <th className="p-3">สไตล์ที่รองรับ</th>
                <th className="p-3 text-right">สถานะ</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60 text-gray-300">
              {strategies.map((strat) => {
                const isNewsAware = strat.id === 'STRAT05' || strat.id === 'STRAT06';
                return (
                  <tr key={strat.id} className="hover:bg-white/5 transition-colors">
                    <td className="p-3 font-bold text-amber-300">{strat.id}</td>
                    <td className="p-3 font-semibold text-white">{strat.name}</td>
                    <td className="p-3 text-gray-400">{strat.category}</td>
                    <td className="p-3">
                      <span
                        className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                          isNewsAware
                            ? 'bg-amber-500/20 text-amber-300'
                            : 'bg-emerald-500/20 text-emerald-300'
                        }`}
                      >
                        {isNewsAware ? 'NEWS-AWARE' : 'MARKET-DRIVEN'}
                      </span>
                    </td>
                    <td className="p-3 text-gray-400 max-w-xs truncate">
                      {strat.required_context.join(', ')}
                    </td>
                    <td className="p-3 text-gray-400">
                      {strat.styles.map((s) => label(s)).join(', ')}
                    </td>
                    <td className="p-3 text-right">
                      <span className="text-emerald-400 font-bold">READY</span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* 4. Safe Read-Only Strategy Configuration Parameters */}
      <section className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4" aria-label="Strategy Parameters">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800 pb-3">
          <div>
            <h4 className="text-sm font-bold text-white">
              พารามิเตอร์ของระบบกลยุทธ์ (Configured Strategy Parameters)
            </h4>
            <p className="text-xs text-gray-400">
              ค่าเกณฑ์การตัดสินใจแบบ Deterministic ที่บันทึกอยู่ในระบบ (Read-Only)
            </p>
          </div>
          <span className="px-2.5 py-1 text-xs font-mono font-semibold rounded bg-gray-800 text-gray-300 border border-gray-700">
            READ-ONLY · SETTINGS CONTROLLED
          </span>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
          <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-1">
            <span className="text-gray-400 text-[10px] block">MINIMUM RR RATIO</span>
            <strong className="text-emerald-400 text-sm">
              {parsedConfig?.minimum_rr || '1.50'}
            </strong>
          </div>
          <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-1">
            <span className="text-gray-400 text-[10px] block">TOLERANCE ATR</span>
            <strong className="text-amber-300 text-sm">
              {parsedConfig?.tolerance_atr || '0.15'}
            </strong>
          </div>
          <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-1">
            <span className="text-gray-400 text-[10px] block">STOP ATR BUFFER</span>
            <strong className="text-rose-400 text-sm">
              {parsedConfig?.stop_atr_buffer || '0.20'}
            </strong>
          </div>
          <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-1">
            <span className="text-gray-400 text-[10px] block">EXPIRY TRIGGER BARS</span>
            <strong className="text-gray-200 text-sm">
              {parsedConfig?.expiry_trigger_bars || 12} bars
            </strong>
          </div>

          <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-1">
            <span className="text-gray-400 text-[10px] block">EVENT LOOKBACK BARS</span>
            <strong className="text-gray-200 text-sm">
              {parsedConfig?.event_lookback_bars || 24} bars
            </strong>
          </div>
          <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-1">
            <span className="text-gray-400 text-[10px] block">PATTERN LOOKBACK</span>
            <strong className="text-gray-200 text-sm">
              {parsedConfig?.pattern_lookback_bars || 100} bars
            </strong>
          </div>
          <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-1">
            <span className="text-gray-400 text-[10px] block">MACD PARAMETERS</span>
            <strong className="text-blue-300 text-sm">
              {parsedConfig ? `${parsedConfig.macd_fast} / ${parsedConfig.macd_slow} / ${parsedConfig.macd_signal}` : '12 / 26 / 9'}
            </strong>
          </div>
          <div className="p-3 bg-black/40 rounded-lg border border-white/5 space-y-1">
            <span className="text-gray-400 text-[10px] block">STOCHASTIC PERIOD</span>
            <strong className="text-purple-300 text-sm">
              {parsedConfig ? `${parsedConfig.stochastic_period} / ${parsedConfig.stochastic_smooth}` : '14 / 3'}
            </strong>
          </div>
        </div>

        <p className="text-[11px] text-gray-400 italic">
          * หมายเหตุ: พารามิเตอร์เหล่านี้ถูกอ่านจากสัญญา StrategyConfig ใน Backend ไม่อนุญาตให้แก้ไขในหน้านี้ การจัดการพารามิเตอร์จะอยู่ที่หน้า Settings (FC-10)
        </p>
      </section>
    </div>
  );
}
