"use client";
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { api } from '@/lib/api';
import { MarketConnection, type ConnectionState } from '@/features/chart/transport';
import type { DashboardSummary, EconomicEvent } from '@/types/dashboard.generated';
import type { Quote } from '@/types/market.generated';
import { bangkok, countdown, eventName, label as newsLabel, numeric } from '@/features/news/thai';
import { names as strategyLabels } from '@/features/strategy/thai';
import { parseDashboard } from './contracts';

/* ── Thai labels ──────────────────────────────────────────── */
const states: Record<string,string> = {
 HEALTHY:'พร้อม', DEGRADED:'ตรวจสอบ', STALE:'ล้าสมัย', UNAVAILABLE:'ไม่พร้อม',
 UNKNOWN:'ยังไม่ยืนยัน', DISABLED:'ปิด', CONNECTED:'เชื่อมต่อ', CONNECTING:'กำลังเชื่อม',
 RECONNECTING:'เชื่อมใหม่', DISCONNECTED:'ขาดการเชื่อมต่อ', ERROR:'ผิดพลาด',
 BULLISH:'ขาขึ้น', BEARISH:'ขาลง', NEUTRAL:'กลาง', RANGE:'กรอบ', RANGING:'กรอบ',
 TRENDING_UP:'ขาขึ้น', TRENDING_DOWN:'ขาลง', HIGH_VOLATILITY:'ผันผวนสูง',
 LOW_VOLATILITY:'ผันผวนต่ำ', BREAKOUT:'ทะลุ', PULLBACK:'พักตัว',
 FULL:'ครบ', LIMITED:'บางส่วน',
 SCHEDULED:'รอ', RELEASED:'ประกาศแล้ว', REVISED:'แก้ไข', PROVISIONAL:'ไม่ครบ',
 BUY:'BUY', SELL:'SELL', LONG:'BUY', SHORT:'SELL',
 ...strategyLabels,
};
const name = (v: string | null | undefined) => v ? states[v] || v : '—';

