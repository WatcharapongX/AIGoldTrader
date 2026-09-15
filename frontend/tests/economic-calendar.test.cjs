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
const contracts = load('features/news/contracts.ts');
const { NextEconomicEventCard, formatCountdown } = load('features/news/NextEconomicEventCard.tsx');
const { NewsRiskSummary } = load('features/news/NewsRiskSummary.tsx');
const { StrategyNewsEligibility } = load('features/news/StrategyNewsEligibility.tsx');
const { EventDetailDrawer } = load('features/news/EventDetailDrawer.tsx');

// Sample Fixtures
const SAMPLE_EVENTS = [
  {
    id: 'evt_usd_nfp',
    calendar_id: 'cal_01',
    event_code: 'NFP',
    event_name: 'Non-Farm Employment Change',
    event_name_th: 'การจ้างงานนอกภาคเกษตร',
    currency: 'USD',
    impact: 'HIGH',
    category: 'EMPLOYMENT',
    scheduled_at: '2026-09-15T12:30:00Z',
    status: 'SCHEDULED',
    forecast: '180',
    previous: '150',
    revised_previous: '145',
    actual: null,
    unit: 'THOUSANDS',
    gold_relevant: true,
    source: 'forexfactory',
    source_mode: 'LIVE',
    revision_version: 1,
    available_at: '2026-09-15T12:30:01Z',
    released_at: null,
    field_conflicts: [],
  },
  {
    id: 'evt_usd_cpi_cancelled',
    calendar_id: 'cal_02',
    event_code: 'CPI',
    event_name: 'Consumer Price Index m/m',
    event_name_th: 'ดัชนีราคาผู้บริโภค',
    currency: 'USD',
    impact: 'HIGH',
    category: 'INFLATION',
    scheduled_at: '2026-09-15T10:00:00Z',
    status: 'CANCELLED',
    forecast: '0.2',
    previous: '0.1',
    revised_previous: null,
    actual: null,
    unit: 'PERCENT',
    gold_relevant: true,
    source: 'forexfactory',
    source_mode: 'LIVE',
    revision_version: 1,
    available_at: '2026-09-15T10:00:01Z',
    released_at: null,
    field_conflicts: [],
  },
  {
    id: 'evt_eur_ecb',
    calendar_id: 'cal_03',
    event_code: 'ECB_RATE',
    event_name: 'ECB Main Refinancing Rate',
    event_name_th: 'อัตราดอกเบี้ย ECB',
    currency: 'EUR',
    impact: 'HIGH',
    category: 'CENTRAL_BANK',
    scheduled_at: '2026-09-15T11:45:00Z',
    status: 'SCHEDULED',
    forecast: '3.75',
    previous: '4.00',
    revised_previous: null,
    actual: null,
    unit: 'PERCENT',
    gold_relevant: true,
    source: 'forexfactory',
    source_mode: 'LIVE',
    revision_version: 1,
    available_at: '2026-09-15T11:45:01Z',
    released_at: null,
    field_conflicts: [],
  },
  {
    id: 'evt_usd_med',
    calendar_id: 'cal_04',
    event_code: 'RETAIL_SALES',
    event_name: 'Retail Sales m/m',
    event_name_th: 'ยอดค้าปลีก',
    currency: 'USD',
    impact: 'MEDIUM',
    category: 'CONSUMER',
    scheduled_at: '2026-09-15T11:30:00Z',
    status: 'SCHEDULED',
    forecast: '0.3',
    previous: '0.1',
    revised_previous: null,
    actual: null,
    unit: 'PERCENT',
    gold_relevant: true,
    source: 'forexfactory',
    source_mode: 'LIVE',
    revision_version: 1,
    available_at: '2026-09-15T11:30:01Z',
    released_at: null,
    field_conflicts: [],
  },
  {
    id: 'evt_usd_past_zero',
    calendar_id: 'cal_05',
    event_code: 'FED_FUNDS',
    event_name: 'Federal Funds Rate',
    event_name_th: 'อัตราดอกเบี้ยนโยบายเฟด',
    currency: 'USD',
    impact: 'HIGH',
    category: 'CENTRAL_BANK',
    scheduled_at: '2026-09-15T02:00:00Z',
    status: 'RELEASED',
    forecast: '0',
    previous: '0',
    revised_previous: '0',
    actual: '0',
    unit: 'PERCENT',
    gold_relevant: true,
    source: 'forexfactory',
    source_mode: 'LIVE',
    revision_version: 2,
    available_at: '2026-09-15T02:00:05Z',
    released_at: '2026-09-15T02:00:01Z',
    field_conflicts: ['forecast'],
  },
];

