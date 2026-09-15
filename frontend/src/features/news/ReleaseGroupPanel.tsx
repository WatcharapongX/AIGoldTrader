'use client';

import React from 'react';
import Link from 'next/link';
import type { EconomicEvent, EventRelevance, ReleaseGroup } from '@/types/news.generated';
import { bangkok, eventName, label, numeric } from './thai';

interface ReleaseGroupPanelProps {
  activeGroup: ReleaseGroup | null;
  events: EconomicEvent[];
  activeEventId?: string | null;
  xauusdRelevance?: Record<string, EventRelevance>;
  upcomingEvents?: EconomicEvent[];
  onSelectEvent?: (id: string) => void;
}

export function ReleaseGroupPanel({
  activeGroup,
  events,
  activeEventId,
  xauusdRelevance = {},
  upcomingEvents = [],
  onSelectEvent,
}: ReleaseGroupPanelProps) {
  // If no active group is present
  if (!activeGroup) {
    const nextUpcoming = upcomingEvents[0];
    return (
      <div
        data-testid="no-active-release-group"
        className="p-6 bg-[#0e1726] border border-gray-800 rounded-xl text-center space-y-3"
      >
        <div className="w-10 h-10 mx-auto rounded-full bg-blue-500/10 border border-blue-500/20 flex items-center justify-center text-blue-400 text-lg">
          📋
        </div>
        <h3 className="text-base font-bold text-white font-mono">
          ไม่มีชุดข่าวที่กำลังอยู่ในช่วงประเมิน (No Active Release Group)
        </h3>
        <p className="text-xs text-gray-400 max-w-md mx-auto">
          ขณะนี้ไม่มีข่าวเศรษฐกิจสำคัญที่กำลังอยู่ในช่วงเวลาสังเกตการณ์รอบการประกาศ ข้อมูลสภาวะมหภาคจะอยู่ในโหมดปกติ (Normal Regime)
        </p>

        {nextUpcoming && (
          <div className="pt-2 border-t border-gray-800 text-xs font-mono text-gray-400 flex flex-col sm:flex-row sm:items-center justify-center gap-2">
            <span>ข่าวสำคัญถัดไป:</span>
            <strong className="text-white">{eventName(nextUpcoming)}</strong>
            <span className="text-amber-300">({bangkok(nextUpcoming.scheduled_at)})</span>
            <Link
              href="/calendar"
              className="text-amber-400 hover:text-amber-300 underline font-semibold ml-1"
            >
              ดูใน Economic Calendar →
            </Link>
          </div>
        )}
      </div>
    );
  }

  // Active event in group
  const activeEvent = activeEventId
    ? events.find((e) => e.id === activeEventId)
    : events.find((e) => activeGroup.event_ids.includes(e.id));

  // Alignment badge color
  const alignmentColor =
    activeGroup.alignment === 'ALL_ALIGNED'
      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
      : activeGroup.alignment === 'MOSTLY_ALIGNED'
      ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
      : activeGroup.alignment === 'CONFLICTING'
      ? 'bg-rose-500/20 text-rose-300 border-rose-500/40 font-bold'
      : 'bg-amber-500/20 text-amber-300 border-amber-500/40';

  const groupEvents = events.filter((e) => activeGroup.event_ids.includes(e.id));

  // Check if any surprise reports UNAVAILABLE_NO_DISTRIBUTION
  const hasNoDistribution = activeGroup.surprises.some(
    (s) => s.normalized_method === 'UNAVAILABLE_NO_DISTRIBUTION'
  );

  return (
    <div
      data-testid="active-release-group-panel"
      className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-5"
    >
      {/* 1. Header & Group Metadata */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />
            <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
              ชุดข่าวที่กำลังประเมิน (Active Release Group)
            </h3>
          </div>
          <p className="text-xs text-gray-400 font-mono mt-1">
            กลุ่ม ID: {activeGroup.group_id.slice(0, 8)}… · {activeGroup.event_ids.length} รายการเหตุการณ์
          </p>
        </div>

        {/* Group Badges: Alignment, Completeness, Score */}
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <span
            data-testid="group-alignment-badge"
            className={`px-2.5 py-1 rounded border ${alignmentColor}`}
          >
            {activeGroup.alignment} ({label(activeGroup.alignment)})
          </span>

          <span
            data-testid="group-completeness-badge"
            className={`px-2.5 py-1 rounded border ${
              activeGroup.completeness === 'COMPLETE'
                ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30'
                : 'bg-amber-500/10 text-amber-300 border-amber-500/30'
            }`}
          >
            {activeGroup.completeness} ({label(activeGroup.completeness)})
          </span>

          {activeGroup.score && (
            <span className="px-2.5 py-1 rounded bg-black/40 text-gray-300 border border-white/5">
              Score: {activeGroup.score}
            </span>
          )}
        </div>
      </div>

      {/* 2. Active Event Focus Card */}
      {activeEvent && (
        <div className="p-4 bg-black/30 border border-white/5 rounded-xl space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <div className="flex items-center gap-2">
                <span className="px-2 py-0.5 text-[10px] font-bold font-mono rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                  {label(activeEvent.impact)}
                </span>
                <span className="px-2 py-0.5 text-[10px] font-bold font-mono rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  {activeEvent.currency}
                </span>
                <span className="text-xs text-gray-400 font-mono">
                  หมวด: {label(activeEvent.category)}
                </span>
              </div>
              <h4 className="text-base font-bold text-white mt-1">
                {eventName(activeEvent)}
              </h4>
              <p className="text-xs text-gray-400 font-mono">
                กำหนดประกาศ: {bangkok(activeEvent.scheduled_at)} (Asia/Bangkok) · รับรู้: {bangkok(activeEvent.available_at)}
              </p>
            </div>

            <div className="text-right font-mono text-xs">
              <span className="text-gray-400 block text-[10px]">สถานะข่าว (Status)</span>
              <strong className="text-amber-400 text-sm font-bold">
                {label(activeEvent.status)}
              </strong>
              <span className="text-[10px] text-gray-500 block">รุ่นที่ {activeEvent.revision_version}</span>
            </div>
          </div>

          {/* Actual vs Forecast vs Previous Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 bg-black/40 rounded-lg border border-white/5 text-xs font-mono">
            <div>
              <span className="text-[10px] text-gray-400 block">ผลประกาศจริง (ACTUAL)</span>
              <strong className="text-emerald-400 text-sm sm:text-base">
                {numeric(activeEvent.actual, activeEvent.unit)}
              </strong>
            </div>
            <div>
              <span className="text-[10px] text-gray-400 block">คาดการณ์ (FORECAST)</span>
              <strong className="text-blue-300 text-sm sm:text-base">
                {activeEvent.forecast == null ? '—' : numeric(activeEvent.forecast, activeEvent.unit)}
              </strong>
            </div>
            <div>
              <span className="text-[10px] text-gray-400 block">ครั้งก่อน (PREVIOUS)</span>
              <strong className="text-gray-300 text-sm sm:text-base">
                {activeEvent.previous == null ? '—' : numeric(activeEvent.previous, activeEvent.unit)}
              </strong>
            </div>
            <div>
              <span className="text-[10px] text-gray-400 block">ปรับครั้งก่อน (REVISED)</span>
              <span className="text-amber-300 text-sm sm:text-base">
                {activeEvent.revised_previous == null ? '—' : numeric(activeEvent.revised_previous, activeEvent.unit)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* 3. Surprise Matrix Table */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
            ตารางการวิเคราะห์ความต่างจากคาดการณ์ (Surprise Matrix)
          </h4>
          <span className="text-[10px] font-mono text-gray-400">
            {activeGroup.surprises.length} เหตุการณ์
          </span>
        </div>

        <div className="overflow-x-auto rounded-xl border border-gray-800 bg-black/20">
          <table data-testid="surprise-matrix-table" className="w-full text-left text-xs font-mono">
            <thead className="bg-[#121c2e]/70 text-gray-400 uppercase border-b border-gray-800">
              <tr>
                <th className="p-2.5">เหตุการณ์ (Event)</th>
                <th className="p-2.5 text-right">ผลจริง</th>
                <th className="p-2.5 text-right">คาดการณ์</th>
                <th className="p-2.5 text-right">Raw Surprise</th>
                <th className="p-2.5 text-right">Relative Surprise</th>
                <th className="p-2.5 text-center">ทิศทาง (Direction)</th>
                <th className="p-2.5 text-center">ขนาด (Magnitude)</th>
                <th className="p-2.5 text-center">ผลต่อ USD</th>
                <th className="p-2.5 text-right">ปรับครั้งก่อน (Delta)</th>
                <th className="p-2.5">Reason Code</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60 text-gray-300">
              {activeGroup.surprises.map((s) => {
                const ev = events.find((e) => e.id === s.event_id);
                const evName = ev ? eventName(ev) : s.event_id.slice(0, 8);

                const dirColor =
                  s.direction === 'ABOVE'
                    ? 'text-emerald-400'
                    : s.direction === 'BELOW'
                    ? 'text-rose-400'
                    : 'text-gray-300';

                const usdColor =
                  s.usd_direction === 'POSITIVE'
                    ? 'text-emerald-300 font-bold'
                    : s.usd_direction === 'NEGATIVE'
                    ? 'text-rose-300 font-bold'
                    : 'text-gray-400';

                return (
                  <tr key={s.event_id} className="hover:bg-white/5 transition-colors">
                    <td className="p-2.5 font-semibold text-white whitespace-nowrap">
                      {ev ? (
                        <button
                          type="button"
                          onClick={() => onSelectEvent?.(ev.id)}
                          className="hover:text-amber-300 text-left underline"
                        >
                          {evName}
                        </button>
                      ) : (
                        evName
                      )}
                    </td>
                    <td className="p-2.5 text-right font-bold text-emerald-400 whitespace-nowrap">
                      {ev ? numeric(ev.actual, ev.unit) : '—'}
                    </td>
                    <td className="p-2.5 text-right text-blue-300 whitespace-nowrap">
                      {ev && ev.forecast != null ? numeric(ev.forecast, ev.unit) : '—'}
                    </td>
                    <td className="p-2.5 text-right whitespace-nowrap">
                      {s.raw != null ? s.raw : '—'}
                    </td>
                    <td className="p-2.5 text-right whitespace-nowrap">
                      {s.relative != null ? s.relative : '—'}
                    </td>
                    <td className={`p-2.5 text-center font-bold whitespace-nowrap ${dirColor}`}>
                      {label(s.direction)} ({s.direction})
                    </td>
                    <td className="p-2.5 text-center whitespace-nowrap text-gray-300">
                      {label(s.magnitude)}
                    </td>
                    <td className={`p-2.5 text-center whitespace-nowrap ${usdColor}`}>
                      {label(s.usd_direction)} ({s.usd_direction})
                    </td>
                    <td className="p-2.5 text-right text-amber-300 whitespace-nowrap">
                      {s.revision_delta != null ? s.revision_delta : '—'}
                    </td>
                    <td className="p-2.5 text-[11px] text-gray-400 whitespace-nowrap">
                      {s.reason_code}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Normalization Disclaimer */}
        {hasNoDistribution && (
          <p className="text-[11px] text-gray-500 font-mono italic">
            * ยังไม่มี historical distribution สำหรับ normalization (ระบบรายงานค่าจริงตามตัวเลขประกาศ ไม่สร้างค่า Z-score หรือ percentile สมมุติ)
          </p>
        )}
      </div>

      {/* 4. Event Comparison & XAUUSD Relevance */}
      <div className="space-y-2 pt-2 border-t border-gray-800">
        <h4 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
          ความสัมพันธ์ต่อทองคำ (XAUUSD Relevance &amp; Macro Channels)
        </h4>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 font-mono text-xs">
          {groupEvents.map((ev) => {
            const rel = xauusdRelevance[ev.id];
            return (
              <div
                key={ev.id}
                className="p-3 bg-black/30 rounded-lg border border-white/5 space-y-1.5"
              >
                <div className="flex items-center justify-between">
                  <strong className="text-white truncate" title={eventName(ev)}>
                    {eventName(ev)}
                  </strong>
                  <span className="text-amber-300 font-bold shrink-0 ml-1">
                    ระดับ {rel?.score != null ? `${rel.score}/3` : 'UNAVAILABLE'}
                  </span>
                </div>

                <div className="text-[11px] text-gray-400">
                  <span>ช่องทางผลกระทบ: </span>
                  <span className="text-blue-300">
                    {rel?.channels && rel.channels.length > 0
                      ? rel.channels.map(label).join(', ')
                      : 'ไม่ระบุ'}
                  </span>
                </div>

                <div className="flex items-center justify-between text-[10px] text-gray-500 pt-1 border-t border-white/5">
                  <span>สกุลเงิน: {ev.currency}</span>
                  <Link
                    href="/calendar"
                    className="text-amber-400 hover:text-amber-300 underline"
                  >
                    ดูปฏิทิน →
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
