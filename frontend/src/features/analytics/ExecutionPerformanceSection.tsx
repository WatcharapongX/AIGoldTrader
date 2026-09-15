'use client';

import React from 'react';

export function ExecutionPerformanceSection() {
  const unavailableMetrics = [
    { key: 'Total Executed Trades', labelTh: 'จำนวนไม้ที่เปิดเทรดจริง', value: 'NOT AVAILABLE', reason: 'ไม่มีชุดข้อมูลการจับคู่คำสั่งซื้อขาย' },
    { key: 'Win Rate', labelTh: 'อัตราการชนะ (Win Rate)', value: 'NOT AVAILABLE', reason: 'ไม่สามารถคำนวณได้เมื่อไม่มีประวัติเทรด' },
    { key: 'Net P&L', labelTh: 'กำไรขาดทุนสุทธิจากการเทรด', value: 'NOT AVAILABLE', reason: 'ยังไม่มี Realized P&L จากการปิด Position' },
    { key: 'Profit Factor', labelTh: 'อัตราส่วนกำไรต่อขาดทุน', value: 'NOT AVAILABLE', reason: 'ต้องการผลรวม Gross Profit และ Gross Loss' },
    { key: 'Expectancy', labelTh: 'ค่าความหวังผลต่อไม้ (Expectancy)', value: 'NOT AVAILABLE', reason: 'ต้องการ Average Win / Loss จากผลเทรดจริง' },
    { key: 'Average RR Realized', labelTh: 'อัตราส่วนผลตอบแทนต่อความเสี่ยงจริง', value: 'NOT AVAILABLE', reason: 'ยังไม่มี Exit Price จริงจากการปิดออเดอร์' },
    { key: 'Maximum Drawdown', labelTh: 'ผลขาดทุนสะสมสูงสุด (Max Drawdown)', value: 'NOT AVAILABLE', reason: 'ต้องการ Time-series Equity Curve ประวัติศาสตร์' },
    { key: 'Sharpe Ratio', labelTh: 'อัตราส่วนผลตอบแทนต่อความเสี่ยงชาร์ป', value: 'NOT AVAILABLE', reason: 'ต้องการการกระจายตัวของผลตอบแทนรายวัน' },
    { key: 'Equity Curve', labelTh: 'เส้นกราฟการเติบโตของพอร์ต', value: 'NOT AVAILABLE', reason: 'ยังไม่มีฐานข้อมูลบันทึกยอด Equity ย้อนหลัง' },
    { key: 'Monthly P&L', labelTh: 'ผลการดำเนินงานรายเดือน', value: 'NOT AVAILABLE', reason: 'ยังไม่มีข้อมูลการปิดบัญชีรายเดือน' },
  ];

  return (
    <div className="bg-[#0f172a] border border-slate-800 rounded-xl p-5 shadow-lg space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-slate-800 gap-2">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
              <span>EXECUTED TRADING PERFORMANCE</span>
              <span className="text-xs font-normal text-rose-400 font-mono">
                (NOT AVAILABLE)
              </span>
            </h2>
            <p className="text-xs text-gray-400">
              ตัวชี้วัดผลการดำเนินงานจากการจับคู่คำสั่งซื้อขายจริง (Realized Trading Results)
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="px-3 py-1 rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30 text-xs font-bold">
            DATASET: NOT AVAILABLE
          </span>
        </div>
      </div>

      {/* Critical Explanation Banner */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-rose-950/40 to-slate-900 border border-rose-900/40 text-xs text-rose-200/90 leading-relaxed space-y-2">
        <div className="flex items-center gap-2 font-bold text-rose-300">
          <svg className="w-4 h-4 text-rose-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
          <span>เหตุผลที่ผลการเทรดยังไม่สามารถแสดงผลได้ (System Boundaries):</span>
        </div>
        <ul className="list-disc list-inside space-y-1 text-slate-300 pl-1 text-[11px]">
          <li><strong>Broker Execution:</strong> ถูกปิดการใช้งาน (DISABLED) ในสถาปัตยกรรมปัจจุบัน</li>
          <li><strong>Paper Orders:</strong> เครื่องยนต์จำลองการจับคู่คำสั่ง Order Execution (Phase 7) ยังไม่เริ่มพัฒนา</li>
          <li><strong>Position Lifecycle:</strong> ระบบบริหารจัดการวงจรชีวิต Open / Close Positions ยังไม่มีในระบบ</li>
          <li><strong>Trade Journal:</strong> ระบบบันทึกการเทรดที่ปิดแล้วยังไม่ได้รับการติดตั้ง</li>
        </ul>
        <div className="text-[11px] text-amber-400 pt-1 border-t border-rose-900/40">
          *ระบบจะไม่แสดงค่า 0 หรือ 0% เป็นตัวแทนคำนวณผลตอบแทน เนื่องจากไม่มีชุดข้อมูลการเทรดจริง การแสดงค่า 0 จะทำให้เกิดความเข้าใจผิดว่าระบบเทรดแพ้ทั้งหมดหรือมีกำไรเป็นศูนย์
        </div>
      </div>

      {/* Unavailable Metrics Matrix */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {unavailableMetrics.map((m) => (
          <div
            key={m.key}
            className="p-3.5 rounded-lg bg-slate-950/60 border border-slate-800 flex flex-col justify-between"
          >
            <div>
              <div className="text-xs font-semibold text-gray-300">{m.key}</div>
              <div className="text-[11px] text-gray-400">{m.labelTh}</div>
            </div>
            <div className="my-2.5">
              <span className="px-2 py-0.5 rounded text-xs font-mono font-bold bg-rose-500/10 text-rose-400 border border-rose-500/20">
                {m.value}
              </span>
            </div>
            <div className="text-[10px] text-slate-400 border-t border-slate-900 pt-1.5 line-clamp-2">
              {m.reason}
            </div>
          </div>
        ))}
      </div>

      {/* Equity Curve Placeholder */}
      <div className="p-6 rounded-lg bg-slate-950/40 border border-dashed border-slate-800 text-center">
        <div className="w-10 h-10 rounded-full bg-slate-900 text-gray-400 flex items-center justify-center mx-auto mb-2">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
          </svg>
        </div>
        <h4 className="text-xs font-bold text-gray-300 uppercase tracking-wider">
          Equity Curve Visualization: NOT AVAILABLE
        </h4>
        <p className="text-[11px] text-gray-400 max-w-lg mx-auto mt-1">
          ระบบไม่สร้างกราฟ Equity Curve จำลองขึ้นมาเองจากยอดเงินปัจจุบันหรือเวลาของ Candidate เนื่องจากเส้นกราฟจริงต้องถูกคำนวณจากประวัติยอดเงินสะสมรายวันของพอร์ตที่เกิดการเทรดจริงเท่านั้น
        </p>
      </div>
    </div>
  );
}
