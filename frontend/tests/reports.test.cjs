const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadContracts() {
  const filename = path.resolve(__dirname, '../src/features/reports/contracts.ts');
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports, module: { exports }, require, Blob, URL, document: {} });
  return exports;
}

const contracts = loadContracts();
const screenCode = fs.readFileSync(path.resolve(__dirname, '../src/features/reports/ReportsScreen.tsx'), 'utf8');

test('CSV export has UTF-8 BOM, stable headers, escaping, and distinct null/zero values', () => {
  const columns = [{ key: 'name', label: 'NAME' }, { key: 'value', label: 'VALUE' }];
  const csv = contracts.buildCsv(columns, [
    { name: 'ข่าว,ทอง "แรง"\nวันนี้', value: null },
    { name: 'zero', value: 0 },
    { name: 'negative number', value: -12.5 },
  ]);
  assert.equal(csv.charCodeAt(0), 0xfeff);
  assert.match(csv, /^﻿NAME,VALUE\r\n/);
  assert.match(csv, /"ข่าว,ทอง ""แรง""\nวันนี้",NULL/);
  assert.match(csv, /zero,0/);
  assert.match(csv, /negative number,-12\.5/);
});

test('CSV formula injection is neutralized for text but numeric negatives are preserved', () => {
  const columns = [{ key: 'value', label: 'VALUE' }];
  for (const formula of ['=2+2', '+SUM(A1:A2)', '-1+2', '@cmd', ' \t=IMPORTXML()']) {
    const csv = contracts.buildCsv(columns, [{ value: formula }]);
    assert.match(csv, new RegExp(`'${formula.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`));
  }
  assert.match(contracts.buildCsv(columns, [{ value: -8 }]), /\r\n-8\r\n$/);
});

test('JSON export is a metadata envelope and safe filenames are normalized', () => {
  const metadata = {
    report_type: 'risk', generated_at: '2026-09-15T00:00:00.000Z', data_as_of: null,
    source: '/risk/decisions', mode: 'PAPER', coverage: '50 max', filters: {},
  };
  const parsed = JSON.parse(contracts.buildJsonExport(metadata, [{ decision: 'BLOCKED', amount: null }]));
  assert.equal(parsed.metadata.report_type, 'risk');
  assert.equal(parsed.records[0].amount, null);
  assert.equal(contracts.reportFilename('../../Risk Report', 'csv', new Date('2026-09-15T00:00:00Z')), 'aigoldtrader-risk-report-2026-09-15.csv');
});

test('candidate parser rejects malformed or oversized report payloads', () => {
  assert.throws(() => contracts.parseCandidateList([{ id: 'only-id' }]));
  assert.throws(() => contracts.parseCandidateList(Array.from({ length: 101 }, () => ({}))));
});

test('Reports screen uses bounded authenticated APIs and isolated aggregate failures', () => {
  for (const endpoint of [
    '/healthz', '/readyz', '/system/status', '/market/status', '/market/quote',
    '/trade-candidates?limit=100', '/strategy/evaluations?limit=25', '/risk/decisions?limit=50',
    '/risk/account', '/risk/portfolio', '/risk/policy', '/risk/kill-switch', '/calendar/economic', '/news/context',
  ]) assert.match(screenCode, new RegExp(endpoint.replace(/[/?*+]/g, '\\$&')));
  assert.match(screenCode, /Promise\.allSettled/);
  assert.match(screenCode, /ข้อผิดพลาดนี้จำกัดอยู่ที่รายงานหมวดนี้/);
  assert.match(screenCode, /latest 100 maximum/);
  assert.match(screenCode, /latest 25 maximum/);
  assert.match(screenCode, /latest 50 maximum/);
});

test('truthfulness states and unavailable performance remain explicit', () => {
  for (const label of ['AVAILABLE', 'PARTIAL', 'STALE', 'UNAVAILABLE', 'NOT IMPLEMENTED']) {
    assert.match(screenCode, new RegExp(label));
  }
  assert.match(screenCode, /Candidate ≠ Executed Trade/);
  assert.match(screenCode, /NOT A BACKTEST/);
  assert.match(screenCode, /Executed Trading Performance/);
  assert.match(screenCode, /value: 'N\/A'/);
  assert.match(screenCode, /ไม่ใช้ 0 หรือ 0%/);
  assert.match(screenCode, /ไม่ใช้ข้อมูลอนาคต/);
  assert.match(screenCode, /Macro Bias เป็นบริบทเชิงพรรณนา ไม่ใช่ Trading Signal/);
});

test('Reports route replaces the former journal placeholder', () => {
  const route = fs.readFileSync(path.resolve(__dirname, '../src/app/(dashboard)/journal/page.tsx'), 'utf8');
  assert.match(route, /ReportsScreen/);
  assert.doesNotMatch(route, /Coming in Phase 8/);
});
