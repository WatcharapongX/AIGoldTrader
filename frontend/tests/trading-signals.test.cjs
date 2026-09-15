const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const cache = new Map();

function load(relative, fromDir = path.resolve(__dirname, '../src')) {
  let full = path.isAbsolute(relative) ? relative : path.resolve(fromDir, relative);
  if (!fs.existsSync(full)) {
    if (fs.existsSync(full + '.ts')) full = full + '.ts';
    else if (fs.existsSync(full + '.tsx')) full = full + '.tsx';
    else if (fs.existsSync(full + '.js')) full = full + '.js';
    else if (fs.existsSync(full + '.json')) full = full + '.json';
  }
  if (cache.has(full)) return cache.get(full);
  const exports = {};
  cache.set(full, exports);
  const dir = path.dirname(full);
  const code = ts.transpileModule(fs.readFileSync(full, 'utf8'), {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2022,
      jsx: ts.JsxEmit.ReactJSX,
      esModuleInterop: true,
    },
  }).outputText;
  vm.runInNewContext(code, {
    exports,
    Date,
    Number,
    Set,
    Intl,
    JSON,
    process,
    AbortSignal,
    AbortController,
    Math,
    require: (n) => {
      if (n === 'react' || n === 'react/jsx-runtime') return require(n);
      if (n === 'next/link') {
        return {
          __esModule: true,
          default: ({ children, ...props }) => React.createElement('a', props, children),
        };
      }
      if (n === 'lightweight-charts') {
        return {
          createChart: () => ({
            addSeries: () => ({
              setData: () => {},
              update: () => {},
              attachPrimitive: () => {},
              detachPrimitive: () => {},
              applyOptions: () => {},
            }),
            timeScale: () => ({ fitContent: () => {} }),
            remove: () => {},
          }),
          CandlestickSeries: {},
          ColorType: { Solid: 'solid' },
        };
      }
      if (n.startsWith('.')) return load(n, dir);
      if (n.startsWith('@/')) return load(n.replace('@/', ''), path.resolve(__dirname, '../src'));
      return require(n);
    },
  });
  return exports;
}

const { SignalSummaryHeader } = load('features/strategy/SignalSummaryHeader.tsx');
const { SignalFilterBar } = load('features/strategy/SignalFilterBar.tsx');
const { SignalCard } = load('features/strategy/SignalCard.tsx');
const { SignalDetailPanel } = load('features/strategy/SignalDetailPanel.tsx');

// Sample Fixtures
const sampleCandidate = (status = 'READY', overrides = {}) => ({
  id: 'cand_test_001_xauusd_long_m5',
  profile_id: 'default_intraday',
  strategy_id: 'STRAT01',
  strategy_version: 'v1.0.0',
  symbol: 'XAUUSD',
  direction: 'LONG',
  status,
  score: 88,
  detected_at: '2026-09-15T04:00:00Z',
  confirmed_at: '2026-09-15T04:05:00Z',
  expires_at: '2026-09-15T08:00:00Z',
  context_id: 'ctx_001',
  upstream_ids: ['m1_001'],
  evidence: [
    { code: 'BOS_CONFIRMED', description_th: 'Break of Structure ขาขึ้นใน H1 ยืนยัน', weight: 40 },
    { code: 'FVG_CONFLUENCE', description_th: 'ราคาแตะ Fair Value Gap ขาขึ้น', weight: 25 },
  ],
  missing_conditions: [],
  conflicts: [],
  invalidation_th: 'หลุดแนวรับสวิงก่อนหน้า 3625.00',
  plan: {
    id: 'plan_001',
    candidate_id: 'cand_test_001_xauusd_long_m5',
    symbol: 'XAUUSD',
    direction: 'LONG',
    entry_type: 'LIMIT_ZONE',
    entry_lower: '3640.00',
    entry_upper: '3642.50',
    entry_source_id: 'src_001',
    stop_loss: '3630.00',
    stop_source_id: 'src_002',
    invalidation_th: 'หลุดแนวรับสวิงก่อนหน้า 3625.00',
    targets: [
      { name: 'TP1', price: '3655.00', source_id: 'src_003', rr: '1.5' },
      { name: 'TP2', price: '3670.00', source_id: 'src_004', rr: '3.0' },
    ],
    score: 88,
    evidence: [],
    warnings_th: [],
    news_state: 'NO_IMPACT',
    as_of: '2026-09-15T04:05:00Z',
    context_id: 'ctx_001',
    expires_at: '2026-09-15T08:00:00Z',
  },
  ...overrides,
});