const SAMPLE_NEWS_CONTEXT = {
  macro_bias: 'NEUTRAL_USD',
  macro_strength: 'MODERATE',
  trade_policy_state: 'INFORMATIONAL',
  news_regime: 'NORMAL',
  spread_state: 'NORMAL',
  volatility_state: 'LOW',
  data_quality: 'COMPLETE',
  multiple_event_risk: false,
  as_of: '2026-09-15T08:00:00Z',
  served_at: '2026-09-15T08:00:01Z',
  cache_age_seconds: 1,
  events: SAMPLE_EVENTS,
  source: 'forexfactory',
  source_mode: 'LIVE',
  strategy_eligibility: {
    STRAT05: 'ALLOWED',
    STRAT06: 'WAITING',
  },
  market_as_of: '2026-09-15T08:00:00Z',
  structure_confirmation: {
    htf_bias: 'BULLISH',
    upstream_as_of: '2026-09-15T08:00:00Z',
  },
};

// 1. Quick Date Boundaries & Backend 7-Day Limit Test
test('Quick Date boundaries enforce backend <= 7 days constraint', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../src/features/news/CalendarWorkspace.tsx'), 'utf8');
  assert.match(code, /tab === 'THIS_WEEK'/);
  assert.match(code, /7 \* 86400000/);
  assert.match(code, /getBangkokDateString/);
  assert.match(code, /Asia\/Bangkok/);
});

// 2. Countdown Formatting Logic Test
test('formatCountdown renders days, hours, minutes, and release time', () => {
  const refMs = Date.parse('2026-09-15T12:00:00Z');

  // 2 days and 30 mins ahead
  const twoDaysAhead = '2026-09-17T12:30:00Z';
  assert.match(formatCountdown(twoDaysAhead, refMs), /2 วัน 0 ชม\. 30 นาที/);

  // 2 hours and 15 mins ahead
  const twoHoursAhead = '2026-09-15T14:15:20Z';
  assert.match(formatCountdown(twoHoursAhead, refMs), /2 ชม\. 15 นาที 20 วินาที/);

  // 45 seconds ahead
  const secondsAhead = '2026-09-15T12:00:45Z';
  assert.equal(formatCountdown(secondsAhead, refMs), '45 วินาที');

  // Past / exactly release time
  assert.equal(
    formatCountdown('2026-09-15T12:00:00Z', refMs),
    'RELEASE TIME (กำลังประกาศ / ประกาศแล้ว)'
  );
  assert.equal(
    formatCountdown('2026-09-15T11:00:00Z', refMs),
    'RELEASE TIME (กำลังประกาศ / ประกาศแล้ว)'
  );
});

// 3. Next High-Impact USD Event Selection Test
test('NextEconomicEventCard selects earliest future HIGH USD event and skips CANCELLED/non-USD', () => {
  // Reference time before NFP (2026-09-15T08:00:00Z)
  const html = renderToStaticMarkup(
    React.createElement(NextEconomicEventCard, {
      events: SAMPLE_EVENTS,
      asOf: '2026-09-15T08:00:00Z',
      source: 'forexfactory',
      sourceMode: 'LIVE',
    })
  );

  // Must select NFP (HIGH, USD, future)
  assert.match(html, /Non-Farm Employment Change|การจ้างงานนอกภาคเกษตร/);
  assert.match(html, /HIGH IMPACT/);
  assert.match(html, /USD/);
  assert.match(html, /180 พัน/);

  // Must NOT pick CANCELLED CPI even though it is earlier than NFP
  assert.doesNotMatch(html, /CPI|ดัชนีราคาผู้บริโภค/);

  // Must NOT pick EUR ECB even though it is HIGH impact
  assert.doesNotMatch(html, /ECB/);

  // Must NOT pick MEDIUM Retail Sales
  assert.doesNotMatch(html, /Retail Sales/);
});

