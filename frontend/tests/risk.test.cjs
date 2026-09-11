const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadModule(relPath) {
  const full = path.resolve(__dirname, '../src', relPath);
  const code = ts.transpileModule(fs.readFileSync(full, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
  }).outputText;
  const exp = {};
  vm.runInNewContext(code, {
    exports: exp,
    Date,
    Number,
    Set,
    JSON,
    Boolean,
    String,
    Array,
    Error,
    console,
  });
  return exp;
}

const {
  parseRiskPolicy,
  parseKillSwitch,
  parsePortfolioRisk,
  parseRiskDecision,
  parseRiskDecisions,
  RiskContractError,
} = loadModule('features/risk/contracts.ts');

const samplePolicy = {
  version: 'risk-policy-1.0.0',
  max_risk_per_trade_pct: '1.0',
  min_risk_per_trade_pct: '0.1',
  max_account_risk_pct: '3.0',
  max_symbol_risk_pct: '3.0',
  max_directional_risk_pct: '3.0',
  max_concurrent_trades: 5,
  daily_loss_limit_pct: '3.0',
  weekly_loss_limit_pct: '6.0',
  max_drawdown_pct: '10.0',
  cooldown_consecutive_losses: 3,
  max_spread_absolute: '0.60',
  news_blackout_minutes: 5,
  news_reduction_window_minutes: 15,
  news_reduction_factor: '0.50',
  reservation_ttl_seconds: 60,
};

const sampleKillSwitch = {
  state: 'INACTIVE',
  trigger_type: 'MANUAL',
  reason_th: 'ระบบทำงานปกติ',
  activated_at: '2026-09-10T12:00:00Z',
  activated_by: 'system',
  cleared_at: null,
  cleared_by: null,
  policy_version: 'risk-policy-1.0.0',
};

const samplePortfolio = {
  account_id: 'acc_001',
  as_of: '2026-09-10T12:00:00Z',
  open_risk_pct: '0.0000',
  reserved_risk_pct: '1.0000',
  total_risk_pct: '1.0000',
  max_account_risk_pct: '3.0000',
  available_risk_pct: '2.0000',
  symbol_risk_pct: { XAUUSD: '1.0000' },
  directional_risk_pct: { LONG: '1.0000', SHORT: '0.0000' },
  active_reservations: [
    {
      id: 'res_001',
      decision_id: 'dec_001',
      account_id: 'acc_001',
      profile_id: 'day_trader',
      symbol: 'XAUUSD',
      direction: 'LONG',
      risk_pct: '1.0000',
      risk_amount: '100.00',
      position_size: '0.14',
      status: 'ACTIVE',
      reserved_at: '2026-09-10T12:00:00Z',
      reserved_until: '2026-09-10T12:01:00Z',
    },
  ],
  active_reservations_count: 1,
  kill_switch_active: false,
  kill_switch_state: null,
  daily_loss_pct: '0.00',
  weekly_loss_pct: '0.00',
  drawdown_pct: '0.00',
  in_cooldown: false,
};

const sampleDecision = {
  id: 'dec_001',
  candidate_id: 'cand_001',
  plan_id: 'plan_001',
  strategy_id: 'STRAT01',
  strategy_version: '1.0.0',
  profile_id: 'day_trader',
  symbol: 'XAUUSD',
  direction: 'LONG',
  decision: 'APPROVED',
  requested_risk_pct: '1.0000',
  approved_risk_pct: '1.0000',
  requested_risk_amount: '100.00',
  approved_risk_amount: '100.00',
  position_size: '0.14',
  entry_lower: '2500.00',
  entry_upper: '2502.00',
  stop_loss: '2495.00',
  stop_distance: '7.00',
  portfolio_exposure_before: '0.0000',
  portfolio_exposure_after: '1.0000',
  account_snapshot_id: 'snap_001',
  symbol_specification_id: 'spec_001',
  policy_version: 'risk-policy-1.0.0',
  as_of: '2026-09-10T12:00:00Z',
  expires_at: '2026-09-10T12:05:00Z',
  reasons_th: ['อนุมัติแผนเทรดตามปกติ ขนาดความเสี่ยง 1.00% ($100.00)'],
  warnings_th: [],
  blocked_reasons_th: [],
  market_provenance: {
    source: 'simulated',
    mode: 'SIMULATED',
    quote_timestamp: '2026-09-10T12:00:00Z',
    quote_bid: '2500.00',
    quote_ask: '2500.30',
    quote_spread: '0.30',
    is_stale: false,
  },
  news_risk_provenance: {
    news_state: 'CALM',
    in_blackout: false,
    in_pre_news_window: false,
    in_post_news_window: false,
    event_ids: [],
    description_th: 'สภาวะข่าวปกติ',
  },
};

