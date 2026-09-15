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
      if (n.endsWith('.json')) {
        const p = path.resolve(__dirname, '../src/features/news/news-contract.generated.json');
        return JSON.parse(fs.readFileSync(p, 'utf8'));
      }
      if (n.endsWith('.css')) return {};
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

const thai = load('features/news/thai.ts');
const { MacroBiasCard } = load('features/news/MacroBiasCard.tsx');
const { ReleaseGroupPanel } = load('features/news/ReleaseGroupPanel.tsx');
const { MarketReactionPanel } = load('features/news/MarketReactionPanel.tsx');
const { StructureConfirmationCard } = load('features/news/StructureConfirmationCard.tsx');
const { MacroReasonPanel } = load('features/news/MacroReasonPanel.tsx');

// Sample Fixtures
const SAMPLE_EVENTS = [
  {
    id: 'evt_001',
    calendar_id: 'cal_01',
    event_code: 'NFP',
    event_name: 'Non-Farm Employment Change',
    event_name_th: 'การจ้างงานนอกภาคเกษตร',
    currency: 'USD',
    impact: 'HIGH',
    category: 'EMPLOYMENT',
    scheduled_at: '2026-09-15T12:30:00Z',
    status: 'RELEASED',
    actual: '250',
    forecast: '180',
    previous: '150',
    revised_previous: '145',
    unit: 'THOUSANDS',
    gold_relevant: true,
    source: 'forexfactory',
    source_mode: 'LIVE',
    revision_version: 2,
    available_at: '2026-09-15T12:30:02Z',
    released_at: '2026-09-15T12:30:01Z',
    field_conflicts: [],
  },
  {
    id: 'evt_002',
    calendar_id: 'cal_01',
    event_code: 'UNEMPLOYMENT',
    event_name: 'Unemployment Rate',
    event_name_th: 'อัตราว่างงาน',
    currency: 'USD',
    impact: 'HIGH',
    category: 'EMPLOYMENT',
    scheduled_at: '2026-09-15T12:30:00Z',
    status: 'RELEASED',
    actual: '4.1',
    forecast: '4.2',
    previous: '4.3',
    revised_previous: null,
    unit: 'PERCENT',
    gold_relevant: true,
    source: 'forexfactory',
    source_mode: 'LIVE',
    revision_version: 1,
    available_at: '2026-09-15T12:30:02Z',
    released_at: '2026-09-15T12:30:01Z',
    field_conflicts: [],
  },
];

const SAMPLE_RELEASE_GROUP = {
  group_id: 'grp_emp_001',
  event_ids: ['evt_001', 'evt_002'],
  alignment: 'ALL_ALIGNED',
  bias: 'USD_STRONG_POSITIVE',
  score: '2.50',
  completeness: 'COMPLETE',
  surprises: [
    {
      event_id: 'evt_001',
      raw: '70',
      relative: '0.3889',
      normalized: null,
      normalized_method: 'UNAVAILABLE_NO_DISTRIBUTION',
      direction: 'ABOVE',
      magnitude: 'LARGE',
      usd_direction: 'POSITIVE',
      revision_delta: '-5',
      reason_code: 'SURPRISE_ALIGNMENT',
    },
    {
      event_id: 'evt_002',
      raw: '-0.1',
      relative: '-0.0238',
      normalized: null,
      normalized_method: 'UNAVAILABLE_NO_DISTRIBUTION',
      direction: 'BELOW',
      magnitude: 'SMALL',
      usd_direction: 'POSITIVE',
      revision_delta: null,
      reason_code: 'SURPRISE_ALIGNMENT',
    },
  ],
};

