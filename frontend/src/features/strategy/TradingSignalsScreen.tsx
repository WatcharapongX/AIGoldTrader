'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { StrategyWorkspace } from '@/features/strategy/StrategyWorkspace';
import { AnalysisPrimitive } from '@/features/analysis/primitive';
import { api } from '@/lib/api';
import { parseStatus, timeframes } from '@/features/chart/contracts';
import type { MarketDataStatus, Timeframe } from '@/types/market.generated';

export function TradingSignalsScreen() {
  const [timeframe, setTimeframe] = useState<Timeframe>('M5');
  const [provider, setProvider] = useState<MarketDataStatus | null>(null);
  const [primitive] = useState(() => new AnalysisPrimitive());
  const [revision, setRevision] = useState('initial');

  useEffect(() => {
    const abort = new AbortController();
    const fetchStatus = async () => {
      try {
        const status = parseStatus(await api.get('/market/status', { signal: abort.signal }));
        setProvider(status);
        setRevision(`rev-${status.source}-${Date.now()}`);
      } catch {
        // Fallback
      }
    };
    void fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => {
      abort.abort();
      clearInterval(interval);
    };
  }, []);

  return (
    <div className="trading-workspace space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
            <p className="market-eyebrow tracking-widest text-xs font-semibold text-gray-400">
              RULE-BASED TRADING SIGNALS & STRATEGY EVALUATION
            </p>
          </div>
          <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight mt-1">Trading Signals</h1>
          <p className="text-xs text-gray-400 mt-0.5">
            ระบบคัดกรองและประเมินสัญญาณเทรดทองคำตาม 7 โปรไฟล์ผู้เทรด พร้อมกฎเกณฑ์ Setup Scoring และแผน Entry / SL / TP
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/trading"
            className="px-3 py-1.5 bg-white/10 hover:bg-white/15 text-gray-300 hover:text-white text-xs font-medium rounded-md border border-white/10 transition-colors flex items-center gap-1"
          >
            <span>←</span>
            <span>Market Overview</span>
          </Link>
          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 text-xs font-semibold rounded-md border border-emerald-500/20">
            PAPER MODE · EXECUTION DISABLED
          </span>
        </div>
      </div>

      {/* Timeframe Bar */}
      <div className="bg-[#101925] border border-[#253044] rounded-xl p-4 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold text-gray-300">กรอบเวลาที่กำลังประเมิน:</span>
          <div className="timeframes" role="group" aria-label="Timeframe">
            {timeframes.map((tf) => (
              <button key={tf} aria-pressed={timeframe === tf} onClick={() => setTimeframe(tf)}>
                {tf}
              </button>
            ))}
          </div>
        </div>
        <span className="text-xs text-gray-400">
          แหล่งข้อมูลราคา: <b className="text-amber-400 font-mono">{provider?.source || 'UNKNOWN'}</b>
        </span>
      </div>

      {/* Strategy Workspace Component */}
      <StrategyWorkspace
        timeframe={timeframe}
        source={provider?.source || 'UNKNOWN'}
        revision={revision}
        primitive={primitive}
      />
    </div>
  );
}