test('NextEconomicEventCard renders empty message when no future High USD event exists without synthetic fabrication', () => {
  // Reference time AFTER all events (2026-09-16T00:00:00Z)
  const html = renderToStaticMarkup(
    React.createElement(NextEconomicEventCard, {
      events: SAMPLE_EVENTS,
      asOf: '2026-09-16T00:00:00Z',
      source: 'mock_macro_v1',
      sourceMode: 'FIXTURE',
    })
  );

  assert.match(html, /ไม่มีข่าว USD ผลกระทบสูงในช่วงข้อมูลที่เลือก/);
  assert.match(html, /ระบบไม่มีการสร้างหรือจำลองเหตุการณ์เท็จ/);
});

// 4. Canonical Trade Policy States Test
test('NewsRiskSummary renders canonical trade_policy_state (INFORMATIONAL, CAUTION, RESTRICTED) and separates Policy from Kill Switch', () => {
  for (const policy of ['INFORMATIONAL', 'CAUTION', 'RESTRICTED']) {
    const ctx = { ...SAMPLE_NEWS_CONTEXT, trade_policy_state: policy };
    const html = renderToStaticMarkup(
      React.createElement(NewsRiskSummary, {
        newsContext: ctx,
        loading: false,
        error: null,
      })
    );

    assert.match(html, new RegExp(policy));
    assert.match(html, /POLICY ≠ KILL SWITCH/);
    assert.match(html, /Macro Bias ≠ Trading Signal/);

    if (policy === 'INFORMATIONAL') {
      assert.match(html, /ปกติ \/ ใช้ประกอบบริบท/);
    } else if (policy === 'CAUTION') {
      assert.match(html, /ต้องระมัดระวังความผันผวน/);
    } else if (policy === 'RESTRICTED') {
      assert.match(html, /จำกัดการเทรดตามนโยบายข่าว/);
    }
  }
});

// 5. Canonical News Regime Handling Test
test('NewsRiskSummary supports all 8 canonical news regimes', () => {
  const regimes = [
    'NORMAL',
    'PRE_NEWS',
    'NEWS_LOCK',
    'RELEASE',
    'POST_NEWS_VOLATILITY',
    'POST_NEWS_CONFIRMATION',
    'NORMALIZED',
    'UNKNOWN',
  ];

  for (const regime of regimes) {
    const ctx = { ...SAMPLE_NEWS_CONTEXT, news_regime: regime };
    const html = renderToStaticMarkup(
      React.createElement(NewsRiskSummary, {
        newsContext: ctx,
        loading: false,
        error: null,
      })
    );

    assert.match(html, new RegExp(regime));
    assert.match(html, new RegExp(thai.label(regime)));
  }
});

test('NewsRiskSummary renders multiple event risk alert banner when active', () => {
  const ctxWithRisk = { ...SAMPLE_NEWS_CONTEXT, multiple_event_risk: true };
  const htmlWithRisk = renderToStaticMarkup(
    React.createElement(NewsRiskSummary, {
      newsContext: ctxWithRisk,
      loading: false,
      error: null,
    })
  );
  assert.match(htmlWithRisk, /แจ้งเตือนความเสี่ยงสะสม:.*Multiple Event Risk/);

  const ctxNoRisk = { ...SAMPLE_NEWS_CONTEXT, multiple_event_risk: false };
  const htmlNoRisk = renderToStaticMarkup(
    React.createElement(NewsRiskSummary, {
      newsContext: ctxNoRisk,
      loading: false,
      error: null,
    })
  );
  assert.doesNotMatch(htmlNoRisk, /แจ้งเตือนความเสี่ยงสะสม/);
});

// 6. Strategy News Eligibility Test
test('StrategyNewsEligibility renders STRAT05 & STRAT06 and states STRAT01–STRAT04 are market-driven', () => {
  const html = renderToStaticMarkup(
    React.createElement(StrategyNewsEligibility, {
      eligibility: {
        STRAT05: 'ALLOWED',
        STRAT06: 'CAUTION',
      },
    })
  );

  assert.match(html, /STRAT05/);
  assert.match(html, /Post-News Momentum/);
  assert.match(html, /ALLOWED/);

  assert.match(html, /STRAT06/);
  assert.match(html, /Post-News Liquidity Reversal/);
  assert.match(html, /CAUTION/);

  // Market-driven playbooks clarification
  assert.match(html, /STRAT01–STRAT04 \(Market-Driven Playbooks\)/);
  assert.match(html, /ข่าวเศรษฐกิจไม่เปลี่ยน Signal Identity/);
});

