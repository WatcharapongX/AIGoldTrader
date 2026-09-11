'use client';

import React, { memo, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { CandlestickSeries, ColorType, createChart, type IChartApi, type ISeriesApi, type UTCTimestamp } from 'lightweight-charts';
import { AnalysisWorkspace } from '@/features/analysis/AnalysisWorkspace';
import { AnalysisPrimitive } from '@/features/analysis/primitive';
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
  return <div ref={container} className="market-chart" aria-label="XAUUSD SMC analysis candlestick chart" role="img" />;
});

export function MarketAnalysisScreen() {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [symbol, setSymbol] = useState('XAUUSD');
  const [timeframe, setTimeframe] = useState<Timeframe>('M5');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [status, setStatus] = useState<ConnectionState>('CONNECTING');
  const [provider, setProvider] = useState<MarketDataStatus | null>(null);
  const [count, setCount] = useState(0);
  const [error, setError] = useState('');
  const [primitive] = useState(() => new AnalysisPrimitive());
  const [revision, setRevision] = useState('');
  const [retry, setRetry] = useState(0);

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
    s.attachPrimitive(primitive);
    return () => {
      s.detachPrimitive(primitive);
      chart.current = null;
      series.current = null;
    };
  });

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

    const refreshSeries = (candles: Candle[], snapshot: boolean) => {
      if (!active) return;
      if (snapshot && candles.length) {
        data.current = candles.slice(-1000);
        series.current?.setData(data.current.map(chartPoint));
        chart.current?.timeScale().fitContent();
      } else {
        for (const item of candles) {
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
      setCount(data.current.length);
      if (snapshot || candles.some((item) => item.is_closed)) {
        setRevision(
          data.current
            .filter((item) => item.is_closed)
            .slice(-300)
            .map((item) => [item.open_time, item.open, item.high, item.low, item.close, item.volume].join(','))
            .join(';'),
        );
      }
    };

    const load = async () => {
      setProvider(null);
      setError('');
      setCount(0);
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

  const number = (value?: string) =>
    value === undefined
      ? '—'
      : Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

  const lastUpdate = quote
    ? new Date(quote.timestamp).toLocaleTimeString('en-GB', { timeZone: 'UTC', hour12: false }) + ' UTC'
    : 'Waiting for quote';

  return (
    <div className="trading-workspace space-y-6">
      {/* Header with Navigation Link to Overview */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />
            <p className="market-eyebrow tracking-widest text-xs font-semibold text-gray-400">
              SMART MONEY CONCEPTS & MARKET STRUCTURE WORKBENCH
            </p>
          </div>
          <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight mt-1">Market Analysis</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            วิเคราะห์โครงสร้างราคา BOS, CHoCH, Liquidity Sweeps และ Multi-Timeframe Confluence จากแท่งเทียนที่ปิดสมบูรณ์แล้ว
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/trading"
            className="px-3 py-1.5 bg-white/10 hover:bg-white/15 text-gray-300 hover:text-white text-xs font-medium rounded-md border border-white/10 transition-colors flex items-center gap-1"
          >
            <span>←</span>
            <span>กลับไป Market Overview</span>
          </Link>
          <div className="market-mode">◈ {providerLabel(provider)}</div>
          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded-md border border-emerald-500/20">
            PAPER · EXECUTION DISABLED
          </span>
        </div>
      </div>

      {/* Market Toolbar */}
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

      {/* SMC Candlestick Chart Panel with Layer Overlays */}
      <section className="chart-panel">
        <div className="chart-toolbar">
          <div className="timeframes" role="group" aria-label="Timeframe">
            {timeframes.map((tf) => (
              <button key={tf} aria-pressed={timeframe === tf} onClick={() => setTimeframe(tf)}>
                {tf}
              </button>
            ))}
          </div>
          <span className="chart-caption">SMC OVERLAYS · CANDLES · BID · UTC</span>
        </div>

        <div className="chart-heading">
          <span>
            {symbol} <b> / {timeframe}</b>
          </span>
          <span data-testid="candle-count">{count} candles</span>
        </div>

        <div className="chart-stage">
          <ChartCanvas bind={bind} />
          {!count && (
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

      {/* Deep SMC & Multi-Timeframe Structural Analysis Component */}
      <AnalysisWorkspace
        symbol={symbol}
        timeframe={timeframe}
        source={provider?.source || ''}
        revision={revision}
        primitive={primitive}
        key={symbol + timeframe + retry}
      />

      {/* Technical Market Information Table */}
      <div className="market-bottom">
        <section className="market-info">
          <h2>Market information</h2>
          <dl>
            <div>
              <dt>Asset class</dt>
              <dd>{selected?.asset_class || 'METAL'}</dd>
            </div>
            <div>
              <dt>Provider</dt>
              <dd>
                {provider?.source || 'Unconfirmed'} / {provider?.mode || 'UNCONFIRMED'}
              </dd>
            </div>
            <div>
              <dt>Trading mode</dt>
              <dd className="gold-text">PAPER · execution disabled</dd>
            </div>
            <div>
              <dt>Timeframe</dt>
              <dd>{timeframe} · UTC boundaries</dd>
            </div>
            <div>
              <dt>Feed session</dt>
              <dd>
                {provider?.mode === 'SIMULATED'
                  ? 'Synthetic · continuous 24/7'
                  : 'Broker session; hours not confirmed'}
              </dd>
            </div>
            <div>
              <dt>Connection</dt>
              <dd>{status}</dd>
            </div>
            <div>
              <dt>Market state</dt>
              <dd>{provider?.market_state || 'UNKNOWN'}</dd>
            </div>
            <div>
              <dt>Source symbol</dt>
              <dd>{provider?.provider_symbol || 'XAUUSD'}</dd>
            </div>
            <div>
              <dt>Tick size · USD</dt>
              <dd>{provider?.tick_size || '—'}</dd>
            </div>
            <div>
              <dt>Last candle · UTC</dt>
              <dd>{provider?.last_candle || '—'}</dd>
            </div>
          </dl>
        </section>
      </div>

      <p className="chart-attribution">TradingView Lightweight Charts™ · Copyright © 2025 TradingView, Inc.</p>
    </div>
  );
}
