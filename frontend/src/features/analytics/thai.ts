/**
 * Thai translations and formatting helpers for Performance & Analytics workspace (FC-08).
 */

import type { CanonicalCandidateState, ReadinessState } from './contracts';

export const CANDIDATE_STATE_TH: Record<CanonicalCandidateState, string> = {
  DETECTED: 'ตรวจพบเบื้องต้น',
  WAITING_CONFIRMATION: 'รอยืนยันสัญญาณ',
  READY: 'พร้อมเทรด (มีแผน)',
  BLOCKED_CONTEXT: 'ติดเงื่อนไขบริบท',
  NO_TRADE: 'ไม่มีเงื่อนไขเข้าเทรด',
  INVALIDATED: 'สัญญาณถูกยกเลิก',
  EXPIRED: 'แผนหมดอายุ',
  SUPERSEDED: 'มีรอบประเมินใหม่แทนที่',
};

export const CANDIDATE_STATE_COLORS: Record<CanonicalCandidateState, { bg: string; text: string; border: string }> = {
  DETECTED: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30' },
  WAITING_CONFIRMATION: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30' },
  READY: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  BLOCKED_CONTEXT: { bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/30' },
  NO_TRADE: { bg: 'bg-slate-500/10', text: 'text-slate-400', border: 'border-slate-500/30' },
  INVALIDATED: { bg: 'bg-zinc-500/10', text: 'text-zinc-400', border: 'border-zinc-500/30' },
  EXPIRED: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30' },
  SUPERSEDED: { bg: 'bg-purple-500/10', text: 'text-purple-400', border: 'border-purple-500/30' },
};

export const RISK_DECISION_TH: Record<'APPROVED' | 'REDUCED' | 'BLOCKED', string> = {
  APPROVED: 'อนุมัติความเสี่ยงเต็มจำนวน',
  REDUCED: 'อนุมัติแบบปรับลดความเสี่ยง',
  BLOCKED: 'ปฏิเสธความเสี่ยง / บล็อก',
};

export const RISK_DECISION_COLORS: Record<'APPROVED' | 'REDUCED' | 'BLOCKED', { bg: string; text: string; border: string }> = {
  APPROVED: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  REDUCED: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/30' },
  BLOCKED: { bg: 'bg-rose-500/10', text: 'text-rose-400', border: 'border-rose-500/30' },
};

export const ACCOUNT_SOURCE_TH: Record<string, string> = {
  CONFIGURED_PAPER: 'บัญชีจำลอง (ค่าเริ่มต้นระบบ)',
  PAPER_ACCOUNT_STATE: 'บัญชีจำลอง (Paper State Service)',
  PAPER_SNAPSHOT: 'Snapshot บัญชีจำลอง',
  CONFIGURED_TEST: 'บัญชีทดสอบระบบ',
  MT5_DEMO: 'บัญชี MT5 Demo',
  MT5_REAL: 'บัญชี MT5 Real (เทรดจริง)',
  UNAVAILABLE: 'ไม่สามารถเชื่อมต่อบัญชีได้',
};

export const READINESS_STATE_TH: Record<ReadinessState, { label: string; bg: string; text: string; border: string }> = {
  READY: { label: 'พร้อมใช้งาน', bg: 'bg-emerald-500/15', text: 'text-emerald-400', border: 'border-emerald-500/30' },
  LIMITED: { label: 'จำกัดประวัติล่าสุด', bg: 'bg-amber-500/15', text: 'text-amber-400', border: 'border-amber-500/30' },
  NOT_IMPLEMENTED: { label: 'ยังไม่พัฒนา', bg: 'bg-zinc-800', text: 'text-zinc-400', border: 'border-zinc-700' },
  NOT_AVAILABLE: { label: 'ไม่มีข้อมูล', bg: 'bg-rose-500/15', text: 'text-rose-400', border: 'border-rose-500/30' },
};

export function formatBangkokTime(isoString: string | null | undefined): string {
  if (!isoString) return 'ไม่มีข้อมูล';
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return 'วันเวลาไม่ถูกต้อง';
    return new Intl.DateTimeFormat('th-TH', {
      timeZone: 'Asia/Bangkok',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(d);
  } catch {
    return isoString;
  }
}

export function formatCurrency(value: string | number | null | undefined, currency: string = '$'): string {
  if (value === null || value === undefined || value === '') return 'N/A';
  const num = Number(value);
  if (!Number.isFinite(num)) return 'N/A';
  return `${currency}${num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatPercent(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'N/A';
  const num = Number(value);
  if (!Number.isFinite(num)) return 'N/A';
  return `${num.toFixed(2)}%`;
}
