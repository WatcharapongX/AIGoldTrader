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
      if (n.startsWith('@/')) {
        return load(n.replace('@/', ''), path.resolve(__dirname, '../src'));
      }
      if (n.startsWith('./') || n.startsWith('../')) {
        return load(n, dir);
      }
      return require(n);
    },
  });
  return exports;
}

const { StrategyCatalogTab } = load('features/strategy/StrategyCatalogTab.tsx');
const { TraderProfilesTab } = load('features/strategy/TraderProfilesTab.tsx');
const { EvaluationsTab } = load('features/strategy/EvaluationsTab.tsx');
const { BacktestReadinessTab } = load('features/strategy/BacktestReadinessTab.tsx');

// Sample domain fixtures
const SAMPLE_STRATEGIES = [
  {
    id: 'STRAT01',
    name: 'SMC Liquidity Reversal',
    version: 'v1.2.1',
    category: 'SMC_LIQUIDITY',
    styles: ['SCALP', 'DAY_TRADE', 'SWING', 'RUN_TREND'],
    required_context: ['HTF', 'SWEEP', 'MSS_CHOCH', 'FVG_OB', 'RETEST'],
    description_th: 'กวาดสภาพคล่อง กลับเข้าระดับเดิม เปลี่ยนโครงสร้าง และย่อทดสอบโซน',
  },
  {
    id: 'STRAT02',
    name: 'Trend Pullback',
    version: 'v1.2.1',
    category: 'TREND_PULLBACK',
    styles: ['SCALP', 'DAY_TRADE', 'SWING', 'RUN_TREND'],
    required_context: ['HTF_TREND', 'BOS', 'PULLBACK_ZONE', 'LTF_CONFIRMATION'],
    description_th: 'ตามแนวโน้มใหญ่ รอย่อเข้าโซนและยืนยันโครงสร้างกรอบเล็ก',
  },
  {
    id: 'STRAT03',
    name: 'Breakout Retest',
    version: 'v1.2.1',
    category: 'BREAKOUT_PATTERN',
    styles: ['SCALP', 'DAY_TRADE', 'SWING', 'RUN_TREND'],
    required_context: ['CONFIRMED_PATTERN', 'CLOSE_BREAK', 'DISPLACEMENT', 'RETEST', 'STRUCTURE'],
    description_th: 'ราคาปิดทะลุกรอบหรือรูปแบบ ตามด้วยการกลับทดสอบและยืนยันโครงสร้าง',
  },
  {
    id: 'STRAT04',
    name: 'Range Mean Reversion',
    version: 'v1.2.1',
    category: 'MEAN_REVERSION',
    styles: ['SCALP', 'DAY_TRADE', 'SWING', 'RUN_TREND'],
    required_context: ['RANGING', 'BOUNDARIES', 'REJECTION', 'STRUCTURE'],
    description_th: 'กลับเข้ากรอบจากขอบราคา ใช้ได้เมื่อไม่มีแนวโน้มแรง',
  },
  {
    id: 'STRAT05',
    name: 'Post-News Momentum',
    version: 'v1.2.1',
    category: 'NEWS_MOMENTUM',
    styles: ['SCALP', 'DAY_TRADE', 'SWING', 'RUN_TREND'],
    required_context: ['NEWS', 'RELEASED_ACTUAL', 'MACRO_ALIGNMENT', 'REACTION', 'SPREAD', 'STRUCTURE'],
    description_th: 'ติดตามแรงหลังประกาศจริง เมื่อข่าว ราคา และโครงสร้างสอดคล้องกัน',
  },
  {
    id: 'STRAT06',
    name: 'Post-News Liquidity Reversal',
    version: 'v1.2.1',
    category: 'NEWS_REVERSAL',
    styles: ['SCALP', 'DAY_TRADE', 'SWING', 'RUN_TREND'],
    required_context: ['NEWS', 'HIGH_IMPACT_RELEASE', 'SWEEP_RECLAIM', 'MSS_CHOCH', 'SPREAD'],
    description_th: 'หลังข่าวแรง รอกวาดราคาและกลับเข้าระดับเดิมพร้อมยืนยันการกลับตัว',
  },
];

