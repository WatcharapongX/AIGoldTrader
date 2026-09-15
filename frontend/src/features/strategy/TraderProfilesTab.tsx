'use client';

import React from 'react';
import type { StrategyDefinition, TraderProfile } from '@/types/strategy.generated';
import { label } from './thai';

interface TraderProfilesTabProps {
  profiles: TraderProfile[];
  loading: boolean;
  error: string | null;
  strategies: StrategyDefinition[];
}

export function TraderProfilesTab({
  profiles,
  loading,
  error,
  strategies,
}: TraderProfilesTabProps) {
  if (loading) {
    return (
      <div data-testid="profiles-loading" className="p-8 text-center text-gray-400 text-sm space-y-2">
        <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto" />
        <p>กำลังโหลดโปรไฟล์ผู้เทรด (Loading Trader Profiles)...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="profiles-error" className="p-6 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-sm">
        <p className="font-bold">เกิดข้อผิดพลาดในการโหลดโปรไฟล์ผู้เทรด:</p>
        <p className="text-xs mt-1 text-rose-400 font-mono">{error}</p>
      </div>
    );
  }

  return (
    <div data-testid="trader-profiles-tab" className="space-y-6">
      {/* 1. Header Information */}
      <div className="p-4 bg-[#0e1726] border border-gray-800 rounded-xl space-y-2">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            โปรไฟล์ผู้เทรดที่กำหนดค่าไว้ ({profiles.length} Trader Profiles)
          </h3>
          <span className="px-2.5 py-0.5 text-xs font-mono font-bold rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
            ISOLATED MULTI-PROFILE EVALUATION
          </span>
        </div>
        <p className="text-xs text-gray-300 leading-relaxed">
          แต่ละโปรไฟล์ผู้เทรดมีแผนภูมิ Timeframe Mapping ที่แยกอิสระจากกันเพื่อจำกัดกรอบเวลาและกลยุทธ์ที่ได้รับอนุญาต (Allowed Strategies) ทำให้สามารถเปรียบเทียบผลการประเมินได้หลายมุมมองพร้อมกันโดยไม่ส่งผลกระทบซึ่งกันและกัน
        </p>
      </div>

      {/* 2. Profiles Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {profiles.map((profile) => {
          const tfMap = profile.timeframe_map;

          return (
            <div
              key={profile.id}
              data-testid={`profile-card-${profile.id}`}
              className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4 flex flex-col justify-between hover:border-gray-700 transition-colors"
            >
              <div className="space-y-3">
                {/* Top Row: Name + Style */}
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <h4 className="text-base font-bold text-white tracking-wide">
                      {profile.name}
                    </h4>
                    <span className="text-xs font-mono text-gray-400 block mt-0.5">
                      ID: {profile.id}
                    </span>
                  </div>

                  <span className="px-2 py-0.5 text-[11px] font-mono font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/40 shrink-0">
                    {label(profile.style)}
                  </span>
                </div>

                {/* Description */}
                <p className="text-xs text-gray-300 leading-relaxed bg-black/20 p-2.5 rounded-lg border border-white/5">
                  {profile.description_th}
                </p>

                {/* Allowed Strategies */}
                <div className="space-y-1.5">
                  <span className="text-[10px] text-gray-400 uppercase font-semibold block">
                    กลยุทธ์ที่ได้รับอนุญาต (Allowed Strategies):
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {profile.allowed_strategies.map((stratId) => {
                      const strat = strategies.find((s) => s.id === stratId);
                      return (
                        <span
                          key={stratId}
                          className="px-2 py-0.5 text-[10px] font-mono rounded bg-white/5 text-gray-200 border border-white/10"
                          title={strat?.name}
                        >
                          {stratId}
                        </span>
                      );
                    })}
                  </div>
                </div>

                {/* Timeframe Map Details */}
                {tfMap && (
                  <div className="space-y-1.5 pt-1">
                    <span className="text-[10px] text-gray-400 uppercase font-semibold block">
                      ผังกรอบเวลา (Timeframe Mapping):
                    </span>
                    <div className="grid grid-cols-4 gap-1.5 text-center text-xs font-mono">
                      <div className="p-2 bg-black/30 rounded border border-white/5">
                        <span className="text-[9px] text-gray-400 block">CONTEXT</span>
                        <strong className="text-amber-400">{tfMap.context}</strong>
                      </div>
                      <div className="p-2 bg-black/30 rounded border border-white/5">
                        <span className="text-[9px] text-gray-400 block">BIAS</span>
                        <strong className="text-blue-400">{tfMap.bias}</strong>
                      </div>
                      <div className="p-2 bg-black/30 rounded border border-white/5">
                        <span className="text-[9px] text-gray-400 block">SETUP</span>
                        <strong className="text-purple-400">{tfMap.setup}</strong>
                      </div>
                      <div className="p-2 bg-black/30 rounded border border-white/5">
                        <span className="text-[9px] text-gray-400 block">TRIGGER</span>
                        <strong className="text-emerald-400">{tfMap.trigger}</strong>
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* Footer Row */}
              <div className="pt-3 border-t border-gray-800/80 flex items-center justify-between text-[11px] text-gray-400 font-mono">
                <span className="text-emerald-400 font-semibold">● ACTIVE</span>
                <span>Min Bars: {tfMap?.minimum_bars || 60}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* 3. Timeframe Map Reference Table */}
      <section className="space-y-3" aria-label="Timeframe Reference Matrix">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            ตารางเปรียบเทียบกรอบเวลาตามสไตล์ (Timeframe Mapping by Style)
          </h3>
          <span className="text-xs text-gray-400">
            ลำดับชั้นการส่งต่อข้อมูล (Context → Bias → Setup → Trigger)
          </span>
        </div>

        <div className="overflow-x-auto rounded-xl border border-gray-800 bg-[#0e1726]">
          <table className="w-full text-left text-xs font-mono">
            <thead className="bg-[#121c2e] text-gray-300 uppercase border-b border-gray-800">
              <tr>
                <th className="p-3">สไตล์การเทรด (Style)</th>
                <th className="p-3">บริบทหลัก (Context TF)</th>
                <th className="p-3">ทิศทางเอียง (Bias TF)</th>
                <th className="p-3">ค้นหาเงื่อนไข (Setup TF)</th>
                <th className="p-3">จุดยืนยันเข้า (Trigger TF)</th>
                <th className="p-3 text-right">จำนวนแท่งขั้นต่ำ (Min Bars)</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60 text-gray-300">
              <tr className="hover:bg-white/5 transition-colors">
                <td className="p-3 font-bold text-amber-300">SCALP (เก็งกำไรสั้น)</td>
                <td className="p-3 text-white">H1 (1 ชั่วโมง)</td>
                <td className="p-3 text-blue-300">M15 (15 นาที)</td>
                <td className="p-3 text-purple-300">M5 (5 นาที)</td>
                <td className="p-3 text-emerald-400 font-bold">M1 (1 นาที)</td>
                <td className="p-3 text-right">60 bars</td>
              </tr>
              <tr className="hover:bg-white/5 transition-colors">
                <td className="p-3 font-bold text-amber-300">DAY_TRADE (ภายในวัน)</td>
                <td className="p-3 text-white">H4 (4 ชั่วโมง)</td>
                <td className="p-3 text-blue-300">H1 (1 ชั่วโมง)</td>
                <td className="p-3 text-purple-300">M15 (15 นาที)</td>
                <td className="p-3 text-emerald-400 font-bold">M5 (5 นาที)</td>
                <td className="p-3 text-right">60 bars</td>
              </tr>
              <tr className="hover:bg-white/5 transition-colors">
                <td className="p-3 font-bold text-amber-300">SWING (รอบระยะกลาง)</td>
                <td className="p-3 text-white">W1 (รายสัปดาห์)</td>
                <td className="p-3 text-blue-300">D1 (รายวัน)</td>
                <td className="p-3 text-purple-300">H4 (4 ชั่วโมง)</td>
                <td className="p-3 text-emerald-400 font-bold">H1 (1 ชั่วโมง)</td>
                <td className="p-3 text-right">60 bars</td>
              </tr>
              <tr className="hover:bg-white/5 transition-colors">
                <td className="p-3 font-bold text-amber-300">RUN_TREND (ตามแนวโน้มใหญ่)</td>
                <td className="p-3 text-white">D1 (รายวัน)</td>
                <td className="p-3 text-blue-300">H4 (4 ชั่วโมง)</td>
                <td className="p-3 text-purple-300">H1 (1 ชั่วโมง)</td>
                <td className="p-3 text-emerald-400 font-bold">M15 (15 นาที)</td>
                <td className="p-3 text-right">60 bars</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