test('parseRiskPolicy parses authoritative policy and enforces constraints', () => {
  const parsed = parseRiskPolicy(samplePolicy);
  assert.equal(parsed.version, 'risk-policy-1.0.0');
  assert.equal(parsed.max_account_risk_pct, '3.0');
  assert.equal(parsed.max_concurrent_trades, 5);

  // Rejects invalid version
  assert.throws(() => parseRiskPolicy({ ...samplePolicy, version: 'invalid-version' }), RiskContractError);
  // Rejects non-numeric limits
  assert.throws(() => parseRiskPolicy({ ...samplePolicy, max_account_risk_pct: 'NaN' }), RiskContractError);
  // Rejects negative/zero concurrent trades
  assert.throws(() => parseRiskPolicy({ ...samplePolicy, max_concurrent_trades: 0 }), RiskContractError);
});

test('parseKillSwitch parses active and inactive states with Thai reasons', () => {
  const inactive = parseKillSwitch(sampleKillSwitch);
  assert.equal(inactive.state, 'INACTIVE');
  assert.equal(inactive.reason_th, 'ระบบทำงานปกติ');

  const active = parseKillSwitch({
    ...sampleKillSwitch,
    state: 'ACTIVE',
    reason_th: 'ปิดระบบฉุกเฉินเนื่องจากความผันผวนสูง',
    activated_by: 'operator_admin',
  });
  assert.equal(active.state, 'ACTIVE');
  assert.equal(active.activated_by, 'operator_admin');

  // Rejects unknown state
  assert.throws(() => parseKillSwitch({ ...sampleKillSwitch, state: 'PAUSED' }), RiskContractError);
  // Rejects invalid timestamp
  assert.throws(() => parseKillSwitch({ ...sampleKillSwitch, activated_at: 'not-a-date' }), RiskContractError);
});

test('parsePortfolioRisk verifies gross directional exposure and reservations', () => {
  const parsed = parsePortfolioRisk(samplePortfolio);
  assert.equal(parsed.total_risk_pct, '1.0000');
  assert.equal(parsed.available_risk_pct, '2.0000');
  assert.equal(parsed.active_reservations.length, 1);
  assert.equal(parsed.active_reservations[0].direction, 'LONG');
  assert.equal(parsed.directional_risk_pct.LONG, '1.0000');
  assert.equal(parsed.directional_risk_pct.SHORT, '0.0000');

  // Rejects invalid timestamp
  assert.throws(() => parsePortfolioRisk({ ...samplePortfolio, as_of: 'invalid' }), RiskContractError);
  // Rejects non-numeric available risk
  assert.throws(() => parsePortfolioRisk({ ...samplePortfolio, available_risk_pct: 'abc' }), RiskContractError);
});

