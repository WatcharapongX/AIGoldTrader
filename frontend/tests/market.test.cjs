const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(file, overrides = {}) {
  const exports = {};
  const source = fs.readFileSync(path.join(__dirname, '../src/features/chart', file), 'utf8');
  const output = ts.transpileModule(source, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true,
  } }).outputText;
  vm.runInNewContext(output, { exports, process, Date, BigInt, setTimeout, clearTimeout, setInterval, clearInterval,
    require: name => name === './contracts' ? load('contracts.ts') :
      name === '@/lib/auth-coordinator' ? { getValidAccessToken: async () => 'fixture' } :
      name === '@/lib/api' ? { clearSession: () => {} } :
      name.endsWith('.json') ? require('../src/features/chart/market-contract.generated.json') : require(name),
    ...overrides,
  });
  return exports;
}
const parsers = load('contracts.ts');
const status = { source: 'simulated', mode: 'SIMULATED', status: 'CONNECTED', last_quote: '2026-09-09T12:00:00Z',
  server_time: '2026-09-09T12:00:00Z', stale_after_seconds: 5, detail: 'Replay', subscriptions: 1 };
const candle = { symbol: 'XAUUSD', timeframe: 'M5', open_time: '2026-09-09T12:00:00Z',
  open: '2350', high: '2352', low: '2349', close: '2351', volume: '10', bid_close: '2351',
  ask_close: '2351.30', source: 'simulated', is_closed: false };
const quote = { symbol: 'XAUUSD', timestamp: '2026-09-09T12:00:00Z', bid: '2351', ask: '2351.30',
  spread: '0.30', volume: '1', source: 'simulated', status: 'CONNECTED' };
const message = { type: 'update', symbol: 'XAUUSD', timeframe: 'M5', sequence: 1, quote,
  candles: [candle], status, error: null };

