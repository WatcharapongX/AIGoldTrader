'use client';

import React, { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  CandlestickSeries,
  ColorType,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts';
import { AnalysisWorkspace } from '@/features/analysis/AnalysisWorkspace';
import { AnalysisPrimitive } from '@/features/analysis/primitive';
import { StrategyAnalysisContext } from '@/features/analysis/StrategyAnalysisContext';
import { AIAgentAdvisoryPanel } from '@/features/analysis/AIAgentAdvisoryPanel';
import { api } from '@/lib/api';
import type { Candle, MarketDataStatus, Quote, SymbolInfo, Timeframe } from '@/types/market.generated';
import type { SetupCandidate, StrategyResponse } from '@/types/strategy.generated';
import type { AccountSnapshotData, SystemStatusResponse } from '@/types';
import type { KillSwitchData, RiskDecisionData } from '@/features/risk/contracts';
import { parseKillSwitch, parseRiskDecisions } from '@/features/risk/contracts';
import type { AIAnalysisResult } from '@/types/ai.generated';
import { instant, parseCandles, parseStatus, parseSymbols, providerLabel, timeframes } from '@/features/chart/contracts';
import { MarketConnection, type ConnectionState } from '@/features/chart/transport';
import { parseUiPreferences, UI_PREFERENCES_KEY } from '@/features/settings/contracts';

function chartPoint(candle: Candle) {
  return {
    time: (instant(candle.open_time) / 1000) as UTCTimestamp,
    open: Number(candle.open),
    high: Number(candle.high),
    low: Number(candle.low),
    close: Number(candle.close),
  };
}

export const ChartCanvas = memo(function ChartCanvas({
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
  return (
    <div
      ref={container}
      className="market-chart"
      aria-label="XAUUSD SMC analysis candlestick chart"
      role="img"
    />
  );
});

export interface MarketAnalysisViewProps {
  symbols: SymbolInfo[];
  symbol: string;
  setSymbol: (symbol: string) => void;
  timeframe: Timeframe;
  setTimeframe: (tf: Timeframe) => void;
  quote: Quote | null;
  status: ConnectionState;
  provider: MarketDataStatus | null;
  count: number;
  error: string;
  primitive: AnalysisPrimitive;
  revision: string;
  setRetry: React.Dispatch<React.SetStateAction<number>>;
  bind: (chart: IChartApi, series: ISeriesApi<'Candlestick'>) => () => void;
  // Upstream Strategy & Risk Context
  candidates: SetupCandidate[];
  selectedCandidateId: string;
  setSelectedCandidateId: (id: string) => void;
  account: AccountSnapshotData | null;
  killSwitch: KillSwitchData | null;
  riskDecision: RiskDecisionData | null;
  systemStatus: SystemStatusResponse | null;
  // AI Advisory Evaluation
  isEvaluating: boolean;
  aiResult: AIAnalysisResult | null;
  evaluatedCandidateId: string | null;
  aiError: string | null;
  onEvaluateAI: () => void;
}

export function MarketAnalysisView({
  symbols,
  symbol,
  setSymbol,
  timeframe,
  setTimeframe,
  quote,
  status,
  provider,
  count,
  error,
  primitive,
  revision,
  setRetry,
  bind,
  candidates,
  selectedCandidateId,
  setSelectedCandidateId,
  account,
  killSwitch,
  riskDecision,
  systemStatus,
  isEvaluating,
  aiResult,
  evaluatedCandidateId,
  aiError,
  onEvaluateAI,
}: MarketAnalysisViewProps) {
  const selected = symbols.find((item) => item.name === symbol);
  const digits = provider?.digits ?? selected?.digits ?? 2;

  const number = (value?: string) =>
    value === undefined
      ? '—'
      : Number(value).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });

  const lastUpdate = quote
    ? new Date(quote.timestamp).toLocaleTimeString('en-GB', { timeZone: 'UTC', hour12: false }) + ' UTC'
    : 'Waiting for quote';

  // Check if current AI result was produced for a different candidate than current selection
  const isOutdated = Boolean(
    aiResult && evaluatedCandidateId && selectedCandidateId && evaluatedCandidateId !== selectedCandidateId
  );
  const outdatedReason = isOutdated && evaluatedCandidateId
    ? `ผลวิเคราะห์ AI นี้สร้างขึ้นสำหรับ Candidate (${evaluatedCandidateId.slice(0, 12)}…) ก่อนหน้า กรุณากดปุ่มเพื่อประเมินใหม่อีกครั้ง`
    : undefined;

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
          <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight mt-1">
            Market Analysis
          </h1>
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
          {selectedCandidateId && (
            <Link href={`/signals?candidate=${encodeURIComponent(selectedCandidateId)}`} className="px-3 py-1.5 bg-amber-500/10 text-amber-300 text-xs font-medium rounded-md border border-amber-500/30">
              Candidate ต้นทาง →
            </Link>
          )}
          <div className="market-mode">◈ {providerLabel(provider)}</div>
          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded-md border border-emerald-500/20 font-mono">
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
        key={symbol + timeframe + revision}
      />

      {/* Deterministic Strategy Candidate & Risk Gate Context */}
      <StrategyAnalysisContext
        candidates={candidates}
        selectedCandidateId={selectedCandidateId}
        onSelectCandidate={setSelectedCandidateId}
        account={account}
        killSwitch={killSwitch}
        riskDecision={riskDecision}
        onEvaluateAI={onEvaluateAI}
        isEvaluating={isEvaluating}
        evaluateError={aiError}
        hasAIResult={Boolean(aiResult)}
        isOutdated={isOutdated}
      />

      {/* Multi-Agent AI Analytical Advisory Panel */}
      <AIAgentAdvisoryPanel
        result={aiResult}
        isLoading={isEvaluating}
        isOutdated={isOutdated}
        outdatedReason={outdatedReason}
        aiSystemStatus={systemStatus?.modules?.ai_provider || null}
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

      <p className="chart-attribution">
        TradingView Lightweight Charts™ · Copyright © 2025 TradingView, Inc.
      </p>
    </div>
  );
}