test('parseRiskDecision parses APPROVED, REDUCED, and BLOCKED decisions', () => {
  const approved = parseRiskDecision(sampleDecision);
  assert.equal(approved.decision, 'APPROVED');
  assert.equal(approved.approved_risk_pct, '1.0000');
  assert.ok(approved.reasons_th[0].includes('อนุมัติแผนเทรดตามปกติ'));

  const reduced = parseRiskDecision({
    ...sampleDecision,
    decision: 'REDUCED',
    approved_risk_pct: '0.5000',
    approved_risk_amount: '50.00',
    position_size: '0.07',
    reasons_th: ['อนุมัติแบบลดความเสี่ยงเหลือ 0.50%'],
    warnings_th: ['ใกล้เวลาประกาศข่าวสำคัญ ปรับลดความเสี่ยง 50%'],
  });
  assert.equal(reduced.decision, 'REDUCED');
  assert.equal(reduced.approved_risk_pct, '0.5000');
  assert.equal(reduced.warnings_th.length, 1);

  const blocked = parseRiskDecision({
    ...sampleDecision,
    decision: 'BLOCKED',
    approved_risk_pct: '0.0000',
    approved_risk_amount: '0.00',
    position_size: '0.0000',
    reasons_th: ['การประเมินถูกปฏิเสธโดยระบบ Kill Switch ฉุกเฉิน'],
    blocked_reasons_th: ['ไม่อนุมัติเนื่องจาก Kill Switch ทำงาน'],
  });
  assert.equal(blocked.decision, 'BLOCKED');
  assert.equal(blocked.position_size, '0.0000');
  assert.equal(blocked.blocked_reasons_th.length, 1);

  // Multiple decisions
  const list = parseRiskDecisions([approved, reduced, blocked]);
  assert.equal(list.length, 3);

  // Rejects unknown decision status
  assert.throws(() => parseRiskDecision({ ...sampleDecision, decision: 'BUY_NOW' }), RiskContractError);
  // Rejects missing candidate ID
  assert.throws(() => parseRiskDecision({ ...sampleDecision, candidate_id: undefined }), RiskContractError);
});

test('risk contracts enforce analysis-only safety (no execution mutations)', () => {
  const d = parseRiskDecision(sampleDecision);
  // Must have immutable decision data without order sending structures
  assert.equal(typeof d.id, 'string');
  assert.equal(typeof d.approved_risk_pct, 'string');
  assert.equal(typeof d.position_size, 'string');
  assert.ok(!('order_id' in d));
  assert.ok(!('ticket' in d));
  assert.ok(!('execute' in d));
});

test('parseKillSwitch handles UNKNOWN fail-closed state', () => {
  const unknown = parseKillSwitch({
    ...sampleKillSwitch,
    state: 'UNKNOWN',
    trigger_type: 'AUTOMATIC_SYSTEM_HEALTH',
    reason_th: 'ไม่สามารถระบุสถานะได้ Fail-Closed',
  });
  assert.equal(unknown.state, 'UNKNOWN');
  assert.equal(unknown.reason_th, 'ไม่สามารถระบุสถานะได้ Fail-Closed');
});

test('parseRiskPolicy handles exact backend field names and aliases', () => {
  const exactPolicy = {
    ...samplePolicy,
    news_high_impact_blackout_pre_minutes: 10,
    news_high_impact_pre_minutes: 20,
    news_high_impact_post_minutes: 25,
    news_blackout_minutes: undefined,
    news_reduction_window_minutes: undefined,
  };
  const parsed = parseRiskPolicy(exactPolicy);
  assert.equal(parsed.news_high_impact_blackout_pre_minutes, 10);
  assert.equal(parsed.news_high_impact_pre_minutes, 20);
  assert.equal(parsed.news_high_impact_post_minutes, 25);
  assert.equal(parsed.news_blackout_minutes, 10);
  assert.equal(parsed.news_reduction_window_minutes, 20);
});

test('parsePortfolioRisk preserves account source and cooldown_until', () => {
  const port = parsePortfolioRisk({
    ...samplePortfolio,
    account_source: 'MT5_DEMO',
    cooldown_until: '2026-09-10T13:00:00Z',
    in_cooldown: true,
  });
  assert.equal(port.account_source, 'MT5_DEMO');
  assert.equal(port.cooldown_until, '2026-09-10T13:00:00Z');
  assert.equal(port.in_cooldown, true);
});

test('parseRiskDecision preserves dependency_fingerprint', () => {
  const dec = parseRiskDecision({
    ...sampleDecision,
    dependency_fingerprint: 'a1b2c3d4e5f60718293a4b5c6d7e8f90',
  });
  assert.equal(dec.dependency_fingerprint, 'a1b2c3d4e5f60718293a4b5c6d7e8f90');
});

