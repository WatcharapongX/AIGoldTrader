const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadContracts() {
  const filename = path.resolve(__dirname, '../src/features/settings/contracts.ts');
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  vm.runInNewContext(code, { exports, module: { exports }, require });
  return exports;
}

const contracts = loadContracts();
const screen = fs.readFileSync(path.resolve(__dirname, '../src/features/settings/SettingsCenter.tsx'), 'utf8');

function validConfiguration() {
  return {
    as_of:'2026-09-16T00:00:00Z', authority:'SERVER_CONFIGURATION', restart_required:true,
    trading:{mode:'PAPER',live_auto_trading:false,broker_execution:'NONE',account_provenance:'CONFIGURED_PAPER'},
    market:{provider:'mt5',account_mode:'DEMO',configured_symbol:'XAUUSD',server_timezone:'UTC',poll_seconds:1,stale_after_seconds:5,archive_real_ticks:false,terminal:'CONFIGURED',account_validation:'CONFIGURED',server_validation:'CONFIGURED',provenance:'DEMO'},
    news:{provider:'fixture',poll_seconds:60,stale_after_seconds:300,provenance:'FIXTURE'},
    ai:{mode:'external',provider_type:'openai_compatible',credential:'MISSING',endpoint:'DEFAULT_PROVIDER',model_mapping:{'fast-advisory':'model-1'},max_concurrent_provider_calls:6,queue_timeout_seconds:15,provenance:'EXTERNAL'},
    infrastructure:{environment:'DEV',redis_enabled:false}, session:{access_token_minutes:30,refresh_session_days:7},
  };
}

test('safe configuration parser preserves distinct truthful modes', () => {
  const parsed = contracts.parseSafeConfiguration(validConfiguration());
  assert.equal(parsed.trading.mode, 'PAPER');
  assert.equal(parsed.market.account_mode, 'DEMO');
  assert.equal(parsed.market.provenance, 'DEMO');
  assert.equal(parsed.news.provenance, 'FIXTURE');
  assert.equal(parsed.ai.credential, 'MISSING');
  assert.equal(parsed.trading.broker_execution, 'NONE');
});

test('safe configuration parser rejects unexpected fields and fake null defaults', () => {
  const leaked = validConfiguration();
  leaked.ai.raw_credential = 'must-not-cross-boundary';
  assert.throws(() => contracts.parseSafeConfiguration(leaked), contracts.SettingsContractError);
  const missing = validConfiguration();
  missing.trading.mode = null;
  assert.throws(() => contracts.parseSafeConfiguration(missing), contracts.SettingsContractError);
});

test('local UI preferences accept only cosmetic allow-listed values', () => {
  const safe = contracts.parseUiPreferences({language:'th',timezone:'UTC',density:'compact',default_timeframe:'H1'});
  assert.equal(safe.timezone, 'UTC');
  const rejected = contracts.parseUiPreferences({language:'th',timezone:'UTC',density:'compact',default_timeframe:'H1',trading_mode:'LIVE'});
  assert.deepEqual(JSON.parse(JSON.stringify(rejected)), JSON.parse(JSON.stringify(contracts.DEFAULT_UI_PREFERENCES)));
  const invalid = contracts.parseUiPreferences({language:'th',timezone:'Mars/Base',density:'compact',default_timeframe:'H1'});
  assert.equal(invalid.timezone, 'Asia/Bangkok');
});

test('Settings loads authoritative read APIs independently and exposes refresh', () => {
  for (const endpoint of ['/configuration/safe','/system/status','/market/status','/news/provider/status','/risk/policy','/strategies','/trader-profiles','/risk/kill-switch']) {
    assert.match(screen, new RegExp(endpoint.replace(/[/?*+]/g, '\\$&')));
  }
  assert.match(screen, /Promise\.allSettled/);
  assert.match(screen, /Refresh Configuration Status/);
  assert.match(screen, /CONFIGURATION STATUS UNAVAILABLE/);
  assert.match(screen, /ไม่มีการแทนค่าด้วยค่าเริ่มต้น/);
});

test('Settings has all governed sections and no server mutation UX', () => {
  for (const label of ['General','Trading & Safety','Market Data','News / Macro','AI Provider','Strategies','Risk Policy','System & Infrastructure','Security / Session','Data Provenance']) assert.match(screen, new RegExp(label));
  for (const forbidden of ["api.post('/configuration", "api.put('/configuration", "api.patch('/configuration", 'Factory Reset', 'Enable Execution', 'Send Test Order']) assert.equal(screen.includes(forbidden), false);
  assert.match(screen, /READ ONLY/);
  assert.match(screen, /SERVER MANAGED/);
  assert.match(screen, /RESTART REQUIRED/);
  assert.match(screen, /LOCAL PREFERENCE/);
});

test('Settings source contains no forbidden secret fields or raw endpoint display', () => {
  const sources = screen + fs.readFileSync(path.resolve(__dirname, '../src/features/settings/contracts.ts'), 'utf8');
  for (const forbidden of ['SECRET_KEY','DATABASE_URL','POSTGRES_PASSWORD','AI_PROVIDER_API_KEY','MT5_EXPECTED_LOGIN','MT5_TERMINAL_PATH']) assert.equal(sources.includes(forbidden), false);
  assert.doesNotMatch(sources, /ai_provider_base_url|database_connection_url|postgres_password/);
});

test('Settings route replaces the Phase 10 placeholder', () => {
  const route = fs.readFileSync(path.resolve(__dirname, '../src/app/(dashboard)/settings/page.tsx'), 'utf8');
  assert.match(route, /SettingsCenter/);
  assert.doesNotMatch(route, /Coming in Phase 10/);
});
