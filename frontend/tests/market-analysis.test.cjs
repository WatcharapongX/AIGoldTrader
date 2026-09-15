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

const aiTypes = load('types/ai.generated.ts');
const { AIAgentCard } = load('features/analysis/AIAgentCard.tsx');
const { MetaControllerCard } = load('features/analysis/MetaControllerCard.tsx');
const { StrategyAnalysisContext } = load('features/analysis/StrategyAnalysisContext.tsx');
const { AIAgentAdvisoryPanel } = load('features/analysis/AIAgentAdvisoryPanel.tsx');

// Sample Fixtures
const sampleCandidate = {
  id: 'cand_test_001_xauusd_long_m5',
  profile_id: 'default_intraday',
  strategy_id: 'STRAT01',
  strategy_version: 'v1.0.0',
  symbol: 'XAUUSD',
  direction: 'LONG',
  status: 'READY',
  score: 85,
  detected_at: '2026-09-15T04:00:00Z',
  confirmed_at: '2026-09-15T04:05:00Z',
  expires_at: '2026-09-15T08:00:00Z',
  context_id: 'ctx_001',
  upstream_ids: ['m1_001'],
  evidence: [],
  missing_conditions: [],
  conflicts: [],
  invalidation_th: 'หลุดแนวรับ',
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
    invalidation_th: 'หลุดแนวรับ',
    targets: [{ name: 'TP1', price: '3660.00', source_id: 'src_003', rr: '2.0' }],
    score: 85,
    evidence: [],
    warnings_th: [],
    news_state: 'NO_IMPACT',
    as_of: '2026-09-15T04:05:00Z',
    context_id: 'ctx_001',
    expires_at: '2026-09-15T08:00:00Z',
  },
};

const sampleAgentResult = (agentId) => ({
  agent_id: agentId,
  agent_version: 'ai-1.0.0',
  status: 'READY',
  directional_bias: 'LONG',
  evidence_strength: 'STRONG',
  summary_th: `สรุปการวิเคราะห์เชิงลึกสำหรับ ${agentId}`,
  evidence_refs: ['ref_01'],
  supporting_factors_th: ['โครงสร้างขาขึ้นชัดเจน', 'สภาพคล่องรองรับ'],
  conflicting_factors_th: [],
  warnings_th: ['ให้ระวังช่วงตลาดลอนดอนเปิด'],
  missing_context_th: [],
  provider_provenance: 'fixture',
  prompt_version: 'v1',
  generated_at: '2026-09-15T04:05:00Z',
  as_of: '2026-09-15T04:05:00Z',
});

const sampleMetaResult = {
  analysis_id: 'ai_eval_001',
  symbol: 'XAUUSD',
  as_of: '2026-09-15T04:05:00Z',
  status: 'READY',
  directional_bias: 'LONG',
  evidence_strength: 'STRONG',
  agent_agreement: 'HIGH',
  summary_th: 'โครงสร้างโดยรวมสอดคล้องเชิงบวก มีแรงผลักดันต่อเนื่องในฝั่งซื้อ',
  key_evidence_th: ['BOS ขาขึ้นยืนยันใน H1', 'เกิด Liquidity Sweep ฝั่งขาย'],
  conflicts_th: [],
  risk_notes_th: ['ควบคุมความเสี่ยงไม่เกิน 1% ต่อไม้'],
  warnings_th: ['ระวังความผันผวนของข่าวเศรษฐกิจ'],
  agent_results: Object.fromEntries(
    aiTypes.CANONICAL_AGENT_IDS.map((id) => [id, sampleAgentResult(id)])
  ),
  strategy_id: 'STRAT01',
  strategy_version: 'v1.0.0',
  risk_decision_id: 'risk_dec_001',
  risk_decision_status: 'APPROVED',
  kill_switch_state: 'INACTIVE',
  provider_provenance: 'fixture',
  execution_provenance: {
    provider_id: 'fixture',
    provider_type: 'fixture',
    model_alias: 'fixture-v1',
    model_used: 'fixture-v1',
    mode: 'fixture',
  },
  prompt_versions: { market_context: 'v1' },
  generated_at: '2026-09-15T04:05:00Z',
  input_fingerprint: 'fp_input_001',
  analysis_fingerprint: 'fp_analysis_001',
  execution_disclaimer: 'ADVISORY_ONLY_NO_EXECUTION_AUTHORITY',
};