test('canonical WS and historical payload accepted', () => {
  assert.equal(parsers.parseMessage(message).quote.spread, '0.30');
  assert.equal(parsers.parseCandles({ candles: [candle], next_cursor: null }).candles.length, 1);
});
const invalid = [
  ['negative volume', m => { m.quote.volume = '-1'; }],
  ['wrong source', m => { m.quote.source = 'live'; }],
  ['ask below bid', m => { m.quote.ask = '1'; }],
  ['wrong spread', m => { m.quote.spread = '0.31'; }],
  ['non-finite price', m => { m.quote.bid = 'NaN'; }],
  ['numeric price', m => { m.quote.bid = 2351; }],
  ['negative price', m => { m.quote.bid = '-1'; }],
  ['invalid calendar', m => { m.quote.timestamp = '2026-02-30T12:00:00Z'; }],
  ['missing timezone', m => { m.quote.timestamp = '2026-09-09T12:00:00'; }],
  ['invalid OHLC', m => { m.candles[0].high = '1'; }],
  ['wrong bucket', m => { m.candles[0].open_time = '2026-09-09T12:01:00Z'; }],
  ['mismatched symbol', m => { m.candles[0].symbol = 'EURUSD'; }],
  ['mismatched timeframe', m => { m.candles[0].timeframe = 'M1'; }],
  ['duplicate candle', m => { m.candles.push({ ...m.candles[0] }); }],
  ['unknown message', m => { m.type = 'signal'; }],
  ['missing status', m => { delete m.status; }],
];
for (const [name, mutate] of invalid) test('reject ' + name, () => {
  const copy = structuredClone(message); mutate(copy);
  assert.throws(() => parsers.parseMessage(copy), /Invalid market data contract/);
});
test('UTC weekly Monday boundary enforced', () => {
  const weekly = { ...candle, timeframe: 'W1', open_time: '2026-09-07T00:00:00Z' };
  assert.equal(parsers.parseCandles({ candles: [weekly], next_cursor: null }).candles.length, 1);
  assert.throws(() => parsers.parseCandles({ candles: [{ ...weekly, open_time: '2026-09-06T00:00:00Z' }], next_cursor: null }));
});
test('transport authenticates in frame, handles duplicates, bounds retries and clears timers', async t => {
  const sockets = [], timers = new Map(), intervals = new Map(), states = [], received = [];
  let nextId = 0;
  class Socket {
    constructor(url) { this.url = url; this.sent = []; sockets.push(this); }
    send(value) { this.sent.push(JSON.parse(value)); }
    close(code = 1006) { this.onclose?.({ code }); }
  }
  const { MarketConnection, reconnectDelay } = load('transport.ts', {
    WebSocket: Socket,
    setTimeout: (fn, delay) => { timers.set(++nextId, { fn, delay }); return nextId; },
    clearTimeout: id => timers.delete(id),
    setInterval: fn => { intervals.set(++nextId, fn); return nextId; },
    clearInterval: id => intervals.delete(id),
  });
  const connection = new MarketConnection(async () => 'private-fixture', m => received.push(m), s => states.push(s), 'XAUUSD', 'M5', 'ws://localhost/ws/market');
  t.after(() => connection.stop());
  connection.start(); await new Promise(setImmediate);
  sockets[0].onopen();
  assert.equal(sockets[0].url, 'ws://localhost/ws/market');
  assert.equal(sockets[0].sent[0].type, 'auth');
  assert.equal(sockets[0].sent[0].token, 'private-fixture');
  sockets[0].onmessage({ data: JSON.stringify(message) });
  sockets[0].onmessage({ data: JSON.stringify(message) });
  assert.equal(received.length, 1);
  sockets[0].close();
  assert.equal([...timers.values()][0].delay, 1000);
  for (let i = 0; i < 10; i++) {
    const item = [...timers.entries()][0];
    if (!item) break;
    timers.delete(item[0]); item[1].fn(); await new Promise(setImmediate);
    sockets.at(-1).close();
  }
  assert.equal(states.at(-1), 'DISCONNECTED');
  assert.equal(reconnectDelay(20), 30000);
  connection.stop();
  assert.equal(timers.size, 0); assert.equal(intervals.size, 0);
});
test('malformed WS response enters ERROR and stops reconnection', async t => {
  const sockets = [];
  let state;
  class Socket { constructor() { sockets.push(this); } close(code) { this.onclose?.({ code }); } }
  const { MarketConnection } = load('transport.ts', { WebSocket: Socket });
  const connection = new MarketConnection(async () => 'fixture', () => assert.fail('Invalid data delivered'), s => { state = s; }, 'XAUUSD', 'M5');
  t.after(() => connection.stop());
  connection.start(); await new Promise(setImmediate);
  sockets[0].onmessage({ data: '{"type":"unknown"}' });
  assert.equal(state, 'ERROR');
  connection.stop();
});

test('real source labels require verified mode and never label replay as real', () => {
  assert.equal(parsers.providerLabel(null), 'DATA SOURCE UNCONFIRMED');
  assert.equal(parsers.providerLabel(status), 'SIMULATED DATA');
  for (const mode of ['DEMO', 'LIVE']) {
    const real = { ...status, source: 'mt5_' + mode.toLowerCase() + '_fixture', mode, digits: 3, tick_size: '0.001' };
    assert.equal(parsers.parseStatus(real).mode, mode);
    assert.equal(parsers.providerLabel(real), 'REAL MARKET DATA / ' + mode + ' CONNECTION');
  }
  assert.throws(() => parsers.parseStatus({ ...status, mode: 'LIVE' }));
  assert.throws(() => parsers.parseStatus({ ...status, source: 'mt5_demo_fixture', mode: 'LIVE' }));
});
test('unknown historical ask accepted but mixed sources rejected', () => {
  const real = { ...candle, source: 'mt5_demo_fixture', ask_close: null };
  assert.equal(parsers.parseCandles({ candles: [real], next_cursor: null }).candles[0].ask_close, null);
  assert.throws(() => parsers.parseCandles({ candles: [real, { ...candle, open_time: '2026-09-09T12:05:00Z' }], next_cursor: null }));
  assert.throws(() => parsers.parseMessage({ ...message, candles: [real] }));
  assert.throws(() => parsers.parseMessage({ ...message, quote: { ...quote, source: 'mt5_demo_fixture' } }));
});
