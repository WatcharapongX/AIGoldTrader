'use client';

import React from 'react';
import type { EventDetail } from '@/types/news.generated';
import { bangkok, eventName, label, numeric } from './thai';

interface EventDetailDrawerProps {
  detail: EventDetail | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

export function EventDetailDrawer({
  detail,
  loading,
  error,
  onClose,
}: EventDetailDrawerProps) {
  if (!detail && !loading && !error) return null;

  return (
    <div
      data-testid="event-detail-drawer"
      role="dialog"
      aria-modal="true"
      aria-label="รายละเอียดข่าวเศรษฐกิจและประวัติการแก้ไข"
      className="fixed inset-0 z-50 flex items-center justify-end bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl h-full bg-[#0e1726] border-l border-gray-800 p-6 overflow-y-auto space-y-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drawer Header */}
        <div className="flex items-start justify-between gap-3 border-b border-gray-800 pb-4">
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-500/20 text-blue-300 font-bold border border-blue-500/40">
                {detail?.event.currency || 'USD'}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 font-bold border border-rose-500/40">
                {label(detail?.event.impact)}
              </span>
              <span className="text-xs text-gray-400 font-mono">
                {detail ? label(detail.event.category) : ''}
              </span>
            </div>

            <h2 className="text-lg font-bold text-white tracking-wide mt-2">
              {detail ? eventName(detail.event) : 'รายละเอียดข่าว'}
            </h2>
            <p className="text-xs text-gray-400 font-mono mt-0.5">
              กำหนดประกาศ: {detail ? bangkok(detail.event.scheduled_at) : '—'} (Bangkok · UTC+7)
            </p>
          </div>

          <button
            type="button"
            data-testid="close-drawer-btn"
            onClick={onClose}
            className="p-2 rounded-lg bg-black/40 text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
            aria-label="ปิด"
          >
            ✕
          </button>
        </div>

        {loading ? (
          <div data-testid="drawer-loading" className="p-8 text-center text-gray-400 text-sm">
            กำลังโหลดข้อมูลรายละเอียดและประวัติการแก้ไข...
          </div>
        ) : error ? (
          <div data-testid="drawer-error" className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs">
            {error}
          </div>
        ) : detail ? (
          <div className="space-y-6">
            {/* Field Conflicts Warning */}
            {detail.event.field_conflicts && detail.event.field_conflicts.length > 0 && (
              <div
                data-testid="field-conflicts-alert"
                className="p-3 bg-amber-500/20 border border-amber-500/50 rounded-lg text-xs text-amber-200 space-y-1"
              >
                <strong className="block">⚠️ ข้อมูลจากแหล่งข่าวมีความขัดแย้ง (Field Conflicts):</strong>
                <p className="text-[11px] font-mono">
                  ฟิลด์ที่ขัดแย้ง: {detail.event.field_conflicts.join(', ')} (ระบบไม่เลือกค่าทดแทนเองตามอำเภอใจ)
                </p>
              </div>
            )}

            {/* Key Value Data Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
              <div className="p-3 bg-black/40 rounded-lg border border-white/5">
                <span className="text-[10px] text-gray-400 block">ผลประกาศจริง (ACTUAL)</span>
                <strong className="text-emerald-400 text-base">
                  {numeric(detail.event.actual, detail.event.unit)}
                </strong>
              </div>
              <div className="p-3 bg-black/40 rounded-lg border border-white/5">
                <span className="text-[10px] text-gray-400 block">คาดการณ์ (FORECAST)</span>
                <strong className="text-blue-300 text-base">
                  {detail.event.forecast == null ? '—' : numeric(detail.event.forecast, detail.event.unit)}
                </strong>
              </div>
              <div className="p-3 bg-black/40 rounded-lg border border-white/5">
                <span className="text-[10px] text-gray-400 block">ครั้งก่อน (PREVIOUS)</span>
                <strong className="text-gray-300 text-base">
                  {detail.event.previous == null ? '—' : numeric(detail.event.previous, detail.event.unit)}
                </strong>
              </div>
              <div className="p-3 bg-black/40 rounded-lg border border-white/5">
                <span className="text-[10px] text-gray-400 block">ปรับครั้งก่อน (REVISED)</span>
                <strong className="text-amber-300 text-base">
                  {detail.event.revised_previous == null ? '—' : numeric(detail.event.revised_previous, detail.event.unit)}
                </strong>
              </div>
            </div>

            {/* Timestamps & Provenance Strip */}
            <div className="p-4 bg-black/30 rounded-xl border border-white/5 space-y-2 text-xs font-mono">
              <div className="flex justify-between border-b border-white/5 pb-1.5">
                <span className="text-gray-400">สถานะข่าว (Status):</span>
                <span className="text-amber-400 font-bold">{label(detail.event.status)}</span>
              </div>
              <div className="flex justify-between border-b border-white/5 pb-1.5">
                <span className="text-gray-400">แหล่งข้อมูล (Source):</span>
                <span className="text-gray-300">{detail.event.source} ({detail.event.source_mode})</span>
              </div>
              <div className="flex justify-between border-b border-white/5 pb-1.5">
                <span className="text-gray-400">เวลารับรู้ (Available At):</span>
                <span className="text-gray-300">{bangkok(detail.event.available_at)}</span>
              </div>
              {detail.event.released_at && (
                <div className="flex justify-between border-b border-white/5 pb-1.5">
                  <span className="text-gray-400">เวลาประกาศจริง (Released At):</span>
                  <span className="text-emerald-300">{bangkok(detail.event.released_at)}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-gray-400">รุ่นข้อมูล (Revision Version):</span>
                <span className="text-gray-300">v{detail.event.revision_version}</span>
              </div>
            </div>

            {/* Revision History List */}
            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-white uppercase tracking-wider font-mono">
                  ประวัติการปรับปรุงตัวเลข (Revision History)
                </h3>
                <span className="text-[11px] font-mono text-gray-400">
                  {detail.revisions.length} ฉบับ
                </span>
              </div>

              {detail.revisions.length === 0 ? (
                <p className="text-xs text-gray-400 italic">ยังไม่มีประวัติการแก้ไขข้อมูล</p>
              ) : (
                <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
                  {detail.revisions.map((rev) => (
                    <div
                      key={rev.revision_version}
                      className="p-3 bg-black/40 border border-white/5 rounded-lg space-y-1.5 text-xs font-mono"
                    >
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-amber-300 font-bold">
                          รุ่นที่ {rev.revision_version} ({label(rev.status)})
                        </span>
                        <span className="text-gray-400">
                          รับรู้: {bangkok(rev.available_at)}
                        </span>
                      </div>

                      <div className="grid grid-cols-3 gap-2 text-[11px] pt-1 border-t border-white/5">
                        <div>
                          <span className="text-gray-400 text-[10px] block">ผลจริง</span>
                          <span className="text-emerald-400 font-bold">
                            {numeric(rev.actual, rev.unit)}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-400 text-[10px] block">ครั้งก่อน</span>
                          <span className="text-gray-300">
                            {rev.previous == null ? '—' : numeric(rev.previous, rev.unit)}
                          </span>
                        </div>
                        <div>
                          <span className="text-gray-400 text-[10px] block">ปรับครั้งก่อน</span>
                          <span className="text-amber-300">
                            {rev.revised_previous == null ? '—' : numeric(rev.revised_previous, rev.unit)}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
