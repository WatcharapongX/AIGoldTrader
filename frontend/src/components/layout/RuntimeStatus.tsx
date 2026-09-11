'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { parseHealth, parseReady } from '@/lib/contracts';
import { parseStatus } from '@/features/chart/contracts';
import type { HealthResponse, ReadyResponse } from '@/types';
import type { MarketDataStatus } from '@/types/market.generated';

export interface RuntimeState {
  health: HealthResponse | null;
  ready: ReadyResponse | null;
  market: MarketDataStatus | null;
}

export function useRuntimeStatus(includeMarket = true): RuntimeState {
  const [state, setState] = useState<RuntimeState>({health:null, ready:null, market:null});
  useEffect(() => {
    const abort = new AbortController();
    let busy = false;
    const refresh = async () => {
      if (busy) return;
      busy = true;
      const signal = AbortSignal.any([abort.signal, AbortSignal.timeout(8000)]);
      const results = await Promise.allSettled([
        api.get('/healthz', {signal}).then(parseHealth),
        api.get('/readyz', {signal}).then(parseReady),
        includeMarket ? api.get('/market/status', {signal}).then(parseStatus) : Promise.resolve(null),
      ]);
      if (!abort.signal.aborted) setState({
        health:results[0].status === 'fulfilled' ? results[0].value : null,
        ready:results[1].status === 'fulfilled' ? results[1].value : null,
        market:results[2].status === 'fulfilled' ? results[2].value : null,
      });
      busy = false;
    };
    void refresh();
    const timer = setInterval(refresh, 15000);
    return () => { abort.abort(); clearInterval(timer); };
  }, [includeMarket]);
  return state;
}

export function TradingStatus({ health }: Pick<RuntimeState, 'health'>) {
  return <div data-testid="trading-status" className="flex flex-wrap items-center gap-x-2 text-xs text-amber-400">
    <strong>{health?.trading_mode ?? 'Trading: UNKNOWN'}</strong>
    <span>Auto Trading: {health ? (health.live_auto_trading ? 'ON' : 'OFF') : 'UNKNOWN'}</span>
  </div>;
}

export function RuntimeHealth({ health, ready, market }: RuntimeState) {
  return <dl data-testid="runtime-health" className="space-y-2 text-xs text-gray-400 break-words">
    <div><dt>Backend</dt><dd>{health ? 'HEALTHY' : 'UNKNOWN / ไม่พร้อมใช้งาน'}</dd></div>
    <div><dt>Database</dt><dd>{ready?.checks.database === true ? 'HEALTHY' : ready?.checks.database === false ? 'UNAVAILABLE' : 'UNKNOWN / ไม่พร้อมใช้งาน'}</dd></div>
    <div><dt>Market Data / MT5</dt><dd>{market ? `${market.source} · ${market.mode} · ${market.status}` : 'UNKNOWN / ไม่พร้อมใช้งาน'}</dd>
      <dd>{market?.detail}</dd></div>
    <div><dt>AI</dt><dd>NOT IMPLEMENTED</dd></div>
  </dl>;
}
