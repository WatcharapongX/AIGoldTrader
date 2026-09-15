'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import type {
  SetupCandidate,
  StrategyDefinition,
  TraderProfile,
  Transition,
} from '@/types/strategy.generated';
import type { KillSwitchData, RiskDecisionData } from '@/features/risk/contracts';
import { api } from '@/lib/api';
import { label, utc } from './thai';

interface SignalDetailPanelProps {
  candidate: SetupCandidate | null;
  strategy?: StrategyDefinition;
  profile?: TraderProfile;
  killSwitch: KillSwitchData | null;
  riskDecisions: RiskDecisionData[];
}

export function SignalDetailPanel({
  candidate,
  strategy,
  profile,
  killSwitch,
  riskDecisions,
}: SignalDetailPanelProps) {
  const [transitions, setTransitions] = useState<Transition[]>([]);
  const [loadingTransitions, setLoadingTransitions] = useState(false);
  const [transitionError, setTransitionError] = useState<string | null>(null);

  // Fetch transition timeline when candidate changes
  useEffect(() => {
    if (!candidate?.id) return;

    let active = true;
    const abort = new AbortController();

    const fetchTransitions = async () => {
      setLoadingTransitions(true);
      setTransitionError(null);
      try {
        const data = (await api.get(`/trade-candidates/${candidate.id}/transitions`, {
          signal: abort.signal,
        })) as Transition[];
        if (active) {
          setTransitions(Array.isArray(data) ? data : []);
        }
      } catch (err) {
        if (active) {
          setTransitionError(err instanceof Error ? err.message : 'โหลดประวัติสถานะไม่สำเร็จ');
          setTransitions([]);
        }
      } finally {
        if (active) setLoadingTransitions(false);
      }
    };

    void fetchTransitions();

    return () => {
      active = false;
      abort.abort();
    };
  }, [candidate?.id]);

  if (!candidate) {
    return (
      <div
        data-testid="signal-detail-empty"
        className="bg-[#0e1726] border border-gray-800 rounded-xl p-8 text-center text-gray-400 space-y-2"
      >
        <span className="text-3xl block">📋</span>
        <h3 className="text-sm font-bold text-gray-300">เลือก Candidate เพื่อดูรายละเอียด</h3>
        <p className="text-xs text-gray-400 max-w-sm mx-auto">
          คลิกเลือก Setup Candidate จากรายการด้านซ้าย เพื่อตรวจสอบแผนราคา Entry / SL / TP, หลักฐานเชิงกฎเกณฑ์ และประวัติสถานะ
        </p>
      </div>
    );
  }

  // Strict Risk Decision Association: candidate_id MUST match exactly
  const matchedRiskDecision = riskDecisions.find((d) => d.candidate_id === candidate.id) || null;

  const isKillActive = killSwitch?.state === 'ACTIVE';
  const isPlanExpired = candidate.status === 'EXPIRED';

  return (
    <div
      data-testid="signal-detail-panel"
      className="bg-[#0e1726] border border-gray-800 rounded-xl p-5 space-y-5"
    >
      {/* 1. Candidate Header & Deep Link Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-3 pb-4 border-b border-gray-800">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`px-2.5 py-0.5 text-xs font-mono font-bold rounded uppercase ${
                candidate.status === 'READY'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  : candidate.status === 'WAITING_CONFIRMATION'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                  : candidate.status === 'BLOCKED_CONTEXT'
                  ? 'bg-orange-500/20 text-orange-300 border border-orange-500/40'
                  : 'bg-gray-800 text-gray-300 border border-gray-700'
              }`}
            >
              {candidate.status} · {label(candidate.status)}
            </span>
            <span
              className={`px-2 py-0.5 text-xs font-bold rounded ${
                candidate.direction === 'LONG'
                  ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                  : candidate.direction === 'SHORT'
                  ? 'bg-rose-500/15 text-rose-400 border border-rose-500/30'
                  : 'bg-gray-800 text-gray-400'
              }`}
            >
              {candidate.direction} ({label(candidate.direction)})
            </span>
            <span className="text-xs font-mono text-gray-400">
              Symbol: <b className="text-white">{candidate.symbol}</b>
            </span>
          </div>

          <h3 className="text-lg font-bold text-white tracking-wide mt-2">
            {strategy?.name || candidate.strategy_id}
          </h3>
          <p className="text-xs text-gray-400 mt-0.5">
            {strategy?.description_th || 'กลยุทธ์ตรวจสอบเงื่อนไขทางเทคนิค'} · โปรไฟล์:{' '}
            <strong className="text-gray-200">{profile?.name || candidate.profile_id}</strong> (
            {profile?.style ? label(profile.style) : ''})
          </p>
        </div>

        {/* Action: Link to Market Analysis with candidate query */}
        <div className="flex flex-col items-start sm:items-end gap-1.5 shrink-0">
          <Link
            href={`/analysis?candidate=${encodeURIComponent(candidate.id)}`}
            className="px-3.5 py-1.5 bg-gradient-to-r from-amber-500/20 to-purple-500/20 hover:from-amber-500/30 hover:to-purple-500/30 text-amber-300 hover:text-amber-200 text-xs font-semibold rounded-lg border border-amber-500/40 transition-all flex items-center gap-1.5 shadow-md"
          >
            <span>🤖</span>
            <span>วิเคราะห์ด้วย AI ใน Market Analysis →</span>
          </Link>
          <span className="text-[10px] text-gray-400 font-mono">
            ID: {candidate.id.slice(0, 16)}…
          </span>
        </div>
      </div>

      {/* 2. Candidate Identity & Timestamps */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 p-3 bg-black/30 rounded-lg border border-white/5 text-xs font-mono">
        <div>
          <span className="text-gray-400 block text-[10px]">EVIDENCE SCORE</span>
          <strong className="text-amber-300 text-sm">{candidate.score} / 100</strong>
        </div>
        <div>
          <span className="text-gray-400 block text-[10px]">DETECTED UTC</span>
          <span className="text-gray-300">{utc(candidate.detected_at)}</span>
        </div>
        <div>
          <span className="text-gray-400 block text-[10px]">CONFIRMED UTC</span>
          <span className="text-gray-300">
            {candidate.confirmed_at ? utc(candidate.confirmed_at) : '—'}
          </span>
        </div>
        <div>
          <span className="text-gray-400 block text-[10px]">EXPIRES UTC</span>
          <span className="text-gray-300">{utc(candidate.expires_at)}</span>
        </div>
      </div>

      {/* 3. Trade Plan Suggestion Geometry */}
      <section className="space-y-3" aria-label="Trade Plan Geometry">
        <div className="flex items-center justify-between pb-1 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <span className="text-base">📐</span>
            <h4 className="text-sm font-bold text-white">
              Deterministic Trade Plan Suggestion
            </h4>
          </div>
          <span className="px-2 py-0.5 text-[10px] font-mono font-bold rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
            SUGGESTION_ONLY
          </span>
        </div>

        <div className="p-3.5 bg-black/40 rounded-xl border border-white/5 space-y-3">
          <div className="flex items-center justify-between text-xs">
            <span className="text-gray-400 font-semibold">
              สถานะแผน: {isPlanExpired ? (
                <span className="text-gray-400 font-bold uppercase">EXPIRED (หมดอายุแล้ว)</span>
              ) : (
                <span className="text-emerald-400 font-bold uppercase">ACTIVE SUGGESTION</span>
              )}
            </span>
            <span className="text-[11px] text-gray-400 italic">
              * แผนราคาเพื่อการวิเคราะห์เท่านั้น ยังไม่ใช่คำสั่งซื้อขาย
            </span>
          </div>

          {candidate.plan ? (
            <div className="space-y-3">
              {/* Entry / SL / Expiry Parameters */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
                <div className="p-2.5 bg-black/40 rounded-lg border border-white/5">
                  <span className="text-gray-400 block text-[10px]">ENTRY TYPE</span>
                  <strong className="text-gray-200">{candidate.plan.entry_type}</strong>
                </div>
                <div className="p-2.5 bg-black/40 rounded-lg border border-white/5">
                  <span className="text-gray-400 block text-[10px]">ENTRY ZONE</span>
                  <strong className="text-amber-300">
                    ${Number(candidate.plan.entry_lower).toFixed(2)} – ${Number(candidate.plan.entry_upper).toFixed(2)}
                  </strong>
                </div>
                <div className="p-2.5 bg-black/40 rounded-lg border border-white/5">
                  <span className="text-gray-400 block text-[10px]">STOP LOSS</span>
                  <strong className="text-rose-400">${Number(candidate.plan.stop_loss).toFixed(2)}</strong>
                </div>
                <div className="p-2.5 bg-black/40 rounded-lg border border-white/5">
                  <span className="text-gray-400 block text-[10px]">PLAN EXPIRES</span>
                  <span className="text-gray-300">{utc(candidate.plan.expires_at)}</span>
                </div>
              </div>

              {/* Targets List */}
              <div>
                <span className="text-xs font-semibold text-emerald-400 block mb-1.5">
                  เป้าหมายทำกำไร (Targets &amp; Risk-to-Reward):
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                  {candidate.plan.targets.map((t, idx) => (
                    <div
                      key={t.name + idx}
                      className="p-2 bg-black/30 rounded-lg border border-emerald-500/20 flex items-center justify-between text-xs font-mono"
                    >
                      <span className="text-gray-300 font-bold">{t.name}:</span>
                      <strong className="text-emerald-400">${Number(t.price).toFixed(2)}</strong>
                      <span className="text-[11px] text-gray-400">RR {t.rr}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Invalidation Rule */}
              <div className="text-xs text-gray-300 bg-black/30 p-2.5 rounded-lg border border-white/5">
                <span className="text-amber-400 font-semibold block mb-0.5">เงื่อนไขยกเลิกแผน (Invalidation):</span>
                <span>{candidate.plan.invalidation_th || candidate.invalidation_th}</span>
              </div>
            </div>
          ) : (
            <p className="text-xs text-gray-400 italic py-2 text-center">
              ยังไม่มีข้อเสนอแผนราคา Entry / SL / TP สำหรับ Candidate นี้
            </p>
          )}
        </div>
      </section>

      {/* 4. Explainability: Evidence, Missing Conditions, Conflicts */}
      <section className="space-y-3" aria-label="Explainability Context">
        <h4 className="text-sm font-bold text-white pb-1 border-b border-gray-800 flex items-center gap-2">
          <span>🔍</span>
          <span>หลักฐานและข้อจำกัดเชิงกฎเกณฑ์ (Explainability)</span>
        </h4>

        {/* Evidence List */}
        <div className="space-y-2">
          <span className="text-xs font-semibold text-emerald-400 block">
            หลักฐานที่สนับสนุน ({candidate.evidence.length} ข้อ):
          </span>
          {candidate.evidence.length > 0 ? (
            <div className="space-y-1.5">
              {candidate.evidence.map((e, idx) => (
                <div
                  key={e.code + idx}
                  className="p-2.5 bg-black/30 rounded-lg border border-white/5 text-xs text-gray-200 flex items-start justify-between gap-2"
                >
                  <div className="flex items-start gap-2">
                    <span className="text-emerald-400 font-bold mt-0.5">✓</span>
                    <span>{e.description_th}</span>
                  </div>
                  <span className="text-amber-300 font-mono font-bold shrink-0">
                    +{e.weight || 0} คะแนน
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-gray-400 italic">ไม่มีหลักฐานบันทึกไว้</p>
          )}
        </div>

        {/* Missing Conditions (Important for DETECTED / WAITING_CONFIRMATION) */}
        {candidate.missing_conditions.length > 0 && (
          <div className="space-y-1.5 pt-1">
            <span className="text-xs font-semibold text-amber-400 block">
              เงื่อนไขที่ยังไม่ครบ (Missing Conditions):
            </span>
            <div className="space-y-1">
              {candidate.missing_conditions.map((m, idx) => (
                <div
                  key={idx}
                  className="p-2 bg-amber-500/10 border border-amber-500/20 rounded-lg text-xs text-amber-200 flex items-start gap-2"
                >
                  <span className="text-amber-400 font-bold mt-0.5">⏳</span>
                  <span>{m}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Conflicts (Important for BLOCKED_CONTEXT) */}
        {candidate.conflicts.length > 0 && (
          <div className="space-y-1.5 pt-1">
            <span className="text-xs font-semibold text-rose-400 block">
              ข้อจำกัดหรือข้อขัดแย้งที่บล็อก Setup (Conflicts):
            </span>
            <div className="space-y-1">
              {candidate.conflicts.map((c, idx) => (
                <div
                  key={idx}
                  className="p-2 bg-rose-500/10 border border-rose-500/25 rounded-lg text-xs text-rose-200 flex items-start gap-2"
                >
                  <span className="text-rose-400 font-bold mt-0.5">⛔</span>
                  <span>{c}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </section>

      {/* 5. Risk & Kill Switch Authority Context */}
      <section className="space-y-3" aria-label="Risk and Safety Gate">
        <h4 className="text-sm font-bold text-white pb-1 border-b border-gray-800 flex items-center gap-2">
          <span>🛡️</span>
          <span>การตรวจสอบความเสี่ยงและความปลอดภัย (Risk Authority)</span>
        </h4>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
          {/* Risk Decision: Strict Association */}
          <div className="p-3.5 bg-black/30 rounded-lg border border-white/5 space-y-1.5">
            <span className="text-gray-400 font-semibold block text-[11px]">
              การอนุมัติความเสี่ยง (Risk Decision):
            </span>
            {matchedRiskDecision ? (
              <div className="space-y-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`font-mono font-bold text-xs px-2 py-0.5 rounded uppercase ${
                      matchedRiskDecision.decision === 'APPROVED'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                        : matchedRiskDecision.decision === 'REDUCED'
                        ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40'
                        : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                    }`}
                  >
                    {matchedRiskDecision.decision}
                  </span>
                  <span className="font-mono text-gray-300">
                    ความเสี่ยง: {matchedRiskDecision.approved_risk_pct}%
                  </span>
                </div>
                <p className="text-gray-300 text-[11px]">
                  ขนาดสัญญาประเมิน: {matchedRiskDecision.position_size} Lot
                </p>
              </div>
            ) : (
              <p className="text-gray-400 italic text-[11px]">
                ยังไม่มี Risk Decision ที่ยืนยันว่าเป็นของ Candidate นี้
              </p>
            )}
          </div>

          {/* Kill Switch Gate */}
          <div className="p-3.5 bg-black/30 rounded-lg border border-white/5 space-y-1.5">
            <span className="text-gray-400 font-semibold block text-[11px]">
              สวิตช์ความปลอดภัยฉุกเฉิน (Kill Switch):
            </span>
            <div className="flex items-center gap-2">
              <span
                className={`font-mono font-bold text-xs px-2 py-0.5 rounded uppercase ${
                  isKillActive
                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40 animate-pulse'
                    : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                }`}
              >
                {isKillActive ? 'ACTIVE (BLOCKED)' : 'NORMAL (CLEAR)'}
              </span>
              <span className="text-gray-300 text-[11px]">
                {isKillActive ? 'การส่งคำสั่งถูกระงับทั่วระบบ' : 'ระบบปกติ 24 ชม.'}
              </span>
            </div>
            {isKillActive && (
              <p className="text-rose-300 text-[11px]">
                เหตุผล: {killSwitch?.reason_th || 'เปิดใช้งานด้วยมือ'}
              </p>
            )}
          </div>
        </div>
      </section>

      {/* 6. Candidate Transition Timeline */}
      <section className="space-y-3" aria-label="Transition Timeline">
        <div className="flex items-center justify-between pb-1 border-b border-gray-800">
          <div className="flex items-center gap-2">
            <span className="text-base">⏱️</span>
            <h4 className="text-sm font-bold text-white">
              ประวัติการเปลี่ยนสถานะ (State Transition Timeline)
            </h4>
          </div>
          <span className="text-xs font-mono text-gray-400">
            {transitions.length} TRANSITIONS
          </span>
        </div>

        {loadingTransitions ? (
          <div className="p-4 text-center text-xs text-amber-400 animate-pulse">
            กำลังโหลดประวัติการเปลี่ยนสถานะ…
          </div>
        ) : transitionError ? (
          <div className="p-3 bg-rose-500/10 border border-rose-500/20 rounded-lg text-xs text-rose-300">
            ข้อผิดพลาด: {transitionError}
          </div>
        ) : transitions.length === 0 ? (
          <div className="p-4 bg-black/20 rounded-lg border border-white/5 text-center text-xs text-gray-400 italic">
            ยังไม่มีประวัติการเปลี่ยนสถานะ
          </div>
        ) : (
          <div className="space-y-2 relative pl-4 border-l-2 border-gray-800">
            {transitions.map((t, idx) => (
              <div key={t.id || idx} className="relative pb-2">
                <span className="absolute -left-[21px] top-1.5 w-2.5 h-2.5 rounded-full bg-amber-400" />
                <div className="p-2.5 bg-black/30 rounded-lg border border-white/5 text-xs space-y-1">
                  <div className="flex items-center justify-between gap-2 font-mono">
                    <span className="font-bold text-white">
                      {t.from_status} → <span className="text-amber-300">{t.to_status}</span>
                    </span>
                    <span className="text-gray-400 text-[10px]">{utc(t.as_of)}</span>
                  </div>
                  {t.reason_th && <p className="text-gray-300 text-[11px]">{t.reason_th}</p>}
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
