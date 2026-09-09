const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function load(file) {
  const exports = {};
  const source = fs.readFileSync(path.join(__dirname, '../src/features/analysis', file), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true,
  }}).outputText;
  vm.runInNewContext(output, { exports, Date, Number, Set, require: name =>
    name.endsWith('.json') ? require('../src/features/analysis/analysis-contract.generated.json') : require(name) });
  return exports;
}
const parser = load('contracts.ts'), drawing = load('primitive.ts');
const fixture = require('./fixtures/analysis.json');
test('backend snapshot is accepted with partial history and confirmed metadata', () => {
  assert.equal(parser.parseAnalysis(fixture).history.status, 'PARTIAL');
});
for (const [name, mutate] of [
  ['unknown field', v => { v.signal = 'BUY'; }],
  ['non-finite price', v => { v.swings[0].price = 'NaN'; }],
  ['overflow price', v => { v.swings[0].price = '1e999'; }],
  ['missing timezone', v => { v.swings[0].confirmed_at = '2026-08-03T00:03:00'; }],
  ['bad calendar', v => { v.as_of = '2026-02-30T00:00:00Z'; }],
  ['future confirmation', v => { v.swings[0].confirmed_at = '2099-01-01T00:00:00Z'; }],
  ['early confirmation', v => { v.swings[0].confirmed_at = '2000-01-01T00:00:00Z'; }],
  ['duplicate ID', v => { v.swings.push(v.swings[0]); }],
  ['oversized objects', v => { v.swings = Array(257).fill(v.swings[0]); }],
  ['invalid zone', v => { v.zones[0].upper_bound = v.zones[0].lower_bound; }],
  ['invalid count', v => { v.history.closed = 999; }],
  ['false complete status', v => { v.history.status = 'COMPLETE'; }],
  ['forming pivot', v => { v.swings[0].confirmation = 'FORMING'; }],
]) test('reject ' + name, () => {
  const value = structuredClone(fixture); mutate(value);
  assert.throws(() => parser.parseAnalysis(value), /Invalid analysis contract/);
});
test('layer filtering is bounded, geometry references exact pivot/zone prices', () => {
  const all = Object.fromEntries(Object.keys(drawing.defaultLayers).map(k => [k, true]));
  const none = Object.fromEntries(Object.keys(all).map(k => [k, false]));
  assert.equal(drawing.shapes(fixture, none).length, 0);
  const shapes = drawing.shapes(fixture, all);
  assert.ok(shapes.length > 0 && shapes.length <= 143);
  const pivot = fixture.swings.find(s => s.scope === 'EXTERNAL');
  assert.ok(shapes.some(s => s.kind === 'point' && s.time === pivot.swing_time && s.price === Number(pivot.price)));
  const zone = fixture.zones[0];
  assert.ok(shapes.some(s => s.kind === 'zone' && s.time === zone.confirmed_at &&
    s.price === Number(zone.lower_bound) && s.upper === Number(zone.upper_bound)));
  assert.equal(drawing.shapes(null, all).length, 0);
});
test('primitive redraw and detach lifecycle has no retained chart references', () => {
  const primitive = new drawing.AnalysisPrimitive();
  let redraws = 0;
  primitive.attached({ requestUpdate: () => redraws++ });
  primitive.update(fixture, drawing.defaultLayers);
  assert.equal(redraws, 2);
  primitive.detached();
  primitive.update(null, drawing.defaultLayers);
  assert.equal(redraws, 2);
  assert.equal(primitive.paneViews().length, 1);
});
test('context requires every unique timeframe', () => {
  const context = { symbol: fixture.symbol, source: fixture.source, algorithm_version: fixture.algorithm_version,
    bias:'MIXED', timeframes: ['M1','M3','M5','M15','M30','H1','H4','D1','W1'].map(timeframe => ({
      timeframe,state:'UNKNOWN',history:fixture.history,status:'PARTIAL_HISTORY',as_of:fixture.as_of,
    })) };
  assert.equal(parser.parseContext(context).timeframes.length, 9);
  context.timeframes[0].timeframe = 'W1';
  assert.throws(() => parser.parseContext(context));
});
