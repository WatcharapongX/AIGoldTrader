'use client';

import React from 'react';
import type { SetupCandidate } from '@/types/strategy.generated';
import type { AccountSnapshotData } from '@/types';
import type { KillSwitchData, RiskDecisionData } from '@/features/risk/contracts';

interface StrategyAnalysisContextProps {
  candidates: SetupCandidate[];
  selectedCandidateId: string;
  onSelectCandidate: (candidateId: string) => void;
  account: AccountSnapshotData | null;
  killSwitch: KillSwitchData | null;
  riskDecision: RiskDecisionData | null;
  onEvaluateAI: () => void;
  isEvaluating: boolean;
  evaluateError: string | null;
  hasAIResult: boolean;
  isOutdated: boolean;
}

export function StrategyAnalysisContext({
  candidates,
  selectedCandidateId,
  onSelectCandidate,
  account,
  killSwitch,
  riskDecision,
  onEvaluateAI,
  isEvaluating,
  evaluateError,
  hasAIResult,
  isOutdated,
}: StrategyAnalysisContextProps) {
  const selectedCandidate = candidates.find((c) => c.id === selectedCandidateId) || candidates[0];
  const hasCandidates = candidates.length > 0;
  const isKillActive = killSwitch?.state === 'ACTIVE';
  const isRiskBlocked = riskDecision?.decision === 'BLOCKED';

  // Zero-call gate condition
  let canEvaluate = true;
  let disabledReason = '';

  if (!hasCandidates || !selectedCandidate) {
    canEvaluate = false;
    disabledReason = 'ยังไม่มี Strategy Candidate สำหรับการวิเคราะห์ด้วย AI';
  } else if (isKillActive) {
    canEvaluate = false;
    disabledReason = `Kill Switch ทำงานอยู่ (${killSwitch?.reason_th || 'ACTIVE'}) — ระงับการวิเคราะห์ AI`;
  } else if (isRiskBlocked) {
    canEvaluate = false;
    disabledReason = 'Risk Engine สั่งบล็อก Candidate นี้ (BLOCKED)';
  } else if (isEvaluating) {
    canEvaluate = false;
    disabledReason = 'กำลังประมวลผลการวิเคราะห์ด้วย AI…';
  }

  return (
    <section
      data-testid="strategy-analysis-context"
      className="bg-[#0e1726] border border-gray-800 rounded-xl p-5 space-y-4"
      aria-label="Strategy and Risk Context"
    >
      {/* Title & Pipeline Invariant Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between pb-3 border-b border-gray-800 gap-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-lg">🎯</span>
            <h3 className="text-base font-bold text-white">
              Deterministic Strategy Candidate &amp; Risk Gate
            </h3>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            AI ทำงานภายใต้กรอบของ Strategy Candidate ที่ยืนยันแล้ว และต้องผ่านการตรวจสอบ Risk / Kill Switch ก่อนเสมอ
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono px-2.5 py-1 rounded bg-black/40 text-gray-300 border border-white/10">
            PIPELINE: MARKET → STRATEGY → RISK → AI
          </span>
        </div>
      </div>

      {/* Upstream Gate Indicators */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
        {/* Account Binding */}
        <div className="p-3 bg-black/20 rounded-lg border border-white/5">
          <span className="text-gray-400 block text-[11px]">ผูกกับบัญชีเทรด (Account):</span>
          <strong className="text-gray-200 block truncate font-mono mt-0.5">
            {account?.account_id || 'UNAVAILABLE'}
          </strong>
          <small className="text-gray-400 block mt-0.5">
            Balance: {account ? `$${Number(account.balance).toLocaleString('en-US', { minimumFractionDigits: 2 })}` : 'UNAVAILABLE'} · {account ? 'ACCOUNT SNAPSHOT' : 'NO ACCOUNT DATA'}
          </small>
        </div>

        {/* Risk Decision Gate */}
        <div className="p-3 bg-black/20 rounded-lg border border-white/5">
          <span className="text-gray-400 block text-[11px]">การอนุมัติความเสี่ยง (Risk Gate):</span>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className={`font-mono font-bold text-xs px-2 py-0.5 rounded uppercase ${
                isRiskBlocked
                  ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                  : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
              }`}
            >
              {riskDecision?.decision || 'CHECKING…'}
            </span>
            <small className="text-gray-400">
              {riskDecision?.decision === 'APPROVED' ? 'ผ่านเกณฑ์ความเสี่ยง' : isRiskBlocked ? 'ถูกบล็อก' : 'สถานะปกติ'}
            </small>
          </div>
        </div>

        {/* Kill Switch Gate */}
        <div className="p-3 bg-black/20 rounded-lg border border-white/5">
          <span className="text-gray-400 block text-[11px]">สวิตช์ความปลอดภัย (Kill Switch):</span>
          <div className="flex items-center gap-2 mt-0.5">
            <span
              className={`font-mono font-bold text-xs px-2 py-0.5 rounded uppercase ${
                isKillActive
                  ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30 animate-pulse'
                  : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
              }`}
            >
              {isKillActive ? 'ACTIVE (ล็อก)' : 'NORMAL (พร้อม)'}
            </span>
            <small className="text-gray-400">
              {isKillActive ? 'สวิตช์ฉุกเฉินเปิดอยู่' : 'ระบบปกติ 24 ชม.'}
            </small>
          </div>
        </div>
      </div>

      {/* Candidate Selection Area */}
      {!hasCandidates ? (
        <div className="p-4 bg-amber-500/10 border border-amber-500/20 rounded-lg text-amber-200 text-xs text-center space-y-1">
          <p className="font-semibold text-sm">ยังไม่มี Strategy Candidate สำหรับการวิเคราะห์ด้วย AI</p>
          <p className="text-gray-400">
            ระบบต้องการ Candidate ที่คำนวณจากกฎเกณฑ์ทางเทคนิคของกลยุทธ์ก่อน เพื่อให้ AI วิเคราะห์ตามบริบทจริง ไม่สามารถวิเคราะห์แบบ Free-Form ได้
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Candidate Selector Bar */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <label htmlFor="candidate-select" className="text-xs text-gray-300 font-medium">
                เลือก Candidate:
              </label>
              <select
                id="candidate-select"
                value={selectedCandidate?.id || ''}
                onChange={(e) => onSelectCandidate(e.target.value)}
                className="bg-black/50 text-white text-xs border border-gray-700 rounded px-2.5 py-1.5 focus:outline-none focus:border-amber-500"
              >
                {candidates.map((cand) => (
                  <option key={cand.id} value={cand.id}>
                    {cand.strategy_id} · {cand.direction} (Score: {cand.score}) · {cand.status}
                  </option>
                ))}
              </select>
            </div>

            <div className="text-[11px] text-gray-400 font-mono">
              ID: {selectedCandidate?.id.slice(0, 16)}… · Profile: {selectedCandidate?.profile_id}
            </div>
          </div>

          {/* Selected Candidate Technical Geometry (Read-Only) */}
          {selectedCandidate && (
            <div className="p-3.5 bg-black/40 rounded-lg border border-white/5 space-y-2.5">
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-2">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold text-amber-400">{selectedCandidate.strategy_id}</span>
                  <span
                    className={`text-[11px] px-2 py-0.5 rounded font-bold font-mono ${
                      selectedCandidate.direction === 'LONG'
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : selectedCandidate.direction === 'SHORT'
                        ? 'bg-rose-500/20 text-rose-400 border border-rose-500/30'
                        : 'bg-gray-700 text-gray-300'
                    }`}
                  >
                    {selectedCandidate.direction}
                  </span>
                  <span className="text-xs text-gray-300">
                    Setup Score: <strong>{selectedCandidate.score}</strong> / 100
                  </span>
                </div>
                <span className="text-[11px] text-gray-400">
                  ตรวจพบเมื่อ: {new Date(selectedCandidate.detected_at).toISOString()}
                </span>
              </div>

              {/* Trade Plan Geometry */}
              {selectedCandidate.plan ? (
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                  <div className="p-2 bg-black/30 rounded border border-white/5">
                    <span className="text-gray-400 block text-[10px]">ENTRY TYPE</span>
                    <strong className="text-gray-200">{selectedCandidate.plan.entry_type}</strong>
                  </div>
                  <div className="p-2 bg-black/30 rounded border border-white/5">
                    <span className="text-gray-400 block text-[10px]">ENTRY RANGE</span>
                    <strong className="text-amber-300">
                      ${Number(selectedCandidate.plan.entry_lower).toFixed(2)} - ${Number(selectedCandidate.plan.entry_upper).toFixed(2)}
                    </strong>
                  </div>
                  <div className="p-2 bg-black/30 rounded border border-white/5">
                    <span className="text-gray-400 block text-[10px]">STOP LOSS</span>
                    <strong className="text-rose-400">${Number(selectedCandidate.plan.stop_loss).toFixed(2)}</strong>
                  </div>
                  <div className="p-2 bg-black/30 rounded border border-white/5">
                    <span className="text-gray-400 block text-[10px]">TARGET (TP1)</span>
                    <strong className="text-emerald-400">
                      {selectedCandidate.plan.targets[0]
                        ? `$${Number(selectedCandidate.plan.targets[0].price).toFixed(2)} (RR ${selectedCandidate.plan.targets[0].rr})`
                        : '—'}
                    </strong>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-gray-400 italic">Candidate นี้ไม่มี Trade Plan Geometry ที่กำหนดไว้</p>
              )}

              <p className="text-[11px] text-gray-400 italic">
                * พารามิเตอร์ราคา Entry / SL / TP คำนวณจากอัลกอริทึมกลยุทธ์เชิงคณิตศาสตร์ (Deterministic) เท่านั้น AI ไม่มีสิทธิ์เปลี่ยนแปลงค่าเหล่านี้
              </p>
            </div>
          )}
        </div>
      )}

      {/* Evaluate Trigger Area */}
      <div className="pt-2 flex flex-col sm:flex-row items-center justify-between gap-3 border-t border-gray-800">
        <div className="text-xs text-gray-400">
          {!canEvaluate && (
            <span className="text-amber-400 flex items-center gap-1">
              <span>⛔</span>
              <span>{disabledReason}</span>
            </span>
          )}
          {canEvaluate && !isEvaluating && (
            <span className="text-gray-400">
              {hasAIResult
                ? isOutdated
                  ? 'Candidate มีการเปลี่ยนแปลง กรุณากดเพื่อประเมินใหม่'
                  : 'พร้อมส่งคำขอวิเคราะห์ซ้ำ (Explicit Refresh)'
                : 'พร้อมส่งคำขอวิเคราะห์ด้วย AI ให้ 6 Analytical Agents'}
            </span>
          )}
          {evaluateError && (
            <span className="text-rose-400 block mt-1">ข้อผิดพลาด: {evaluateError}</span>
          )}
        </div>

        <button
          type="button"
          onClick={onEvaluateAI}
          disabled={!canEvaluate || isEvaluating}
          className={`px-5 py-2 text-xs font-bold rounded-lg transition-all flex items-center gap-2 font-mono ${
            !canEvaluate || isEvaluating
              ? 'bg-gray-800 text-gray-500 cursor-not-allowed border border-gray-700'
              : hasAIResult
              ? 'bg-amber-600 hover:bg-amber-500 text-white shadow-lg hover:shadow-amber-500/20'
              : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-lg hover:shadow-emerald-500/20'
          }`}
        >
          {isEvaluating ? (
            <>
              <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              <span>กำลังวิเคราะห์ด้วย AI…</span>
            </>
          ) : (
            <>
              <span>🤖</span>
              <span>{hasAIResult ? 'รีเฟรชการวิเคราะห์ AI' : 'วิเคราะห์ด้วย AI'}</span>
            </>
          )}
        </button>
      </div>
    </section>
  );
}