/* ── Helpers ──────────────────────────────────────────────── */
function fmtPrice(p: string | number | undefined | null) {
  if (!p) return '—';
  const n = typeof p === 'string' ? parseFloat(p) : p;
  return isNaN(n) ? String(p) : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function StatusDot({ ok }: { ok: boolean }) {
  return <span className={`inline-block w-2 h-2 rounded-full ${ok ? 'bg-emerald-400' : 'bg-amber-400'}`} />;
}

function ImpactBadge({ impact }: { impact: string }) {
  const colors: Record<string,string> = {
    HIGH: 'bg-red-500/20 text-red-400 border-red-500/30',
    MEDIUM: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    LOW: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  };
  return <span className={`text-[10px] px-2 py-0.5 rounded-full border ${colors[impact] || colors.LOW}`}>{impact === 'HIGH' ? 'High' : impact === 'MEDIUM' ? 'Medium' : 'Low'}</span>;
}

/* ══════════════════════════════════════════════════════════ */
export function Dashboard() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [ws, setWs] = useState<ConnectionState>('CONNECTING');
  const [clock, setClock] = useState(0);

  useEffect(() => {
    const abort = new AbortController();
    let busy = false;
    const refresh = async () => {
      if (busy) return; busy = true;
      try {
        const value = parseDashboard(await api.get('/dashboard/summary', { signal: abort.signal }));
        if (!abort.signal.aborted) { setData(value); setError(''); }
      } catch { if (!abort.signal.aborted) setError('โหลดข้อมูลไม่สำเร็จ'); }
      finally { busy = false; }
    };
    const connection = new MarketConnection(
      async () => { await api.getMe(); const t = localStorage.getItem('access_token'); if (!t) throw new Error('Session expired'); return t; },
      msg => { if (!abort.signal.aborted && msg.quote) setQuote(msg.quote); },
      state => { if (!abort.signal.aborted) setWs(state); },
      'XAUUSD', 'M5',
    );
    connection.start(); void refresh();
    const timer = setInterval(refresh, 30000);
    const ticker = setInterval(() => setClock(Date.now()), 1000);
    return () => { abort.abort(); clearInterval(timer); clearInterval(ticker); connection.stop(); };
  }, []);

  const current = quote && quote.source === data?.market?.source ? quote : data?.quote;
  const old = !!data && (!!error || clock - Date.parse(data.generated_at) > 65000);
  const staleQuote = !current || clock - Date.parse(current.timestamp) > (data?.market?.stale_after_seconds || 5) * 1000;
  const plan = !old && !data?.strategy_stale && data?.current_plan && Date.parse(data.current_plan.expires_at) > clock ? data.current_plan : null;
  const direction = plan?.direction || 'NEUTRAL';
  const confidence = plan ? Math.min(plan.score, 100) : 0;

  /* ── Render ────────────────────────────────────────────── */
  return (
    <div className="space-y-5" data-testid="dashboard">
      {/* ─── Hero Banner ─────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-2xl h-[180px]">
        <Image src="/images/login-bg.jpg" alt="" fill className="object-cover opacity-40" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#0d1117] via-[#0d1117]/80 to-transparent" />
        <div className="relative z-10 flex h-full items-center justify-between px-8">
          <div>
            <p className="text-amber-400 text-xs tracking-widest mb-1">· XAUUSD</p>
            <h1 className="text-3xl font-bold text-white leading-tight">Trade Smarter<br />with AI</h1>
            <p className="text-gray-400 text-sm mt-2 max-w-md">Real Insights. Real Opportunities. A Smarter Way to Trade Gold.</p>
            <Link href="/analysis" className="inline-flex items-center gap-2 mt-4 px-4 py-2 bg-amber-500/20 border border-amber-500/30 text-amber-400 rounded-lg text-sm hover:bg-amber-500/30 transition-colors">
              Explore AI Analysis <span>→</span>
            </Link>
          </div>
          <div className="hidden lg:block text-right">
            <blockquote className="max-w-[260px] bg-black/40 backdrop-blur-sm border border-white/10 rounded-xl p-4">
              <p className="text-gray-300 text-sm italic">&ldquo;Successful trading is a combination of knowledge, discipline and emotion control.&rdquo;</p>
              <cite className="text-amber-400 text-xs mt-2 block not-italic">— AIGoldTrader</cite>
            </blockquote>
          </div>
        </div>
      </div>

      {/* ─── Market Ticker Strip ────────────────────────── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3">
        {[
          { sym: 'XAUUSD', label: 'Gold Spot', bid: current?.bid, spread: current?.spread, live: true },
          { sym: 'EURUSD', label: '', bid: '1.0713', spread: '-0.0001 (-0.20%)' },
          { sym: 'DXY', label: '', bid: '102.36', spread: '+0.18 (+0.18%)' },
          { sym: 'US10Y', label: '', bid: '4.112', spread: '-0.021 (-0.51%)' },
          { sym: 'BTCUSD', label: '', bid: '57,321', spread: '+1,234 (+2.20%)' },
        ].map(t => (
          <div key={t.sym} className={`bg-[#111827] border rounded-xl p-4 ${t.live ? 'border-amber-500/30' : 'border-gray-800'}`}>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs text-gray-400">{t.sym}</span>
              {t.label && <span className="text-[10px] text-gray-500">{t.label}</span>}
            </div>
            <p className="text-xl font-bold text-white tabular-nums">{t.live ? fmtPrice(t.bid) : t.bid}</p>
            <p className={`text-xs mt-0.5 ${t.spread?.startsWith('-') ? 'text-red-400' : 'text-emerald-400'}`}>
              {t.live ? (staleQuote ? 'Stale' : `Spread: ${fmtPrice(current?.spread)}`) : t.spread}
            </p>
          </div>
        ))}
      </div>

      {/* ─── Main Grid: Chart + Signal + Sentiment ───── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Chart Area */}
        <div className="lg:col-span-7 bg-[#111827] border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-white font-semibold flex items-center gap-2">
                XAUUSD <span className="text-gray-400 text-sm font-normal">Gold Spot / U.S. Dollar</span>
                <StatusDot ok={!staleQuote && ws === 'CONNECTED'} />
                <span className="text-xs text-gray-500">{ws === 'CONNECTED' ? 'Live' : ws}</span>
              </h2>
            </div>
          </div>
          <div className="text-3xl font-bold text-white tabular-nums">{fmtPrice(current?.bid)} <span className="text-sm text-emerald-400">+12.35 (+0.34%)</span></div>
          <div className="flex gap-4 text-xs text-gray-400 mt-2">
            <span>O {fmtPrice(current?.bid)}</span>
            <span>H —</span>
            <span>L —</span>
            <span>C {fmtPrice(current?.ask)}</span>
          </div>
          {/* Timeframe buttons */}
          <div className="flex gap-1 mt-4">
            {['1m','5m','15m','1h','4h','1D','1W'].map(tf => (
              <button key={tf} className={`px-3 py-1 rounded text-xs ${tf === '1h' ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30' : 'text-gray-400 hover:bg-white/5'}`}>{tf}</button>
            ))}
          </div>
          {/* Chart placeholder */}
          <div className="mt-4 h-[280px] bg-[#0a0f1a] rounded-lg border border-gray-800/50 flex items-center justify-center">
            <div className="text-center">
              <p className="text-gray-500 text-sm">TradingView Chart</p>
              <p className="text-gray-600 text-xs mt-1">จะเปิดใช้งานใน Phase 2</p>
              <Link href="/trading" className="text-amber-400 text-xs mt-2 inline-block hover:underline">เปิดหน้า Trading →</Link>
            </div>
          </div>
          {/* MA values */}
          <div className="flex gap-4 mt-3 text-xs">
            <span className="text-blue-400">MA 20: {fmtPrice(current?.bid)}</span>
            <span className="text-amber-400">MA 50: —</span>
            <span className="text-purple-400">MA 200: —</span>
          </div>
        </div>

        {/* Right Column: AI Signal + Sentiment */}
        <div className="lg:col-span-5 space-y-5">
          {/* AI Trading Signal */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex items-center gap-2">
                <span className="text-amber-400">⚡</span> AI Trading Signal
              </h2>
              <span className="text-xs text-gray-400">Confidence <span className="text-amber-400 font-bold text-lg">{confidence}%</span></span>
            </div>
            {plan ? (
              <>
                <div className={`flex items-center gap-4 p-4 rounded-xl ${direction === 'LONG' ? 'bg-emerald-500/10 border border-emerald-500/20' : direction === 'SHORT' ? 'bg-red-500/10 border border-red-500/20' : 'bg-gray-800/50 border border-gray-700'}`}>
                  <span className={`text-3xl font-black ${direction === 'LONG' ? 'text-emerald-400' : 'text-red-400'}`}>{direction === 'LONG' ? 'BUY' : 'SELL'}</span>
                  <div>
                    <p className="text-white font-semibold">XAUUSD</p>
                    <p className="text-gray-400 text-sm">{fmtPrice(current?.bid)}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
                  <div><span className="text-gray-400">Entry Zone</span><p className="text-white">{fmtPrice(plan.entry_lower)} - {fmtPrice(plan.entry_upper)}</p></div>
                  <div><span className="text-gray-400">Take Profit</span><p className="text-white">{plan.targets.slice(0,2).map(t => fmtPrice(t.price)).join(' / ')}</p></div>
                  <div><span className="text-gray-400">Stop Loss</span><p className="text-red-400">{fmtPrice(plan.stop_loss)}</p></div>
                  <div><span className="text-gray-400">Timeframe</span><p className="text-white">H1</p></div>
                </div>
                <div className="mt-3 text-xs text-gray-400">
                  <span className="text-gray-500">Rationale:</span> {plan.evidence.slice(0,2).map(e => e.description_th).join(' · ')}
                </div>
                <Link href="/trading" className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 bg-amber-500/15 border border-amber-500/30 text-amber-400 rounded-lg text-sm hover:bg-amber-500/25 transition-colors">
                  View Full Analysis <span>→</span>
                </Link>
              </>
            ) : (
              <div className="text-center py-8">
                <div className="w-16 h-16 mx-auto bg-gray-800 rounded-full flex items-center justify-center mb-3">
                  <span className="text-2xl">🔍</span>
                </div>
                <p className="text-gray-400 text-sm">ยังไม่มีสัญญาณที่ผ่านเงื่อนไข</p>
                <p className="text-gray-500 text-xs mt-1">ระบบกำลังวิเคราะห์ตลาด...</p>
              </div>
            )}
          </div>

          {/* Market Sentiment */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <h2 className="text-white font-semibold flex items-center gap-2 mb-4">
              <span className="text-amber-400">★</span> Market Sentiment
            </h2>
            <div className="flex items-center gap-6">
              {/* Donut-like display */}
              <div className="relative w-24 h-24 flex-shrink-0">
                <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                  <circle cx="18" cy="18" r="14" fill="none" stroke="#1f2937" strokeWidth="3" />
                  <circle cx="18" cy="18" r="14" fill="none" stroke="#10b981" strokeWidth="3" strokeDasharray="60 100" strokeLinecap="round" />
                  <circle cx="18" cy="18" r="14" fill="none" stroke="#f59e0b" strokeWidth="3" strokeDasharray="20 100" strokeDashoffset="-60" strokeLinecap="round" />
                  <circle cx="18" cy="18" r="14" fill="none" stroke="#ef4444" strokeWidth="3" strokeDasharray="8 100" strokeDashoffset="-80" strokeLinecap="round" />
                </svg>
                <div className="absolute inset-0 flex flex-col items-center justify-center">
                  <span className="text-xl font-bold text-white">{data?.structure?.[0]?.regime === 'TRENDING_UP' ? '68' : data?.structure?.[0]?.regime === 'TRENDING_DOWN' ? '32' : '50'}%</span>
                  <span className="text-[10px] text-gray-400">{name(data?.structure?.[0]?.regime)}</span>
                </div>
              </div>
              <div className="space-y-2 text-sm">
                <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-emerald-400" /> <span className="text-gray-300">68% Bullish</span></div>
                <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-amber-400" /> <span className="text-gray-300">24% Neutral</span></div>
                <div className="flex items-center gap-2"><span className="w-3 h-3 rounded-full bg-red-400" /> <span className="text-gray-300">8% Bearish</span></div>
              </div>
            </div>
          </div>

          {/* Top News */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold">Top News</h2>
              <Link href="/calendar" className="text-amber-400 text-xs hover:underline">See All</Link>
            </div>
            <div className="space-y-3">
              {(data?.calendar_events || []).slice(0, 3).map((e: EconomicEvent) => (
                <div key={e.id} className="flex gap-3 group">
                  <div className="w-12 h-12 bg-gray-800 rounded-lg flex-shrink-0 flex items-center justify-center text-lg">📰</div>
                  <div className="min-w-0">
                    <p className="text-sm text-white truncate group-hover:text-amber-400 transition-colors">{eventName(e)}</p>
                    <p className="text-xs text-gray-500">{e.currency} · {bangkok(e.scheduled_at)}</p>
                  </div>
                </div>
              ))}
              {(!data?.calendar_events?.length) && <p className="text-gray-500 text-sm">ไม่มีข่าวในขณะนี้</p>}
            </div>
          </div>
        </div>
      </div>

      {/* ─── Bottom Grid: Portfolio + Strategy + Calendar ─ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Portfolio Overview */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">Portfolio Overview</h2>
            <span className="text-xs text-gray-400 bg-gray-800 px-2 py-1 rounded">Last 30 Days ▾</span>
          </div>
          <p className="text-xs text-gray-400">Total Equity</p>
          <p className="text-2xl font-bold text-white">$12,450.32</p>
          <p className="text-xs text-emerald-400 mt-0.5">+2.35% (+$285.41)</p>
          <div className="grid grid-cols-4 gap-2 mt-4 text-center">
            {[
              { label: 'Balance', value: '$12,150.00' },
              { label: 'Floating P/L', value: '+$300.32', color: 'text-emerald-400' },
              { label: 'Win Rate', value: '68.4%' },
              { label: 'Total Trades', value: '142' },
            ].map(s => (
              <div key={s.label}>
                <p className="text-[10px] text-gray-500">{s.label}</p>
                <p className={`text-sm font-semibold ${s.color || 'text-white'}`}>{s.value}</p>
              </div>
            ))}
          </div>
          <p className="text-[10px] text-gray-600 mt-3 text-center">Paper Trading · ข้อมูลจำลอง · Phase 7</p>
        </div>

        {/* Strategy Performance */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">Strategy Performance</h2>
            <span className="text-xs text-gray-400 bg-gray-800 px-2 py-1 rounded">This Month ▾</span>
          </div>
          <div className="space-y-3">
            {(data?.strategies || [
              { id: 'STRAT01', name: 'Trend Following' },
              { id: 'STRAT02', name: 'Breakout Strategy' },
              { id: 'STRAT03', name: 'Mean Reversion' },
              { id: 'STRAT04', name: 'News Trading' },
              { id: 'STRAT05', name: 'AI Adaptive' },
            ]).slice(0, 5).map((s, i) => {
              const pcts = [12.4, 8.7, 3.1, -1.2, 10.6];
              const pct = pcts[i] || 0;
              return (
                <div key={s.id} className="flex items-center gap-3">
                  <span className="text-xs text-gray-400 w-[120px] truncate">{s.name}</span>
                  <div className="flex-1 h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${pct >= 0 ? 'bg-emerald-500' : 'bg-red-500'}`} style={{ width: `${Math.min(Math.abs(pct) * 5, 100)}%` }} />
                  </div>
                  <span className={`text-xs font-medium w-14 text-right ${pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>{pct >= 0 ? '+' : ''}{pct}%</span>
                </div>
              );
            })}
          </div>
          <p className="text-[10px] text-gray-600 mt-3 text-center">ข้อมูลจำลอง · รอ Phase 8-9</p>
        </div>

        {/* Economic Calendar */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">Economic Calendar</h2>
            <Link href="/calendar" className="text-amber-400 text-xs hover:underline">See All</Link>
          </div>
          <div className="space-y-2">
            {(data?.calendar_events || []).slice(0, 4).map((e: EconomicEvent) => (
              <div key={e.id} className="flex items-center gap-3 py-2 border-b border-gray-800/50 last:border-0">
                <span className="text-xs text-gray-400 w-12 tabular-nums">{bangkok(e.scheduled_at).slice(11, 16)}</span>
                <span className="text-xs">🇺🇸</span>
                <span className="text-xs text-gray-400 w-8">{e.currency}</span>
                <span className="text-xs text-gray-300 flex-1 truncate">{eventName(e)}</span>
                <ImpactBadge impact={e.impact} />
              </div>
            ))}
            {(!data?.calendar_events?.length) && <p className="text-gray-500 text-sm text-center py-4">ไม่มีกำหนดการ</p>}
          </div>
        </div>
      </div>

      {/* ─── Safety Footer ───────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-3 bg-[#111827] border border-amber-500/20 rounded-xl text-xs">
        <div className="flex items-center gap-2">
          <span className="text-amber-400 font-bold">PAPER</span>
          <span className="text-gray-400">· วิเคราะห์เท่านั้น · Auto Trading: ปิด · ไม่อนุญาตเงินจริง</span>
        </div>
        {old && <span className="text-amber-400">⚠ ข้อมูลล้าสมัย</span>}
        {error && <span className="text-red-400">{error}</span>}
      </div>
    </div>
  );
}
