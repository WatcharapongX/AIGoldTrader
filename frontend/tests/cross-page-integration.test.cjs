const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const read = (relative) => fs.readFileSync(path.join(root, relative), 'utf8');

test('sidebar cross-page route inventory resolves to concrete pages', () => {
  const routes = ['dashboard', 'trading', 'analysis', 'signals', 'backtesting', 'calendar', 'scanner', 'analytics', 'journal', 'settings'];
  for (const route of routes) {
    assert.equal(fs.existsSync(path.join(root, 'src/app/(dashboard)', route, 'page.tsx')), true, `missing route: ${route}`);
  }
  const sidebar = read('src/components/layout/Sidebar.tsx');
  for (const route of routes) assert.match(sidebar, new RegExp(`/${route}`));
});

test('candidate and event route adapters sanitize bounded scalar query values', () => {
  const analysis = read('src/app/(dashboard)/analysis/page.tsx');
  const signals = read('src/app/(dashboard)/signals/page.tsx');
  const calendar = read('src/app/(dashboard)/calendar/page.tsx');
  for (const source of [analysis, signals, calendar]) {
    assert.match(source, /await searchParams/);
    assert.match(source, /Array\.isArray/);
    assert.match(source, /length <= (?:200|maxLength)/);
  }
  assert.match(analysis, /allowedTimeframes/);
  assert.match(signals, /initialCandidateId/);
  assert.match(calendar, /initialEventId/);
});

test('authentication round-trip preserves internal deep-link identity safely', () => {
  const proxy = read('src/proxy.ts');
  const login = read('src/app/login/page.tsx');
  assert.match(proxy, /pathname \+ \(request\.nextUrl\.search \|\| ""\)/);
  assert.match(login, /new URLSearchParams\(window\.location\.search\)/);
  assert.match(login, /requested\?\.startsWith\("\/"\)/);
  assert.match(login, /!requested\.startsWith\("\/\/"\)/);
});

test('analysis binds risk decision to the exact selected candidate and fails closed', () => {
  const screen = read('src/features/analysis/MarketAnalysisScreen.tsx');
  assert.match(screen, /riskDecisions\.find\(\(decision\) => decision\.candidate_id === selectedCandidateId\)/);
  assert.doesNotMatch(screen, /setRiskDecision\(parsed\[0\]\)/);
  assert.match(screen, /killSwitch\?\.state !== 'INACTIVE'/);
  assert.match(screen, /!riskDecision/);
  assert.match(screen, /evaluatedCandidateId !== selectedCandidateId/);
});

test('signals and calendar validate requested identities against authoritative data', () => {
  const signals = read('src/features/strategy/TradingSignalsScreen.tsx');
  const calendar = read('src/features/news/CalendarWorkspace.tsx');
  assert.match(signals, /currentCandidates\.find\(\(candidate\) => candidate\.id === initialCandidateId\)/);
  assert.match(signals, /historyCandidates\.find\(\(candidate\) => candidate\.id === initialCandidateId\)/);
  assert.match(signals, /ไม่พบ Candidate ที่ระบุในข้อมูล authoritative/);
  assert.match(calendar, /currentCalendarEvents\.some\(\(event\) => event\.id === initialEventId\)/);
  assert.match(calendar, /ไม่พบ Event ที่ระบุในช่วงปฏิทิน authoritative/);
});

test('unknown kill switch is never presented as clear or normal', () => {
  for (const relative of [
    'src/features/analysis/StrategyAnalysisContext.tsx',
    'src/features/strategy/SignalSummaryHeader.tsx',
    'src/features/strategy/SignalDetailPanel.tsx',
  ]) {
    const source = read(relative);
    assert.match(source, /isKillUnknown/);
    assert.match(source, /UNKNOWN/);
  }
  const context = read('src/features/analysis/StrategyAnalysisContext.tsx');
  assert.match(context, /fail-closed/);
  assert.match(context, /NOT EVALUATED/);
});

test('dashboard uses canonical policy and does not fabricate risk or AI verdicts', () => {
  const dashboard = read('src/features/dashboard/Dashboard.tsx');
  assert.match(dashboard, /trade_policy_state \|\| 'UNAVAILABLE'/);
  assert.match(dashboard, /decision\.candidate_id === plan\.candidate_id/);
  assert.match(dashboard, /NOT EVALUATED ON DASHBOARD/);
  assert.match(dashboard, /href="\/journal"/);
  assert.doesNotMatch(dashboard, /APPROVED \(Risk Gate Passed\)/);
  assert.doesNotMatch(dashboard, /6 \/ 6 Agents Ready/);
  assert.doesNotMatch(dashboard, /href="\/reports"/);
});

test('outbound source links preserve encoded candidate, event, symbol, and timeframe identity', () => {
  const sources = [
    read('src/features/dashboard/Dashboard.tsx'),
    read('src/features/overview/MarketOverviewScreen.tsx'),
    read('src/features/strategy/SignalDetailPanel.tsx'),
    read('src/features/strategy/EvaluationsTab.tsx'),
    read('src/features/reports/ReportsScreen.tsx'),
  ].join('\n');
  assert.match(sources, /\/signals\?candidate=\$\{encodeURIComponent/);
  assert.match(sources, /\/analysis\?candidate=\$\{encodeURIComponent/);
  assert.match(sources, /\/calendar\?event=\$\{encodeURIComponent/);
  assert.match(sources, /symbol=\$\{encodeURIComponent\(symbol\)\}/);
  assert.match(sources, /timeframe=\$\{encodeURIComponent\(timeframe\)\}/);
});

test('local display preferences are consumed by shell and both chart workspaces', () => {
  const contracts = read('src/features/settings/contracts.ts');
  const settings = read('src/features/settings/SettingsCenter.tsx');
  const shell = read('src/components/layout/AppShell.tsx');
  const market = read('src/features/overview/MarketOverviewScreen.tsx');
  const analysis = read('src/features/analysis/MarketAnalysisScreen.tsx');
  assert.match(contracts, /UI_PREFERENCES_KEY/);
  assert.match(settings, /ui-preferences:changed/);
  assert.match(shell, /data-density/);
  assert.match(shell, /preferences\.timezone/);
  assert.match(market, /default_timeframe/);
  assert.match(analysis, /default_timeframe/);
});
