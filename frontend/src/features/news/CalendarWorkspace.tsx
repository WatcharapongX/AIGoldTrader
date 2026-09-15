'use client';

import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { api } from '@/lib/api';
import type { CalendarPage, EconomicEvent, EventDetail, NewsResponse } from '@/types/news.generated';
import { parseCalendar, parseEvent, parseNews } from './contracts';
import { bangkok, eventName, label, labels, numeric } from './thai';
import { ProviderStatus } from './ProviderStatus';
import { NextEconomicEventCard } from './NextEconomicEventCard';
import { NewsRiskSummary } from './NewsRiskSummary';
import { StrategyNewsEligibility } from './StrategyNewsEligibility';
import { EventDetailDrawer } from './EventDetailDrawer';
import './news.css';

type QuickDateTab = 'TODAY' | 'TOMORROW' | 'THIS_WEEK' | 'CUSTOM';

function getBangkokDateString(date: Date = new Date()): string {
  return date.toLocaleDateString('en-CA', { timeZone: 'Asia/Bangkok' });
}

function getQuickRange(tab: QuickDateTab, customDate?: string) {
  const bkkTodayStr = getBangkokDateString();
  const todayStart = new Date(`${bkkTodayStr}T00:00:00+07:00`);

  if (tab === 'TODAY') {
    const start = todayStart;
    const end = new Date(start.getTime() + 86400000);
    return { start: start.toISOString(), end: end.toISOString() };
  }
  if (tab === 'TOMORROW') {
    const start = new Date(todayStart.getTime() + 86400000);
    const end = new Date(start.getTime() + 86400000);
    return { start: start.toISOString(), end: end.toISOString() };
  }
  if (tab === 'THIS_WEEK') {
    const start = todayStart;
    // Exactly 7 days (backend range limit: last - first <= 7 days)
    const end = new Date(start.getTime() + 7 * 86400000);
    return { start: start.toISOString(), end: end.toISOString() };
  }
  if (tab === 'CUSTOM' && customDate) {
    const start = new Date(`${customDate}T00:00:00+07:00`);
    const end = new Date(start.getTime() + 86400000);
    return { start: start.toISOString(), end: end.toISOString() };
  }
  return { start: undefined, end: undefined };
}