// 1. Canonical Macro Bias & Strength Test
test('MacroBiasCard renders all canonical Macro Bias states and disclaims trading signal', () => {
  const canonicalBiases = [
    'USD_STRONG_POSITIVE',
    'USD_POSITIVE',
    'USD_NEUTRAL',
    'USD_NEGATIVE',
    'USD_STRONG_NEGATIVE',
    'CONFLICTING',
    'UNKNOWN',
  ];

  for (const bias of canonicalBiases) {
    const html = renderToStaticMarkup(
      React.createElement(MacroBiasCard, {
        macroBias: bias,
        macroStrength: 'STRONG',
        newsRegime: 'NORMAL',
        releaseStatus: 'RELEASED',
        dataQuality: 'COMPLETE',
        multipleEventRisk: false,
      })
    );

    assert.match(html, new RegExp(bias));
    assert.match(html, /MACRO BIAS ≠ TRADING SIGNAL/);
    assert.match(html, /ภาพรวม USD เป็นเพียงบริบท ไม่ใช่คำสั่งซื้อหรือขายทอง/);
  }
});

test('MacroBiasCard supports USD_NEUTRAL and rejects NEUTRAL_USD as canonical', () => {
  // Verify thai.ts translation for USD_NEUTRAL exists
  assert.equal(thai.label('USD_NEUTRAL'), 'ข้อมูลใกล้เคียงคาดการณ์');

  const contract = JSON.parse(
    fs.readFileSync(path.resolve(__dirname, '../src/features/news/news-contract.generated.json'), 'utf8')
  );
  const schemas = contract.schemas || contract.definitions || {};
  const macroBiasEnum = schemas.NewsResponse?.properties?.macro_bias?.enum || [];
  assert.ok(macroBiasEnum.includes('USD_NEUTRAL'), 'USD_NEUTRAL must be in contract enum');
  assert.ok(!macroBiasEnum.includes('NEUTRAL_USD'), 'NEUTRAL_USD must NOT be in contract enum');
});

test('MacroBiasCard renders canonical Macro Strength states', () => {
  const strengths = ['STRONG', 'MODERATE', 'MIXED', 'UNKNOWN'];
  for (const strength of strengths) {
    const html = renderToStaticMarkup(
      React.createElement(MacroBiasCard, {
        macroBias: 'USD_POSITIVE',
        macroStrength: strength,
        newsRegime: 'NORMAL',
        releaseStatus: 'RELEASED',
        dataQuality: 'COMPLETE',
        multipleEventRisk: false,
      })
    );
    assert.match(html, new RegExp(strength));
  }
});

test('MacroBiasCard renders Multiple Event Risk alert banner when active', () => {
  const htmlActive = renderToStaticMarkup(
    React.createElement(MacroBiasCard, {
      macroBias: 'USD_POSITIVE',
      macroStrength: 'STRONG',
      multipleEventRisk: true,
    })
  );
  assert.match(htmlActive, /แจ้งเตือนความเสี่ยงสะสม \(Multiple Event Risk\)/);

  const htmlInactive = renderToStaticMarkup(
    React.createElement(MacroBiasCard, {
      macroBias: 'USD_POSITIVE',
      macroStrength: 'STRONG',
      multipleEventRisk: false,
    })
  );
  assert.doesNotMatch(htmlInactive, /แจ้งเตือนความเสี่ยงสะสม/);
});

// 2. Active Release Group & Surprise Matrix Test
test('ReleaseGroupPanel renders active group, alignment, completeness, and surprise matrix', () => {
  const html = renderToStaticMarkup(
    React.createElement(ReleaseGroupPanel, {
      activeGroup: SAMPLE_RELEASE_GROUP,
      events: SAMPLE_EVENTS,
      activeEventId: 'evt_001',
      xauusdRelevance: {
        evt_001: { affected_currency: 'USD', score: 3, channels: ['USD', 'INTEREST_RATES'] },
        evt_002: { affected_currency: 'USD', score: 2, channels: ['USD'] },
      },
    })
  );

  // Group metadata
  assert.match(html, /ALL_ALIGNED/);
  assert.match(html, /COMPLETE/);
  assert.match(html, /grp_emp_/);

  // Active event display
  assert.match(html, /Non-Farm Employment Change|การจ้างงานนอกภาคเกษตร/);
  assert.match(html, /250 พัน/);
  assert.match(html, /180 พัน/);

  // Surprise Matrix
  assert.match(html, /ABOVE/);
  assert.match(html, /สูงกว่าคาดการณ์/);
  assert.match(html, /BELOW/);
  assert.match(html, /ต่ำกว่าคาดการณ์/);
  assert.match(html, /POSITIVE/);
  assert.match(html, /SURPRISE_ALIGNMENT/);

  // Normalization notice
  assert.match(html, /ยังไม่มี historical distribution สำหรับ normalization/);

  // XAUUSD relevance
  assert.match(html, /ระดับ 3\/3/);
  assert.match(html, /ค่าเงินดอลลาร์/);
});

