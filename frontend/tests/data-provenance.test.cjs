const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

function loadProvenance() {
  const filename = path.resolve(__dirname, '../src/components/data-provenance.tsx');
  const exports = {};
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX, esModuleInterop: true },
  }).outputText;
  vm.runInNewContext(code, { exports, module: { exports }, require: (name) => name === 'react' || name === 'react/jsx-runtime' ? require(name) : require(name) });
  return exports;
}

const provenance = loadProvenance();

test('global provenance taxonomy never collapses distinct data modes', () => {
  const expected = {
    LIVE: 'REAL MARKET DATA · LIVE',
    DEMO: 'MT5 DEMO · REAL MARKET DATA',
    SIMULATED: 'SIMULATED · NOT LIVE MARKET DATA',
    REPLAY: 'REPLAY · HISTORICAL',
    FIXTURE: 'FIXTURE · TEST DATA',
    PAPER: 'CONFIGURED PAPER',
    DERIVED: 'DERIVED',
    ACTUAL: 'AUTHORITATIVE ANALYSIS',
    'NOT IMPLEMENTED': 'NOT IMPLEMENTED',
  };
  for (const [mode, label] of Object.entries(expected)) assert.equal(provenance.provenanceLabel(mode), label);
  assert.equal(provenance.provenanceLabel(undefined), 'UNAVAILABLE');
  assert.equal(new Set(Object.values(expected)).size, Object.keys(expected).length);
});

test('provenance line renders source, condition, timestamp, and derivation separately', () => {
  const html = renderToStaticMarkup(React.createElement(provenance.DataProvenanceLine, {
    source: 'mt5_demo_iux', mode: 'DEMO', condition: 'STALE', asOf: '2026-09-15T10:00:00Z', derivedFrom: 'M15 closed candles',
  }));
  for (const value of ['MT5 DEMO · REAL MARKET DATA', 'STALE', 'mt5_demo_iux', '2026-09-15T10:00:00Z', 'M15 closed candles']) assert.match(html, new RegExp(value));
});

test('production source has no known provider, account, policy, or AI silent fallback literals', () => {
  const root = path.resolve(__dirname, '../src');
  const files = [];
  const visit = (dir) => {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) visit(full);
      else if (/\.(ts|tsx)$/.test(entry.name)) files.push(full);
    }
  };
  visit(root);
  const source = files.map((file) => fs.readFileSync(file, 'utf8')).join('\n');
  for (const forbidden of [
    "source = 'mock_macro_v1'", "sourceMode = 'FIXTURE'", "model_used || 'fixture-v1'",
    "provider?.source || 'mt5_demo_iux'", "provider?.status || 'CONNECTED'", "'$10,000.00'",
    "riskPolicyState === 'UNAVAILABLE' || !riskPolicy\n                    ? '1%'",
  ]) assert.equal(source.includes(forbidden), false, `forbidden fallback: ${forbidden}`);
});