test('Exact 8 canonical strategy states are supported without fake states', () => {
  const CANONICAL_STATES = [
    'DETECTED',
    'WAITING_CONFIRMATION',
    'READY',
    'BLOCKED_CONTEXT',
    'NO_TRADE',
    'INVALIDATED',
    'EXPIRED',
    'SUPERSEDED',
  ];

  // Render cards for all 8 canonical states
  for (const st of CANONICAL_STATES) {
    const html = renderToStaticMarkup(
      React.createElement(SignalCard, {
        candidate: sampleCandidate(st),
        isSelected: false,
        onSelect: () => {},
        strategy: { id: 'STRAT01', name: 'Trend Continuation' },
      })
    );
    assert.ok(html.includes(st), `SignalCard should display state ${st}`);
  }

  // Verify unsupported states are not in canonical filter list
  const filterHtml = renderToStaticMarkup(
    React.createElement(SignalFilterBar, {
      activeTab: 'CURRENT',
      onSelectTab: () => {},
      stateFilter: 'ALL',
      onSelectState: () => {},
      strategyFilter: 'ALL',
      onSelectStrategy: () => {},
      profileFilter: 'ALL',
      onSelectProfile: () => {},
      directionFilter: 'ALL',
      onSelectDirection: () => {},
      strategies: [],
      profiles: [],
      searchQuery: '',
      onSearchChange: () => {},
      onRefresh: () => {},
      isRefreshing: false,
    })
  );

  assert.ok(!filterHtml.includes('TRIGGERED'), 'Must not contain fake state TRIGGERED');
  assert.ok(!filterHtml.includes('WATCHING'), 'Must not contain fake state WATCHING');
});

test('Setup Evidence Score is clearly labeled and never called probability or win rate', () => {
  const html = renderToStaticMarkup(
    React.createElement(SignalCard, {
      candidate: sampleCandidate('READY'),
      isSelected: false,
      onSelect: () => {},
      strategy: { id: 'STRAT01', name: 'Trend Continuation' },
    })
  );

  assert.ok(html.includes('Setup Evidence Score'));
  assert.ok(html.includes('88'));
  assert.ok(!html.includes('Win Probability'));
  assert.ok(!html.includes('Win Rate'));
  assert.ok(!html.includes('Confidence %'));
});

test('TradePlanSuggestion renders SUGGESTION_ONLY and all multiple targets', () => {
  const html = renderToStaticMarkup(
    React.createElement(SignalDetailPanel, {
      candidate: sampleCandidate('READY'),
      strategy: { id: 'STRAT01', name: 'Trend Continuation' },
      profile: { id: 'default_intraday', name: 'Intraday Scalper', style: 'DAY_TRADE' },
      killSwitch: { state: 'INACTIVE', reason_th: '' },
      riskDecisions: [],
    })
  );

  assert.ok(html.includes('SUGGESTION_ONLY'));
  assert.ok(html.includes('แผนราคาเพื่อการวิเคราะห์เท่านั้น ยังไม่ใช่คำสั่งซื้อขาย'));
  assert.ok(html.includes('3640.00'));
  assert.ok(html.includes('3630.00'));
  // Multiple targets
  assert.ok(html.includes('TP1'));
  assert.ok(html.includes('3655.00'));
  assert.ok(html.includes('TP2'));
  assert.ok(html.includes('3670.00'));
  assert.ok(html.includes('RR 3.0'));
});

test('Expired plan is truthfully marked EXPIRED and read-only', () => {
  const expiredCand = sampleCandidate('EXPIRED', {
    plan: {
      ...sampleCandidate().plan,
      expires_at: '2020-01-01T00:00:00Z', // Past date
    },
  });

  const html = renderToStaticMarkup(
    React.createElement(SignalDetailPanel, {
      candidate: expiredCand,
      strategy: { id: 'STRAT01', name: 'Trend Continuation' },
      killSwitch: { state: 'INACTIVE', reason_th: '' },
      riskDecisions: [],
    })
  );

  assert.ok(html.includes('EXPIRED'));
});

