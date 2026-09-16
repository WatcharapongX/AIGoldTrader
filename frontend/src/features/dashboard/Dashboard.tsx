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
import type { AccountSnapshotData, HealthResponse, SystemStatusResponse } from '@/types';
import { RealtimeMarketChart } from './RealtimeMarketChart';
import {
  parseAccountSnapshot,
  parseKillSwitch,
  parsePortfolioRisk,
  parseRiskDecisions,
  parseRiskPolicy,
  type KillSwitchData,
  type PortfolioRiskData,
  type RiskDecisionData,
  type RiskPolicyData,
} from '@/features/risk/contracts';

/* ── Thai labels ──────────────────────────────────────────── */
const states: Record<string, string> = {
  HEALTHY: 'พร้อม',
  DEGRADED: 'ตรวจสอบ',
  STALE: 'ล้าสมัย',
  UNAVAILABLE: 'ไม่พร้อม',
  UNKNOWN: 'ยังไม่ยืนยัน',
  DISABLED: 'ปิด',
  CONNECTED: 'เชื่อมต่อ',
  CONNECTING: 'กำลังเชื่อม',
  RECONNECTING: 'เชื่อมใหม่',
  DISCONNECTED: 'ขาดการเชื่อมต่อ',
  ERROR: 'ผิดพลาด',
  BULLISH: 'ขาขึ้น',
  BEARISH: 'ขาลง',
  NEUTRAL: 'กลาง',
  RANGE: 'กรอบ',
  RANGING: 'กรอบ',
  TRENDING_UP: 'ขาขึ้น',
  TRENDING_DOWN: 'ขาลง',
  HIGH_VOLATILITY: 'ผันผวนสูง',
  LOW_VOLATILITY: 'ผันผวนต่ำ',
  BREAKOUT: 'ทะลุ',
  PULLBACK: 'พักตัว',
  FULL: 'ครบ',
  LIMITED: 'บางส่วน',
  SCHEDULED: 'รอ',
  RELEASED: 'ประกาศแล้ว',
  REVISED: 'แก้ไข',
  PROVISIONAL: 'ไม่ครบ',
  BUY: 'BUY',
  SELL: 'SELL',
  LONG: 'BUY',
  SHORT: 'SELL',
  NORMAL: 'ปกติ',
  ACTIVE: 'เปิดใช้งาน',
  CLEAR: 'ปกติ',
  FIXTURE_READY: 'Fixture พร้อม',
  EXTERNAL_READY: 'External พร้อม',
  EXTERNAL_NOT_CONFIGURED: 'ยังไม่ตั้งค่า Key',
  ...strategyLabels,
};
const name = (v: string | null | undefined) => (v ? states[v] || v : '—');

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
  const colors: Record<string, string> = {
    HIGH: 'bg-red-500/20 text-red-400 border-red-500/30',
    MEDIUM: 'bg-amber-500/20 text-amber-400 border-amber-500/30',
    LOW: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  };
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${colors[impact] || colors.LOW}`}>
      {impact === 'HIGH' ? 'High' : impact === 'MEDIUM' ? 'Medium' : impact === 'LOW' ? 'Low' : impact}
    </span>
  );
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

  // Authoritative lifecycle resources
  const [portfolioRisk, setPortfolioRisk] = useState<PortfolioRiskData | null>(null);
  const [killSwitch, setKillSwitch] = useState<KillSwitchData | null>(null);
  const [riskPolicy, setRiskPolicy] = useState<RiskPolicyData | null>(null);
  const [account, setAccount] = useState<AccountSnapshotData | null>(null);
  const [decisions, setDecisions] = useState<RiskDecisionData[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null);

  const [portfolioRiskState, setPortfolioRiskState] = useState<'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE'>('LOADING');
  const [killSwitchState, setKillSwitchState] = useState<'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE'>('LOADING');
  const [riskPolicyState, setRiskPolicyState] = useState<'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE'>('LOADING');
  const [accountState, setAccountState] = useState<'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE'>('LOADING');
  const [decisionsState, setDecisionsState] = useState<'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE'>('LOADING');
  const [systemStatusState, setSystemStatusState] = useState<'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE'>('LOADING');

  useEffect(() => {
    const abort = new AbortController();
    let busy = false;
    const refresh = async () => {
      if (busy) return;
      busy = true;
      try {
        const [dashRes, portRes, ksRes, polRes, accRes, decRes, sysRes] = await Promise.allSettled([
          api.get('/dashboard/summary', { signal: abort.signal }).then(parseDashboard),
          api.get('/risk/portfolio', { signal: abort.signal }).then(parsePortfolioRisk),
          api.get('/risk/kill-switch', { signal: abort.signal }).then(parseKillSwitch),
          api.get('/risk/policy', { signal: abort.signal }).then(parseRiskPolicy),
          api.get('/risk/account?account_id=default_paper_account', { signal: abort.signal }).then(parseAccountSnapshot),
          api.get('/risk/decisions?limit=5', { signal: abort.signal }).then(parseRiskDecisions),
          api.get('/system/status', { signal: abort.signal }) as Promise<SystemStatusResponse>,
        ]);

        if (!abort.signal.aborted) {
          if (dashRes.status === 'fulfilled') {
            setData(dashRes.value);
            setError('');
          } else {
            setError('โหลดข้อมูลไม่สำเร็จ');
          }

          if (portRes.status === 'fulfilled') {
            setPortfolioRisk(portRes.value);
            setPortfolioRiskState('READY');
          } else {
            setPortfolioRiskState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          }

          if (ksRes.status === 'fulfilled') {
            setKillSwitch(ksRes.value);
            setKillSwitchState(ksRes.value.state === 'UNKNOWN' ? 'UNAVAILABLE' : 'READY');
          } else {
            setKillSwitchState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          }

          if (polRes.status === 'fulfilled') {
            setRiskPolicy(polRes.value);
            setRiskPolicyState('READY');
          } else {
            setRiskPolicyState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          }

          if (accRes.status === 'fulfilled') {
            setAccount(accRes.value);
            setAccountState('READY');
          } else {
            setAccountState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          }

          if (decRes.status === 'fulfilled') {
            setDecisions(decRes.value);
            setDecisionsState('READY');
          } else {
            setDecisionsState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          }

          if (sysRes.status === 'fulfilled') {
            setSystemStatus(sysRes.value as SystemStatusResponse);
            setSystemStatusState('READY');
          } else {
            setSystemStatusState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          }
        }
      } catch {
        if (!abort.signal.aborted) {
          setError('โหลดข้อมูลไม่สำเร็จ');
          setPortfolioRiskState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          setKillSwitchState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          setRiskPolicyState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          setAccountState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          setDecisionsState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
          setSystemStatusState((prev) => (prev === 'READY' || prev === 'STALE' ? 'STALE' : 'UNAVAILABLE'));
        }
      } finally {
        busy = false;
      }
    };

    const connection = new MarketConnection(
      async () => {
        await api.getMe();
        const t = localStorage.getItem('access_token');
        if (!t) throw new Error('Session expired');
        return t;
      },
      (msg) => {
        if (abort.signal.aborted) return;
        setMarketStatus(msg.status);
        setQuote(msg.quote);
        if (msg.type === 'snapshot') setMarketCandles(msg.candles);
        else if (msg.candles.length) {
          setMarketCandles((value) => mergeCandles(value, msg.candles, false));
        }
      },
      (state) => {
        if (!abort.signal.aborted) setWs(state);
      },
      'XAUUSD',
      'M5'
    );

    connection.start();
    void refresh();
    const timer = setInterval(refresh, 30000);
    const ticker = setInterval(() => setClock(Date.now()), 1000);
    return () => {
      abort.abort();
      clearInterval(timer);
      clearInterval(ticker);
      connection.stop();
    };
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
      portfolioRiskState={portfolioRiskState}
      killSwitch={killSwitch}
      killSwitchState={killSwitchState}
      riskPolicy={riskPolicy}
      riskPolicyState={riskPolicyState}
      account={account}
      accountState={accountState}
      decisions={decisions}
      decisionsState={decisionsState}
      systemStatus={systemStatus}
      systemStatusState={systemStatusState}
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
  portfolioRiskState = 'READY',
  killSwitch,
  killSwitchState = 'READY',
  riskPolicy,
  riskPolicyState = 'READY',
  account,
  accountState = 'READY',
  decisions = [],
  decisionsState = 'READY',
  systemStatus,
  systemStatusState = 'READY',
}: {
  data: DashboardSummary | null;
  error: string;
  quote: Quote | null;
  marketStatus: MarketDataStatus | null;
  marketCandles: Candle[];
  ws: ConnectionState;
  clock: number;
  portfolioRisk?: PortfolioRiskData | null;
  portfolioRiskState?: 'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE';
  killSwitch?: KillSwitchData | null;
  killSwitchState?: 'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE';
  riskPolicy?: RiskPolicyData | null;
  riskPolicyState?: 'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE';
  account?: AccountSnapshotData | null;
  accountState?: 'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE';
  decisions?: RiskDecisionData[];
  decisionsState?: 'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE';
  systemStatus?: SystemStatusResponse | null;
  systemStatusState?: 'LOADING' | 'READY' | 'STALE' | 'UNAVAILABLE';
}) {
  const market = marketStatus || data?.market;
  const current =
    market && quote?.source === market.source && quote.symbol === 'XAUUSD'
      ? quote
      : market && data?.quote?.source === market.source
      ? data.quote
      : null;

  const old = !!data && (!!error || clock - Date.parse(data.generated_at) > 65000);
  const staleQuote =
    !current ||
    !clock ||
    clock < Date.parse(current.timestamp) ||
    clock - Date.parse(current.timestamp) > (market?.stale_after_seconds || 5) * 1000;

  const liveMarket =
    !staleQuote &&
    !error &&
    ws === 'CONNECTED' &&
    market?.status === 'CONNECTED' &&
    current?.status === 'CONNECTED' &&
    (market.mode === 'DEMO' || market.mode === 'LIVE');

  const marketLabel =
    market?.mode === 'SIMULATED'
      ? 'SIMULATED DATA'
      : liveMarket
      ? market?.mode === 'DEMO' ? 'MT5 DEMO · REAL MARKET DATA' : 'REAL MARKET DATA · LIVE'
      : market
      ? 'Market Data: ' + market.status + ' · ' + (staleQuote ? 'STALE / ไม่พร้อม' : 'ข้อมูลล่าสุด')
      : 'Market Data: UNKNOWN';

  const visibleCandles = market
    ? marketCandles.filter((c) => c.source === market.source && c.symbol === 'XAUUSD' && c.timeframe === 'M5')
    : [];
  const closedM5Candles = visibleCandles.filter((c) => c.is_closed);
  const latestCandle = visibleCandles.at(-1);

  const calcMA = (period: number): number | null => {
    if (closedM5Candles.length < period) return null;
    const slice = closedM5Candles.slice(-period);
    const sum = slice.reduce((acc, c) => acc + Number(c.close), 0);
    return sum / period;
  };
  const ma20 = calcMA(20);
  const ma50 = calcMA(50);
  const ma200 = calcMA(200);

  const safetyHealth = !old && data ? ({ trading_mode: data.trading_mode, live_auto_trading: data.live_auto_trading } as HealthResponse) : null;
  const plan =
    clock > 0 && !old && !data?.strategy_stale && data?.current_plan && Date.parse(data.current_plan.expires_at) > clock
      ? data.current_plan
      : null;
  const matchedPlanRiskDecision = plan ? decisions.find((decision) => decision.candidate_id === plan.candidate_id) || null : null;
  const direction = plan?.direction || 'NEUTRAL';

  // Global Session Indicator (Deterministic UTC Hour)
  const currentUtcHour = clock
    ? new Date(clock).getUTCHours() + new Date(clock).getUTCMinutes() / 60
    : new Date().getUTCHours() + new Date().getUTCMinutes() / 60;

  const sessionName =
    currentUtcHour >= 13 && currentUtcHour < 16.5
      ? 'London / NY Overlap (High Liquidity)'
      : currentUtcHour >= 13 && currentUtcHour < 21
      ? 'New York Session'
      : currentUtcHour >= 8 && currentUtcHour < 16.5
      ? 'London Session'
      : currentUtcHour >= 0 && currentUtcHour < 9
      ? 'Asian Session'
      : 'Inter-Session Transition';

  // Macro Risk Window Determination
  const activeEvent = data?.news?.events?.find((e) => e.id === data?.news?.active_event_id);
  const newsRiskState = data?.news?.trade_policy_state || 'UNAVAILABLE';

  // AI Provider status label
  const aiProviderMode = systemStatus?.ai_mode || 'unavailable';
  const aiStatusLabel =
    systemStatus?.ai_status_label ||
    (aiProviderMode === 'fixture' ? 'FIXTURE ADVISORY' : 'AI STATUS UNAVAILABLE');

  return (
    <div className="space-y-5 min-w-0" data-testid="dashboard">
      {/* ─── Global Safety Header ───────────────────────── */}
      <div className="rounded-xl border border-amber-500/30 bg-[#111827] p-3 flex flex-wrap items-center justify-between gap-3">
        <TradingStatus health={safetyHealth} />
        <div className="flex items-center gap-2 text-xs">
          <span className="px-2 py-0.5 rounded bg-amber-500/15 border border-amber-500/30 text-amber-300 font-medium">
            TRADING_MODE={safetyHealth?.trading_mode ?? 'UNKNOWN'}
          </span>
          <span className="px-2 py-0.5 rounded bg-gray-800 border border-gray-700 text-gray-400 font-mono">
            LIVE_AUTO_TRADING={safetyHealth ? (safetyHealth.live_auto_trading ? 'ON' : 'OFF') : 'UNKNOWN'}
          </span>
        </div>
        {error && <p role="alert" className="text-red-400 text-sm w-full">{error} · ข้อมูลเดิมอาจล้าสมัย</p>}
      </div>

      {/* ─── Section A: Executive Operations Center ──────── */}
      <div className="relative overflow-hidden rounded-2xl min-h-[220px]">
        <Image src="/images/login-bg.jpg" alt="" fill className="object-cover opacity-40" priority />
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
                <span className="text-xs px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-gray-300 font-mono">
                  {marketLabel}
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
            <Link href="/settings" className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-400 hover:text-gray-200 rounded-lg text-xs transition-colors">
              <span>⚙️</span>
              <span>Settings</span>
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
        ].map((t) => (
          <div key={t.sym} className={`bg-[#111827] border rounded-xl p-4 ${t.live ? 'border-amber-500/30' : 'border-gray-800'}`}>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-xs text-gray-400 font-semibold">{t.sym}</span>
              {t.label && <span className="text-[10px] text-gray-500">{t.label}</span>}
            </div>
            <p className="text-xl font-bold text-white tabular-nums">{fmtPrice(t.bid)}</p>
            <p className={`text-xs mt-0.5 ${t.live && !staleQuote ? 'text-emerald-400' : 'text-gray-500'}`}>
              {t.live ? (staleQuote ? 'ข้อมูลราคาล้าสมัย/ไม่พร้อม' : `Spread: ${fmtPrice(current?.spread)}`) : '—'}
            </p>
          </div>
        ))}
      </div>

      {/* ─── Main Grid: Chart + Strategy Opportunity ─────── */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Chart + Market Pulse Area (7 cols) */}
        <div className="lg:col-span-7 space-y-5">
          {/* Main Chart Card */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
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
            <p className="text-xs text-gray-400 mt-2" data-testid="quote-provenance">
              {marketLabel} · {market?.source || 'UNKNOWN'}<br />Quote: {current?.timestamp || '—'}
            </p>
            <p className="text-xs text-gray-500 mt-2">
              M5 candle: {latestCandle?.open_time || '—'} · {latestCandle ? (latestCandle.is_closed ? 'CLOSED' : 'FORMING') : 'ยังไม่มีข้อมูล'}
            </p>
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
              {staleQuote && <span className="text-red-400 font-medium">(STALE)</span>}
            </div>
          </div>

          {/* Section B: Market State & Multi-Timeframe Alignment */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex items-center gap-2">
                <span className="text-amber-400">★</span> Market State & Multi-Timeframe Structure
              </h2>
              <span className="text-xs text-gray-400">Deterministic SMC</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="rounded-xl border border-gray-800 bg-[#0a0f1a] p-4">
                <p className="text-xs text-gray-500 font-medium">สภาวะตลาดปัจจุบัน (Primary Regime)</p>
                <p className="text-2xl font-bold text-white mt-1">{name(data?.structure?.[0]?.regime)}</p>
                <p className="text-xs text-gray-400 mt-1">
                  {data?.structure?.[0]?.timeframe ? `กรอบเวลา ${data.structure[0].timeframe} · โครงสร้างภายนอก: ${name(data.structure[0].external_state)}` : 'ยังไม่มีข้อมูลโครงสร้างตลาด'}
                </p>
                <p className="text-[11px] text-gray-600 mt-2">ประเมินจากแท่งเทียนที่ปิดแล้ว ไม่มีการ Lookahead</p>
              </div>

              <div className="rounded-xl border border-gray-800 bg-[#0a0f1a] p-4 space-y-2 text-xs">
                <p className="text-gray-500 font-medium border-b border-gray-800 pb-1">Multi-Timeframe Alignment</p>
                {data?.structure?.length ? (
                  data.structure.map((s) => (
                    <div key={s.timeframe} className="flex justify-between items-center py-0.5">
                      <span className="font-semibold text-gray-300">{s.timeframe}</span>
                      <span className="text-amber-400 font-medium">{name(s.regime)}</span>
                      <span className="text-gray-500 font-mono text-[10px]">{s.history.closed} แท่งปิด</span>
                    </div>
                  ))
                ) : (
                  <p className="text-gray-500 py-2">กำลังรวบรวมข้อมูลหลายกรอบเวลา…</p>
                )}
              </div>
            </div>

            {/* Key Levels Strip */}
            {data?.key_levels && data.key_levels.length > 0 && (
              <div className="mt-4 pt-3 border-t border-gray-800/80">
                <p className="text-[11px] text-gray-500 font-medium mb-2">ระดับราคาสำคัญที่ยืนยันแล้ว (Key Levels):</p>
                <div className="flex flex-wrap gap-2">
                  {data.key_levels.slice(0, 6).map((k) => (
                    <span key={k.id} className="text-xs px-2.5 py-1 rounded bg-white/5 border border-white/10 text-gray-300 font-mono">
                      {k.kind}: <b className="text-amber-400">{fmtPrice(k.price)}</b>
                    </span>
                  ))}
                </div>
              </div>
            )}

            <Link href="/analysis" className="mt-4 block text-xs text-amber-400 hover:underline">
              เปิดห้องวิเคราะห์ SMC & MTF แบบเต็ม (Analysis Desk) →
            </Link>
          </div>
        </div>

        {/* Right Column: Opportunity + AI Intelligence + News Risk (5 cols) */}
        <div className="lg:col-span-5 space-y-5">
          {/* Section C: Deterministic Strategy Opportunity */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex flex-wrap items-center gap-2">
                <span className="text-amber-400">⚡</span> Latest Strategy Candidate
              </h2>
              <span data-testid="setup-score" className="text-xs text-gray-400">
                Setup Score <span className="text-amber-400 font-bold text-lg">{plan ? plan.score + '/100' : '—'}</span>
              </span>
            </div>
            <p className="text-xs text-gray-400 mb-3">คะแนนตามกฎ ไม่ใช่ความน่าจะเป็นและไม่ใช่ผลจาก AI</p>
            {plan ? (
              <>
                <div className={`flex items-center gap-4 p-4 rounded-xl ${direction === 'LONG' ? 'bg-emerald-500/10 border border-emerald-500/20' : direction === 'SHORT' ? 'bg-red-500/10 border border-red-500/20' : 'bg-gray-800/50 border border-gray-700'}`}>
                  <span className={`text-3xl font-black ${direction === 'LONG' ? 'text-emerald-400' : 'text-red-400'}`}>{direction}</span>
                  <div>
                    <p className="text-white font-semibold">XAUUSD</p>
                    <p className="text-gray-400 text-sm">{fmtPrice(current?.bid)}</p>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3 mt-4 text-sm">
                  <div><span className="text-gray-400">Entry Zone</span><p className="text-white">{fmtPrice(plan.entry_lower)} - {fmtPrice(plan.entry_upper)}</p></div>
                  <div><span className="text-gray-400">Take Profit</span><p className="text-white">{plan.targets.slice(0, 2).map((t) => fmtPrice(t.price)).join(' / ')}</p></div>
                  <div><span className="text-gray-400">Stop Loss</span><p className="text-red-400">{fmtPrice(plan.stop_loss)}</p></div>
                  <div><span className="text-gray-400">Strategy</span><p className="text-white">{data?.candidates.find((c) => c.id === plan.candidate_id)?.strategy_id || '—'}</p></div>
                </div>
                <div className="mt-3 text-xs text-gray-400">
                  <span className="text-gray-500">Rationale:</span> {plan.evidence.slice(0, 2).map((e) => e.description_th).join(' · ')}
                </div>
                <div className="mt-2 text-[11px] text-gray-500 flex justify-between">
                  <span>สถานะความเสี่ยง: <b className={matchedPlanRiskDecision?.decision === 'APPROVED' ? 'text-emerald-400' : 'text-amber-400'}>{matchedPlanRiskDecision?.decision || 'NOT EVALUATED'}</b></span>
                  <span>หมดอายุ: {bangkok(plan.expires_at).slice(11, 19)}</span>
                </div>
                <Link href={`/signals?candidate=${encodeURIComponent(plan.candidate_id)}`} className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 bg-amber-500/15 border border-amber-500/30 text-amber-400 rounded-lg text-sm hover:bg-amber-500/25 transition-colors">
                  ดูรายละเอียดสัญญาณเทรดทั้งหมด (Signals) <span>→</span>
                </Link>
              </>
            ) : (
              <div className="text-center py-8">
                <div className="w-16 h-16 mx-auto bg-gray-800 rounded-full flex items-center justify-center mb-3">
                  <span className="text-2xl">🔍</span>
                </div>
                <p className="text-gray-300 text-sm font-semibold">ยังไม่พบ Setup ที่ผ่านเงื่อนไข</p>
                <p className="text-gray-500 text-xs mt-1.5 max-w-xs mx-auto">
                  {!data || old
                    ? 'ข้อมูลไม่พร้อมใช้งาน / ล้าสมัย'
                    : 'ระบบกำลังติดตามโครงสร้างตลาดและเงื่อนไขของ Strategy (STRAT01–STRAT06) อย่างต่อเนื่องโดยไม่มีการประดิษฐ์สัญญาณจำลอง'}
                </p>
                <Link href="/signals" className="inline-block text-amber-400 text-xs mt-3 hover:underline">
                  ไปที่หน้า Trading Signals →
                </Link>
              </div>
            )}
          </div>

          {/* Section D: AI Advisory Intelligence Card */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex items-center gap-2">
                <span>🤖</span> AI Advisory Intelligence
              </h2>
              <div className="flex items-center gap-1.5">
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-purple-500/15 text-purple-300 border border-purple-500/30">
                  {aiStatusLabel}
                </span>
                <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                  ADVISORY ONLY
                </span>
              </div>
            </div>

            <div className="rounded-xl border border-gray-800 bg-[#0a0f1a] p-4 space-y-3 text-xs">
              <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                <span className="text-gray-400">Candidate-bound AI Advisory:</span>
                <span className="text-white font-semibold">
                  NOT EVALUATED ON DASHBOARD
                </span>
              </div>

              <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                <span className="text-gray-400">Strategy Candidate Direction:</span>
                <span className={`font-bold ${direction === 'LONG' ? 'text-emerald-400' : direction === 'SHORT' ? 'text-red-400' : 'text-gray-300'}`}>
                  {plan ? direction : 'UNAVAILABLE'}
                </span>
              </div>

              <div className="flex justify-between items-center border-b border-gray-800 pb-2">
                <span className="text-gray-400">AI Provider Runtime:</span>
                <span className="text-gray-200 font-mono font-semibold">{aiStatusLabel}</span>
              </div>

              <p className="text-gray-400 text-xs leading-relaxed">
                Dashboard ไม่มีผล AI แบบ durable สำหรับ Candidate นี้; เปิด Analysis เพื่อประเมินแบบ explicit โดยยังคงอยู่ภายใต้ Risk และ Kill Switch gate
              </p>

              <div className="text-[11px] text-gray-500 pt-1 border-t border-gray-800/80">
                <span>ความรับผิดชอบ: </span>
                <span className="text-gray-400">AI ให้คำแนะนำเชิงวิเคราะห์เท่านั้น ไม่มีสิทธิ์ส่งคำสั่งหรือปรับลดการควบคุมความเสี่ยง</span>
              </div>
            </div>

            <Link href={plan ? `/analysis?candidate=${encodeURIComponent(plan.candidate_id)}` : '/analysis'} className="mt-3 block text-xs text-amber-400 hover:underline">
              ดูความเห็นของ AI แต่ละ Agent ในห้องวิเคราะห์ →
            </Link>
          </div>

          {/* Section E (Part 2): Top News & Macro Context */}
          <div className="bg-[#111827] border border-gray-800 rounded-xl p-5">
            <div className="flex items-center justify-between mb-3">
              <div>
                <h2 className="text-white font-semibold flex items-center gap-1.5">
                  <span>📰</span> Top News & Macro Risk
                </h2>
                <p className="text-[10px] text-gray-500 mt-0.5">
                  {data?.news_provider
                    ? `${data.news_provider.source} · ${data.news_provider.source_mode} · ${name(data.news_provider.state)}`
                    : 'กำลังตรวจสอบ Forex Factory'}
                  {activeEvent ? ` · กำลังติดตาม: ${eventName(activeEvent)}` : ''}
                </p>
              </div>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                newsRiskState === 'RESTRICTED'
                  ? 'bg-red-500/20 text-red-400 border-red-500/30'
                  : newsRiskState === 'CAUTION'
                  ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
              }`}>
                NEWS RISK: {newsRiskState}
              </span>
            </div>
            <div className="space-y-3">
              {(data?.calendar_events || []).slice(0, 3).map((e: EconomicEvent) => (
                <Link href={`/calendar?event=${encodeURIComponent(e.id)}`} key={e.id} className="flex gap-3 group">
                  <div className="w-10 h-10 bg-gray-800 rounded-lg flex-shrink-0 flex items-center justify-center text-base">📰</div>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-white truncate group-hover:text-amber-400 transition-colors">{eventName(e)}</p>
                    <div className="flex items-center gap-2 mt-0.5">
                      <p className="text-xs text-gray-500">{e.currency} · {bangkok(e.scheduled_at).slice(11, 16)}</p>
                      <ImpactBadge impact={e.impact} />
                    </div>
                  </div>
                </Link>
              ))}
              {!data?.calendar_events?.length && (
                <p className="text-gray-500 text-sm py-2">
                  {data?.news_provider && !old ? 'ไม่มีรายการในช่วงข้อมูลที่ได้รับ' : 'ข้อมูลข่าวไม่พร้อมใช้งาน'}
                </p>
              )}
            </div>
            <Link href="/calendar" className="mt-3 block text-xs text-amber-400 hover:underline">
              ดูปฏิทินเศรษฐกิจทั้งหมด (Economic Calendar) →
            </Link>
          </div>
        </div>
      </div>

      {/* ─── Bottom Grid: Portfolio Risk + Account + Activity + Subsystem Health ─ */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Card 1: Section E - Portfolio & Risk Gate */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex items-center gap-1.5">
                <span>🛡️</span> Portfolio Risk
              </h2>
              <span className={`text-[10px] font-bold px-2 py-0.5 rounded border ${
                killSwitchState === 'UNAVAILABLE' || !killSwitch || killSwitch.state === 'UNKNOWN'
                  ? 'bg-amber-500/20 text-amber-400 border-amber-500/30'
                  : killSwitch.state === 'ACTIVE'
                  ? 'bg-red-500/20 text-red-400 border-red-500/30'
                  : killSwitchState === 'STALE'
                  ? 'bg-gray-500/20 text-gray-400 border-gray-500/30'
                  : 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30'
              }`}>
                {killSwitchState === 'UNAVAILABLE' || !killSwitch || killSwitch.state === 'UNKNOWN'
                  ? 'KS: UNKNOWN'
                  : killSwitch.state === 'ACTIVE'
                  ? 'KS: ACTIVE'
                  : killSwitchState === 'STALE'
                  ? 'KS: STALE'
                  : 'KS: NORMAL'}
              </span>
            </div>

            <div className="space-y-2 text-xs text-gray-300">
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">ความเสี่ยงรวมพอร์ต:</span>
                <span className="font-mono text-white font-bold">
                  {portfolioRiskState === 'UNAVAILABLE' || !portfolioRisk
                    ? 'UNAVAILABLE'
                    : portfolioRiskState === 'STALE'
                    ? `${Number(portfolioRisk.total_risk_pct).toFixed(2)}% (STALE)`
                    : `${Number(portfolioRisk.total_risk_pct).toFixed(2)}% / 3.00%`}
                </span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">คำสั่งที่จองความเสี่ยง:</span>
                <span className="font-mono text-gray-200">
                  {portfolioRisk ? `${portfolioRisk.active_reservations_count} คำสั่ง` : 'UNAVAILABLE'}
                </span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">เพดานขาดทุนรายวัน:</span>
                <span className="font-mono text-gray-200">
                  {riskPolicyState === 'UNAVAILABLE' || !riskPolicy
                    ? 'UNAVAILABLE'
                    : `${Math.round(Number(riskPolicy.daily_loss_limit_pct))}%`}
                </span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">เสี่ยงสูงสุดต่อไม้:</span>
                <span className="font-mono text-gray-200">
                  {riskPolicyState === 'UNAVAILABLE' || !riskPolicy
                    ? 'UNAVAILABLE'
                    : `${Math.round(Number(riskPolicy.max_risk_per_trade_pct))}%`}
                </span>
              </div>
            </div>

            <p className="text-xs text-gray-400 mt-2">
              จะพร้อมใช้งานหลังเปิด Paper Trading และมีข้อมูลบัญชีจริง
            </p>
            <p className="text-[11px] text-gray-500 mt-1">
              ระบบ Fail-Closed: หากข้อมูลขาดหายจะปฏิเสธคำสั่งโดยอัตโนมัติ
            </p>
          </div>

          <Link
            href="/risk"
            className="mt-4 w-full inline-flex items-center justify-center gap-1.5 py-2 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/30 text-emerald-400 rounded-lg text-xs font-semibold transition-colors"
          >
            <span>เข้าสู่ห้องบริหารความเสี่ยง (Risk Desk) →</span>
          </Link>
        </div>

        {/* Card 2: Section F - Performance & Capital Health (Paper) */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex items-center gap-1.5">
                <span>💼</span> Capital Health
              </h2>
              <span className="text-[10px] text-amber-400 bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 rounded font-medium">
                {account ? `${account.trading_mode}${accountState === 'STALE' ? ' · STALE' : ''}` : 'UNAVAILABLE'}
              </span>
            </div>

            <div className="space-y-2 text-xs text-gray-300">
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">ยอดเงินในบัญชี (Balance):</span>
                <span className="font-mono text-white font-bold">
                  {account ? `$${fmtPrice(account.balance)}` : 'UNAVAILABLE'}
                </span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">มูลค่าสุทธิ (Equity):</span>
                <span className="font-mono text-white font-bold">
                  {account ? `$${fmtPrice(account.equity)}` : 'UNAVAILABLE'}
                </span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">Free Margin:</span>
                <span className="font-mono text-gray-200">
                  {account?.free_margin != null ? `$${fmtPrice(account.free_margin)}` : 'UNAVAILABLE'}
                </span>
              </div>
              <div className="flex justify-between border-b border-gray-800/80 pb-1.5">
                <span className="text-gray-400">Current Snapshot Drawdown:</span>
                <span className="font-mono text-emerald-400 font-semibold">
                  {account && Number(account.peak_equity) > Number(account.equity) && Number(account.peak_equity) > 0
                    ? `${(((Number(account.peak_equity) - Number(account.equity)) / Number(account.peak_equity)) * 100).toFixed(2)}%`
                    : account ? '0.00%' : 'UNAVAILABLE'}
                </span>
              </div>
            </div>

            {/* Truthful Empty State for Executed Trades */}
            <div className="mt-3 p-2.5 rounded-lg border border-dashed border-gray-800 bg-[#0a0f1a] text-[11px] text-gray-400">
              <p className="font-semibold text-gray-300">ยังไม่มีประวัติการเทรดที่ Execute จริง</p>
              <p className="text-xs text-gray-400 mt-1">
                จะพร้อมใช้งานหลังมีประวัติ Paper Trading สำหรับวิเคราะห์ผลการเทรด
              </p>
              <p className="text-gray-500 mt-1">
                Broker Execution ยังถูกปิดใช้งาน (TRADING_MODE=PAPER) — ไม่มีการประดิษฐ์ผลกำไรหรือสถิติจำลอง
              </p>
            </div>
          </div>

          <Link
            href="/journal"
            className="mt-4 w-full inline-flex items-center justify-center gap-1.5 py-2 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 hover:text-white rounded-lg text-xs font-medium transition-colors"
          >
            <span>เปิดรายงานข้อมูล (Reports) →</span>
          </Link>
        </div>

        {/* Card 3: Section G - Recent Activity Feed */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-white font-semibold flex items-center gap-1.5">
                <span>📋</span> Recent Activity
              </h2>
              <span className="text-[10px] text-gray-400 bg-gray-800 px-2 py-0.5 rounded border border-gray-700">
                {decisionsState === 'STALE' ? 'REAL EVENTS (STALE)' : 'REAL EVENTS'}
              </span>
            </div>

            <div className="space-y-2.5 text-xs">
              {decisions.length > 0 ? (
                decisions.slice(0, 3).map((d) => (
                  <Link href={`/signals?candidate=${encodeURIComponent(d.candidate_id)}`} key={d.id} className="block border-b border-gray-800/80 pb-2 hover:bg-white/[0.02]">
                    <div className="flex justify-between items-center">
                      <span className="font-semibold text-white">{d.strategy_id}</span>
                      <span className={`text-[10px] px-1.5 py-0.2 rounded font-bold ${
                        d.decision === 'APPROVED' ? 'bg-emerald-500/20 text-emerald-400' : 'bg-red-500/20 text-red-400'
                      }`}>
                        {d.decision}
                      </span>
                    </div>
                    <p className="text-gray-400 text-[11px] mt-0.5 truncate">{d.reasons_th[0] || 'การประเมินความเสี่ยงสำเร็จ'}</p>
                    <span className="text-[10px] text-gray-500">{bangkok(d.as_of).slice(11, 19)} UTC+7</span>
                  </Link>
                ))
              ) : data?.candidates && data.candidates.length > 0 ? (
                data.candidates.slice(0, 3).map((c) => (
                  <Link href={`/signals?candidate=${encodeURIComponent(c.id)}`} key={c.id} className="block border-b border-gray-800/80 pb-2 hover:bg-white/[0.02]">
                    <div className="flex justify-between items-center">
                      <span className="font-semibold text-white">{c.strategy_id} ({c.profile_id})</span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-amber-500/15 text-amber-300 font-bold">
                        {c.status}
                      </span>
                    </div>
                    <p className="text-gray-400 text-[11px] mt-0.5">คะแนน Setup: {c.score}/100 · ทิศทาง {c.direction}</p>
                    <span className="text-[10px] text-gray-500">{bangkok(c.detected_at).slice(11, 19)} UTC+7</span>
                  </Link>
                ))
              ) : (
                <div className="py-4 text-center text-gray-500">
                  <p>ยังไม่มีบันทึกกิจกรรมล่าสุด</p>
                  <p className="text-[10px] text-gray-600 mt-1">ระบบบันทึกเฉพาะการประเมินจริง</p>
                </div>
              )}
            </div>
          </div>

          <Link
            href="/signals"
            className="mt-4 w-full inline-flex items-center justify-center gap-1.5 py-2 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-300 hover:text-white rounded-lg text-xs font-medium transition-colors"
          >
            <span>ดูประวัติสัญญาณทั้งหมด →</span>
          </Link>
        </div>

        {/* Card 4: Section H - Subsystem Health & Economic Calendar Link */}
        <div className="bg-[#111827] border border-gray-800 rounded-xl p-5 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className="text-white font-semibold flex items-center gap-1.5">
                  <span>⚙️</span> Subsystem Health
                </h2>
                <p className="text-[10px] text-gray-500 mt-0.5">
                  {data?.news_provider?.source === 'forex_factory'
                    ? `Forex Factory · ${data.news_provider.source_mode}`
                    : data?.news_provider?.source || 'UNKNOWN / กำลังตรวจสอบ'}
                </p>
              </div>
              <Link href="/calendar" className="text-amber-400 text-xs hover:underline">See All</Link>
            </div>
            <p className="text-xs text-gray-400 mb-3">
              Health: {systemStatusState === 'STALE' || old ? 'STALE' : data?.news_provider?.state || 'UNKNOWN'}
            </p>
            <div className="space-y-2">
              {(data?.calendar_events || []).slice(0, 3).map((e: EconomicEvent) => (
                <Link href={`/calendar?event=${encodeURIComponent(e.id)}`} key={e.id} className="flex flex-wrap items-center gap-2 py-1.5 border-b border-gray-800/50 last:border-0 hover:bg-white/[0.02]">
                  <span className="text-xs text-gray-400 w-10 tabular-nums">{bangkok(e.scheduled_at).slice(11, 16)}</span>
                  <span className="text-xs text-gray-400 w-8">{e.currency}</span>
                  <span className="text-xs text-gray-300 flex-1 truncate">{eventName(e)}</span>
                  <ImpactBadge impact={e.impact} />
                  <p className="w-full text-[11px] text-gray-500" data-testid="calendar-values">
                    Forecast {e.forecast ?? '—'} · Previous {e.previous ?? '—'} · Actual {e.actual ?? '—'}
                  </p>
                </Link>
              ))}
              {!data?.calendar_events?.length && (
                <p className="text-gray-500 text-sm text-center py-4">
                  {data?.news_provider && !old ? 'ไม่มีรายการในช่วงข้อมูลที่ได้รับ' : 'ข้อมูลปฏิทินไม่พร้อมใช้งาน'}
                </p>
              )}
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
          <span className="text-gray-400">วิเคราะห์เท่านั้น · ไม่มีการส่งคำสั่งซื้อขาย (Advisory Only · Execution Disabled)</span>
        </div>
        {old && <span className="text-amber-400 font-semibold">⚠ ข้อมูลล้าสมัย</span>}
        {error && <span className="text-red-400 font-semibold">{error}</span>}
      </div>
    </div>
  );
}
