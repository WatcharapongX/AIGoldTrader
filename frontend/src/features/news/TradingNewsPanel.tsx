'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { NewsResponse } from '@/types/news.generated';
import { parseNews } from './contracts';
import { bangkok } from './thai';
import { ProviderStatus } from './ProviderStatus';
import { NextEconomicEventCard } from './NextEconomicEventCard';
import { StrategyNewsEligibility } from './StrategyNewsEligibility';
import { MacroBiasCard } from './MacroBiasCard';
import { ReleaseGroupPanel } from './ReleaseGroupPanel';
import { MarketReactionPanel } from './MarketReactionPanel';
import { StructureConfirmationCard } from './StructureConfirmationCard';
import { MacroReasonPanel } from './MacroReasonPanel';
import './news.css';

export function TradingNewsPanel() {
  const [view, setView] = useState<string>('current');
  const [data, setData] = useState<{ view: string; value: NewsResponse; received: number } | null>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState<boolean>(true);
  const [clockString, setClockString] = useState<string>('');

  // Clock ticker for Bangkok time
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

  // Fetch News Context (GET /api/news/context?view=...) every 15s
  useEffect(() => {
    const abort = new AbortController();
    let busy = false;

    const fetchData = async () => {
      if (busy) return;
      busy = true;
      try {
        const res = await api.get('/news/context?view=' + encodeURIComponent(view), {
          signal: abort.signal,
        });
        const value = parseNews(res);
        if (!abort.signal.aborted) {
          setData({ view, value, received: Date.now() });
          setError('');
        }
      } catch (err) {
        if (!abort.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : 'โหลดบริบทข่าวไม่ได้ กรุณารอการเชื่อมต่ออีกครั้ง'
          );
        }
      } finally {
        busy = false;
        if (!abort.signal.aborted) {
          setLoading(false);
        }
      }
    };

    void fetchData();
    const timer = setInterval(fetchData, 15000);
    return () => {
      abort.abort();
      clearInterval(timer);
    };
  }, [view]);

  const current = data?.view === view ? data : null;
  const n = current?.value;

  return (
    <section
      className="news-panel space-y-6"
      aria-label="บริบทข่าวเศรษฐกิจและปฏิกิริยาตลาด"
      data-testid="news-panel"
    >
      {/* 1. Header & Source Mode Strip */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
            <p className="news-kicker uppercase font-mono tracking-wider text-xs font-semibold text-gray-400">
              MACROECONOMIC INTELLIGENCE &amp; REACTION WORKBENCH
            </p>
          </div>
          <h2 className="text-xl lg:text-2xl font-bold text-white tracking-tight mt-1">
            บริบทข่าวและเศรษฐกิจมหภาค (Macro Context &amp; Market Reaction)
          </h2>
          <p className="text-xs text-gray-400 mt-0.5">
            วิเคราะห์ผลประกาศเศรษฐกิจ ภาพรวม USD ปฏิกิริยาราคาทอง และการยืนยันจากโครงสร้างตลาด
          </p>
        </div>

        {/* Action Badges & Clock */}
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <div className="px-3 py-1.5 rounded-lg bg-[#121c2e] border border-gray-800 text-gray-300 flex items-center gap-2">
            <span className="text-amber-400">🕒 BKK:</span>
            <span>{clockString || 'Asia/Bangkok · UTC+7'}</span>
          </div>

          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 font-semibold rounded-md border border-emerald-500/20">
            PAPER MODE · EXECUTION DISABLED
          </span>

          <Link
            href="/calendar"
            className="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 rounded-lg border border-amber-500/40 transition-colors flex items-center gap-1"
          >
            <span>📅</span>
            <span>เปิดปฏิทินข่าว →</span>
          </Link>
        </div>
      </div>

      {/* 2. Provider Health Status */}
      <div className="space-y-2">
        <ProviderStatus />

        {/* Source Mode Truthfulness Banner */}
        <div
          data-testid="news-source-mode-banner"
          className={`p-3 rounded-xl border text-xs font-mono flex items-center justify-between flex-wrap gap-2 ${
            n?.source_mode === 'LIVE'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : n?.source_mode === 'FIXTURE'
              ? 'bg-amber-500/15 border-amber-500/40 text-amber-200'
              : 'bg-rose-500/10 border-rose-500/30 text-rose-300'
          }`}
        >
          <div className="flex items-center gap-2">
            <span className="font-bold">
              {n?.source_mode === 'LIVE'
                ? '🟢 REAL MACRO DATA'
                : n?.source_mode === 'FIXTURE'
                ? '🟡 DEMO / FIXTURE MACRO DATA'
                : '🔴 DATA UNAVAILABLE'}
            </span>
            <span>
              {n?.source_mode === 'FIXTURE'
                ? '— ข้อมูลข่าวสาธิต กำหนดเวลาและตัวเลขนี้ไม่ใช่ข่าวจริง'
                : n?.source_mode === 'LIVE'
                ? '— ข้อมูลข่าวจริง โปรดตรวจความครอบคลุมและสถานะพร้อมใช้'
                : '— แหล่งข่าวไม่พร้อมใช้งาน'}
            </span>
          </div>

          <span className="text-[10px] opacity-80">
            Market Source: {n?.market_source || 'mt5_demo_iux'} · ข่าวและราคาเป็นคนละแหล่งข้อมูล
          </span>
        </div>

        {/* Fixture View Selector (STRICTLY ONLY when source_mode === 'FIXTURE') */}
        {n?.source_mode === 'FIXTURE' && (
          <div className="p-3 bg-black/40 border border-white/5 rounded-xl flex items-center justify-between gap-3 text-xs font-mono">
            <span className="text-amber-300 font-bold">
              มุมมองสาธิต (Fixture Demo View):
            </span>
            <select
              aria-label="มุมมองสาธิต"
              value={view}
              onChange={(e) => setView(e.target.value)}
              className="bg-[#1b293c] border border-gray-700 text-gray-200 rounded-lg px-3 py-1.5"
            >
              <option value="current">ตามเวลาปัจจุบัน (Current)</option>
              <option value="pre">ก่อนประกาศ (Pre-News)</option>
              <option value="release">เพิ่งประกาศ (Release)</option>
              <option value="post">หลังประกาศ (Post-News)</option>
              <option value="none">ไม่มีข่าว (No Event)</option>
            </select>
          </div>
        )}
      </div>

      {/* Error alert with fallback */}
      {error && (
        <div
          role="alert"
          className="p-4 bg-rose-500/10 border border-rose-500/30 rounded-xl text-rose-300 text-xs font-mono space-y-1"
        >
          <strong>⚠️ {error}</strong>
          <p className="text-[11px] text-gray-400">
            ข้อมูลเดิมอาจล้าสมัย ระบบจะระงับการอ้างอิงสิทธิ์กลยุทธ์จนกว่าการเชื่อมต่อจะกลับมาเป็นปกติ
          </p>
        </div>
      )}

      {loading && !n ? (
        <div role="status" className="p-12 text-center text-gray-400 text-sm space-y-2">
          <div className="w-6 h-6 border-2 border-amber-500 border-t-transparent rounded-full animate-spin mx-auto" />
          <p>กำลังโหลดข้อมูลบริบทข่าวและเศรษฐกิจมหภาค...</p>
        </div>
      ) : !n ? null : (
        <div className="space-y-6">
          {/* 3. Top Row: Macro Bias Card & Next High-Impact USD Event */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-7">
              <MacroBiasCard
                macroBias={n.macro_bias}
                macroStrength={n.macro_strength}
                newsRegime={n.news_regime}
                releaseStatus={n.release_status}
                dataQuality={n.data_quality}
                multipleEventRisk={n.multiple_event_risk}
                calendarState={n.calendar_state}
              />
            </div>

            <div className="lg:col-span-5">
              <NextEconomicEventCard
                events={n.upcoming_events || n.events}
                source={n.source}
                sourceMode={n.source_mode}
                asOf={n.as_of}
              />
            </div>
          </div>

          {/* 4. Active Release Group & Surprise Matrix */}
          <ReleaseGroupPanel
            activeGroup={n.active_group}
            events={n.events}
            activeEventId={n.active_event_id}
            xauusdRelevance={n.xauusd_relevance}
            upcomingEvents={n.upcoming_events}
          />

          {/* 5. Market Reaction Analysis (T+1m, T+5m, T+15m, Spread, Volatility) */}
          <MarketReactionPanel
            reactionState={n.reaction_state}
            reactionWindows={n.reaction_windows}
            spreadState={n.spread_state}
            currentSpread={n.current_spread}
            baselineSpread={n.baseline_spread}
            spreadRatio={n.spread_ratio}
            volatilityState={n.volatility_state}
            sourceMode={n.source_mode}
          />

          {/* 6. Confluence & Eligibility: Structure Confirmation & Strategy News Eligibility */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <StructureConfirmationCard structure={n.structure_confirmation} />
            <div className="space-y-6">
              <StrategyNewsEligibility eligibility={n.strategy_eligibility} />
              <MacroReasonPanel
                tradePolicyState={n.trade_policy_state}
                reasonCodes={n.reason_codes}
              />
            </div>
          </div>

          {/* 7. Provenance & Metadata Footer */}
          <footer className="p-4 bg-black/40 border border-white/5 rounded-xl text-xs font-mono text-gray-400 space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2 text-[11px]">
              <span>
                เวลาข้อมูล: {bangkok(n.as_of)} (Asia/Bangkok)
              </span>
              <span>
                ตลาด: {n.market_as_of ? bangkok(n.market_as_of) : '—'}
              </span>
              <span>
                สร้าง: {bangkok(n.generated_at)} · ส่ง: {bangkok(n.served_at)}
              </span>
              <span className="text-amber-400">
                อายุแคช: {n.cache_age_seconds ? n.cache_age_seconds.toFixed(1) : '0.0'}s
              </span>
            </div>

            <details className="pt-2 border-t border-white/5 cursor-pointer">
              <summary className="text-gray-300 hover:text-amber-300 transition-colors">
                ที่มาและการคำนวณทางเทคนิค (Provenance Details) ▾
              </summary>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 text-[11px] text-gray-400">
                <p>แหล่งข่าว: <strong className="text-white">{n.source}</strong> ({n.source_mode})</p>
                <p>News Engine Version: <strong className="text-white">{n.news_engine_version || 'news-1.2.0'}</strong></p>
                <p>Config ID: <code className="text-gray-300">{n.config_id}</code></p>
                <p className="truncate">Fingerprint: <code className="text-gray-300">{n.fingerprint}</code></p>
                <p>Upstream Structure: <code className="text-gray-300">{n.structure_confirmation.upstream_input_id || '—'}</code></p>
              </div>
            </details>
          </footer>
        </div>
      )}
    </section>
  );
}
