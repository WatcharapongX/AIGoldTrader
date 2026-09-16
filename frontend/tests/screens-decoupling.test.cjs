const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('MarketOverviewScreen is decoupled and focuses on market pulse and global sessions', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../src/features/overview/MarketOverviewScreen.tsx'), 'utf8');
  assert.match(code, /Market Overview/);
  assert.match(code, /GLOBAL_SESSIONS/);
  assert.match(code, /Asian Session/);
  assert.match(code, /European Session/);
  assert.match(code, /US Session/);
  assert.match(code, /London \/ NY Overlap/);
  assert.match(code, /systemStatus\?\.trading_mode \?\? 'UNKNOWN'/);
  assert.match(code, /systemStatus\.live_auto_trading/);
  assert.match(code, /FAIL-CLOSED POLICY/);
  assert.match(code, /US Dollar Index \(DXY\)/);
  assert.match(code, /US 10Y Yield/);
  assert.match(code, /href={`\/analysis\?symbol=\$\{encodeURIComponent\(symbol\)\}&timeframe=\$\{encodeURIComponent\(timeframe\)\}`}|href="\/analysis"/);
  assert.match(code, /href="\/signals"/);
  assert.match(code, /href="\/calendar"/);

  // Assert it does not bloat with deep strategy candidates or news panels
  assert.doesNotMatch(code, /<StrategyWorkspace/);
  assert.doesNotMatch(code, /<TradingNewsPanel/);
  assert.doesNotMatch(code, /<AnalysisWorkspace/);
});

test('MarketAnalysisScreen is dedicated to SMC and market structure workbench', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../src/features/analysis/MarketAnalysisScreen.tsx'), 'utf8');
  assert.match(code, /Market Analysis/);
  assert.match(code, /AnalysisWorkspace/);
  assert.match(code, /AnalysisPrimitive/);
  assert.match(code, /SMART MONEY CONCEPTS & MARKET STRUCTURE/);
  assert.match(code, /href="\/trading"/);

  // Assert it does not duplicate strategy signals or news panels
  assert.doesNotMatch(code, /<StrategyWorkspace/);
  assert.doesNotMatch(code, /<TradingNewsPanel/);
});

test('TradingSignalsScreen is dedicated to strategy evaluation and candidate scoring', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../src/features/strategy/TradingSignalsScreen.tsx'), 'utf8');
  assert.match(code, /Trading Signals/);
  assert.match(code, /StrategyWorkspace/);
  assert.match(code, /PAPER MODE · EXECUTION DISABLED/);
});

test('NewsSentimentScreen is dedicated to macroeconomic context and sentiment', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../src/features/news/NewsSentimentScreen.tsx'), 'utf8');
  assert.match(code, /News & Sentiment/);
  assert.match(code, /TradingNewsPanel/);
  assert.match(code, /href="\/calendar"/);
});

test('PerformanceScreen is dedicated to operational analytics and decoupled from trade execution', () => {
  const code = fs.readFileSync(path.resolve(__dirname, '../src/features/analytics/PerformanceScreen.tsx'), 'utf8');
  assert.match(code, /PerformanceStatusHeader/);
  assert.match(code, /AccountSnapshotCard/);
  assert.match(code, /PortfolioRiskCard/);
  assert.match(code, /CandidateAnalyticsPanel/);
  assert.match(code, /RiskDecisionAnalyticsPanel/);
  assert.match(code, /ExecutionPerformanceSection/);
  assert.match(code, /PerformanceReadinessPanel/);
});

test('Page routes mount the decoupled screens', () => {
  const tradingPage = fs.readFileSync(path.resolve(__dirname, '../src/app/(dashboard)/trading/page.tsx'), 'utf8');
  assert.match(tradingPage, /MarketOverviewScreen/);

  const analysisPage = fs.readFileSync(path.resolve(__dirname, '../src/app/(dashboard)/analysis/page.tsx'), 'utf8');
  assert.match(analysisPage, /MarketAnalysisScreen/);

  const signalsPage = fs.readFileSync(path.resolve(__dirname, '../src/app/(dashboard)/signals/page.tsx'), 'utf8');
  assert.match(signalsPage, /TradingSignalsScreen/);

  const scannerPage = fs.readFileSync(path.resolve(__dirname, '../src/app/(dashboard)/scanner/page.tsx'), 'utf8');
  assert.match(scannerPage, /NewsSentimentScreen/);

  const backtestingPage = fs.readFileSync(path.resolve(__dirname, '../src/app/(dashboard)/backtesting/page.tsx'), 'utf8');
  assert.match(backtestingPage, /StrategyLabScreen/);

  const analyticsPage = fs.readFileSync(path.resolve(__dirname, '../src/app/(dashboard)/analytics/page.tsx'), 'utf8');
  assert.match(analyticsPage, /PerformanceScreen/);
});