const SAMPLE_PROFILES = [
  {
    id: 'research',
    name: 'Strategy Lab',
    description_th: 'โปรไฟล์วิเคราะห์แยกผล ไม่ส่งคำสั่งซื้อขาย',
    style: 'DAY_TRADE',
    allowed_strategies: ['STRAT01', 'STRAT02', 'STRAT03', 'STRAT04', 'STRAT05', 'STRAT06'],
    timeframe_map: {
      style: 'DAY_TRADE',
      context: 'H4',
      bias: 'H1',
      setup: 'M15',
      trigger: 'M5',
      minimum_bars: 60,
    },
    config_id: 'cfg_001',
  },
  {
    id: 'smc',
    name: 'SMC Specialist',
    description_th: 'โปรไฟล์วิเคราะห์แยกผล ไม่ส่งคำสั่งซื้อขาย',
    style: 'SCALP',
    allowed_strategies: ['STRAT01'],
    timeframe_map: {
      style: 'SCALP',
      context: 'H1',
      bias: 'M15',
      setup: 'M5',
      trigger: 'M1',
      minimum_bars: 60,
    },
    config_id: 'cfg_001',
  },
  {
    id: 'trend',
    name: 'Trend Runner',
    description_th: 'โปรไฟล์วิเคราะห์แยกผล ไม่ส่งคำสั่งซื้อขาย',
    style: 'RUN_TREND',
    allowed_strategies: ['STRAT02'],
    timeframe_map: {
      style: 'RUN_TREND',
      context: 'D1',
      bias: 'H4',
      setup: 'H1',
      trigger: 'M15',
      minimum_bars: 60,
    },
    config_id: 'cfg_001',
  },
  {
    id: 'liquidity',
    name: 'Liquidity Specialist',
    description_th: 'โปรไฟล์วิเคราะห์แยกผล ไม่ส่งคำสั่งซื้อขาย',
    style: 'SWING',
    allowed_strategies: ['STRAT01'],
    timeframe_map: {
      style: 'SWING',
      context: 'W1',
      bias: 'D1',
      setup: 'H4',
      trigger: 'H1',
      minimum_bars: 60,
    },
    config_id: 'cfg_001',
  },
  {
    id: 'breakout',
    name: 'Breakout Trader',
    description_th: 'โปรไฟล์วิเคราะห์แยกผล ไม่ส่งคำสั่งซื้อขาย',
    style: 'DAY_TRADE',
    allowed_strategies: ['STRAT03'],
    timeframe_map: {
      style: 'DAY_TRADE',
      context: 'H4',
      bias: 'H1',
      setup: 'M15',
      trigger: 'M5',
      minimum_bars: 60,
    },
    config_id: 'cfg_001',
  },
  {
    id: 'range',
    name: 'Range Trader',
    description_th: 'โปรไฟล์วิเคราะห์แยกผล ไม่ส่งคำสั่งซื้อขาย',
    style: 'SCALP',
    allowed_strategies: ['STRAT04'],
    timeframe_map: {
      style: 'SCALP',
      context: 'H1',
      bias: 'M15',
      setup: 'M5',
      trigger: 'M1',
      minimum_bars: 60,
    },
    config_id: 'cfg_001',
  },
  {
    id: 'news',
    name: 'News Trader',
    description_th: 'โปรไฟล์วิเคราะห์แยกผล ไม่ส่งคำสั่งซื้อขาย',
    style: 'DAY_TRADE',
    allowed_strategies: ['STRAT05', 'STRAT06'],
    timeframe_map: {
      style: 'DAY_TRADE',
      context: 'H4',
      bias: 'H1',
      setup: 'M15',
      trigger: 'M5',
      minimum_bars: 60,
    },
    config_id: 'cfg_001',
  },
];

