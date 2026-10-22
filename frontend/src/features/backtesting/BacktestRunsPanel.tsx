'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { api } from '@/lib/api';

interface BacktestRun {
  id: string;
  status: string;
  symbol: string;
  strategy_id: string;
  profile_id: string;
  simulation_fingerprint: string | null;
  failure_code: string | null;
  payload: {
    metrics?: Record<string, string | number | null>;
    provenance?: Record<string, string>;
  };
}

interface TradeItem {
  candidate_id: string;
  status: string;
  direction?: string | null;
  net_pnl?: string;
  r_multiple?: string | null;
  exit_reason?: string;
}

export function BacktestRunsPanel() {
  const [runs, setRuns] = useState<BacktestRun[] | null>(null);
  const [selected, setSelected] = useState<BacktestRun | null>(null);
  const [trades, setTrades] = useState<TradeItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = (await api.get('/backtests?limit=50')) as BacktestRun[];
      setRuns(data);
      setError(null);
    } catch (e) {
      setRuns([]);
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const openRun = async (run: BacktestRun) => {
    setSelected(run);
    try {
      const data = (await api.get(`/backtests/${run.id}/trades?limit=100`)) as { items: TradeItem[] };
      setTrades(data.items ?? []);
    } catch {
      setTrades([]);
    }
  };

  const metrics = selected?.payload?.metrics;

  return (
    <section aria-label="Backtest Runs" className="space-y-4 rounded-xl border border-gray-800 bg-[#0e1726] p-5">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-bold text-white">Backtest Runs (Batch D5/D6)</h4>
        <button type="button" onClick={() => void load()} className="rounded border border-white/10 px-3 py-1 text-xs text-gray-200">
          รีเฟรช
        </button>
      </div>
      {error && runs?.length === 0 && (
        <p role="alert" className="text-xs text-amber-300">UNAVAILABLE — โหลดรายการ backtest ไม่สำเร็จ ({error})</p>
      )}
      {runs === null && <p role="status" className="text-xs text-gray-400">กำลังโหลด…</p>}
      {runs !== null && runs.length === 0 && !error && (
        <p className="text-xs text-gray-400">ยังไม่มี backtest run — สร้างผ่าน API <code>POST /api/backtests</code> ด้วย governed replay inputs</p>
      )}
      {runs !== null && runs.length > 0 && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <ul className="space-y-2">
            {runs.map((run) => (
              <li key={run.id}>
                <button
                  type="button"
                  onClick={() => void openRun(run)}
                  className="w-full rounded-lg border border-white/10 bg-black/30 p-3 text-left text-xs text-gray-200"
                  aria-pressed={selected?.id === run.id}
                >
                  <span className="font-mono font-bold text-white">{run.id}</span>{' '}
                  <span className="text-amber-300">{run.status}</span>
                  <span className="block text-gray-400">
                    {run.symbol} · {run.strategy_id} · {run.profile_id}
                  </span>
                  {run.simulation_fingerprint && (
                    <span className="block break-all text-[10px] text-gray-500">fp: {run.simulation_fingerprint}</span>
                  )}
                </button>
              </li>
            ))}
          </ul>
          {selected && (
            <div className="rounded-lg border border-white/10 bg-black/30 p-3 text-xs text-gray-200">
              <h5 className="font-bold text-white">Run Detail</h5>
              {selected.payload.provenance && (
                <p className="mt-1 break-all text-[10px] text-gray-400">
                  provenance: risk={selected.payload.provenance.risk_replay_fingerprint ?? '—'} · data=
                  {selected.payload.provenance.data_fingerprint ?? '—'}
                </p>
              )}
              {metrics ? (
                <dl className="mt-2 grid grid-cols-2 gap-2 font-mono">
                  <div>Trades: {String(metrics.total_trades ?? '—')}</div>
                  <div>Win rate: {metrics.win_rate == null ? 'N/A' : `${metrics.win_rate}%`}</div>
                  <div>Net: {String(metrics.net_profit ?? '—')}</div>
                  <div>PF: {metrics.profit_factor == null ? 'N/A' : String(metrics.profit_factor)}</div>
                  <div>Max DD: {String(metrics.max_drawdown ?? '—')}</div>
                  <div>Return: {metrics.return_pct == null ? 'N/A' : `${metrics.return_pct}%`}</div>
                </dl>
              ) : (
                <p className="mt-2 text-gray-400">ไม่มี metrics (run ไม่สำเร็จ: {selected.failure_code ?? selected.status})</p>
              )}
              <h6 className="mt-3 font-bold text-white">Trade Ledger ({trades.length})</h6>
              <ul className="mt-1 max-h-64 space-y-1 overflow-auto font-mono text-[11px]">
                {trades.map((t, i) => (
                  <li key={`${t.candidate_id}-${i}`} className="flex justify-between gap-2">
                    <span>{t.status}</span>
                    <span>{t.direction ?? '—'}</span>
                    <span>{t.net_pnl ?? '0'}</span>
                    <span>{t.exit_reason ?? ''}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
