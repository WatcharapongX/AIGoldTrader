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
import {
  parseKillSwitch,
  parsePortfolioRisk,
  parseRiskPolicy,
  type KillSwitchData,
  type PortfolioRiskData,
  type RiskPolicyData,
} from '@/features/risk/contracts';

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

  // Phase 5 Risk states
  const [portfolioRisk, setPortfolioRisk] = useState<PortfolioRiskData | null>(null);
  const [killSwitch, setKillSwitch] = useState<KillSwitchData | null>(null);
  const [riskPolicy, setRiskPolicy] = useState<RiskPolicyData | null>(null);

  useEffect(() => {
    const abort = new AbortController();
    let busy = false;
    const refresh = async () => {
      if (busy) return; busy = true;
      try {
        const [dashRes, portRes, ksRes, polRes] = await Promise.allSettled([
          api.get('/dashboard/summary', { signal: abort.signal }).then(parseDashboard),
          api.get('/risk/portfolio', { signal: abort.signal }).then(parsePortfolioRisk),
          api.get('/risk/kill-switch', { signal: abort.signal }).then(parseKillSwitch),
          api.get('/risk/policy', { signal: abort.signal }).then(parseRiskPolicy),
        ]);
        if (!abort.signal.aborted) {
          if (dashRes.status === 'fulfilled') {
            setData(dashRes.value);
            setError('');
          } else {
            setError('โหลดข้อมูลไม่สำเร็จ');
          }
          if (portRes.status === 'fulfilled') setPortfolioRisk(portRes.value);
          if (ksRes.status === 'fulfilled') setKillSwitch(ksRes.value);
          if (polRes.status === 'fulfilled') setRiskPolicy(polRes.value);
        }
      } catch {
        if (!abort.signal.aborted) setError('โหลดข้อมูลไม่สำเร็จ');
      } finally {
        busy = false;
      }
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

  return (
    <DashboardView
      data={data}
      error={error}
      quote={quote}
      marketStatus={marketStatus}
      marketCandles={marketCandles}
      ws={ws}
      clock={clock}
      portfolioRisk={portfolioRisk}
      killSwitch={killSwitch}
      riskPolicy={riskPolicy}
    />
  );
}

export function DashboardView({
  data,
  error,
  quote,
  marketStatus,
  marketCandles,
  ws,
  clock,
  portfolioRisk,
  killSwitch,
  riskPolicy,
}: {
  data: DashboardSummary | null;
  error: string;
  quote: Quote | null;
  marketStatus: MarketDataStatus | null;
  marketCandles: Candle[];
  ws: ConnectionState;
  clock: number;
  portfolioRisk?: PortfolioRiskData | null;
  killSwitch?: KillSwitchData | null;
  riskPolicy?: RiskPolicyData | null;
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
  const calcMA = (period: number): number | null => {
    if (visibleCandles.length < period) return null;
    const slice = visibleCandles.slice(-period);
    const sum = slice.reduce((acc, c) => acc + Number(c.close), 0);
    return sum / period;
  };
  const ma20 = calcMA(20);
  const ma50 = calcMA(50);
  const ma200 = calcMA(200);
  const safetyHealth = !old && data ? {trading_mode:data.trading_mode, live_auto_trading:data.live_auto_trading} as HealthResponse : null;
  const plan = clock > 0 && !old && !data?.strategy_stale && data?.current_plan && Date.parse(data.current_plan.expires_at) > clock ? data.current_plan : null;
  const direction = plan?.direction || 'NEUTRAL';

  // Global Session Indicator
  const currentUtcHour = clock
    ? new Date(clock).getUTCHours() + new Date(clock).getUTCMinutes() / 60
    : new Date().getUTCHours() + new Date().getUTCMinutes() / 60;

  const sessionName = currentUtcHour >= 13 && currentUtcHour < 16.5
    ? 'London / NY Overlap (High Liquidity)'
    : currentUtcHour >= 13 && currentUtcHour < 21
    ? 'New York Session'
    : currentUtcHour >= 8 && currentUtcHour < 16.5
    ? 'London Session'
    : currentUtcHour >= 0 && currentUtcHour < 9
    ? 'Asian Session'
    : 'Inter-Session Transition';

  /* ── Render ────────────────────────────────────────────── */
  return (
    <div className="space-y-5 min-w-0" data-testid="dashboard">
      <div className="rounded-xl border border-amber-500/30 bg-[#111827] p-3">
        <TradingStatus health={safetyHealth} />
        {error && <p role="alert" className="text-red-400 text-sm">{error} · ข้อมูลเดิมอาจล้าสมัย</p>}
      </div>

      {/* ─── Hero Banner: Executive Operations Center ────── */}
      <div className="relative overflow-hidden rounded-2xl min-h-[220px]">
        <Image src="/images/login-bg.jpg" alt="" fill className="object-cover opacity-40" />
        <div className="absolute inset-0 bg-gradient-to-r from-[#0d1117] via-[#0d1117]/85 to-transparent" />
        <div className="relative z-10 flex flex-col justify-between h-full px-4 md:px-8 py-5">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div>
              <div className="flex flex-wrap items-center gap-2 mb-1.5">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-amber-400 text-xs font-semibold tracking-widest uppercase">
                  XAUUSD · EXECUTIVE TRADING OPERATIONS
                </span>
                <span className="text-gray-500 text-xs font-mono">|</span>
                <span className="text-xs bg-amber-500/15 border border-amber-500/30 text-amber-300 px-2 py-0.5 rounded-full font-medium">
                  {sessionName}
                </span>
              </div>
              <h1 className="text-2xl md:text-3xl font-bold text-white leading-tight">
                Trade Smarter with Verified Data
              </h1>
              <p className="text-gray-400 text-xs md:text-sm mt-1.5 max-w-xl leading-relaxed">
                ภาพรวมตลาดทองคำ ระบบคัดกรองสัญญาณเทรด และการควบคุมความเสี่ยงระดับพอร์ตโฟลิโอ (Fail-Closed Risk Gate)
              </p>
            </div>

            <div className="hidden xl:block text-right">
              <blockquote className="max-w-[260px] bg-black/50 backdrop-blur-sm border border-white/10 rounded-xl p-3.5 text-left">
                <p className="text-gray-300 text-xs italic">&ldquo;Successful trading is a combination of knowledge, discipline and emotion control.&rdquo;</p>
                <cite className="text-amber-400 text-[11px] mt-1.5 block not-italic font-semibold">— AIGoldTrader</cite>
              </blockquote>
            </div>
          </div>

          {/* Quick Command Chips Hub */}
          <div className="flex flex-wrap items-center gap-2 mt-4 pt-3 border-t border-white/10">
            <span className="text-[11px] text-gray-400 uppercase font-semibold mr-1">Workspace Hub:</span>
            <Link href="/trading" className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/40 text-amber-300 rounded-lg text-xs font-medium transition-colors">
              <span>📊</span>
              <span>Market Overview</span>
            </Link>
            <Link href="/analysis" className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/15 border border-white/15 text-gray-200 rounded-lg text-xs font-medium transition-colors">
              <span>📐</span>
              <span>SMC Analysis</span>
            </Link>
            <Link href="/signals" className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/10 hover:bg-white/15 border border-white/15 text-gray-200 rounded-lg text-xs font-medium transition-colors">
              <span>🤖</span>
              <span>Trading Signals</span>
            </Link>
            <Link href="/risk" className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-emerald-500/15 hover:bg-emerald-500/25 border border-emerald-500/30 text-emerald-300 rounded-lg text-xs font-medium transition-colors">
              <span>🛡️</span>
              <span>Risk Management Desk</span>
            </Link>
            <Link href="/calendar" className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-400 hover:text-gray-200 rounded-lg text-xs transition-colors">
              <span>📅</span>
              <span>Economic Calendar</span>
            </Link>
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

      {/* ─── Main Grid: Chart + Signal + Structure ──────── */}
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
          <Link href="/trading" className="inline-block text-amber-400 text-sm mt-3 hover:underline">
            เปิดหน้า Market Overview แบบละเอียด →
          </Link>
          <div data-testid="moving-averages" className="flex flex-wrap gap-4 mt-3 text-xs">
            <span className="text-blue-400">MA 20: {ma20 !== null ? fmtPrice(ma20) : '—'}</span>
            <span className="text-amber-400">MA 50: {ma50 !== null ? fmtPrice(ma50) : '—'}</span>
            <span className="text-purple-400">MA 200: {ma200 !== null ? fmtPrice(ma200) : '—'}</span>
          </div>
        </div>

        {/* Right Column: Strategy + Structure + Macro Context */}
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
                <Link href="/signals" className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 bg-amber-500/15 border border-amber-500/30 text-amber-400 rounded-lg text-sm hover:bg-amber-500/25 transition-colors">
                  ดูรายละเอียดสัญญาณเทรดทั้งหมด (Signals) <span>→</span>
                </Link>
              </>
            ) : (
              <div className="text-center py-8">
                <div className="w-16 h-16 mx-auto bg-gray-800 rounded-full flex items-center justify-center mb-3">
                  <span className="text-2xl">🔍</span>
                </div>
                <p className="text-gray-400 text-sm">ยังไม่มีสัญญาณที่ผ่านเงื่อนไข</p>
                <p className="text-gray-500 text-xs mt-1">{!data || old ? "ข้อมูลไม่พร้อมใช้งาน / ล้าสมัย" : "ยังไม่มี Setup ที่พร้อมจากข้อมูลล่าสุด"}</p>
                <Link href="/signals" className="inline-block text-amber-400 text-xs mt-3 hover:underline">
                  ไปที่หน้า Trading Signals →
                </Link>
              </div>
            )}
          </div>

          {/* Authoritative market structure */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <h2 className="text-white font-semibold flex flex-wrap items-center gap-2 mb-3">
              <span className="text-amber-400">★</span> Market Structure
            </h2>
            <div className="rounded-xl border border-gray-800 bg-[#0a0f1a] p-4">
              <p className="text-2xl font-bold text-white">{name(data?.structure?.[0]?.regime)}</p>
              <p className="text-xs text-gray-400 mt-1">
                {data?.structure?.[0]?.timeframe ? `ผลวิเคราะห์โครงสร้าง ${data.structure[0].timeframe}` : 'ยังไม่มีข้อมูลโครงสร้างตลาด'}
              </p>
              <p className="text-[11px] text-gray-600 mt-1">ไม่ใช่ sentiment percentage และไม่ใช่คำสั่งซื้อขาย</p>
            </div>
            <Link href="/analysis" className="mt-3 block text-xs text-amber-400 hover:underline">
              เปิดห้องวิเคราะห์ SMC & MTF แบบเต็ม (Analysis Desk) →
            </Link>
          </div>

          {/* Top News & Macro Context */}
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
                  <div className="w-10 h-10 bg-gray-800 rounded-lg flex-shrink-0 flex items-center justify-center text-base">📰</div>
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

      {/* ─── Bottom Grid: Portfolio Risk + Strategy Audit + Economic Calendar ─ */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* Paper portfolio & Risk Governance (Phase 5 Connected!) */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex items-center gap-1.5">
                <span>🛡️</span> Portfolio & Risk Gate
              </h2>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                killSwitch?.state === 'ACTIVE'
                  ? 'bg-red-500/20 text-red-400 border-red-500/30'
                  : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
              }`}>
                {killSwitch?.state === 'ACTIVE' ? 'KILL SWITCH: ACTIVE' : 'KILL SWITCH: NORMAL'}
              </span>
            </div>

            <div className="space-y-2 text-xs text-gray-300">
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">โหมดการซื้อขาย:</span>
                <span className="text-amber-400 font-semibold">PAPER TRADING</span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">ความเสี่ยงรวมพอร์ต:</span>
                <span className="font-mono text-white font-bold">
                  {portfolioRisk?.total_risk_pct && Number(portfolioRisk.total_risk_pct) > 0
                    ? `${Number(portfolioRisk.total_risk_pct).toFixed(2)}`
                    : '0.00 / ปกติ'}
                </span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">เพดานขาดทุนรายวัน:</span>
                <span className="font-mono text-gray-200">
                  {riskPolicy?.daily_loss_limit_pct ? `${Math.round(Number(riskPolicy.daily_loss_limit_pct))}%` : '3%'}
                </span>
              </div>
            </div>

            <p className="text-xs text-gray-400 mt-2">
              จะพร้อมใช้งานหลังเปิด Paper Trading และมีข้อมูลบัญชีจริง
            </p>
          </div>

          <Link
            href="/risk"
            className="mt-4 w-full inline-flex items-center justify-center gap-1.5 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 rounded-lg text-xs font-semibold transition-colors"
          >
            <span>เข้าสู่ห้องบริหารความเสี่ยง (Risk Desk) →</span>
          </Link>
        </div>

        {/* Strategy performance & Governance */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex items-center gap-1.5">
                <span>📈</span> Strategy Performance
              </h2>
              <span className="text-[10px] text-gray-400 bg-gray-800 px-2 py-0.5 rounded border border-gray-700">
                AUDIT VERIFIED
              </span>
            </div>

            <div className="space-y-2 text-xs text-gray-300">
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">กลยุทธ์ที่ประเมิน:</span>
                <span className="text-gray-200">7 Profiles (SMC / Scalp / Swing)</span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">ความเสี่ยงต่อไม้:</span>
                <span className="font-mono text-gray-200">
                  {riskPolicy?.max_risk_per_trade_pct ? `${Math.round(Number(riskPolicy.max_risk_per_trade_pct))}%` : '1%'}
                </span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">บันทึกประวัติ:</span>
                <span className="text-gray-300">Immutable Audit Log</span>
              </div>
            </div>

            <p className="text-xs text-gray-400 mt-2">
              จะพร้อมใช้งานหลังมีประวัติ Paper Trading สำหรับวิเคราะห์ผลการเทรด
            </p>
          </div>

          <Link
            href="/journal"
            className="mt-4 w-full inline-flex items-center justify-center gap-1.5 py-2 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 hover:text-white rounded-lg text-xs font-medium transition-colors"
          >
            <span>ดูบันทึกประวัติ (Trade Journal) →</span>
          </Link>
        </div>

        {/* Economic Calendar */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
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

          <Link
            href="/calendar"
            className="mt-4 w-full inline-flex items-center justify-center gap-1.5 py-2 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 text-amber-400 rounded-lg text-xs font-semibold transition-colors"
          >
            <span>เปิดปฏิทินเศรษฐกิจฉบับเต็ม →</span>
          </Link>
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