test('ReleaseGroupPanel renders clean empty state when no active release group exists', () => {
  const html = renderToStaticMarkup(
    React.createElement(ReleaseGroupPanel, {
      activeGroup: null,
      events: [],
      upcomingEvents: [SAMPLE_EVENTS[0]],
    })
  );

  assert.match(html, /ไม่มีชุดข่าวที่กำลังอยู่ในช่วงประเมิน \(No Active Release Group\)/);
  assert.match(html, /ข่าวสำคัญถัดไป/);
  assert.match(html, /Non-Farm Employment Change|การจ้างงานนอกภาคเกษตร/);
});

// 3. Market Reaction Analysis Test
test('MarketReactionPanel renders reaction state, windows, ATR, and classifications', () => {
  const reactionWindows = [
    {
      seconds: 60,
      status: 'READY',
      cutoff: '2026-09-15T12:31:00Z',
      price_before: '2500.00',
      price_after: '2492.50',
      return_percent: '-0.30',
      move_atr: '1.25',
      range_atr: '1.80',
      tick_activity_ratio: '3.40',
      classification: 'STRONG_DIRECTIONAL',
    },
    {
      seconds: 300,
      status: 'READY',
      cutoff: '2026-09-15T12:35:00Z',
      price_before: '2500.00',
      price_after: '2505.00',
      return_percent: '0.20',
      move_atr: '0.80',
      range_atr: '2.50',
      tick_activity_ratio: '2.10',
      classification: 'WHIPSAW',
    },
    {
      seconds: 900,
      status: 'WAITING',
      cutoff: '2026-09-15T12:45:00Z',
    },
  ];

  const html = renderToStaticMarkup(
    React.createElement(MarketReactionPanel, {
      reactionState: 'READY',
      reactionWindows,
      spreadState: 'SPREAD_ELEVATED',
      currentSpread: '2.8',
      baselineSpread: '1.8',
      spreadRatio: '1.56',
      volatilityState: 'ELEVATED',
      sourceMode: 'LIVE',
    })
  );

  // Reaction State
  assert.match(html, /READY/);
  assert.match(html, /พร้อมประเมิน/);

  // Windows
  assert.match(html, /T\+1 นาที/);
  assert.match(html, /-0.3%/);
  assert.match(html, /STRONG_DIRECTIONAL/);
  assert.match(html, /ราคาเคลื่อนทางเดียวชัดเจน/);

  assert.match(html, /T\+5 นาที/);
  assert.match(html, /WHIPSAW/);
  assert.match(html, /ราคาสะบัดสองทาง/);

  assert.match(html, /T\+15 นาที/);
  assert.match(html, /WAITING/);

  // Spread & Volatility
  assert.match(html, /SPREAD_ELEVATED/);
  assert.match(html, /1.56x/);
  assert.match(html, /ELEVATED/);

  // Correlation disclaimer
  assert.match(html, /Correlation vs Causation/);
  assert.match(html, /ไม่ได้พิสูจน์ความสัมพันธ์เชิงสาเหตุว่าข่าวเป็นปัจจัยเดียว/);
});

