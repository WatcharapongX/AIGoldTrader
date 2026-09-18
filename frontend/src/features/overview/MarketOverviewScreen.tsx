'use client';

import React, { memo, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import { api } from '@/lib/api';
import type { Candle, MarketDataStatus, Quote, SymbolInfo, Timeframe } from '@/types/market.generated';
import {
  instant,
  parseCandles,
  parseStatus,
  parseSymbols,
  providerLabel,
  timeframes,
} from '@/features/chart/contracts';
import { parseUiPreferences, UI_PREFERENCES_KEY } from '@/features/settings/contracts';
import { MarketConnection, type ConnectionState } from '@/features/chart/transport';
import { getValidAccessToken } from '@/lib/auth-coordinator';
import { DataProvenanceLine } from '@/components/data-provenance';
import { AnalysisPrimitive, defaultLayers, type Layers } from '@/features/analysis/primitive';
import { parseAnalysis, parseContext } from '@/features/analysis/contracts';
import type {
  AnalysisResponse as AnalysisSnapshot,
  LiquidityLevel,
  MultiTimeframeContext,
} from '@/types/analysis.generated';
import type { SystemStatusResponse } from '@/types';

function chartPoint(candle: Candle) {
  return {
    time: (instant(candle.open_time) / 1000) as UTCTimestamp,
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close),
  };
}

const ChartCanvas = memo(function ChartCanvas({
  bind,
}: {
  bind: (chart: IChartApi, series: ISeriesApi<'Candlestick'>) => () => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!container.current) return;
    const chart = createChart(container.current, {
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: '#0d1420' }, textColor: '#8898ae', attributionLogo: true },
      grid: { vertLines: { color: '#172130' }, horzLines: { color: '#172130' } },
      rightPriceScale: { borderColor: '#253044', scaleMargins: { top: 0.12, bottom: 0.1 } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: '#253044', rightOffset: 8 },
      crosshair: { vertLine: { color: '#73839a' }, horzLine: { color: '#73839a' } },
    });
    const series = chart.addSeries(CandlestickSeries, {
      upColor: '#36c4a4',
      downColor: '#ed7a88',
      wickUpColor: '#36c4a4',
      wickDownColor: '#ed7a88',
      borderVisible: false,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });
    const unbind = bind(chart, series);
    return () => {
      unbind();
      chart.remove();
    };
  }, [bind]);
  return <div ref={container} className="market-chart" aria-label="XAUUSD overview candlestick chart" role="img" />;
});

export interface GlobalSession {
  name: string;
  city: string;
  flag: string;
  utcOpen: number;
  utcClose: number;
}

export const GLOBAL_SESSIONS: GlobalSession[] = [
  { name: 'Asian Session', city: 'Tokyo / Sydney', flag: '🇯🇵', utcOpen: 0, utcClose: 9 },
  { name: 'European Session', city: 'London / Frankfurt', flag: '🇬🇧', utcOpen: 8, utcClose: 16.5 },
  { name: 'US Session', city: 'New York', flag: '🇺🇸', utcOpen: 13, utcClose: 21 },
  { name: 'London / NY Overlap', city: 'Prime Gold Liquidity', flag: '⭐', utcOpen: 13, utcClose: 16.5 },
];

export function isSessionActive(session: GlobalSession, currentUtcHour: number): boolean {
  if (session.utcOpen < session.utcClose) {
    return currentUtcHour >= session.utcOpen && currentUtcHour < session.utcClose;
  }
  return currentUtcHour >= session.utcOpen || currentUtcHour < session.utcClose;
}

const REGIME_NAMES_TH: Record<string, string> = {
  TRENDING_UP: 'แนวโน้มขาขึ้น (Trending Up)',
  TRENDING_DOWN: 'แนวโน้มขาลง (Trending Down)',
  RANGING: 'พักตัวในกรอบ (Ranging)',
  HIGH_VOLATILITY: 'ความผันผวนสูง (High Volatility)',
  LOW_VOLATILITY: 'ความผันผวนต่ำ (Low Volatility)',
  BREAKOUT: 'เกิดการเบรกเอาต์ (Breakout)',
  PULLBACK: 'ย่อตัวตามเทรนด์ (Pullback)',
  UNKNOWN: 'ยังไม่ระบุสภาวะ',
};

