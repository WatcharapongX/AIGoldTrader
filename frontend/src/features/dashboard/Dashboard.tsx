"use client";
import { useEffect, useState } from 'react';
import Link from 'next/link';
import Image from 'next/image';
import { api } from '@/lib/api';
import { MarketConnection, type ConnectionState } from '@/features/chart/transport';
import type { DashboardSummary, EconomicEvent } from '@/types/dashboard.generated';
import type { Candle, Quote, MarketDataStatus } from '@/types/market.generated';
import { bangkok, eventName } from '@/features/news/thai';
import { names as strategyLabels } from '@/features/strategy/thai';
import { parseDashboard } from './contracts';
import { TradingStatus } from '@/components/layout/RuntimeStatus';
import type { HealthResponse } from '@/types';
import { RealtimeMarketChart } from './RealtimeMarketChart';

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
  if (p === null || p === undefined || p === '') return '—';
  const n = typeof p === 'string' ? parseFloat(p) : p;
  return !Number.isFinite(n) ? '—' : n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function mergeCandles(current: Candle[], incoming: Candle[], snapshot: boolean) {
  if (snapshot) return incoming.slice(-300);
  const next = [...current];
  for (const candle of incoming) {
    const last = next.at(-1);
    if (last?.open_time === candle.open_time) next[next.length - 1] = candle;
    else if (!last || Date.parse(candle.open_time) > Date.parse(last.open_time)) next.push(candle);
  }
  return next.slice(-300);
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
  return <span className={`text-[10px] px-2 py-0.5 rounded-full border ${colors[impact] || colors.LOW}`}>{impact === 'HIGH' ? 'High' : impact === 'MEDIUM' ? 'Medium' : impact === 'LOW' ? 'Low' : impact}</span>;
}

/* ══════════════════════════════════════════════════════════ */
export function Dashboard() {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [error, setError] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [marketCandles, setMarketCandles] = useState<Candle[]>([]);
  const [marketStatus, setMarketStatus] = useState<MarketDataStatus | null>(null);
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
      msg => {
        if (abort.signal.aborted) return;
        setMarketStatus(msg.status);
        setQuote(msg.quote);
        if (msg.type === 'snapshot') setMarketCandles(msg.candles);
        else if (msg.candles.length) {
          setMarketCandles(value => mergeCandles(value, msg.candles, false));
        }
      },
      state => { if (!abort.signal.aborted) setWs(state); },
      'XAUUSD', 'M5',
    );
    connection.start(); void refresh();
    const timer = setInterval(refresh, 30000);
    const ticker = setInterval(() => setClock(Date.now()), 1000);
    return () => { abort.abort(); clearInterval(timer); clearInterval(ticker); connection.stop(); };
  }, []);

  return <DashboardView data={data} error={error} quote={quote} marketStatus={marketStatus}
    marketCandles={marketCandles} ws={ws} clock={clock} />;
}