const SAMPLE_CURRENT_EVAL = {
  evaluation: {
    id: 'eval_001',
    context: {
      id: 'ctx_001',
      symbol: 'XAUUSD',
      source: 'mt5_demo_iux',
      mode: 'ACTUAL',
      as_of: '2026-09-15T04:00:00Z',
      config_id: 'cfg_001_test',
      strategy_config_json: JSON.stringify({
        minimum_rr: '1.50',
        tolerance_atr: '0.15',
        stop_atr_buffer: '0.20',
        expiry_trigger_bars: 12,
        event_lookback_bars: 24,
        pattern_lookback_bars: 100,
        macd_fast: 12,
        macd_slow: 26,
        macd_signal: 9,
        stochastic_period: 14,
        stochastic_smooth: 3,
      }),
      engine_version: 'v1.2.1',
      current_session: 'LONDON',
      frames: [
        { timeframe: 'M1', bars: 1000, requested: 1000 },
        { timeframe: 'M5', bars: 1000, requested: 1000 },
        { timeframe: 'H1', bars: 300, requested: 300 },
        { timeframe: 'H4', bars: 300, requested: 300 },
        { timeframe: 'D1', bars: 300, requested: 300 },
        { timeframe: 'W1', bars: 231, requested: 300 },
      ],
    },
    candidates: [
      {
        id: 'cand_001',
        strategy_id: 'STRAT01',
        profile_id: 'smc',
        symbol: 'XAUUSD',
        direction: 'LONG',
        status: 'READY',
        score: 85,
        detected_at: '2026-09-15T03:55:00Z',
        expires_at: '2026-09-15T08:00:00Z',
        plan: { id: 'plan_001' },
      },
      {
        id: 'cand_002',
        strategy_id: 'STRAT02',
        profile_id: 'trend',
        symbol: 'XAUUSD',
        direction: 'SHORT',
        status: 'WAITING_CONFIRMATION',
        score: 70,
        detected_at: '2026-09-15T03:50:00Z',
        expires_at: '2026-09-15T08:00:00Z',
        plan: null,
      },
    ],
  },
  generated_at: '2026-09-15T04:00:01Z',
  served_at: '2026-09-15T04:00:02Z',
  stale: false,
};

test('Strategy Catalog renders STRAT01–STRAT06 with versions, categories, and styles', () => {
  const html = renderToStaticMarkup(
    React.createElement(StrategyCatalogTab, {
      strategies: SAMPLE_STRATEGIES,
      loading: false,
      error: null,
      strategyConfigJson: SAMPLE_CURRENT_EVAL.evaluation.context.strategy_config_json,
    })
  );

  for (let i = 1; i <= 6; i++) {
    const id = `STRAT0${i}`;
    assert.ok(html.includes(id), `Must render strategy ${id}`);
  }

  assert.ok(html.includes('SMC Liquidity Reversal'));
  assert.ok(html.includes('Trend Pullback'));
  assert.ok(html.includes('Breakout Retest'));
  assert.ok(html.includes('Range Mean Reversion'));
  assert.ok(html.includes('Post-News Momentum'));
  assert.ok(html.includes('Post-News Liquidity Reversal'));
  assert.ok(html.includes('v1.2.1'));
});

test('News dependency is truthfully distinguished: STRAT01–04 Market-Driven vs STRAT05–06 News-Aware', () => {
  const html = renderToStaticMarkup(
    React.createElement(StrategyCatalogTab, {
      strategies: SAMPLE_STRATEGIES,
      loading: false,
      error: null,
    })
  );

  assert.ok(html.includes('STRAT01–STRAT04: Market-Driven Playbooks'));
  assert.ok(html.includes('STRAT05–STRAT06: News-Aware Playbooks'));
  assert.ok(html.includes('Independent of Macro News'));
  assert.ok(html.includes('NEWS-AWARE'));
  assert.ok(html.includes('MARKET-DRIVEN'));
});

test('Trader Profiles tab renders 7 canonical profiles with multi-timeframe mappings', () => {
  const html = renderToStaticMarkup(
    React.createElement(TraderProfilesTab, {
      profiles: SAMPLE_PROFILES,
      loading: false,
      error: null,
      strategies: SAMPLE_STRATEGIES,
    })
  );

  assert.ok(html.includes('7 Trader Profiles'));
  assert.ok(html.includes('Strategy Lab'));
  assert.ok(html.includes('SMC Specialist'));
  assert.ok(html.includes('Trend Runner'));
  assert.ok(html.includes('Liquidity Specialist'));
  assert.ok(html.includes('Breakout Trader'));
  assert.ok(html.includes('Range Trader'));
  assert.ok(html.includes('News Trader'));

  // Timeframe mappings
  assert.ok(html.includes('CONTEXT'));
  assert.ok(html.includes('BIAS'));
  assert.ok(html.includes('SETUP'));
  assert.ok(html.includes('TRIGGER'));
  assert.ok(html.includes('60 bars'));
});