// 7. Event Detail Drawer & Revision History Test
test('EventDetailDrawer renders event details, revision list, and field conflicts warning', () => {
  const event = SAMPLE_EVENTS[4]; // Fed funds event with actual: '0' and field conflict ['forecast']
  const detail = {
    event,
    revisions: [
      {
        revision_version: 1,
        actual: '0',
        previous: '0%',
        revised_previous: null,
        status: 'RELEASED',
        available_at: '2026-09-15T02:00:01Z',
        unit: '%',
      },
      {
        revision_version: 2,
        actual: '0',
        previous: '0%',
        revised_previous: '0%',
        status: 'REVISED',
        available_at: '2026-09-15T02:00:05Z',
        unit: '%',
      },
    ],
    as_of: '2026-09-15T08:00:00Z',
  };

  const html = renderToStaticMarkup(
    React.createElement(EventDetailDrawer, {
      detail,
      loading: false,
      error: null,
      onClose: () => {},
    })
  );

  assert.match(html, /Federal Funds Rate|อัตราดอกเบี้ยนโยบายเฟด/);
  assert.match(html, /ข้อมูลจากแหล่งข่าวมีความขัดแย้ง \(Field Conflicts\)/);
  assert.match(html, /forecast/);
  assert.match(html, /ประวัติการปรับปรุงตัวเลข/);
  assert.match(html, /2 ฉบับ/);
  assert.match(html, /รุ่นที่ 1/);
  assert.match(html, /รุ่นที่ 2/);
});

// 8. Numeric Zero vs Missing Null Safety Test
test('Numeric formatter treats zero as valid and null as unannounced', () => {
  assert.equal(thai.numeric(0, 'PERCENT'), '0%');
  assert.equal(thai.numeric('0', 'PERCENT'), '0%');
  assert.equal(thai.numeric(0), '0');
  assert.equal(thai.numeric('0'), '0');
  assert.equal(thai.numeric(null), 'ยังไม่มีผลประกาศ');
  assert.equal(thai.numeric(undefined), 'ยังไม่มีผลประกาศ');
  assert.equal(thai.numeric('1.5', 'PERCENT'), '1.5%');
  assert.equal(thai.numeric('250', 'THOUSANDS'), '250 พัน');
});

// 9. Calendar Workspace Invariants & Decoupling Test
test('CalendarWorkspace enforces paper trading invariants and authoritative routes', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../src/features/news/CalendarWorkspace.tsx'), 'utf8');

  // Invariant: Paper trading badge
  assert.match(code, /PAPER MODE · EXECUTION DISABLED/);

  // Invariant: Live clock with Asia/Bangkok
  assert.match(code, /Asia\/Bangkok/);

  // Invariant: Authoritative endpoints only
  assert.match(code, /\/calendar\/economic/);
  assert.match(code, /\/news\/context/);
  assert.match(code, /\/news\/events\//);

  // Invariant: Zero order execution buttons
  assert.doesNotMatch(code, /place-order/i);
  assert.doesNotMatch(code, /buy-button/i);
  assert.doesNotMatch(code, /sell-button/i);

  // Invariant: Source mode truthfulness banner
  assert.match(code, /calendar-source-mode-banner/);
  assert.match(code, /REAL ECONOMIC CALENDAR/);
  assert.match(code, /ข้อมูลข่าวสาธิต · DEMO NEWS DATA/);
  assert.match(code, /CALENDAR UNAVAILABLE/);
});

// 10. News and Calendar Contracts Validation Test
test('Contracts parser parses calendar payload correctly', () => {
  const fixture = require('./fixtures/news.json');
  const calPayload = {
    events: fixture.events,
    source: fixture.source,
    source_mode: 'FIXTURE',
    state: 'AVAILABLE',
    as_of: fixture.as_of,
    generated_at: fixture.as_of,
    truncated: false,
  };
  const parsed = contracts.parseCalendar(calPayload);
  assert.equal(parsed.events.length, 3);
  assert.equal(parsed.source, 'fixture_economic_v1');
});
