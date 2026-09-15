'use client';

import React, { useEffect, useState, useMemo } from 'react';
import type { EconomicEvent } from '@/types/news.generated';
import { bangkok, eventName, label, numeric } from './thai';

interface NextEconomicEventCardProps {
  events: EconomicEvent[];
  source?: string;
  sourceMode?: string;
  onSelectEvent?: (id: string) => void;
  asOf?: string;
}

export function formatCountdown(scheduledAt: string, nowMs: number): string {
  const targetMs = Date.parse(scheduledAt);
  if (!Number.isFinite(targetMs) || nowMs === 0) return '—';

  const diffMs = targetMs - nowMs;
  if (diffMs <= 0) {
    return 'RELEASE TIME (กำลังประกาศ / ประกาศแล้ว)';
  }

  const totalSec = Math.floor(diffMs / 1000);
  const days = Math.floor(totalSec / 86400);
  const hours = Math.floor((totalSec % 86400) / 3600);
  const minutes = Math.floor((totalSec % 3600) / 60);
  const seconds = totalSec % 60;

  if (days > 0) {
    return `${days} วัน ${hours} ชม. ${minutes} นาที`;
  }
  if (hours > 0) {
    return `${hours} ชม. ${minutes} นาที ${seconds} วินาที`;
  }
  if (minutes > 0) {
    return `${minutes} นาที ${seconds} วินาที`;
  }
  return `${seconds} วินาที`;
}

export function NextEconomicEventCard({
  events,
  source = 'mock_macro_v1',
  sourceMode = 'FIXTURE',
  onSelectEvent,
  asOf,
}: NextEconomicEventCardProps) {
  const [elapsedSec, setElapsedSec] = useState<number>(0);
  const [initialNow] = useState<number>(() => Date.now());

  // Local 1-second ticker for smooth countdown without refetching network
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSec((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, []);

  const baseMs = asOf ? Date.parse(asOf) : initialNow;
  const currentMs = baseMs + elapsedSec * 1000;

  // Find the next upcoming HIGH USD event that is NOT cancelled
  const nextEvent = useMemo(() => {
    const candidates = events.filter((e) => {
      if (e.currency !== 'USD') return false;
      if (e.impact !== 'HIGH') return false;
      if (e.status === 'CANCELLED') return false;
      const sched = Date.parse(e.scheduled_at);
      return Number.isFinite(sched) && sched > currentMs;
    });

    if (candidates.length === 0) return null;
    candidates.sort((a, b) => Date.parse(a.scheduled_at) - Date.parse(b.scheduled_at));
    return candidates[0];
  }, [events, currentMs]);

  const countdownText = nextEvent
    ? formatCountdown(nextEvent.scheduled_at, currentMs)
    : '';

  return (
    <div
      data-testid="next-high-impact-usd-card"
      className="p-5 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4 relative overflow-hidden"
    >
      {/* Card Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-gray-800 pb-3">
        <div className="flex items-center gap-2">
          <span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" />
          <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">
            ข่าว USD ผลกระทบสูงรายการถัดไป (Next High-Impact USD Event)
          </h3>
        </div>

        <div className="flex items-center gap-2 text-[10px] font-mono">
          <span className="text-gray-400">แหล่งข้อมูล: {source}</span>
          <span
            className={`px-2 py-0.5 rounded font-bold ${
              sourceMode === 'LIVE'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
            }`}
          >
            {sourceMode}
          </span>
        </div>
      </div>

      {nextEvent ? (
        <div className="space-y-4">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            {/* Event Name & Category */}
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="px-2 py-0.5 text-xs font-bold font-mono rounded bg-rose-500/20 text-rose-300 border border-rose-500/40">
                  🔴 HIGH IMPACT
                </span>
                <span className="px-2 py-0.5 text-xs font-bold font-mono rounded bg-blue-500/20 text-blue-300 border border-blue-500/40">
                  {nextEvent.currency}
                </span>
                <span className="text-xs text-gray-400 font-mono">
                  หมวด: {label(nextEvent.category)}
                </span>
              </div>

              <h4 className="text-lg font-bold text-white tracking-wide">
                {eventName(nextEvent)}
              </h4>
              <p className="text-xs text-gray-400 font-mono">
                กำหนดประกาศ: {bangkok(nextEvent.scheduled_at)} (Bangkok · UTC+7)
              </p>
            </div>

            {/* Countdown Box */}
            <div className="p-3 bg-black/40 border border-white/10 rounded-xl text-center md:text-right min-w-[200px]">
              <span className="text-[10px] text-gray-400 uppercase font-mono block">
                นับถอยหลังสู่วันประกาศ (COUNTDOWN)
              </span>
              <strong
                data-testid="countdown-display"
                className="text-lg sm:text-xl font-bold font-mono text-amber-300 block mt-0.5"
              >
                {countdownText}
              </strong>
            </div>
          </div>

          {/* Metric Comparison (Forecast vs Previous) */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 bg-black/30 rounded-lg border border-white/5 text-xs font-mono">
            <div>
              <span className="text-[10px] text-gray-400 block">คาดการณ์ (FORECAST)</span>
              <strong className="text-blue-300">
                {nextEvent.forecast == null ? '—' : numeric(nextEvent.forecast, nextEvent.unit)}
              </strong>
            </div>
            <div>
              <span className="text-[10px] text-gray-400 block">ครั้งก่อน (PREVIOUS)</span>
              <strong className="text-gray-300">
                {nextEvent.previous == null ? '—' : numeric(nextEvent.previous, nextEvent.unit)}
              </strong>
            </div>
            <div>
              <span className="text-[10px] text-gray-400 block">ปรับครั้งก่อน (REVISED)</span>
              <span className="text-gray-400">
                {nextEvent.revised_previous == null ? '—' : numeric(nextEvent.revised_previous, nextEvent.unit)}
              </span>
            </div>
            <div>
              <span className="text-[10px] text-gray-400 block">สถานะ (STATUS)</span>
              <span className="text-amber-400 font-bold">
                {label(nextEvent.status)}
              </span>
            </div>
          </div>

          {/* Action to view detail */}
          {onSelectEvent && (
            <div className="flex justify-end pt-1">
              <button
                type="button"
                onClick={() => onSelectEvent(nextEvent.id)}
                className="text-xs font-mono text-amber-400 hover:text-amber-300 underline flex items-center gap-1"
              >
                ดูรายละเอียดและการปรับปรุงตัวเลข (View Event Details) →
              </button>
            </div>
          )}
        </div>
      ) : (
        <div data-testid="no-upcoming-high-usd" className="p-6 text-center text-gray-400 text-xs space-y-1">
          <span className="text-xl block">📅</span>
          <p className="font-semibold text-gray-300">
            ไม่มีข่าว USD ผลกระทบสูงในช่วงข้อมูลที่เลือก
          </p>
          <p className="text-[11px] text-gray-400">
            ระบบไม่มีการสร้างหรือจำลองเหตุการณ์เท็จ (No Synthetic Events Fabricated)
          </p>
        </div>
      )}
    </div>
  );
}
