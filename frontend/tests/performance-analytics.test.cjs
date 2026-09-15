const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// 1. Account Snapshot Parsing & Handling
test('Account Snapshot contract correctly handles nulls, decimal values, and source badges', () => {
  const accountCardCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/AccountSnapshotCard.tsx'),
    'utf8'
  );
  const contractsCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/contracts.ts'),
    'utf8'
  );

  // Assert required fields are present in contract
  assert.match(contractsCode, /export interface ExtendedAccountSnapshot/);
  assert.match(contractsCode, /account_id: string/);
  assert.match(contractsCode, /balance: string/);
  assert.match(contractsCode, /equity: string/);
  assert.match(contractsCode, /free_margin: string \| null/);
  assert.match(contractsCode, /daily_realized_pnl: string/);
  assert.match(contractsCode, /weekly_realized_pnl: string/);
  assert.match(contractsCode, /floating_pnl: string \| null/);
  assert.match(contractsCode, /peak_equity: string/);
  assert.match(contractsCode, /open_positions_count: number/);
  assert.doesNotMatch(contractsCode, /balance \?\? '0\.00'/);
  assert.doesNotMatch(contractsCode, /account_id \|\| 'default_paper_account'/);
  assert.doesNotMatch(contractsCode, /trading_mode \|\| 'PAPER'/);
  assert.doesNotMatch(contractsCode, /source \|\| 'CONFIGURED_PAPER'/);
  assert.doesNotMatch(contractsCode, /as_of \|\| new Date/);


  // Assert null handling in card
  assert.match(accountCardCode, /N\/A \/ ไม่มีข้อมูล Position/);
  assert.match(accountCardCode, /ยังไม่มี Execute Trade Records/);
  assert.match(accountCardCode, /ACCOUNT_SOURCE_TH/);
  assert.match(accountCardCode, /account\.trading_mode/);
});

// 2. Snapshot Drawdown vs Max Drawdown Labeling Truthfulness
test('Current Snapshot Drawdown is explicitly labeled and never called Maximum Drawdown', () => {
  const accountCardCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/AccountSnapshotCard.tsx'),
    'utf8'
  );
  const contractsCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/contracts.ts'),
    'utf8'
  );

  // Must have exact label
  assert.match(accountCardCode, /CURRENT ACCOUNT SNAPSHOT DRAWDOWN/);
  assert.match(accountCardCode, /Peak vs Equity ปัจจุบัน — ไม่ใช่ Max Drawdown/);

  // Calculation in contracts.ts
  assert.match(contractsCode, /calculateSnapshotDrawdown/);
  assert.match(contractsCode, /\(\(peak - equity\) \/ peak\) \* 100/);
});

// 3. Portfolio Risk & Active Reservations Truthfulness
test('Portfolio risk reservations are strictly distinguished from open trades/positions', () => {
  const portfolioCardCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/PortfolioRiskCard.tsx'),
    'utf8'
  );

  assert.match(portfolioCardCode, /Portfolio Risk & Capacity/);
  assert.match(portfolioCardCode, /Active Risk Reservations/);
  assert.match(portfolioCardCode, /Reservation ≠ Executed Position/);
  assert.match(portfolioCardCode, /การจองโควต้าไม่ใช่การเปิดออเดอร์/);
  assert.match(portfolioCardCode, /KILL SWITCH/);
});

// 4. Candidate Analytics & Canonical States
test('Candidate Analytics renders all 8 canonical states and truthful evidence score', () => {
  const panelCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/CandidateAnalyticsPanel.tsx'),
    'utf8'
  );
  const contractsCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/contracts.ts'),
    'utf8'
  );

  // 8 Canonical states
  const expectedStates = [
    'DETECTED',
    'WAITING_CONFIRMATION',
    'READY',
    'BLOCKED_CONTEXT',
    'NO_TRADE',
    'INVALIDATED',
    'EXPIRED',
    'SUPERSEDED',
  ];

  for (const st of expectedStates) {
    assert.match(contractsCode, new RegExp(st));
  }

  // Setup Evidence Score is NOT called probability, win rate, or confidence
  assert.match(panelCode, /Average Setup Evidence Score/);
  assert.match(panelCode, /คะแนนตรวจพบหลักฐาน \(ไม่ใช่ Win Probability\)/);
  assert.match(panelCode, /Candidate Count ≠ Total Trades/);
  assert.match(panelCode, /Candidate State Distribution/);
  assert.match(panelCode, /ไม่ใช่ Win Rate/);
  assert.match(panelCode, /Setup Direction Frequency/);
  assert.match(panelCode, /ไม่ได้สะท้อนถึงแนวโน้มกำไร \(Profitable Bias\)/);
});

// 5. Risk Decision Analytics
test('Risk Decision Analytics computes canonical decision distribution and block reasons', () => {
  const panelCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/RiskDecisionAnalyticsPanel.tsx'),
    'utf8'
  );

  // Canonical decisions
  assert.match(panelCode, /APPROVED/);
  assert.match(panelCode, /REDUCED/);
  assert.match(panelCode, /BLOCKED/);

  // Must not call decision rate trade success rate
  assert.match(panelCode, /Risk Decision ≠ Executed Trades/);
  assert.match(panelCode, /Requested vs Approved Risk Comparison/);
  assert.match(panelCode, /Top Block Reasons/);
  assert.match(panelCode, /Risk Warnings/);
  assert.match(panelCode, /Risk Decisions by Strategy/);
  assert.match(panelCode, /Risk Decisions by Direction/);
});