test('Current Evaluation renders all 8 canonical states and truthful score without calling it probability', () => {
  const html = renderToStaticMarkup(
    React.createElement(EvaluationsTab, {
      currentEvaluation: SAMPLE_CURRENT_EVAL,
      historicalEvaluations: [],
      candidates: SAMPLE_CURRENT_EVAL.evaluation.candidates,
      strategies: SAMPLE_STRATEGIES,
      profiles: SAMPLE_PROFILES,
      loadingCurrent: false,
      loadingHistory: false,
      loadingCandidates: false,
      error: null,
    })
  );

  // Canonical 8 states
  const CANONICAL_STATES = [
    'READY',
    'WAITING_CONFIRMATION',
    'DETECTED',
    'BLOCKED_CONTEXT',
    'NO_TRADE',
    'INVALIDATED',
    'EXPIRED',
    'SUPERSEDED',
  ];
  for (const st of CANONICAL_STATES) {
    assert.ok(html.includes(st), `Must display canonical state ${st}`);
  }

  // Evidence score
  assert.ok(html.includes('85'));
  assert.ok(html.includes('/ 100'));
  assert.ok(!html.includes('Win Rate: 85%'));
  assert.ok(!html.includes('Confidence 85%'));
  assert.ok(!html.includes('Probability 85%'));
});

test('Historical Evaluations are prominently labeled Snapshots and explicitly NOT a Backtest', () => {
  const html = renderToStaticMarkup(
    React.createElement(EvaluationsTab, {
      currentEvaluation: null,
      historicalEvaluations: [SAMPLE_CURRENT_EVAL],
      candidates: [],
      strategies: SAMPLE_STRATEGIES,
      profiles: SAMPLE_PROFILES,
      loadingCurrent: false,
      loadingHistory: false,
      loadingCandidates: false,
      error: null,
    })
  );

  assert.ok(html.includes('Historical Evaluation Snapshots'));
  assert.ok(html.includes('ไม่ใช่ผลการจำลองการเทรดย้อนหลัง (Backtest)'));
  assert.ok(html.includes('ไม่มีการคำนวณกำไร/ขาดทุน (P&amp;L)'));
  assert.ok(!html.includes('Backtest Results Table'));
});

test('Candidate Descriptive Statistics show frequency counts without inferring profitability', () => {
  const html = renderToStaticMarkup(
    React.createElement(EvaluationsTab, {
      currentEvaluation: null,
      historicalEvaluations: [],
      candidates: SAMPLE_CURRENT_EVAL.evaluation.candidates,
      strategies: SAMPLE_STRATEGIES,
      profiles: SAMPLE_PROFILES,
      loadingCurrent: false,
      loadingHistory: false,
      loadingCandidates: false,
      error: null,
    })
  );

  assert.ok(html.includes('Candidate Descriptive Statistics'));
  assert.ok(html.includes('ตามกลยุทธ์ (By Strategy)'));
  assert.ok(html.includes('ตามโปรไฟล์ (By Profile)'));
  assert.ok(html.includes('ตามฝั่ง (By Direction)'));
  assert.ok(html.includes('LONG (ซื้อ)'));
  assert.ok(html.includes('SHORT (ขาย)'));
  assert.ok(html.includes('ไม่ใช่อัตราความแม่นยำ (Win Rate)'));
});

test('Backtest tab truthfully displays NOT IMPLEMENTED, disabled action, and W1 partial history', () => {
  const html = renderToStaticMarkup(
    React.createElement(BacktestReadinessTab, {
      context: SAMPLE_CURRENT_EVAL.evaluation.context,
    })
  );

  // Status
  assert.ok(html.includes('PENDING PHASE 9 (ยังไม่เปิดใช้งาน)'));
  assert.ok(html.includes('NOT IMPLEMENTED · PHASE 9 PENDING'));

  // Disabled button
  assert.ok(html.includes('Backtest Engine ยังไม่เปิดใช้งาน (Pending Phase 9)'));
  assert.ok(html.includes('disabled=""') || html.includes('disabled'));

  // Truthfulness Badges
  assert.ok(html.includes('NO FAKE TRADES'));
  assert.ok(html.includes('NO FAKE WIN RATE'));
  assert.ok(html.includes('NO FAKE P&amp;L'));
  assert.ok(html.includes('NO FAKE PROFIT FACTOR'));
  assert.ok(html.includes('NO FAKE SHARPE'));
  assert.ok(html.includes('NO FAKE EQUITY CURVE'));

  // W1 Partial
  assert.ok(html.includes('W1'));
  assert.ok(html.includes('231'));
  assert.ok(html.includes('PARTIAL HISTORY'));

  // Negative assertion on fake performance metrics
  const forbiddenMetrics = ['Win Rate: 68%', 'Profit Factor: 2.1', 'Sharpe Ratio: 1.85', 'Max Drawdown: -4.2%'];
  for (const m of forbiddenMetrics) {
    assert.ok(!html.includes(m), `Forbidden fabricated metric: ${m}`);
  }
});