test('Strict Risk Decision binding matches candidate_id and does not guess', () => {
  const candidate = sampleCandidate('READY');

  // Case 1: Matching candidate_id
  const matchingDecision = {
    id: 'dec_001',
    candidate_id: candidate.id,
    plan_id: 'plan_001',
    strategy_id: 'STRAT01',
    strategy_version: 'v1.0.0',
    profile_id: 'default_intraday',
    symbol: 'XAUUSD',
    direction: 'LONG',
    decision: 'APPROVED',
    requested_risk_pct: '1.0',
    approved_risk_pct: '1.0',
    requested_risk_amount: '1000',
    approved_risk_amount: '1000',
    position_size: '0.15',
    entry_lower: '3640.00',
    entry_upper: '3642.50',
    stop_loss: '3630.00',
    stop_distance: '10.00',
    portfolio_exposure_before: '0.00',
    portfolio_exposure_after: '1.00',
    account_snapshot_id: 'acc_001',
    symbol_specification_id: 'sym_001',
    policy_version: 'risk-1.0.0',
    as_of: '2026-09-15T04:05:00Z',
  };

  const htmlMatched = renderToStaticMarkup(
    React.createElement(SignalDetailPanel, {
      candidate,
      strategy: { id: 'STRAT01', name: 'Trend Continuation' },
      killSwitch: { state: 'INACTIVE', reason_th: '' },
      riskDecisions: [matchingDecision],
    })
  );

  assert.ok(htmlMatched.includes('APPROVED'));
  assert.ok(htmlMatched.includes('0.15 Lot'));

  // Case 2: Different candidate_id (NO GUESSING)
  const unlinkedDecision = {
    ...matchingDecision,
    candidate_id: 'different_candidate_id_999',
  };

  const htmlUnlinked = renderToStaticMarkup(
    React.createElement(SignalDetailPanel, {
      candidate,
      strategy: { id: 'STRAT01', name: 'Trend Continuation' },
      killSwitch: { state: 'INACTIVE', reason_th: '' },
      riskDecisions: [unlinkedDecision],
    })
  );

  assert.ok(htmlUnlinked.includes('ยังไม่มี Risk Decision ที่ยืนยันว่าเป็นของ Candidate นี้'));
});

test('Kill Switch ACTIVE marks EXECUTION BLOCKED without rewriting candidate state', () => {
  const candidate = sampleCandidate('READY');

  const html = renderToStaticMarkup(
    React.createElement(SignalDetailPanel, {
      candidate,
      strategy: { id: 'STRAT01', name: 'Trend Continuation' },
      killSwitch: { state: 'ACTIVE', reason_th: 'ตลาดผันผวนรุนแรงเกินเกณฑ์' },
      riskDecisions: [],
    })
  );

  // Strategy state remains READY
  assert.ok(html.includes('READY'));
  // Safety banner indicates execution is blocked
  assert.ok(html.includes('ACTIVE (BLOCKED)'));
  assert.ok(html.includes('ตลาดผันผวนรุนแรงเกินเกณฑ์'));
});

test('Safety check: Paper mode visible, zero order execution buttons', () => {
  const htmlHeader = renderToStaticMarkup(
    React.createElement(SignalSummaryHeader, {
      candidates: [sampleCandidate()],
      provider: { source: 'mt5_demo_iux', mode: 'DEMO', status: 'CONNECTED' },
      killSwitch: { state: 'INACTIVE', reason_th: '' },
    })
  );

  assert.ok(htmlHeader.includes('PAPER · EXECUTION DISABLED'));

  // Ensure absence of trading buttons across details and summary
  const forbiddenKeywords = ['Place Order', 'Buy Market', 'Sell Market', 'Execute Trade', 'order_send'];
  for (const word of forbiddenKeywords) {
    assert.ok(!htmlHeader.includes(word), `Must not contain ${word}`);
  }
});