export function MarketAnalysisScreen({
  initialCandidateId = null,
  initialSymbol = null,
  initialTimeframe = null,
}: {
  initialCandidateId?: string | null;
  initialSymbol?: string | null;
  initialTimeframe?: string | null;
}) {
  const [symbols, setSymbols] = useState<SymbolInfo[]>([]);
  const [symbol, setSymbol] = useState(initialSymbol || 'XAUUSD');
  const [timeframe, setTimeframe] = useState<Timeframe>((initialTimeframe as Timeframe) || 'M15');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [status, setStatus] = useState<ConnectionState>('CONNECTING');
  const [provider, setProvider] = useState<MarketDataStatus | null>(null);
  const [count, setCount] = useState(0);
  const [error, setError] = useState('');
  const [primitive] = useState(() => new AnalysisPrimitive());
  const [revision, setRevision] = useState('');
  const [retry, setRetry] = useState(0);

  // Upstream Strategy & Risk state
  const [candidates, setCandidates] = useState<SetupCandidate[]>([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string>('');
  const [candidateLinkNotice, setCandidateLinkNotice] = useState('');
  const [symbolLinkNotice, setSymbolLinkNotice] = useState('');
  const [account, setAccount] = useState<AccountSnapshotData | null>(null);
  const [killSwitch, setKillSwitch] = useState<KillSwitchData | null>(null);
  const [riskDecisions, setRiskDecisions] = useState<RiskDecisionData[]>([]);
  const [systemStatus, setSystemStatus] = useState<SystemStatusResponse | null>(null);

  // AI Advisory evaluation state (transient local state)
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [aiResult, setAiResult] = useState<AIAnalysisResult | null>(null);
  const [evaluatedCandidateId, setEvaluatedCandidateId] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const data = useRef<Candle[]>([]);
  const latest = useRef<Quote | null>(null);
  const staleSeconds = useRef(5);
  const connectionState = useRef<ConnectionState>('CONNECTING');
  const riskDecision = useMemo(
    () => riskDecisions.find((decision) => decision.candidate_id === selectedCandidateId) || null,
    [riskDecisions, selectedCandidateId],
  );

  useEffect(() => {
    if (initialTimeframe) return;
    const timer = window.setTimeout(() => {
      try {
        const stored = localStorage.getItem(UI_PREFERENCES_KEY);
        if (stored) setTimeframe(parseUiPreferences(JSON.parse(stored)).default_timeframe);
      } catch {}
    }, 0);
    return () => window.clearTimeout(timer);
  }, [initialTimeframe]);

  const bindCandidates = useCallback((list: SetupCandidate[]) => {
    setCandidates(list);
    const requested = initialCandidateId ? list.find((candidate) => candidate.id === initialCandidateId) : null;
    setSelectedCandidateId(requested?.id || list[0]?.id || '');
    setCandidateLinkNotice(initialCandidateId && !requested ? 'ไม่พบ Candidate ที่ระบุในข้อมูล authoritative; แสดงรายการล่าสุดแทน' : '');
  }, [initialCandidateId]);

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

  // 1. Fetch Upstream Context (Candidates, Account, Kill Switch, Risk Decisions, System Status)
  useEffect(() => {
    let active = true;
    const abort = new AbortController();

    const fetchUpstream = async () => {
      // System status
      try {
        const sys = (await api.get('/system/status', { signal: abort.signal })) as SystemStatusResponse;
        if (active) setSystemStatus(sys);
      } catch {}

      // Account
      try {
        const acc = (await api.get('/risk/account?account_id=default_paper_account', {
          signal: abort.signal,
        })) as AccountSnapshotData;
        if (active) setAccount(acc);
      } catch {}

      // Kill Switch
      try {
        const rawKs = await api.get('/risk/kill-switch', { signal: abort.signal });
        if (active) setKillSwitch(parseKillSwitch(rawKs));
      } catch {}

      // Strategy Candidates
      try {
        const list = (await api.get('/trade-candidates?limit=10', {
          signal: abort.signal,
        })) as SetupCandidate[];
        if (active && Array.isArray(list) && list.length > 0) {
          bindCandidates(list);
        } else {
          // Fallback to /strategy/context
          const strat = (await api.get('/strategy/context', { signal: abort.signal })) as StrategyResponse;
          if (active && strat.evaluation?.candidates?.length) {
            bindCandidates(strat.evaluation.candidates);
          }
        }
      } catch {
        try {
          const strat = (await api.get('/strategy/context', { signal: abort.signal })) as StrategyResponse;
          if (active && strat.evaluation?.candidates?.length) {
            bindCandidates(strat.evaluation.candidates);
          }
        } catch {}
      }

      // Risk Decisions
      try {
        const rawDecisions = await api.get('/risk/decisions?limit=50', { signal: abort.signal });
        const parsed = parseRiskDecisions(rawDecisions);
        if (active) {
          setRiskDecisions(parsed);
        }
      } catch {}
    };

    void fetchUpstream();

    return () => {
      active = false;
      abort.abort();
    };
  }, [retry, bindCandidates]);

  // 2. Fetch Candlestick & Quote Market Feed
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
          if (initialSymbol && !list.some((item) => item.name === symbol)) {
            setSymbolLinkNotice(`ไม่พบ Symbol ${initialSymbol} ในแหล่งข้อมูล authoritative; กลับไปใช้ XAUUSD`);
            setSymbol('XAUUSD');
            return;
          }
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
  }, [symbol, timeframe, retry, initialSymbol]);

  // Digits update
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

  // 3. AI Evaluation Trigger
  const handleEvaluateAI = async () => {
    const candidate = candidates.find((c) => c.id === selectedCandidateId) || candidates[0];
    if (!candidate || !riskDecision || killSwitch?.state !== 'INACTIVE') {
      setAiError('AI evaluation ถูกระงับ: ต้องมี Risk Decision ของ Candidate เดียวกันและ Kill Switch ต้องยืนยันเป็น INACTIVE');
      return;
    }

    setIsEvaluating(true);
    setAiError(null);

    try {
      const payload = {
        candidate_id: candidate.id,
        account_id: account?.account_id || 'default_paper_account',
        profile_id: candidate.profile_id || undefined,
      };
      const result = (await api.post('/ai-analysis/evaluate', payload)) as AIAnalysisResult;
      setAiResult(result);
      setEvaluatedCandidateId(candidate.id);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'เกิดข้อผิดพลาดในการวิเคราะห์ AI';
      setAiError(message);
    } finally {
      setIsEvaluating(false);
    }
  };

  return (
    <>{(candidateLinkNotice || symbolLinkNotice) && <div role="alert" className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 text-xs text-amber-300">{candidateLinkNotice || symbolLinkNotice}</div>}<MarketAnalysisView
      symbols={symbols}
      symbol={symbol}
      setSymbol={setSymbol}
      timeframe={timeframe}
      setTimeframe={setTimeframe}
      quote={quote}
      status={status}
      provider={provider}
      count={count}
      error={error}
      primitive={primitive}
      revision={revision}
      setRetry={setRetry}
      bind={bind}
      candidates={candidates}
      selectedCandidateId={selectedCandidateId}
      setSelectedCandidateId={setSelectedCandidateId}
      account={account}
      killSwitch={killSwitch}
      riskDecision={riskDecision}
      systemStatus={systemStatus}
      isEvaluating={isEvaluating}
      aiResult={aiResult}
      evaluatedCandidateId={evaluatedCandidateId}
      aiError={aiError}
      onEvaluateAI={handleEvaluateAI}
    /></>
  );
}
