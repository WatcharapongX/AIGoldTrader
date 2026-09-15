import type { SetupCandidate } from '@/types/strategy.generated';

export type ReportStatus = 'AVAILABLE' | 'PARTIAL' | 'STALE' | 'UNAVAILABLE' | 'NOT IMPLEMENTED';
export type ExportScalar = string | number | boolean | null | undefined;
export type ExportRow = Record<string, ExportScalar>;

export interface ExportColumn {
  key: string;
  label: string;
}

export interface ReportExportMetadata {
  report_type: string;
  generated_at: string;
  data_as_of: string | null;
  source: string;
  mode: string;
  coverage: string;
  filters: Record<string, string>;
}

const FORMULA_PREFIX = /^[\s\u0000-\u001f]*[=+\-@]/u;

/** Neutralize spreadsheet formulas only for text; legitimate negative numbers remain numeric. */
export function neutralizeSpreadsheetText(value: string): string {
  return FORMULA_PREFIX.test(value) ? `'${value}` : value;
}

function csvCell(value: ExportScalar): string {
  if (value === null || value === undefined) return 'NULL';
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : 'NULL';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  const safe = neutralizeSpreadsheetText(value);
  return /[",\r\n]/u.test(safe) ? `"${safe.replaceAll('"', '""')}"` : safe;
}

/** Stable RFC-4180-style CSV with a UTF-8 BOM for Excel/Thai compatibility. */
export function buildCsv(columns: ExportColumn[], rows: ExportRow[]): string {
  const header = columns.map((column) => csvCell(column.label)).join(',');
  const body = rows.map((row) => columns.map((column) => csvCell(row[column.key])).join(','));
  return `\uFEFF${[header, ...body].join('\r\n')}\r\n`;
}

export function buildJsonExport(metadata: ReportExportMetadata, rows: ExportRow[]): string {
  return JSON.stringify({ metadata, records: rows }, null, 2);
}

export function reportFilename(reportType: string, extension: 'csv' | 'json', now = new Date()): string {
  const slug = reportType.toLowerCase().replace(/[^a-z0-9]+/gu, '-').replace(/^-+|-+$/gu, '').slice(0, 48) || 'report';
  const date = now.toISOString().slice(0, 10);
  return `aigoldtrader-${slug}-${date}.${extension}`;
}

export function downloadTextArtifact(filename: string, content: string, mimeType: string): void {
  const blob = new Blob([content], { type: `${mimeType};charset=utf-8` });
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  anchor.rel = 'noopener';
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
}

const CANDIDATE_STATES = new Set([
  'DETECTED', 'WAITING_CONFIRMATION', 'READY', 'BLOCKED_CONTEXT',
  'NO_TRADE', 'INVALIDATED', 'EXPIRED', 'SUPERSEDED',
]);

export function parseCandidateList(value: unknown): SetupCandidate[] {
  if (!Array.isArray(value) || value.length > 100) throw new Error('Invalid candidate report payload');
  for (const item of value) {
    if (!item || typeof item !== 'object') throw new Error('Invalid candidate record');
    const row = item as Record<string, unknown>;
    if (
      typeof row.id !== 'string' || typeof row.profile_id !== 'string' ||
      typeof row.strategy_id !== 'string' || typeof row.symbol !== 'string' ||
      !['LONG', 'SHORT', 'NO_TRADE'].includes(String(row.direction)) ||
      !CANDIDATE_STATES.has(String(row.status)) || typeof row.score !== 'number' ||
      !Number.isFinite(row.score) || typeof row.detected_at !== 'string' ||
      !Array.isArray(row.evidence) || !Array.isArray(row.missing_conditions) || !Array.isArray(row.conflicts)
    ) throw new Error('Invalid candidate record');
  }
  return value as SetupCandidate[];
}