export function CalendarWorkspace() {
  // Quick date tab & custom date
  const [quickTab, setQuickTab] = useState<QuickDateTab>('THIS_WEEK');
  const [customDate, setCustomDate] = useState<string>('');

  // Filters
  const [impact, setImpact] = useState<string>('');
  const [status, setStatus] = useState<string>('');
  const [category, setCategory] = useState<string>('');
  const [currency, setCurrency] = useState<string>('');
  const [relevant, setRelevant] = useState<boolean>(true);

  // Data states
  const [data, setData] = useState<{ key: string; value: CalendarPage } | null>(null);
  const [newsContext, setNewsContext] = useState<NewsResponse | null>(null);
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState<boolean>(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  // Loading, refreshing, and errors
  const [loadingCalendar, setLoadingCalendar] = useState<boolean>(true);
  const [loadingContext, setLoadingContext] = useState<boolean>(true);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [calendarError, setCalendarError] = useState<string>('');
  const [contextError, setContextError] = useState<string | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);

  // Live Bangkok clock ticker (updates second-by-second)
  const [clockString, setClockString] = useState<string>('');
  useEffect(() => {
    const updateClock = () => {
      const now = new Date();
      setClockString(
        now.toLocaleString('th-TH', {
          timeZone: 'Asia/Bangkok',
          dateStyle: 'medium',
          timeStyle: 'medium',
        })
      );
    };
    updateClock();
    const timer = setInterval(updateClock, 1000);
    return () => clearInterval(timer);
  }, []);

  // Compute query string from active filters and quick range
  const { start: qStart, end: qEnd } = useMemo(
    () => getQuickRange(quickTab, customDate),
    [quickTab, customDate]
  );

  const queryKey = useMemo(() => {
    const query = new URLSearchParams({ relevant_only: String(relevant) });
    if (impact) query.set('impact', impact);
    if (status) query.set('status', status);
    if (category) query.set('category', category);
    if (currency) query.set('currency', currency);
    if (qStart) query.set('start', qStart);
    if (qEnd) query.set('end', qEnd);
    return query.toString();
  }, [relevant, impact, status, category, currency, qStart, qEnd]);

  // Fetch Calendar Events (GET /api/calendar/economic)
  useEffect(() => {
    const abort = new AbortController();
    let busy = false;

    const loadCalendar = async () => {
      if (busy) return;
      busy = true;
      setIsRefreshing(true);
      try {
        const res = await api.get('/calendar/economic?' + queryKey, { signal: abort.signal });
        const value = parseCalendar(res);
        if (!abort.signal.aborted) {
          setData({ key: queryKey, value });
          setCalendarError('');
        }
      } catch {
        if (!abort.signal.aborted) {
          setCalendarError('โหลดปฏิทินเศรษฐกิจไม่ได้ กรุณาตรวจสอบการเชื่อมต่อ');
        }
      } finally {
        busy = false;
        if (!abort.signal.aborted) {
          setLoadingCalendar(false);
          setIsRefreshing(false);
        }
      }
    };

    void loadCalendar();
    const timer = setInterval(loadCalendar, 30000);
    return () => {
      abort.abort();
      clearInterval(timer);
    };
  }, [queryKey, refreshTrigger]);

  // Fetch News Context (GET /api/news/context) independently
  useEffect(() => {
    const abort = new AbortController();
    let busy = false;

    const loadContext = async () => {
      if (busy) return;
      busy = true;
      try {
        const res = await api.get('/news/context', { signal: abort.signal });
        const parsed = parseNews(res);
        if (!abort.signal.aborted) {
          setNewsContext(parsed);
          setContextError(null);
        }
      } catch (err) {
        if (!abort.signal.aborted) {
          setContextError(err instanceof Error ? err.message : 'โหลดบริบทความเสี่ยงข่าวไม่สำเร็จ');
        }
      } finally {
        busy = false;
        if (!abort.signal.aborted) {
          setLoadingContext(false);
        }
      }
    };

    void loadContext();
    const timer = setInterval(loadContext, 30000);
    return () => {
      abort.abort();
      clearInterval(timer);
    };
  }, [refreshTrigger]);

  const currentCalendar = data?.key === queryKey ? data.value : null;
  const currentCalendarAsOf = currentCalendar?.as_of;

  // Open Event Detail Drawer (GET /api/news/events/{id})
  const openEvent = useCallback(
    async (id: string) => {
      if (!currentCalendarAsOf) return;
      setLoadingDetail(true);
      setDetailError(null);
      try {
        const res = await api.get(
          `/news/events/${encodeURIComponent(id)}?as_of=${encodeURIComponent(
            currentCalendarAsOf
          )}`
        );
        setDetail(parseEvent(res));
      } catch (err) {
        setDetailError(err instanceof Error ? err.message : 'โหลดรายละเอียดข่าวไม่ได้');
      } finally {
        setLoadingDetail(false);
      }
    },
    [currentCalendarAsOf]
  );

  const currentCalendarEvents = currentCalendar?.events;

  // Group events by Bangkok Date for readable timeline
  const groupedEvents = useMemo(() => {
    if (!currentCalendarEvents) return [];
    const groups: { dateLabel: string; events: EconomicEvent[] }[] = [];
    const map = new Map<string, EconomicEvent[]>();

    for (const e of currentCalendarEvents) {
      const bkkDate = new Date(e.scheduled_at).toLocaleDateString('th-TH', {
        timeZone: 'Asia/Bangkok',
        weekday: 'short',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
      });
      if (!map.has(bkkDate)) {
        map.set(bkkDate, []);
        groups.push({ dateLabel: bkkDate, events: map.get(bkkDate)! });
      }
      map.get(bkkDate)!.push(e);
    }
    return groups;
  }, [currentCalendarEvents]);

  return (
    <div className="calendar-workspace news-panel space-y-6">
      {/* 1. SECTION A — CALENDAR COMMAND HEADER */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
            <p className="news-kicker uppercase font-mono tracking-wider text-xs font-semibold text-gray-400">
              MACROECONOMIC CALENDAR &amp; POINT-IN-TIME REVISIONS
            </p>
          </div>
          <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight mt-1">
            Economic Calendar
          </h1>
          <p className="text-xs text-gray-400 mt-0.5">
            ปฏิทินเศรษฐกิจ สภาวะความเสี่ยงของข่าว และการประเมินสิทธิ์กลยุทธ์ตามข้อมูลตัวเลขจริง
          </p>
        </div>

        {/* Action badges & Clock */}
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <div className="px-3 py-1.5 rounded-lg bg-[#121c2e] border border-gray-800 text-gray-300 flex items-center gap-2">
            <span className="text-amber-400">🕒 BKK:</span>
            <span>{clockString || 'Asia/Bangkok · UTC+7'}</span>
          </div>

          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 font-semibold rounded-md border border-emerald-500/20">
            PAPER MODE · EXECUTION DISABLED
          </span>

          <button
            type="button"
            data-testid="refresh-calendar-btn"
            onClick={() => setRefreshTrigger((v) => v + 1)}
            disabled={isRefreshing}
            className="px-3 py-1.5 bg-[#121c2e] hover:bg-white/10 text-gray-300 rounded-lg border border-gray-800 transition-colors flex items-center gap-1.5"
          >
            <span className={isRefreshing ? 'animate-spin' : ''}>↻</span>
            <span>{isRefreshing ? 'กำลังซิงค์…' : 'รีเฟรช'}</span>
          </button>
        </div>
      </div>

      {/* 2. SECTION B — PROVIDER STATUS & DATA SOURCE MODE */}
      <div className="space-y-2">
        <ProviderStatus />

        {/* Source Mode Truthfulness Banner */}
        <div
          data-testid="calendar-source-mode-banner"
          className={`p-3 rounded-xl border text-xs font-mono flex items-center justify-between flex-wrap gap-2 ${
            currentCalendar?.source_mode === 'LIVE'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : currentCalendar?.source_mode === 'FIXTURE'
              ? 'bg-amber-500/15 border-amber-500/40 text-amber-200'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="font-bold">
              {currentCalendar?.source_mode === 'LIVE'
                ? '🟢 REAL ECONOMIC CALENDAR'
                : currentCalendar?.source_mode === 'FIXTURE'
                ? '🟡 ข้อมูลข่าวสาธิต · DEMO NEWS DATA'
                : '🔴 CALENDAR UNAVAILABLE'}
            </span>
            <span>
              {currentCalendar?.source_mode === 'FIXTURE'
                ? '— ข้อมูลข่าวสาธิต ไม่ใช่กำหนดการหรือผลประกาศจริง'
                : currentCalendar?.source_mode === 'LIVE'
                ? '— ข้อมูลข่าวจริง โปรดตรวจสอบข้อจำกัดของแหล่งข่าว'
                : '— ผู้ให้บริการปฏิทินไม่พร้อมใช้งาน'}
            </span>
          </div>

          <span className="text-[10px] opacity-80">
            Source: {currentCalendar?.source || 'UNAVAILABLE'} · State: {currentCalendar?.state || 'UNAVAILABLE'}
          </span>
        </div>
      </div>

      {/* 3. SECTION D & C — NEXT HIGH-IMPACT USD EVENT & CURRENT NEWS RISK */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Next High-Impact USD Event Card (7 cols) */}
        <div className="lg:col-span-7">
          <NextEconomicEventCard
            events={currentCalendar?.events || []}
            source={currentCalendar?.source}
            sourceMode={currentCalendar?.source_mode}
            onSelectEvent={openEvent}
            asOf={currentCalendar?.as_of}
          />
        </div>

        {/* Current News Risk Summary (5 cols) */}
        <div className="lg:col-span-5">
          <NewsRiskSummary
            newsContext={newsContext}
            loading={loadingContext}
            error={contextError}
          />
        </div>
      </div>

      {/* 4. SECTION I — STRATEGY NEWS ELIGIBILITY */}
      <StrategyNewsEligibility eligibility={newsContext?.strategy_eligibility} />

      {/* 5. SECTION E & F — QUICK DATE NAVIGATION & FILTERS */}
      <div className="p-4 bg-[#0e1726] border border-gray-800 rounded-xl space-y-4">
        {/* Quick Date Tabs */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-gray-800 pb-3">
          <div className="flex items-center gap-1.5 overflow-x-auto font-mono text-xs">
            <button
              type="button"
              data-testid="tab-today"
              onClick={() => setQuickTab('TODAY')}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                quickTab === 'TODAY'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`}
            >
              วันนี้ (TODAY)
            </button>

            <button
              type="button"
              data-testid="tab-tomorrow"
              onClick={() => setQuickTab('TOMORROW')}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                quickTab === 'TOMORROW'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`}
            >
              พรุ่งนี้ (TOMORROW)
            </button>

            <button
              type="button"
              data-testid="tab-this-week"
              onClick={() => setQuickTab('THIS_WEEK')}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                quickTab === 'THIS_WEEK'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`}
            >
              สัปดาห์นี้ (THIS WEEK · 7 DAYS)
            </button>

            <button
              type="button"
              data-testid="tab-custom"
              onClick={() => setQuickTab('CUSTOM')}
              className={`px-3 py-1.5 rounded-lg font-bold transition-all ${
                quickTab === 'CUSTOM'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`}
            >
              กำหนดเอง (CUSTOM)
            </button>
          </div>

          {/* Custom Date Input */}
          {quickTab === 'CUSTOM' && (
            <div className="flex items-center gap-2">
              <label htmlFor="custom-date-picker" className="text-xs text-gray-400 font-mono">วันที่:</label>
              <input
                id="custom-date-picker"
                type="date"
                aria-label="วันที่ข่าว"
                value={customDate}
                onChange={(e) => setCustomDate(e.target.value)}
                className="bg-black/40 border border-gray-700 rounded-lg px-2.5 py-1 text-xs text-gray-200 font-mono"
              />
            </div>
          )}
        </div>

        {/* Detailed Filters Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-xs font-mono">
          {/* Currency Filter */}
          <div>
            <label htmlFor="currency-filter-select" className="text-[10px] text-gray-400 block mb-1">สกุลเงิน (CURRENCY)</label>
            <select
              id="currency-filter-select"
              aria-label="สกุลเงิน"
              value={currency}
              onChange={(e) => setCurrency(e.target.value)}
              className="w-full bg-black/40 border border-gray-700 rounded-lg p-2 text-gray-200"
            >
              <option value="">ทั้งหมด (ALL)</option>
              <option value="USD">USD (ดอลลาร์)</option>
              <option value="EUR">EUR (ยูโร)</option>
              <option value="GBP">GBP (ปอนด์)</option>
              <option value="JPY">JPY (เยน)</option>
              <option value="AUD">AUD (ออสเตรเลีย)</option>
              <option value="CAD">CAD (แคนาดา)</option>
              <option value="CHF">CHF (ฟรังก์)</option>
              <option value="NZD">NZD (นิวซีแลนด์)</option>
            </select>
          </div>

          {/* Impact Filter */}
          <div>
            <label htmlFor="impact-filter-select" className="text-[10px] text-gray-400 block mb-1">ผลกระทบ (IMPACT)</label>
            <select
              id="impact-filter-select"
              aria-label="ผลกระทบ"
              value={impact}
              onChange={(e) => setImpact(e.target.value)}
              className="w-full bg-black/40 border border-gray-700 rounded-lg p-2 text-gray-200"
            >
              <option value="">ทั้งหมด (ALL)</option>
              <option value="HIGH">HIGH (สูง)</option>
              <option value="MEDIUM">MEDIUM (ปานกลาง)</option>
              <option value="LOW">LOW (ต่ำ)</option>
            </select>
          </div>

          {/* Category Filter */}
          <div>
            <label htmlFor="category-filter-select" className="text-[10px] text-gray-400 block mb-1">หมวดหมู่ (CATEGORY)</label>
            <select
              id="category-filter-select"
              aria-label="ประเภท"
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full bg-black/40 border border-gray-700 rounded-lg p-2 text-gray-200"
            >
              <option value="">ทั้งหมด (ALL)</option>
              {[
                'EMPLOYMENT',
                'INFLATION',
                'CENTRAL_BANK',
                'GROWTH',
                'CONSUMER',
                'MANUFACTURING',
                'SERVICES',
                'HOUSING',
                'LABOR',
                'OTHER',
              ].map((v) => (
                <option key={v} value={v}>
                  {labels[v] || v}
                </option>
              ))}
            </select>
          </div>

          {/* Status Filter */}
          <div>
            <label htmlFor="status-filter-select" className="text-[10px] text-gray-400 block mb-1">สถานะ (STATUS)</label>
            <select
              id="status-filter-select"
              aria-label="สถานะ"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full bg-black/40 border border-gray-700 rounded-lg p-2 text-gray-200"
            >
              <option value="">ทั้งหมด (ALL)</option>
              <option value="upcoming">ยังไม่ประกาศ (Upcoming)</option>
              <option value="released">ประกาศแล้ว (Released)</option>
            </select>
          </div>

          {/* Gold Relevance Checkbox */}
          <div className="flex items-center gap-2 pt-4">
            <label className="flex items-center gap-2 cursor-pointer text-gray-200">
              <input
                type="checkbox"
                checked={relevant}
                onChange={(e) => setRelevant(e.target.checked)}
                className="rounded bg-black/40 border-gray-700 text-amber-500 focus:ring-0"
              />
              <span className="text-xs">กระทบทอง (XAUUSD)</span>
            </label>
          </div>

          {/* Quick Clear Filter */}
          <div className="flex items-center justify-end pt-4">
            <button
              type="button"
              onClick={() => {
                setImpact('');
                setStatus('');
                setCategory('');
                setCurrency('');
                setRelevant(true);
                setQuickTab('THIS_WEEK');
                setCustomDate('');
              }}
              className="text-[11px] text-gray-400 hover:text-amber-400 underline"
            >
              ล้างตัวกรอง (Reset)
            </button>
          </div>
        </div>
      </div>

      {/* 6. SECTION G — EVENT LIST / TIMELINE */}
      <section className="space-y-4" aria-label="Economic Events List">
        {calendarError && (
          <div role="alert" className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs">
            {calendarError}
          </div>
        )}

        {loadingCalendar && !currentCalendar ? (
          <div role="status" className="p-12 text-center text-gray-400 text-sm space-y-2">
            <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto" />
            <p>กำลังโหลดรายการข่าวเศรษฐกิจ...</p>
          </div>
        ) : !currentCalendar ? null : (
          <div className="space-y-4">
            {/* Metadata bar */}
            <div className="flex items-center justify-between text-xs font-mono text-gray-400 px-1">
              <span>
                ข้อมูล ณ เวลา: {bangkok(currentCalendar.as_of)} · {currentCalendar.events.length} เหตุการณ์
              </span>
              {currentCalendar.truncated && (
                <span className="text-amber-400 font-bold">
                  * แสดงข้อมูลบางส่วน กรุณาจำกัดตัวกรอง (Truncated)
                </span>
              )}
            </div>

            {currentCalendar.events.length === 0 ? (
              <div
                data-testid="calendar-empty"
                className="p-12 bg-[#0e1726] border border-gray-800 rounded-xl text-center text-gray-400 text-xs space-y-2"
              >
                <span className="text-2xl block">🔍</span>
                <p className="font-semibold text-gray-300">
                  ไม่มีข่าวตามเงื่อนไขในช่วงข้อมูลนี้
                </p>
                <p className="text-[11px] text-gray-400">
                  ลองปรับเปลี่ยนตัวกรองสกุลเงิน, ระดับผลกระทบ หรือช่วงเวลาที่ต้องการค้นหา
                </p>
              </div>
            ) : (
              <div className="space-y-6">
                {groupedEvents.map((group) => (
                  <div key={group.dateLabel} className="space-y-2">
                    {/* Date Divider */}
                    <div className="flex items-center gap-2 text-xs font-mono text-amber-300 bg-[#121c2e] p-2.5 rounded-lg border border-gray-800">
                      <span>📅</span>
                      <strong className="tracking-wide uppercase">{group.dateLabel}</strong>
                      <span className="text-gray-500">({group.events.length} รายการ)</span>
                    </div>

                    {/* Events Table / Card List */}
                    <div className="overflow-x-auto rounded-xl border border-gray-800 bg-[#0e1726]">
                      <table className="w-full text-left text-xs font-mono">
                        <thead className="bg-[#121c2e]/60 text-gray-400 uppercase border-b border-gray-800">
                          <tr>
                            <th className="p-3">เวลา (Bangkok)</th>
                            <th className="p-3">สกุลเงิน</th>
                            <th className="p-3">ผลกระทบ</th>
                            <th className="p-3">ชื่อข่าว / เหตุการณ์</th>
                            <th className="p-3">หมวดหมู่</th>
                            <th className="p-3">สถานะ</th>
                            <th className="p-3 text-right">ผลจริง</th>
                            <th className="p-3 text-right">คาดการณ์</th>
                            <th className="p-3 text-right">ครั้งก่อน</th>
                            <th className="p-3 text-center">รายละเอียด</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-800/60 text-gray-300">
                          {group.events.map((e) => {
                            const isHigh = e.impact === 'HIGH';
                            const isMedium = e.impact === 'MEDIUM';

                            return (
                              <tr key={e.id} className="hover:bg-white/5 transition-colors">
                                {/* Time */}
                                <td className="p-3 font-semibold text-white whitespace-nowrap">
                                  {bangkok(e.scheduled_at).split(' ').pop()}
                                </td>

                                {/* Currency */}
                                <td className="p-3">
                                  <span className="font-bold text-blue-300">{e.currency}</span>
                                </td>

                                {/* Impact */}
                                <td className="p-3 whitespace-nowrap">
                                  <span
                                    className={`px-2 py-0.5 text-[10px] font-bold rounded ${
                                      isHigh
                                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                                        : isMedium
                                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                        : 'bg-gray-800 text-gray-400'
                                    }`}
                                  >
                                    {label(e.impact)}
                                  </span>
                                </td>

                                {/* Event Name (Clickable) */}
                                <td className="p-3 font-semibold text-white max-w-xs">
                                  <button
                                    type="button"
                                    onClick={() => void openEvent(e.id)}
                                    className="text-left text-white hover:text-amber-300 transition-colors cursor-pointer"
                                  >
                                    {eventName(e)}
                                  </button>
                                </td>

                                {/* Category */}
                                <td className="p-3 text-gray-400 whitespace-nowrap">
                                  {labels[e.category] || label(e.category)}
                                </td>

                                {/* Status */}
                                <td className="p-3 whitespace-nowrap">
                                  <span
                                    className={`text-[10px] font-bold ${
                                      e.status === 'RELEASED' || e.status === 'REVISED'
                                        ? 'text-emerald-400'
                                        : e.status === 'CANCELLED'
                                        ? 'text-gray-500 line-through'
                                        : e.status === 'DELAYED'
                                        ? 'text-orange-400'
                                        : 'text-blue-300'
                                    }`}
                                  >
                                    {label(e.status)}
                                  </span>
                                </td>

                                {/* Actual (numeric zero handled strictly) */}
                                <td className="p-3 text-right font-bold text-emerald-400 whitespace-nowrap">
                                  {numeric(e.actual, e.unit)}
                                </td>

                                {/* Forecast */}
                                <td className="p-3 text-right text-blue-300 whitespace-nowrap">
                                  {e.forecast == null ? '—' : numeric(e.forecast, e.unit)}
                                </td>

                                {/* Previous */}
                                <td className="p-3 text-right text-gray-300 whitespace-nowrap">
                                  {e.previous == null ? '—' : numeric(e.previous, e.unit)}
                                </td>

                                {/* Action to inspect drawer */}
                                <td className="p-3 text-center">
                                  <button
                                    type="button"
                                    onClick={() => void openEvent(e.id)}
                                    className="px-2 py-1 rounded bg-black/40 hover:bg-white/10 text-amber-300 text-[11px] border border-white/10"
                                    title="ดูประวัติการแก้ไขตัวเลข"
                                  >
                                    ตรวจสอบ →
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      {/* 7. SECTION H — EVENT DETAIL & REVISION DRAWER */}
      <EventDetailDrawer
        detail={detail}
        loading={loadingDetail}
        error={detailError}
        onClose={() => setDetail(null)}
      />
    </div>
  );
}
