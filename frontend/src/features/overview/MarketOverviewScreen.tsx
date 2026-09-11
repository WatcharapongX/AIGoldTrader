'use client';

import React, { memo, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { CandlestickSeries, ColorType, createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts';
import { api } from '@/lib/api';
import type { Candle, MarketDataStatus, Quote, SymbolInfo, Timeframe } from '@/types/market.generated';
import { instant, parseCandles, parseStatus, parseSymbols, providerLabel, timeframes } from '@/features/chart/contracts';
import { MarketConnection, type ConnectionState } from '@/features/chart/transport';

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

interface GlobalSession {
  name: string;
  city: string;
  flag: string;
  utcOpen: number;
  utcClose: number;
}

const GLOBAL_SESSIONS: GlobalSession[] = [
  { name: 'Asian Session', city: 'Tokyo / Sydney', flag: '🇯🇵', utcOpen: 0, utcClose: 9 },
  { name: 'European Session', city: 'London / Frankfurt', flag: '🇬🇧', utcOpen: 8, utcClose: 16.5 },
  { name: 'US Session', city: 'New York', flag: '🇺🇸', utcOpen: 13, utcClose: 21 },
  { name: 'London / NY Overlap', city: 'Prime Gold Liquidity', flag: '⭐', utcOpen: 13, utcClose: 16.5 },
];

function isSessionActive(session: GlobalSession, currentUtcHour: number): boolean {
  if (session.utcOpen < session.utcClose) {
    return currentUtcHour >= session.utcOpen && currentUtcHour < session.utcClose;
  }
  return currentUtcHour >= session.utcOpen || currentUtcHour < session.utcClose;
}

export function MarketOverviewScreen() {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [symbol, setSymbol] = useState('XAUUSD');
  const [timeframe, setTimeframe] = useState<Timeframe>('M15');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [status, setStatus] = useState<ConnectionState>('CONNECTING');
  const [provider, setProvider] = useState<MarketDataStatus | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);
  const [currentUtc, setCurrentUtc] = useState<Date>(new Date());

  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const data = useRef<Candle[]>([]);
  const latest = useRef<Quote | null>(null);
  const staleSeconds = useRef(5);
  const connectionState = useRef<ConnectionState>('CONNECTING');

  const [bind] = useState(() => (c: IChartApi, s: ISeriesApi<'Candlestick'>) => {
    chart.current = c;
    series.current = s;
    s.setData(data.current.map(chartPoint));
    return () => {
      chart.current = null;
      series.current = null;
    };
  });

  // Clock ticker for global sessions
  useEffect(() => {
    const timer = setInterval(() => setCurrentUtc(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const currentUtcHour = currentUtc.getUTCHours() + currentUtc.getUTCMinutes() / 60;

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
          async () => {
            await api.getMe();
            const token = localStorage.getItem('access_token');
            if (!token) throw new Error('Session expired');
            return token;
          },
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

  const selected = symbols.find((item) => item.name === symbol);
  const digits = provider?.digits ?? selected?.digits ?? 2;

  useEffect(() => {
    series.current?.applyOptions({
      priceFormat: {
        type: 'price',
        precision: digits,
        minMove: provider?.tick_size ? Number(provider.tick_size) : 10 ** -digits,
      },
    });
  }, [digits, provider?.tick_size]);

  const number = (value?: string | number) =>
    value === undefined || value === null
      ? '—'
      : Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

  const lastUpdate = quote
    ? new Date(quote.timestamp).toLocaleTimeString('en-GB', { timeZone: 'UTC', hour12: false }) + ' UTC'
    : 'Waiting for quote';

  // Calculate daily high/low and range from loaded candles
  const dayHigh = candles.length ? Math.max(...candles.map((c) => Number(c.high))) : null;
  const dayLow = candles.length ? Math.min(...candles.map((c) => Number(c.low))) : null;
  const dayRange = dayHigh !== null && dayLow !== null ? dayHigh - dayLow : null;

  return (
    <div className="trading-workspace space-y-6">
      {/* Title & Safety Strip */}
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
          <div className="market-mode">◈ {providerLabel(provider)}</div>
          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded-md border border-emerald-500/20">
            🛡️ TRADING MODE: PAPER
          </span>
          <span className="px-3 py-1.5 bg-gray-800 text-gray-300 text-xs font-semibold rounded-md border border-gray-700">
            AUTO TRADING: OFF
          </span>
        </div>
      </div>

      {/* Global Trading Sessions Strip */}
      <section className="bg-[#0f1724] border border-gray-800/80 rounded-xl p-4" aria-label="Global Market Sessions">
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 mb-3">
          <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-2">
            <span>🌐</span> สภาวะตลาดโลก (Global Trading Sessions)
          </span>
          <span className="text-xs text-gray-400 font-mono">
            UTC Time: {currentUtc.toISOString().slice(11, 19)} · Bangkok: {currentUtc.toLocaleTimeString('th-TH', { timeZone: 'Asia/Bangkok' })}
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
                  <span className="font-mono text-[11px] text-gray-500">{String(s.utcOpen).padStart(2, '0')}:00 - {String(Math.floor(s.utcClose)).padStart(2, '0')}:{s.utcClose % 1 ? '30' : '00'} UTC</span>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Quote Toolbar */}
      <section className="market-toolbar" aria-label="Market quote">
        <div className="market-symbol">
          <span className="gold-symbol">Au</span>
          <div>
            <label htmlFor="market-symbol">Instrument</label>
            <select
              id="market-symbol"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
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

        <div className="market-connection">
          <span data-testid="connection" className={'connection-label state-' + status.toLowerCase()}>
            ● {status}
          </span>
          <small data-testid="last-update">{lastUpdate}</small>
        </div>
      </section>

      {/* Candlestick Chart Panel */}
      <section className="chart-panel">
        <div className="chart-toolbar">
          <div className="timeframes" role="group" aria-label="Timeframe">
            {timeframes.map((tf) => (
              <button key={tf} aria-pressed={timeframe === tf} onClick={() => setTimeframe(tf)}>
                {tf}
              </button>
            ))}
          </div>
          <span className="chart-caption">CANDLES · BID · UTC · CLEAN PRICE ACTION</span>
        </div>

        <div className="chart-heading">
          <span>
            {symbol} <b> / {timeframe}</b>
          </span>
          <span data-testid="candle-count">{candles.length} candles</span>
        </div>

        <div className="chart-stage">
          <ChartCanvas bind={bind} />
          {!candles.length && (
            <div className="chart-overlay" role="status">
              {error ? 'NO DATA' : 'Loading historical candles…'}
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

      {/* Notice bar if error/reconnecting */}
      {(error || ['ERROR', 'DISCONNECTED', 'RECONNECTING', 'STALE'].includes(status)) && (
        <div className="market-notice" role="status">
          <span>{error || status + ' — waiting for fresh market data.'}</span>
          <button onClick={() => setRetry((v) => v + 1)}>Reconnect</button>
        </div>
      )}

      {/* Market Pulse & Daily Metrics Grid */}
      <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4" aria-label="Market pulse and metrics">
        <div className="bg-[#101925] border border-[#253044] rounded-xl p-4">
          <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider block mb-1">กรอบราคาของวัน (Day Range)</span>
          <div className="text-lg font-bold text-white font-mono">{dayRange !== null ? `${number(dayRange)} USD` : '—'}</div>
          <div className="text-xs text-gray-400 mt-2 flex justify-between border-t border-gray-800 pt-2 font-mono">
            <span>High: <b className="text-emerald-400">{number(dayHigh ?? undefined)}</b></span>
            <span>Low: <b className="text-red-400">{number(dayLow ?? undefined)}</b></span>
          </div>
        </div>

        <div className="bg-[#101925] border border-[#253044] rounded-xl p-4">
          <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider block mb-1">ความสดและสเปรด (Spread Evaluation)</span>
          <div className="text-lg font-bold text-emerald-400 font-mono">{quote?.spread ? `${number(quote.spread)} USD` : '—'}</div>
          <div className="text-xs text-gray-400 mt-2 border-t border-gray-800 pt-2 flex justify-between">
            <span>สถานะสเปรด:</span>
            <span className="text-gray-300 font-medium">ปกติสำหรับการเทรดทอง</span>
          </div>
        </div>

        <div className="bg-[#101925] border border-[#253044] rounded-xl p-4">
          <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider block mb-1">สถานะผู้ให้บริการ (Provider Mode)</span>
          <div className="text-lg font-bold text-amber-400">{provider?.mode || 'UNCONFIRMED'}</div>
          <div className="text-xs text-gray-400 mt-2 border-t border-gray-800 pt-2 flex justify-between">
            <span>Source:</span>
            <span className="text-gray-300 font-mono text-[11px]">{provider?.source || 'Unconfirmed'}</span>
          </div>
        </div>

        <div className="bg-[#101925] border border-[#253044] rounded-xl p-4">
          <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider block mb-1">ความปลอดภัย (Trading Protection)</span>
          <div className="text-lg font-bold text-emerald-400">FAIL-CLOSED ACTIVE</div>
          <div className="text-xs text-gray-400 mt-2 border-t border-gray-800 pt-2 flex justify-between">
            <span>Kill Switch:</span>
            <span className="text-emerald-400 font-semibold">NORMAL (READY)</span>
          </div>
        </div>
      </section>

      {/* Cross-Asset Macro Context Strip */}
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

      {/* Quick Navigation Hub */}
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
              href="/analysis"
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