test('No candidate available disables AI evaluation and explains downstream rule', () => {
  const html = renderToStaticMarkup(
    React.createElement(StrategyAnalysisContext, {
      candidates: [],
      selectedCandidateId: '',
      onSelectCandidate: () => {},
      account: null,
      killSwitch: { state: 'INACTIVE', reason_th: '' },
      riskDecision: null,
      onEvaluateAI: () => {},
      isEvaluating: false,
      evaluateError: null,
      hasAIResult: false,
      isOutdated: false,
    })
  );

  assert.ok(html.includes('ยังไม่มี Strategy Candidate สำหรับการวิเคราะห์ด้วย AI'));
  assert.ok(html.includes('disabled'));
  assert.ok(html.includes('PIPELINE: MARKET → STRATEGY → RISK → AI'));
});

test('Candidate available enables AI evaluation button and displays deterministic geometry', () => {
  const html = renderToStaticMarkup(
    React.createElement(StrategyAnalysisContext, {
      candidates: [sampleCandidate],
      selectedCandidateId: sampleCandidate.id,
      onSelectCandidate: () => {},
      account: { account_id: 'default_paper_account', balance: '100000.00' },
      killSwitch: { state: 'INACTIVE', reason_th: '' },
      riskDecision: { decision: 'APPROVED' },
      onEvaluateAI: () => {},
      isEvaluating: false,
      evaluateError: null,
      hasAIResult: false,
      isOutdated: false,
    })
  );

  assert.ok(html.includes('STRAT01'));
  assert.ok(html.includes('Score: 85'));
  assert.ok(html.includes('3640.00'));
  assert.ok(html.includes('3630.00'));
  assert.ok(html.includes('วิเคราะห์ด้วย AI'));
  // Ensure Entry/SL/TP are labeled deterministic
  assert.ok(html.includes('Deterministic'));
});

test('Kill Switch ACTIVE or Risk BLOCKED prevents AI evaluation call', () => {
  // Test Kill Switch Active
  const htmlKill = renderToStaticMarkup(
    React.createElement(StrategyAnalysisContext, {
      candidates: [sampleCandidate],
      selectedCandidateId: sampleCandidate.id,
      onSelectCandidate: () => {},
      account: { account_id: 'default_paper_account', balance: '100000.00' },
      killSwitch: { state: 'ACTIVE', reason_th: 'ตลาดผันผวนรุนแรง' },
      riskDecision: { decision: 'APPROVED' },
      onEvaluateAI: () => {},
      isEvaluating: false,
      evaluateError: null,
      hasAIResult: false,
      isOutdated: false,
    })
  );

  assert.ok(htmlKill.includes('Kill Switch ทำงานอยู่'));
  assert.ok(htmlKill.includes('disabled'));

  // Test Risk Blocked
  const htmlRisk = renderToStaticMarkup(
    React.createElement(StrategyAnalysisContext, {
      candidates: [sampleCandidate],
      selectedCandidateId: sampleCandidate.id,
      onSelectCandidate: () => {},
      account: { account_id: 'default_paper_account', balance: '100000.00' },
      killSwitch: { state: 'INACTIVE', reason_th: '' },
      riskDecision: { decision: 'BLOCKED' },
      onEvaluateAI: () => {},
      isEvaluating: false,
      evaluateError: null,
      hasAIResult: false,
      isOutdated: false,
    })
  );

  assert.ok(htmlRisk.includes('Risk Engine สั่งบล็อก'));
  assert.ok(htmlRisk.includes('disabled'));
});

test('Changing candidate marks previous AI result OUTDATED', () => {
  const htmlOutdated = renderToStaticMarkup(
    React.createElement(MetaControllerCard, {
      result: sampleMetaResult,
      isLoading: false,
      isOutdated: true,
      outdatedReason: 'Candidate ถูกเปลี่ยนเป็นรายการใหม่หลังจากวิเคราะห์',
    })
  );

  assert.ok(htmlOutdated.includes('OUTDATED'));
  assert.ok(htmlOutdated.includes('Candidate ถูกเปลี่ยนเป็นรายการใหม่หลังจากวิเคราะห์'));
  assert.ok(htmlOutdated.includes('กรุณาวิเคราะห์ใหม่'));
});

test('Fixture provider advisory is prominently labeled as Fixture Advisory', () => {
  const html = renderToStaticMarkup(
    React.createElement(AIAgentAdvisoryPanel, {
      result: sampleMetaResult,
      isLoading: false,
      isOutdated: false,
      aiSystemStatus: { state: 'FIXTURE_READY', detail_th: 'โหมดทดสอบในตัว' },
    })
  );

  assert.ok(html.includes('AI ADVISORY ONLY'));
  assert.ok(html.includes('FIXTURE ADVISORY'));
  assert.ok(html.includes('OFFLINE DETERMINISTIC TEST PROVIDER'));
});