export function MarketOverviewScreen() {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [symbol, setSymbol] = useState('XAUUSD');
  const [timeframe, setTimeframe] = useState<Timeframe>('M15');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [status, setStatus] = useState<ConnectionState>('CONNECTING');
  const [provider, setProvider] = useState<MarketDataStatus | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [analysis, setAnalysis] = useState<AnalysisSnapshot | null>(null);
  const [analysisState, setAnalysisState] = useState<'READY' | 'LOADING' | 'STALE' | 'UNAVAILABLE'>('LOADING');
  const [mtfContext, setMtfContext] = useState<MultiTimeframeContext | null>(null);
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [currentUtc, setCurrentUtc] = useState<Date>(new Date());
  const [layers, setLayers] = useState<Layers>(defaultLayers);

  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const data = useRef<Candle[]>([]);
  const latest = useRef<Quote | null>(null);
  const staleSeconds = useRef(5);
  const connectionState = useRef<ConnectionState>('CONNECTING');
  useEffect(() => {
    const timer = window.setTimeout(() => {
      try {
        const stored = localStorage.getItem(UI_PREFERENCES_KEY);
        if (stored) setTimeframe(parseUiPreferences(JSON.parse(stored)).default_timeframe);
      } catch {}
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const [primitive] = useState(() => new AnalysisPrimitive());

  const [bind] = useState(() => (c: IChartApi, s: ISeriesApi<'Candlestick'>) => {
    chart.current = c;
    series.current = s;
    s.setData(data.current.map(chartPoint));
    s.attachPrimitive(primitive);
    return () => {
      s.detachPrimitive(primitive);
      chart.current = null;
      series.current = null;
    };
  });

  // Sync AnalysisPrimitive when analysis or layer toggles change
  useEffect(() => {
    primitive.update(analysis, layers);
  }, [analysis, layers, primitive]);

  // Live 1-second clock ticker
  useEffect(() => {
    const timer = setInterval(() => setCurrentUtc(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch analysis structure & MTF context
  useEffect(() => {
    let active = true;
    const abort = new AbortController();

    const fetchAnalysisData = async () => {
      try {
        setAnalysisState((prev) => (prev === 'READY' ? 'STALE' : 'LOADING'));
        const [structRes, ctxRes, sysRes] = await Promise.allSettled([
          api.get(`/analysis/structure?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=300`, { signal: abort.signal }).then(parseAnalysis),
          api.get(`/analysis/context?symbol=${encodeURIComponent(symbol)}&limit=300`, { signal: abort.signal }).then(parseContext),
          api.get('/system/status', { signal: abort.signal }) as Promise<SystemStatusResponse>,
        ]);
        if (!active) return;
        if (structRes.status === 'fulfilled') {
          setAnalysis(structRes.value);
          setAnalysisState('READY');
        } else {
          setAnalysisState('UNAVAILABLE');
        }
        if (ctxRes.status === 'fulfilled') {
          setMtfContext(ctxRes.value);
        }
        if (sysRes.status === 'fulfilled') {
          setSystemStatus(sysRes.value);
        }
      } catch {
        if (active) setAnalysisState('UNAVAILABLE');
      }
    };

    void fetchAnalysisData();
    const interval = setInterval(fetchAnalysisData, 20000);

    return () => {
      active = false;
      abort.abort();
      clearInterval(interval);
    };
  }, [symbol, timeframe, retry]);

  // Market WebSocket & Candles loader
  useEffect(() => {
    let active = true;
    let connection: MarketConnection | null = null;
    const abort = new AbortController();
    const state = (next: ConnectionState) => {
      connectionState.current = next;
      if (active) setStatus(next);
    };

    data.current = [];
    series.current?.setData([]);

    const refreshSeries = (incoming: Candle[], snapshot: boolean) => {
      if (!active) return;
      if (snapshot && incoming.length) {
        data.current = incoming.slice(-1000);
        series.current?.setData(data.current.map(chartPoint));
        chart.current?.timeScale().fitContent();
      } else {
        for (const item of incoming) {
          const last = data.current.at(-1);
          if (last && instant(item.open_time) < instant(last.open_time)) continue;
          if (last?.open_time === item.open_time) data.current[data.current.length - 1] = item;
          else data.current.push(item);

          if (data.current.length > 1000) {
            data.current = data.current.slice(-1000);
            series.current?.setData(data.current.map(chartPoint));
          } else {
            series.current?.update(chartPoint(item));
          }
        }
      }
      setCandles([...data.current]);
    };

    const load = async () => {
      setProvider(null);
      setError('');
      setCandles([]);
      setQuote(null);
      latest.current = null;
      state('CONNECTING');

      try {
        const service = parseStatus(await api.get('/market/status', { signal: abort.signal }));
        if (!active) return;
        setProvider(service);
        staleSeconds.current = service.stale_after_seconds;

        for (let attempt = 0; attempt < 30; attempt++) {
          const list = parseSymbols(await api.get('/symbols', { signal: abort.signal }));
          if (!active) return;
          setSymbols(list);
          if (list.some((item) => item.name === symbol)) {
            const page = parseCandles(
              await api.get(
                `/market/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${timeframe}&limit=300`,
                { signal: abort.signal },
              ),
            );
            if (!active) return;
            if (page.candles.length) {
              if (page.candles.some((item) => item.source !== service.source)) {
                throw new Error('Market source mismatch');
              }
              refreshSeries(page.candles, true);
              break;
            }
          }
          if (attempt === 29) throw new Error('Historical data unavailable. Please retry.');
          const progress = parseStatus(await api.get('/market/status', { signal: abort.signal }));
          if (!active) return;
          setProvider(progress);
          if (progress.status === 'ERROR') throw new Error(progress.detail);
          await new Promise((resolve) => setTimeout(resolve, 500));
          if (!active) return;
        }

        connection = new MarketConnection(
          getValidAccessToken,
          (message) => {
            if (!active) return;
            setProvider(message.status);
            staleSeconds.current = message.status.stale_after_seconds;
            if (message.quote) {
              latest.current = message.quote;
              setQuote(message.quote);
            }
            if (message.error) setError(message.error);
            refreshSeries(message.candles, message.type === 'snapshot');
          },
          state,
          symbol,
          timeframe,
        );
        connection.start();
      } catch (cause) {
        if (active) {
          state('ERROR');
          setError(cause instanceof Error ? cause.message : 'Market data unavailable');
        }
      }
    };

    void load();

    const freshness = setInterval(() => {
      if (
        active &&
        latest.current &&
        connectionState.current === 'CONNECTED' &&
        Date.now() - instant(latest.current.timestamp) > staleSeconds.current * 1000
      ) {
        setStatus('STALE');
      }
    }, 1000);

    return () => {
      active = false;
      abort.abort();
      connection?.stop();
      clearInterval(freshness);
    };
  }, [symbol, timeframe, retry]);

  const toggleLayer = (layer: keyof Layers) => {
    setLayers((prev) => ({ ...prev, [layer]: !prev[layer] }));
  };

  return (
    <MarketOverviewView
      symbol={symbol}
      symbols={symbols}
      onSelectSymbol={setSymbol}
      timeframe={timeframe}
      onSelectTimeframe={setTimeframe}
      quote={quote}
      status={status}
      provider={provider}
      candles={candles}
      analysis={analysis}
      analysisState={analysisState}
      mtfContext={mtfContext}
      systemStatus={systemStatus}
      error={error}
      onRetry={() => setRetry((v) => v + 1)}
      layers={layers}
      onToggleLayer={toggleLayer}
      bindChart={bind}
      currentUtc={currentUtc}
    />
  );
}

export function MarketOverviewView({
  symbol,
  symbols,
  onSelectSymbol,
  timeframe,
  onSelectTimeframe,
  quote,
  status,
  provider,
  candles,
  analysis,
  analysisState,
  mtfContext,
  systemStatus,
  error,
  onRetry,
  layers,
  onToggleLayer,
  bindChart,
  currentUtc,
}: {
  symbol: string;
  symbols: SymbolInfo[];
  onSelectSymbol: (s: string) => void;
  timeframe: Timeframe;
  onSelectTimeframe: (tf: Timeframe) => void;
  quote: Quote | null;
  status: ConnectionState;
  provider: MarketDataStatus | null;
  candles: Candle[];
  analysis: AnalysisSnapshot | null;
  analysisState: 'READY' | 'LOADING' | 'STALE' | 'UNAVAILABLE';
  mtfContext: MultiTimeframeContext | null;
  systemStatus: SystemStatusResponse | null;
  error: string;
  onRetry: () => void;
  layers: Layers;
  onToggleLayer: (layer: keyof Layers) => void;
  bindChart: (chart: IChartApi, series: ISeriesApi<'Candlestick'>) => () => void;
  currentUtc: Date;
}) {
  const selected = symbols.find((item) => item.name === symbol);
  const digits = provider?.digits ?? selected?.digits ?? 2;

  const number = (value?: string | number | null) =>
    value === undefined || value === null
      ? '—'
      : Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

  const currentUtcHour = currentUtc.getUTCHours() + currentUtc.getUTCMinutes() / 60;

  // Last update timestamp
  const lastUpdate = quote
    ? new Date(quote.timestamp).toLocaleTimeString('en-GB', { timeZone: 'UTC', hour12: false }) + ' UTC'
    : 'Waiting for quote';

  // Latest candle OHLC
  const latestCandle = candles.at(-1);

  // Daily high / low / range
  const dayHigh = candles.length ? Math.max(...candles.map((c) => Number(c.high))) : null;
  const dayLow = candles.length ? Math.min(...candles.map((c) => Number(c.low))) : null;
  const dayRange = dayHigh !== null && dayLow !== null ? dayHigh - dayLow : null;

  // Mid price & price change
  const midPrice =
    quote?.bid && quote?.ask ? (Number(quote.bid) + Number(quote.ask)) / 2 : null;
  const firstCandle = candles[0];
  const priceChange =
    midPrice !== null && firstCandle ? midPrice - Number(firstCandle.open) : null;
  const priceChangePct =
    priceChange !== null && firstCandle && Number(firstCandle.open) > 0
      ? (priceChange / Number(firstCandle.open)) * 100
      : null;

  // ATR & Volume Indicators
  const atrValue = analysis?.indicators?.ATR?.value ?? null;
  const avgVolume = analysis?.indicators?.VOLUME_AVERAGE?.value ?? null;

  // Nearest Liquidity Level Calculation
  let nearestLevel: { level: LiquidityLevel; distanceUsd: number } | null = null;
  if (analysis?.liquidity && quote?.bid) {
    const bidNum = Number(quote.bid);
    const activeLevels = analysis.liquidity.filter((l) => l.status === 'ACTIVE');
    if (activeLevels.length) {
      let closest = activeLevels[0];
      let minDiff = Math.abs(Number(closest.price) - bidNum);
      for (const lvl of activeLevels) {
        const diff = Math.abs(Number(lvl.price) - bidNum);
        if (diff < minDiff) {
          minDiff = diff;
          closest = lvl;
        }
      }
      nearestLevel = { level: closest, distanceUsd: Number(closest.price) - bidNum };
    }
  }

  // Structure events: latest BOS & CHOCH
  const latestBOS = analysis?.events?.filter((e) => e.kind === 'BOS').at(-1);
  const latestCHOCH = analysis?.events?.filter((e) => e.kind === 'CHOCH' || e.kind === 'MSS').at(-1);

  // W1 Partial history detection
  const isW1Partial = timeframe === 'W1' && candles.length > 0 && candles.length < 300;

  // Source Badge determination
  const sourceLabel =
    status === 'ERROR' || status === 'DISCONNECTED'
      ? { text: 'UNAVAILABLE', cls: 'bg-red-500/20 text-red-400 border-red-500/30' }
      : status === 'STALE'
      ? { text: 'STALE DATA', cls: 'bg-amber-500/20 text-amber-400 border-amber-500/30' }
      : provider?.mode === 'SIMULATED'
      ? { text: 'SIMULATED DATA', cls: 'bg-orange-500/20 text-orange-400 border-orange-500/30' }
      : provider?.mode === 'DEMO'
      ? { text: 'MT5 DEMO · REAL PRICES', cls: 'bg-blue-500/20 text-blue-400 border-blue-500/30' }
      : provider?.mode === 'LIVE'
      ? { text: 'REAL MARKET DATA', cls: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' }
      : { text: 'CONNECTING…', cls: 'bg-gray-800 text-gray-400 border-gray-700' };

  return (
    <div className="trading-workspace space-y-6">
      {/* ─── Top Header & Safety Badges ───────────────────────────── */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
            <p className="market-eyebrow tracking-widest text-xs font-semibold text-gray-400">EXECUTIVE MARKET WORKSPACE</p>
          </div>
          <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight mt-1">Market Overview</h1>
          <p className="text-xs text-gray-400 mt-0.5">ภาพรวมตลาดทองคำ XAUUSD เรียลไทม์ ตลาดโลก และสภาวะความผันผวน</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`px-2.5 py-1 text-xs font-bold rounded border ${sourceLabel.cls}`}>
          <DataProvenanceLine source={provider?.source} mode={provider?.mode} condition={status === 'STALE' ? 'STALE' : status === 'CONNECTED' && provider ? 'FRESH' : status === 'CONNECTING' || status === 'RECONNECTING' ? 'DEGRADED' : 'UNAVAILABLE'} asOf={quote?.timestamp || provider?.last_quote} />
            ◈ {sourceLabel.text}
          </span>
          <div className="market-mode">◈ {providerLabel(provider)}</div>
          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded-md border border-emerald-500/20">
            🛡️ TRADING MODE: {systemStatus?.trading_mode ?? 'UNKNOWN'}
          </span>
          <span className="px-3 py-1.5 bg-gray-800 text-gray-300 text-xs font-semibold rounded-md border border-gray-700">
            AUTO TRADING: {systemStatus ? (systemStatus.live_auto_trading ? 'ON' : 'OFF') : 'UNKNOWN'}
          </span>
          <span className="px-3 py-1.5 bg-gray-800 text-gray-300 text-xs font-semibold rounded-md border border-gray-700">
            FAIL-CLOSED POLICY
          </span>
        </div>
      </div>

      {/* ─── Section E: Global Market Sessions (Strictly preserved) ─ */}
      <section className="bg-[#0f1724] border border-gray-800/80 rounded-xl p-4" aria-label="Global Market Sessions">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mb-3">
          <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-2">
            <span>🌐</span> สภาวะตลาดโลก (Global Trading Sessions)
          </span>
          <span className="text-xs text-gray-400 font-mono">
            UTC Time: {currentUtc.toISOString().slice(11, 19)} · Bangkok: {currentUtc.toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' })} · DERIVED FROM CLIENT CLOCK + UTC SESSION RULES
          </span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {GLOBAL_SESSIONS.map((s) => {
            const active = isSessionActive(s, currentUtcHour);
            return (
              <div
                key={s.name}
                className={`p-3 rounded-lg border transition-all ${
                  active
                    ? 'bg-amber-500/10 border-amber-500/40 shadow-sm shadow-amber-500/5'
                    : 'bg-white/5 border-white/5 text-gray-400'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-sm font-semibold text-gray-200 flex items-center gap-1.5">
                    <span>{s.flag}</span>
                    <span>{s.name}</span>
                  </span>
                  <span
                    className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      active ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'bg-gray-800 text-gray-500'
                    }`}
                  >
                    {active ? '● OPEN' : 'CLOSED'}
                  </span>
                </div>
                <div className="text-xs text-gray-400 mt-1 flex justify-between">
                  <span>{s.city}</span>
                  <span className="font-mono text-[11px] text-gray-500">
                    {String(s.utcOpen).padStart(2, '0')}:00 - {String(Math.floor(s.utcClose)).padStart(2, '0')}:{s.utcClose % 1 ? '30' : '00'} UTC
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* ─── Section A: Quote Toolbar / Ticker Strip ─────────────── */}
      <section className="market-toolbar" aria-label="Market quote">
        <div className="market-symbol">
          <span className="gold-symbol">Au</span>
          <div>
            <label htmlFor="market-symbol">Instrument</label>
            <select
              id="market-symbol"
              value={symbol}
              onChange={(e) => onSelectSymbol(e.target.value)}
              className="bg-transparent text-white font-bold"
            >
              {(symbols.length ? symbols : [{ name: 'XAUUSD', source_available: true }]).map((item) => (
                <option key={item.name} value={item.name} disabled={!item.source_available}>
                  {item.name}
                </option>
              ))}
            </select>
            <small>Gold / US Dollar</small>
          </div>
        </div>

        <div className="quote-cell">
          <span>BID</span>
          <strong data-testid="bid" className="bid-value">
            {number(quote?.bid)}
          </strong>
        </div>

        <div className="quote-cell">
          <span>ASK</span>
          <strong data-testid="ask">{number(quote?.ask)}</strong>
        </div>

        <div className="quote-cell">
          <span>SPREAD · USD</span>
          <strong data-testid="spread">{number(quote?.spread)}</strong>
        </div>

        <div className="quote-cell">
          <span>MID / LAST</span>
          <strong className="text-gray-200 font-mono">
            {midPrice !== null ? number(midPrice) : '—'}
          </strong>
        </div>

        <div className="quote-cell">
          <span>CHANGE</span>
          <strong className={priceChange !== null && priceChange >= 0 ? 'text-emerald-400 font-mono' : 'text-red-400 font-mono'}>
            {priceChange !== null ? `${priceChange >= 0 ? '+' : ''}${number(priceChange)} (${priceChangePct?.toFixed(2)}%)` : '—'}
          </strong>
        </div>

        <div className="market-connection">
          <span data-testid="connection" className={'connection-label state-' + status.toLowerCase()}>
            ● {status}
          </span>
          <small data-testid="last-update">{lastUpdate}</small>
        </div>
      </section>

      {/* ─── Section B & C: Candlestick Chart Panel ───────────────── */}
      <section className="chart-panel">
        <div className="chart-toolbar flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-4">
            <div className="timeframes" role="group" aria-label="Timeframe">
              {timeframes.map((tf) => (
                <button
                  key={tf}
                  aria-pressed={timeframe === tf}
                  onClick={() => onSelectTimeframe(tf)}
                  className={timeframe === tf ? 'active' : ''}
                >
                  {tf}
                </button>
              ))}
            </div>

            {/* W1 Partial History Truthful Badge */}
            {isW1Partial && (
              <span className="px-2.5 py-1 rounded text-xs font-semibold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                PARTIAL HISTORY: {candles.length} / 300 bars
              </span>
            )}
          </div>

          {/* Overlay Toggles */}
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-gray-500 font-medium mr-1">Overlays:</span>
            <button
              onClick={() => onToggleLayer('BOS')}
              className={`px-2 py-1 rounded border text-[11px] font-semibold transition-colors ${
                layers.BOS ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-gray-800/60 text-gray-400 border-gray-700'
              }`}
            >
              Structure
            </button>
            <button
              onClick={() => onToggleLayer('Liquidity')}
              className={`px-2 py-1 rounded border text-[11px] font-semibold transition-colors ${
                layers.Liquidity ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-gray-800/60 text-gray-400 border-gray-700'
              }`}
            >
              Liquidity
            </button>
            <button
              onClick={() => onToggleLayer('FVG')}
              className={`px-2 py-1 rounded border text-[11px] font-semibold transition-colors ${
                layers.FVG ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-gray-800/60 text-gray-400 border-gray-700'
              }`}
            >
              FVG
            </button>
            <button
              onClick={() => onToggleLayer('OB')}
              className={`px-2 py-1 rounded border text-[11px] font-semibold transition-colors ${
                layers.OB ? 'bg-amber-500/20 text-amber-300 border-amber-500/40' : 'bg-gray-800/60 text-gray-400 border-gray-700'
              }`}
            >
              Order Block
            </button>
          </div>
        </div>

        <div className="chart-heading flex items-center justify-between">
          <span>
            {symbol} <b> / {timeframe}</b>
          </span>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-400 font-mono">
              Structure Analysis: <b className={analysisState === 'READY' ? 'text-emerald-400' : 'text-amber-400'}>{analysisState}</b>
            </span>
            <span data-testid="candle-count">{candles.length} candles</span>
          </div>
        </div>

        <div className="chart-stage">
          <ChartCanvas bind={bindChart} />
          {!candles.length && (
            <div className="chart-overlay" role="status">
              {error ? (
                <div className="text-center p-4">
                  <p className="text-red-400 font-semibold">{error}</p>
                  <button onClick={onRetry} className="mt-2 px-3 py-1 bg-gray-800 hover:bg-gray-700 text-xs rounded border border-gray-700">
                    โหลดข้อมูลใหม่ (Retry)
                  </button>
                </div>
              ) : (
                'Loading historical candles…'
              )}
            </div>
          )}
        </div>

        <div className="chart-footer">
          <span>
            {provider?.mode === 'SIMULATED'
              ? 'Deterministic replay · not live market prices'
              : provider?.detail || 'Verifying market source…'}
          </span>
          <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
            Charts by TradingView
          </a>
        </div>
      </section>

      {/* Notice bar if error/reconnecting/stale */}
      {(error || ['ERROR', 'DISCONNECTED', 'RECONNECTING', 'STALE'].includes(status)) && (
        <div className="market-notice" role="status">
          <span>{error || status + ' — waiting for fresh market data.'}</span>
          <button onClick={onRetry}>Reconnect</button>
        </div>
      )}

      {/* ─── Section D: Market Statistics Strip ───────────────────── */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4" aria-label="Market pulse and metrics">
        {/* Candle OHLC */}
        <div className="bg-[#101925] border border-[#253044] rounded-xl p-4">
          <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider block mb-1">
            แท่งเทียนปัจจุบัน ({timeframe} OHLC)
          </span>
          <div className="grid grid-cols-2 gap-1 text-xs font-mono mt-1">
            <span className="text-gray-400">O: <b className="text-gray-200">{number(latestCandle?.open)}</b></span>
            <span className="text-gray-400">H: <b className="text-emerald-400">{number(latestCandle?.high)}</b></span>
            <span className="text-gray-400">L: <b className="text-red-400">{number(latestCandle?.low)}</b></span>
            <span className="text-gray-400">C: <b className="text-amber-400">{number(latestCandle?.close)}</b></span>
          </div>
          <div className="text-[11px] text-gray-500 mt-2 border-t border-gray-800 pt-1.5 flex justify-between">
            <span>Volume:</span>
            <span className="font-mono text-gray-400">{latestCandle?.volume != null ? Number(latestCandle.volume).toLocaleString() : '—'}</span>
          </div>
        </div>

        {/* Daily Range */}
        <div className="bg-[#101925] border border-[#253044] rounded-xl p-4">
          <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider block mb-1">กรอบราคาของวัน (Day Range)</span>
          <div className="text-lg font-bold text-white font-mono">{dayRange !== null ? `${number(dayRange)} USD` : '—'}</div>
          <div className="text-xs text-gray-400 mt-2 flex justify-between border-t border-gray-800 pt-2 font-mono">
            <span>High: <b className="text-emerald-400">{number(dayHigh ?? undefined)}</b></span>
            <span>Low: <b className="text-red-400">{number(dayLow ?? undefined)}</b></span>
          </div>
        </div>

        {/* Volatility & ATR */}
        <div className="bg-[#101925] border border-[#253044] rounded-xl p-4">
          <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider block mb-1">ความผันผวน & ATR (14)</span>
          <div className="text-lg font-bold text-amber-400 font-mono">
            {atrValue !== null ? `${number(atrValue)} USD` : '—'}
          </div>
          <div className="text-xs text-gray-400 mt-2 border-t border-gray-800 pt-2 flex justify-between">
            <span>สภาวะความผันผวน:</span>
            <span className="text-gray-300 font-medium">
              {analysis?.regime ? REGIME_NAMES_TH[analysis.regime] || analysis.regime : '—'}
            </span>
          </div>
        </div>

        {/* Average Volume & Activity */}
        <div className="bg-[#101925] border border-[#253044] rounded-xl p-4">
          <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider block mb-1">ปริมาณการซื้อขายเฉลี่ย (Avg Vol)</span>
          <div className="text-lg font-bold text-gray-200 font-mono">
            {avgVolume !== null ? Number(avgVolume).toLocaleString() : '—'}
          </div>
          <div className="text-xs text-gray-400 mt-2 border-t border-gray-800 pt-2 flex justify-between">
            <span>สถานะสเปรด:</span>
            <span className="text-gray-300 font-medium">ไม่มีการจัดระดับเกณฑ์ · แสดง Spread ตาม Quote</span>
          </div>
        </div>

        {/* Data Provider Health */}
        <div className="bg-[#101925] border border-[#253044] rounded-xl p-4">
          <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider block mb-1">สถานะผู้ให้บริการ (Provider)</span>
          <div className="text-lg font-bold text-amber-400">{provider?.mode || 'UNCONFIRMED'}</div>
          <div className="text-xs text-gray-400 mt-2 border-t border-gray-800 pt-2 flex justify-between font-mono text-[11px]">
            <span>Source:</span>
            <span className="text-gray-300 truncate max-w-[120px]">{provider?.source || 'Unconfirmed'}</span>
          </div>
        </div>
      </section>

      {/* ─── Section F & G: Market Structure & Key Levels ─────────── */}
      <section className="grid grid-cols-1 lg:grid-cols-2 gap-5" aria-label="Market structure and key levels">
        {/* Section F: Market Structure Summary */}
        <div className="bg-[#101925] border border-[#253044] rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-gray-200 uppercase tracking-wider flex items-center gap-2">
              <span>📐</span> โครงสร้างราคาและแนวโน้ม (Market Structure Summary)
            </h2>
            <Link href={`/analysis?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`} className="text-amber-400 text-xs hover:underline">
              ห้องวิเคราะห์เต็ม (Analysis Desk) →
            </Link>
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
              <span className="text-gray-400">สภาวะตลาด (Regime):</span>
              <span className="text-amber-400 font-bold">
                {analysis?.regime ? REGIME_NAMES_TH[analysis.regime] || analysis.regime : '—'}
              </span>
            </div>

            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
              <span className="text-gray-400">โครงสร้างภายนอก (External State):</span>
              <span className={`font-bold px-2 py-0.5 rounded text-[11px] ${
                analysis?.external_state === 'BULLISH' ? 'bg-emerald-500/20 text-emerald-400' : analysis?.external_state === 'BEARISH' ? 'bg-red-500/20 text-red-400' : 'bg-gray-800 text-gray-300'
              }`}>
                {analysis?.external_state || 'NEUTRAL'}
              </span>
            </div>

            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
              <span className="text-gray-400">BOS ล่าสุด (Break of Structure):</span>
              <span className="font-mono text-gray-200">
                {latestBOS ? `${latestBOS.direction} ที่ ${number(latestBOS.price)}` : 'ยังไม่มี BOS ล่าสุด'}
              </span>
            </div>

            <div className="flex justify-between items-center border-b border-gray-800 pb-2">
              <span className="text-gray-400">CHoCH / MSS ล่าสุด:</span>
              <span className="font-mono text-gray-200">
                {latestCHOCH ? `${latestCHOCH.kind} ${latestCHOCH.direction} ที่ ${number(latestCHOCH.price)}` : 'ยังไม่มี CHoCH ล่าสุด'}
              </span>
            </div>

            {/* MTF Context Mini Strip */}
            <div className="pt-2">
              <span className="text-[11px] text-gray-400 font-medium block mb-2">การสอดประสานหลายกรอบเวลา (Multi-Timeframe Alignment):</span>
              <div className="grid grid-cols-5 gap-2 text-center">
                {(mtfContext?.timeframes || []).filter((r) => ['M5', 'M15', 'H1', 'H4', 'D1'].includes(r.timeframe)).map((row) => (
                  <div key={row.timeframe} className="p-2 rounded bg-white/5 border border-white/5">
                    <span className="text-[10px] text-gray-400 font-bold block">{row.timeframe}</span>
                    <span className={`text-[11px] font-semibold mt-0.5 block ${
                      row.state === 'BULLISH' ? 'text-emerald-400' : row.state === 'BEARISH' ? 'text-red-400' : 'text-gray-400'
                    }`}>
                      {row.state === 'BULLISH' ? 'BULL' : row.state === 'BEARISH' ? 'BEAR' : 'NEUT'}
                    </span>
                    <span className="text-[9px] text-gray-500 font-mono block mt-0.5">{row.history.closed}b</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Section G: Key Levels & Liquidity */}
        <div className="bg-[#101925] border border-[#253044] rounded-xl p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-sm font-bold text-gray-200 uppercase tracking-wider flex items-center gap-2">
              <span>🎯</span> ระดับราคาสำคัญและสภาพคล่อง (Key Levels & Liquidity)
            </h2>
            {nearestLevel && (
              <span className="text-xs px-2.5 py-0.5 rounded bg-amber-500/15 border border-amber-500/30 text-amber-300 font-mono">
                ใกล้สุด: {nearestLevel.level.kind} ({nearestLevel.distanceUsd >= 0 ? '+' : ''}{nearestLevel.distanceUsd.toFixed(2)} USD)
              </span>
            )}
          </div>

          <div className="space-y-3 text-xs">
            {/* Active confirmed levels */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
              {(analysis?.liquidity || []).filter((l) => l.status === 'ACTIVE').slice(-6).map((lvl) => (
                <div key={lvl.id} className="p-2.5 rounded-lg bg-white/5 border border-white/10 font-mono">
                  <div className="flex justify-between items-center text-[10px] text-gray-400">
                    <span>{lvl.kind}</span>
                    <span className={lvl.side === 'HIGH' ? 'text-emerald-400' : 'text-red-400'}>{lvl.side}</span>
                  </div>
                  <div className="text-sm font-bold text-amber-400 mt-1">{number(lvl.price)}</div>
                </div>
              ))}
              {!analysis?.liquidity?.length && (
                <p className="col-span-3 text-center py-6 text-gray-500">กำลังรวบรวมระดับราคาสำคัญ…</p>
              )}
            </div>

            {/* Dealing Range Equilibrium */}
            {analysis?.dealing_range && (
              <div className="mt-3 p-3 rounded-lg bg-black/40 border border-white/5 text-xs font-mono">
                <div className="flex justify-between items-center text-gray-300">
                  <span>Dealing Range (Premium / Discount):</span>
                  <span className="text-amber-400 font-bold">{analysis.dealing_range.location}</span>
                </div>
                <div className="grid grid-cols-3 gap-2 mt-2 text-[11px] text-gray-400">
                  <span>High: <b className="text-emerald-400">{number(analysis.dealing_range.upper_bound)}</b></span>
                  <span>EQ: <b className="text-amber-300">{number(analysis.dealing_range.equilibrium)}</b></span>
                  <span>Low: <b className="text-red-400">{number(analysis.dealing_range.lower_bound)}</b></span>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>

      {/* ─── Section H: Subsystem Data Health ─────────────────────── */}
      <section className="bg-[#101925] border border-[#253044] rounded-xl p-4" aria-label="Subsystem Health">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-2">
            <span>⚙️</span> ความสมบูรณ์ของระบบข้อมูล (Subsystem Health & Telemetry)
          </span>
          <span className="text-[11px] text-gray-500 font-mono">
            {systemStatus?.as_of ? `Updated: ${systemStatus.as_of.slice(11, 19)} UTC` : 'Checking system…'}
          </span>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 text-xs">
          <div className="p-2.5 rounded-lg bg-white/5 border border-white/5">
            <span className="text-[11px] text-gray-400 block">Market Provider</span>
            <span className="font-semibold text-gray-200 mt-0.5 block">{provider?.source || 'UNAVAILABLE'}</span>
            <span className="text-[10px] text-gray-500">{provider?.mode || 'UNAVAILABLE'}</span>
          </div>
          <div className="p-2.5 rounded-lg bg-white/5 border border-white/5">
            <span className="text-[11px] text-gray-400 block">MT5 Connection</span>
            <span className={`font-semibold mt-0.5 block ${provider?.status === 'CONNECTED' ? 'text-emerald-400' : 'text-amber-400'}`}>
              {provider?.status || 'UNAVAILABLE'}
            </span>
            <span className="text-[10px] text-gray-500">Spread: {quote?.spread ?? 'UNAVAILABLE'}</span>
          </div>
          <div className="p-2.5 rounded-lg bg-white/5 border border-white/5">
            <span className="text-[11px] text-gray-400 block">WebSocket Transport</span>
            <span className={`font-semibold mt-0.5 block ${status === 'CONNECTED' ? 'text-emerald-400' : 'text-amber-400'}`}>
              {status}
            </span>
            <span className="text-[10px] text-gray-500">Quote transport status</span>
          </div>
          <div className="p-2.5 rounded-lg bg-white/5 border border-white/5">
            <span className="text-[11px] text-gray-400 block">Historical Data</span>
            <span className="font-semibold text-gray-200 mt-0.5 block">{error ? 'UNAVAILABLE' : `${candles.length} Bars`}</span>
            <span className="text-[10px] text-gray-500">{timeframe} Timeframe</span>
          </div>
          <div className="p-2.5 rounded-lg bg-white/5 border border-white/5">
            <span className="text-[11px] text-gray-400 block">Risk Engine</span>
            <span className="font-semibold text-emerald-400 mt-0.5 block">
              {systemStatus?.modules?.risk_engine?.state || 'UNAVAILABLE'}
            </span>
            <span className="text-[10px] text-gray-500">Fail-closed by policy</span>
          </div>
          <div className="p-2.5 rounded-lg bg-white/5 border border-white/5">
            <span className="text-[11px] text-gray-400 block">Kill Switch</span>
            <span className="font-semibold text-emerald-400 mt-0.5 block">
              {systemStatus?.modules?.kill_switch?.state || 'UNAVAILABLE'}
            </span>
            <span className="text-[10px] text-gray-500">Authoritative system status</span>
          </div>
        </div>
      </section>

      {/* ─── Macro Drivers Strip (Strictly preserved for decoupling test) ─ */}
      <section className="bg-[#101925] border border-[#253044] rounded-xl p-5" aria-label="Macroeconomic drivers">
        <h2 className="text-sm font-bold text-gray-200 uppercase tracking-wider mb-3 flex items-center gap-2">
          <span>📊</span> ตัวขับเคลื่อนเศรษฐกิจมหภาคที่สัมพันธ์กับราคาทองคำ (Macro Drivers)
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          <div className="bg-black/30 p-3 rounded-lg border border-white/5">
            <div className="font-semibold text-gray-200">US Dollar Index (DXY)</div>
            <p className="text-gray-400 mt-1">ความสัมพันธ์ผกผัน (Inverse): เมื่อดอลลาร์แข็งค่า ทองคำมักเผชิญแรงกดดัน</p>
          </div>
          <div className="bg-black/30 p-3 rounded-lg border border-white/5">
            <div className="font-semibold text-gray-200">US 10Y Yield</div>
            <p className="text-gray-400 mt-1">ผลตอบแทนพันธบัตรแท้จริง: ต้นทุนค่าเสียโอกาสของการถือครองทองคำแท่ง</p>
          </div>
          <div className="bg-black/30 p-3 rounded-lg border border-white/5">
            <div className="font-semibold text-gray-200">Silver Spot (XAGUSD)</div>
            <p className="text-gray-400 mt-1">โลหะมีค่าคู่เคียง: ยืนยันการเคลื่อนไหวของกลุ่ม Precious Metals ร่วมกัน</p>
          </div>
          <div className="bg-black/30 p-3 rounded-lg border border-white/5">
            <div className="font-semibold text-gray-200">WTI Crude Oil</div>
            <p className="text-gray-400 mt-1">ภาพสะท้อนเงินเฟ้อ: ความคาดหวังแรงกดดันเงินเฟ้อและต้นทุนพลังงานโลก</p>
          </div>
        </div>
      </section>

      {/* ─── Quick Navigation Hub (Strictly preserved for decoupling test) ─ */}
      <section className="bg-gradient-to-r from-amber-500/10 via-transparent to-blue-500/10 border border-amber-500/20 rounded-xl p-6" aria-label="Quick Action Hub">
        <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-white">ต้องการเจาะลึกโครงสร้างราคา หรือตรวจสอบสัญญาณเทรด?</h2>
            <p className="text-sm text-gray-300 mt-1">
              เข้าสู่ห้องทำงานวิเคราะห์โครงสร้าง Smart Money Concepts (SMC) หรือดูการคัดกรองสัญญาณเทรดที่ผ่านการรับรองความเสี่ยง
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <Link
              href={`/analysis?symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}`}
              className="px-4 py-2.5 bg-amber-500 hover:bg-amber-400 text-black font-bold text-xs rounded-lg transition-colors shadow-lg shadow-amber-500/10 flex items-center gap-1.5"
            >
              <span>📐</span>
              <span>เปิดห้องวิเคราะห์ SMC เชิงลึก →</span>
            </Link>
            <Link
              href="/signals"
              className="px-4 py-2.5 bg-white/10 hover:bg-white/15 text-white font-semibold text-xs rounded-lg border border-white/10 transition-colors flex items-center gap-1.5"
            >
              <span>🤖</span>
              <span>ดูสัญญาณเทรด (Signals) →</span>
            </Link>
            <Link
              href="/calendar"
              className="px-4 py-2.5 bg-white/5 hover:bg-white/10 text-gray-300 font-medium text-xs rounded-lg border border-white/10 transition-colors flex items-center gap-1.5"
            >
              <span>📅</span>
              <span>ปฏิทินข่าวเศรษฐกิจ →</span>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