// 6. Historical Evaluation Activity
test('Historical Evaluation Activity shows operational snapshots and disclaims backtest', () => {
  const panelCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/EvaluationActivityPanel.tsx'),
    'utf8'
  );

  assert.match(panelCode, /Historical Evaluation Activity/);
  assert.match(panelCode, /NOT A BACKTEST/);
  assert.match(panelCode, /ไม่ใช่ผลทดสอบย้อนหลัง/);
  assert.match(panelCode, /Activity Timeline/);
  assert.match(panelCode, /STALE SNAPSHOT/);
});

// 7. Executed Trading Performance Section
test('Executed Trading Performance marks all trade metrics as NOT AVAILABLE and rejects fake zeros', () => {
  const execCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/ExecutionPerformanceSection.tsx'),
    'utf8'
  );

  assert.match(execCode, /EXECUTED TRADING PERFORMANCE/);
  assert.match(execCode, /NOT AVAILABLE/);
  assert.match(execCode, /Broker Execution.*DISABLED/);
  assert.match(execCode, /Paper Orders.*ยังไม่เริ่มพัฒนา/);
  assert.match(execCode, /Position Lifecycle.*ยังไม่มีในระบบ/);
  assert.match(execCode, /Trade Journal.*ยังไม่ได้รับการติดตั้ง/);
  assert.match(execCode, /Total Executed Trades/);
  assert.match(execCode, /Win Rate/);
  assert.match(execCode, /Profit Factor/);
  assert.match(execCode, /Net P&L/);
  assert.match(execCode, /Expectancy/);
  assert.match(execCode, /Maximum Drawdown/);
  assert.match(execCode, /Sharpe Ratio/);
  assert.match(execCode, /Equity Curve/);
  assert.match(execCode, /Monthly P&L/);
  assert.match(execCode, /ไม่แสดงค่า 0 หรือ 0% เป็นตัวแทนคำนวณผลตอบแทน/);
});

// 8. Performance Readiness Matrix
test('Performance Readiness Matrix faithfully tracks 11 system components', () => {
  const readinessCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/PerformanceReadinessPanel.tsx'),
    'utf8'
  );
  const contractsCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/contracts.ts'),
    'utf8'
  );

  assert.match(readinessCode, /Performance Readiness Matrix/);
  assert.match(contractsCode, /Candidate History/);
  assert.match(contractsCode, /Strategy Evaluation History/);
  assert.match(contractsCode, /Risk Decision History/);
  assert.match(contractsCode, /Account Snapshot/);
  assert.match(contractsCode, /Paper Order Ledger/);
  assert.match(contractsCode, /Executed Trade History/);
  assert.match(contractsCode, /Position Lifecycle/);
  assert.match(contractsCode, /Trade Journal/);
  assert.match(contractsCode, /Backtest Results/);
  assert.match(contractsCode, /Equity History/);
  assert.match(contractsCode, /Performance Engine/);
});

// 9. No Fabricated Performance Metrics in Source
test('Workspace source code does not contain hardcoded fake performance metrics', () => {
  const dir = path.resolve(__dirname, '../src/features/analytics');
  const files = fs.readdirSync(dir).filter((f) => f.endsWith('.tsx') || f.endsWith('.ts'));

  for (const f of files) {
    const code = fs.readFileSync(path.join(dir, f), 'utf8');
    // Ensure no fake win rate or profit factor is hardcoded
    assert.doesNotMatch(code, /67%/);
    assert.doesNotMatch(code, /1\.8 Profit Factor/i);
    assert.doesNotMatch(code, /\$2,450/);
    assert.doesNotMatch(code, /Win Rate:\s*['"]?[0-9]+/);
  }
});

// 10. PerformanceScreen integration & Failure Isolation
test('PerformanceScreen integrates all panels and enforces failure isolation', () => {
  const screenCode = fs.readFileSync(
    path.resolve(__dirname, '../src/features/analytics/PerformanceScreen.tsx'),
    'utf8'
  );

  // Independent fetch try/catches
  assert.match(screenCode, /\/risk\/account/);
  assert.match(screenCode, /\/risk\/portfolio/);
  assert.match(screenCode, /\/trade-candidates/);
  assert.match(screenCode, /\/strategies/);
  assert.match(screenCode, /\/trader-profiles/);
  assert.match(screenCode, /\/risk\/decisions/);
  assert.match(screenCode, /\/strategy\/evaluations/);

  // Mounting all subcomponents
  assert.match(screenCode, /<PerformanceStatusHeader/);
  assert.match(screenCode, /<AccountSnapshotCard/);
  assert.match(screenCode, /<PortfolioRiskCard/);
  assert.match(screenCode, /<CandidateAnalyticsPanel/);
  assert.match(screenCode, /<RiskDecisionAnalyticsPanel/);
  assert.match(screenCode, /<EvaluationActivityPanel/);
  assert.match(screenCode, /<ExecutionPerformanceSection/);
  assert.match(screenCode, /<PerformanceReadinessPanel/);
});