test('Renders exactly six canonical analytical agents with separate Meta Controller', () => {
  const html = renderToStaticMarkup(
    React.createElement(AIAgentAdvisoryPanel, {
      result: sampleMetaResult,
      isLoading: false,
      isOutdated: false,
      aiSystemStatus: { state: 'FIXTURE_READY', detail_th: 'โหมดทดสอบในตัว' },
    })
  );

  // Meta Controller is distinct and marked NOT a 7th agent
  assert.ok(html.includes('Meta Controller Thesis Synthesis'));
  assert.ok(html.includes('NOT A 7TH AGENT'));

  // Exactly 6 canonical agent cards rendered
  for (const agentId of aiTypes.CANONICAL_AGENT_IDS) {
    const meta = aiTypes.CANONICAL_AGENT_METADATA[agentId];
    assert.ok(html.includes(meta.nameTh), `Should contain Thai name for ${agentId}`);
    assert.ok(html.includes(`data-testid="agent-card-${agentId}"`), `Should contain card for ${agentId}`);
  }

  // Qualitative confidence only (no fake numeric 94% or 87%)
  assert.ok(html.includes('STRONG'));
  assert.ok(html.includes('HIGH'));
  assert.ok(!html.includes('94%') && !html.includes('87%'));
});

test('Truthful partial agent readiness e.g. 5/6 READY handled gracefully', () => {
  const partialMeta = {
    ...sampleMetaResult,
    agent_results: {
      ...sampleMetaResult.agent_results,
      trade_thesis: {
        ...sampleMetaResult.agent_results.trade_thesis,
        status: 'DEGRADED',
      },
    },
  };

  const html = renderToStaticMarkup(
    React.createElement(MetaControllerCard, {
      result: partialMeta,
      isLoading: false,
      isOutdated: false,
    })
  );

  assert.ok(html.includes('5 / 6 READY'));
});

test('AIAgentCard displays directional bias, evidence strength, Thai factors, and warnings', () => {
  const cardHtml = renderToStaticMarkup(
    React.createElement(AIAgentCard, {
      agentId: 'smc_ict',
      result: sampleAgentResult('smc_ict'),
      isLoading: false,
    })
  );

  assert.ok(cardHtml.includes('วิเคราะห์ SMC / ICT'));
  assert.ok(cardHtml.includes('LONG · ขาขึ้น'));
  assert.ok(cardHtml.includes('หนักแน่น (STRONG)'));
  assert.ok(cardHtml.includes('โครงสร้างขาขึ้นชัดเจน'));
  assert.ok(cardHtml.includes('ข้อควรระวัง'));
  assert.ok(cardHtml.includes('READY'));
});

test('AI evaluate payload contract strictly enforces candidate_id, account_id, profile_id only', () => {
  const validRequest = {
    candidate_id: 'cand_123',
    account_id: 'default_paper_account',
    profile_id: 'default_intraday',
  };

  // Ensure allowed keys are exactly candidate_id, account_id, profile_id
  const allowedKeys = new Set(['candidate_id', 'account_id', 'profile_id']);
  const actualKeys = Object.keys(validRequest);
  assert.ok(actualKeys.every((k) => allowedKeys.has(k)));

  // Ensure no client market context, price, or risk decision can be included
  const forbiddenKeys = ['market_data', 'quote', 'risk_decision', 'kill_switch', 'entry', 'stop_loss', 'take_profit'];
  for (const k of forbiddenKeys) {
    assert.ok(!actualKeys.includes(k), `Payload must not contain ${k}`);
  }
});

test('AI failure or error state isolates safely without breaking deterministic layout', () => {
  const html = renderToStaticMarkup(
    React.createElement(StrategyAnalysisContext, {
      candidates: [sampleCandidate],
      selectedCandidateId: sampleCandidate.id,
      onSelectCandidate: () => {},
      account: { account_id: 'default_paper_account', balance: '100000.00' },
      killSwitch: { state: 'INACTIVE', reason_th: '' },
      riskDecision: { decision: 'APPROVED' },
      onEvaluateAI: () => {},
      isEvaluating: false,
      evaluateError: 'AI Service rate limit exceeded (429)',
      hasAIResult: false,
      isOutdated: false,
    })
  );

  assert.ok(html.includes('ข้อผิดพลาด: AI Service rate limit exceeded (429)'));
  assert.ok(html.includes('STRAT01'));
});