export function DashboardView({data, error, quote, marketStatus, marketCandles, ws, clock}: {
  data: DashboardSummary | null; error: string; quote: Quote | null;
  marketStatus: MarketDataStatus | null; marketCandles: Candle[];
  ws: ConnectionState; clock: number;
}) {
  const market = marketStatus || data?.market;
  const current = market && quote?.source === market.source && quote.symbol === 'XAUUSD' ? quote
    : market && data?.quote?.source === market.source ? data.quote : null;
  const old = !!data && (!!error || clock - Date.parse(data.generated_at) > 65000);
  const staleQuote = !current || !clock || clock < Date.parse(current.timestamp) ||
    clock - Date.parse(current.timestamp) > (market?.stale_after_seconds || 5) * 1000;
  const liveMarket = !staleQuote && !error && ws === 'CONNECTED' && market?.status === 'CONNECTED' &&
    current?.status === 'CONNECTED' && (market.mode === 'DEMO' || market.mode === 'LIVE');
  const marketLabel = market?.mode === 'SIMULATED' ? 'SIMULATED DATA' : liveMarket ? 'Live Market Data'
    : market ? 'Market Data: ' + market.status + ' · ' + (staleQuote ? 'STALE / ไม่พร้อม' : 'ข้อมูลล่าสุด') : 'Market Data: UNKNOWN';
  const visibleCandles = market ? marketCandles.filter(c => c.source === market.source && c.symbol === 'XAUUSD' && c.timeframe === 'M5') : [];
  const latestCandle = visibleCandles.at(-1);
  const safetyHealth = !old && data ? {trading_mode:data.trading_mode, live_auto_trading:data.live_auto_trading} as HealthResponse : null;
  const plan = clock > 0 && !old && !data?.strategy_stale && data?.current_plan && Date.parse(data.current_plan.expires_at) > clock ? data.current_plan : null;
  const direction = plan?.direction || 'NEUTRAL';

  /* ── Render ────────────────────────────────────────────── */
  return (
    <div className="space-y-5 min-w-0" data-testid="dashboard">
      <div className="rounded-xl border border-amber-500/30 bg-[#111827] p-3">
        <TradingStatus health={safetyHealth} />
        {error && <p role="alert" className="text-red-400 text-sm">{error} · ข้อมูลเดิมอาจล้าสมัย</p>}
      </div>
      {/* ─── Hero Banner ─────────────────────────────────── */}
      <div className="relative overflow-hidden rounded-2xl min-h-[210px]">
        <Image src="/images/login-bg.jpg" alt="" fill className="object-cover opacity-40" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#0d1117] via-[#0d1117]/80 to-transparent" />
        <div className="relative z-10 flex h-full items-center justify-between px-4 md:px-8 py-5">
          <div>
            <p className="text-amber-400 text-xs tracking-widest mb-1">· XAUUSD</p>
            <h1 className="text-3xl font-bold text-white leading-tight">Trade Smarter<br />with Verified Data</h1>
            <p className="text-gray-400 text-sm mt-2 max-w-md">ราคา กราฟ และข่าวพร้อมแหล่งที่มาและสถานะความสดของข้อมูล</p>
            <Link href="/analysis" className="inline-flex items-center gap-2 mt-4 px-4 py-2 bg-amber-500/20 border border-amber-500/30 text-amber-400 rounded-lg text-sm hover:bg-amber-500/30 transition-colors">
              เปิดหน้าวิเคราะห์ <span>→</span>
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
          {
            sym: 'XAUUSD',
            label: market ? market.source + ' · ' + market.mode : 'UNKNOWN / ยังไม่มีข้อมูล',
            bid: current?.bid,
            spread: current?.spread,
            live: true,
          },
          { sym: 'EURUSD', label: 'ยังไม่เชื่อมต่อข้อมูล', bid: null, spread: null },
          { sym: 'DXY', label: 'ยังไม่เชื่อมต่อข้อมูล', bid: null, spread: null },
          { sym: 'US10Y', label: 'ยังไม่เชื่อมต่อข้อมูล', bid: null, spread: null },
          { sym: 'BTCUSD', label: 'ยังไม่เชื่อมต่อข้อมูล', bid: null, spread: null },
        ].map(t => (
          <div key={t.sym} className={`bg-[#111827] border rounded-xl p-4 ${t.live ? 'border-amber-500/30' : 'border-gray-800'}`}>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs text-gray-400">{t.sym}</span>
              {t.label && <span className="text-[10px] text-gray-500">{t.label}</span>}
            </div>
            <p className="text-xl font-bold text-white tabular-nums">{fmtPrice(t.bid)}</p>
            <p className={`text-xs mt-0.5 ${t.live && !staleQuote ? 'text-emerald-400' : 'text-gray-500'}`}>
              {t.live ? (staleQuote ? 'ข้อมูลราคาล้าสมัย/ไม่พร้อม' : `Spread: ${fmtPrice(current?.spread)}`) : '—'}
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
              <h2 className="text-white font-semibold flex flex-wrap items-center gap-2">
                XAUUSD <span className="text-gray-400 text-sm font-normal">Gold Spot / U.S. Dollar</span>
                <StatusDot ok={liveMarket} />
                <span className="text-xs text-gray-500">{marketLabel}</span>
              </h2>
            </div>
          </div>
          <div className="text-3xl font-bold text-white tabular-nums">
            {fmtPrice(current?.bid)}

          </div>
          <p className="text-xs text-gray-400 mt-2" data-testid="quote-provenance">{marketLabel} · {market?.source || 'UNKNOWN'}<br />Quote: {current?.timestamp || '—'}</p>
          <p className="text-xs text-gray-500 mt-2">M5 candle: {latestCandle?.open_time || '—'} · {latestCandle ? (latestCandle.is_closed ? 'CLOSED' : 'FORMING') : 'ยังไม่มีข้อมูล'}</p>
          <div data-testid="ohlc" className="flex flex-wrap gap-3 text-xs text-gray-400 mt-2">
            <span>O {fmtPrice(latestCandle?.open)}</span>
            <span>H {fmtPrice(latestCandle?.high)}</span>
            <span>L {fmtPrice(latestCandle?.low)}</span>
            <span>C {fmtPrice(latestCandle?.close)}</span>
            <span>Bid {fmtPrice(current?.bid)}</span>
            <span>Ask {fmtPrice(current?.ask)}</span>
          </div>
          <div className="flex items-center gap-3 mt-4">
            <span className="px-3 py-1 rounded text-xs bg-amber-500/20 text-amber-400 border border-amber-500/30">M5 · {marketLabel}</span>
            <span className="text-xs text-gray-500">{market?.source || 'UNKNOWN'}</span>
          </div>
          <div className="relative mt-4 h-[280px] bg-[#0a0f1a] rounded-lg border border-gray-800/50 overflow-hidden">
            <RealtimeMarketChart candles={visibleCandles} />
            {!visibleCandles.length && (
              <div className="absolute inset-0 flex items-center justify-center text-center bg-[#0a0f1a]/80">
                <div>
                  <p className="text-gray-400 text-sm">ยังไม่มีข้อมูลกราฟ XAUUSD</p>
                  <p className="text-gray-600 text-xs mt-1">{market?.detail || 'รอข้อมูลแท่งเทียน M5'}</p>
                </div>
              </div>
            )}
          </div>
          <Link href="/trading" className="inline-block text-amber-400 text-sm mt-3">เปิดกราฟ XAUUSD แบบละเอียด →</Link>
          <div data-testid="moving-averages" className="flex flex-wrap gap-4 mt-3 text-xs">
            <span className="text-blue-400">MA 20: —</span>
            <span className="text-amber-400">MA 50: —</span>
            <span className="text-purple-400">MA 200: —</span>
          </div>
        </div>

        {/* Right Column: Strategy + Structure */}
        <div className="lg:col-span-5 space-y-5">
          {/* Deterministic strategy setup */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex flex-wrap items-center gap-2">
                <span className="text-amber-400">⚡</span> Strategy Setup
              </h2>
              <span data-testid="setup-score" className="text-xs text-gray-400">Setup Score <span className="text-amber-400 font-bold text-lg">{plan ? plan.score + '/100' : '—'}</span></span>
            </div>
            <p className="text-xs text-gray-400 mb-3">คะแนนตามกฎ ไม่ใช่ความน่าจะเป็นและไม่ใช่ผลจาก AI</p>
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
                  <div><span className="text-gray-400">Strategy</span><p className="text-white">{data?.candidates.find(c => c.id === plan.candidate_id)?.strategy_id || '—'}</p></div>
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
                <p className="text-gray-500 text-xs mt-1">{!data || old ? "ข้อมูลไม่พร้อมใช้งาน / ล้าสมัย" : "ยังไม่มี Setup ที่พร้อมจากข้อมูลล่าสุด"}</p>
              </div>
            )}
          </div>

          {/* Authoritative market structure */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <h2 className="text-white font-semibold flex flex-wrap items-center gap-2 mb-4">
              <span className="text-amber-400">★</span> Market Structure
            </h2>
            <div className="rounded-xl border border-gray-800 bg-[#0a0f1a] p-5">
              <p className="text-2xl font-bold text-white">{name(data?.structure?.[0]?.regime)}</p>
              <p className="text-xs text-gray-400 mt-2">
                {data?.structure?.[0]?.timeframe ? `ผลวิเคราะห์โครงสร้าง ${data.structure[0].timeframe}` : 'ยังไม่มีข้อมูลโครงสร้างตลาด'}
              </p>
              <p className="text-[11px] text-gray-600 mt-2">ไม่ใช่ sentiment percentage และไม่ใช่คำสั่งซื้อขาย</p>
            </div>
          </div>

          {/* Top News */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-white font-semibold">Top News</h2>
                <p className="text-[10px] text-gray-500 mt-0.5">
                  {data?.news_provider
                    ? `${data.news_provider.source} · ${data.news_provider.source_mode} · ${name(data.news_provider.state)}`
                    : 'กำลังตรวจสอบ Forex Factory'}
                </p>
              </div>
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
              {(!data?.calendar_events?.length) && <p className="text-gray-500 text-sm">{data?.news_provider && !old ? "ไม่มีรายการในช่วงข้อมูลที่ได้รับ" : "ข้อมูลข่าวไม่พร้อมใช้งาน"}</p>}
            </div>
          </div>
        </div>
      </div>

      {/* ─── Bottom Grid: Portfolio + Strategy + Calendar ─ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Paper portfolio availability */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">Portfolio Overview</h2>
            <span className="text-xs text-amber-400 bg-amber-500/10 border border-amber-500/20 px-2 py-1 rounded">PAPER · ยังไม่เปิดใช้งาน</span>
          </div>
          <p className="text-sm text-gray-400">จะพร้อมใช้งานหลังเปิด Paper Trading และมีข้อมูลบัญชีจริง</p>
        </div>

        {/* Strategy performance availability */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold">Strategy Performance</h2>
            <span className="text-xs text-gray-500 bg-gray-800 px-2 py-1 rounded">ยังไม่มีสถิติ</span>
          </div>
          <p className="text-sm text-gray-400">จะพร้อมใช้งานหลังมีประวัติ Paper Trading สำหรับวิเคราะห์ผลการเทรด</p>
        </div>

        {/* Economic Calendar */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-white font-semibold">Economic Calendar</h2>
              <p className="text-[10px] text-gray-500 mt-0.5">
                {data?.news_provider?.source === 'forex_factory'
                  ? `Forex Factory · ${data.news_provider.source_mode}`
                  : data?.news_provider?.source || 'UNKNOWN / ยังไม่มีข้อมูลผู้ให้บริการ'}
              </p>
            </div>
            <Link href="/calendar" className="text-amber-400 text-xs hover:underline">See All</Link>
          </div>
          <p className="text-xs text-gray-400 mb-3">Health: {old ? 'STALE' : data?.news_provider?.state || 'UNKNOWN'}</p>
          <div className="space-y-2">
            {(data?.calendar_events || []).slice(0, 4).map((e: EconomicEvent) => (
              <div key={e.id} className="flex flex-wrap items-center gap-3 py-2 border-b border-gray-800/50 last:border-0">
                <span className="text-xs text-gray-400 w-12 tabular-nums">{bangkok(e.scheduled_at).slice(11, 16)}</span>
                <span className="text-xs">🇺🇸</span>
                <span className="text-xs text-gray-400 w-8">{e.currency}</span>
                <span className="text-xs text-gray-300 flex-1 truncate">{eventName(e)}</span>
                <ImpactBadge impact={e.impact} />
                <p className="w-full text-xs text-gray-400" data-testid="calendar-values">
                  Forecast {e.forecast ?? '—'} · Previous {e.previous ?? '—'} · Actual {e.actual ?? '—'}
                </p>
              </div>
            ))}
            {(!data?.calendar_events?.length) && <p className="text-gray-500 text-sm text-center py-4">{data?.news_provider && !old ? "ไม่มีรายการในช่วงข้อมูลที่ได้รับ" : "ข้อมูลปฏิทินไม่พร้อมใช้งาน"}</p>}
          </div>
        </div>
      </div>

      {/* ─── Safety Footer ───────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-[#111827] border border-amber-500/20 rounded-xl text-xs">
        <div className="flex items-center gap-2">
          <span className="text-gray-400">วิเคราะห์เท่านั้น · ไม่มีการส่งคำสั่งซื้อขาย</span>
        </div>
        {old && <span className="text-amber-400">⚠ ข้อมูลล้าสมัย</span>}
        {error && <span className="text-red-400">{error}</span>}
      </div>
    </div>
  );
}