test('MarketReactionPanel enforces canonical Volatility states (no LOW)', () => {
  const contract = JSON.parse(
    fs.readFileSync(path.resolve(__dirname, '../src/features/news/news-contract.generated.json'), 'utf8')
  );
  const schemas = contract.schemas || contract.definitions || {};
  const volEnum = schemas.NewsResponse?.properties?.volatility_state?.enum || [];
  assert.ok(volEnum.includes('NORMAL'), 'NORMAL must be in volatility_state enum');
  assert.ok(volEnum.includes('ELEVATED'), 'ELEVATED must be in volatility_state enum');
  assert.ok(volEnum.includes('EXTREME'), 'EXTREME must be in volatility_state enum');
  assert.ok(volEnum.includes('UNAVAILABLE'), 'UNAVAILABLE must be in volatility_state enum');
  assert.ok(!volEnum.includes('LOW'), 'LOW must NOT be in volatility_state enum');
});

// 4. Structure Confirmation & Confluence Test
test('StructureConfirmationCard renders structure status, references, provenance, and absence rule', () => {
  const structure = {
    status: 'ALIGNED',
    upstream_input_id: 'inp_struct_01',
    upstream_config_id: 'cfg_struct_01',
    upstream_algorithm_version: 'v1.2.0',
    upstream_as_of: '2026-09-15T12:35:00Z',
    upstream_window_start: '2026-09-15T08:00:00Z',
    references: {
      H1_BOS: 'BULLISH',
      M15_CHOCH: 'CONFIRMED',
      SWEEP_LEVEL: '2490.50',
    },
  };

  const html = renderToStaticMarkup(
    React.createElement(StructureConfirmationCard, { structure })
  );

  assert.match(html, /ALIGNED/);
  assert.match(html, /สอดคล้อง/);
  assert.match(html, /H1_BOS/);
  assert.match(html, /M15_CHOCH/);
  assert.match(html, /SWEEP_LEVEL/);
  assert.match(html, /NOT_INCLUDED_UNKNOWN/);
  assert.match(html, /Absence means Unknown, not Invalidated/);
  assert.match(html, /ECONOMIC RELEASE/);
  assert.match(html, /TRADE POLICY/);
});

// 5. Trade Policy & Reason Codes Test
test('MacroReasonPanel renders canonical Trade Policy states and reason codes in Thai', () => {
  for (const policy of ['INFORMATIONAL', 'CAUTION', 'RESTRICTED']) {
    const html = renderToStaticMarkup(
      React.createElement(MacroReasonPanel, {
        tradePolicyState: policy,
        reasonCodes: ['POLICY_INFORMATIONAL', 'SURPRISE_ALIGNMENT', 'CUSTOM_UNKNOWN_CODE'],
      })
    );

    assert.match(html, new RegExp(policy));
    assert.match(html, /POLICY ≠ RISK ENGINE KILL SWITCH/);
    assert.match(html, /ทิศทางตัวเลขสอดคล้องกัน/);
    assert.match(html, /CUSTOM_UNKNOWN_CODE/); // Safely displays raw unknown code
  }
});

// 6. Non-Fabrication & Safety Invariants Test
test('News & Sentiment screen enforces non-fabrication and paper trading invariants', () => {
  const screenCode = fs.readFileSync(path.resolve(__dirname, '../src/features/news/NewsSentimentScreen.tsx'), 'utf8');
  const panelCode = fs.readFileSync(path.resolve(__dirname, '../src/features/news/TradingNewsPanel.tsx'), 'utf8');

  // Invariant: Paper trading badge
  assert.match(screenCode, /PAPER MODE · ADVISORY \/ CONTEXT ONLY · EXECUTION DISABLED/);
  assert.match(panelCode, /PAPER MODE · EXECUTION DISABLED/);

  // Invariant: No fake RSS / articles / social sentiment
  assert.doesNotMatch(panelCode, /reuters|bloomberg|twitter|reddit|social_sentiment/i);

  // Invariant: No fake bullish % or sentiment scores
  assert.doesNotMatch(panelCode, /bullishPercentage|fearAndGreed|sentimentScore/i);

  // Invariant: Zero order execution buttons
  assert.doesNotMatch(panelCode, /place-order|buy-button|sell-button/i);

  // Invariant: Links to /calendar and /trading
  assert.match(screenCode, /href="\/calendar"/);
  assert.match(screenCode, /href="\/trading"/);
});
