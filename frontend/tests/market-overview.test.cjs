const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

const cache = new Map();

function load(relative) {
  const full = path.resolve(__dirname, '../src', relative);
  if (cache.has(full)) return cache.get(full);
  const exports = {};
  cache.set(full, exports);
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
      if (n.includes('primitive')) {
        return {
          AnalysisPrimitive: class {
            update() {}
          },
          defaultLayers: {
            Swings: true,
            Labels: true,
            BOS: true,
            CHOCH: true,
            MSS: false,
            Liquidity: true,
            FVG: false,
            OB: false,
            PremiumDiscount: false,
            Sessions: false,
          },
        };
      }
      const resolved = n.startsWith('@/')
        ? path.resolve(__dirname, '../src', n.slice(2))
        : path.resolve(path.dirname(full), n);
      if (n.endsWith('.json')) return JSON.parse(fs.readFileSync(resolved, 'utf8'));
      return load(
        path.relative(
          path.resolve(__dirname, '../src'),
          fs.existsSync(resolved + '.tsx') ? resolved + '.tsx' : resolved + '.ts',
        ),
      );
    },
  });
  return exports;
}

const { MarketOverviewView } = load('features/overview/MarketOverviewScreen.tsx');

const text = (component, props) =>
  renderToStaticMarkup(React.createElement(component, props))
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ');

function defaultProps() {
  const quote = {
    symbol: 'XAUUSD',
    timestamp: '2026-09-09T13:14:51.239Z',
    bid: '4123.45',
    ask: '4123.78',
    volume: '150',
    source: 'mt5_demo_iux',
    mode: 'DEMO',
    spread: '0.33',
    status: 'CONNECTED',
  };
  const provider = {
    source: 'mt5_demo_iux',
    mode: 'DEMO',
    status: 'CONNECTED',
    last_quote: '2026-09-09T13:14:51.239Z',
    server_time: '2026-09-09T13:14:51.239Z',
    stale_after_seconds: 5,
    detail: 'Real market data / DEMO connection',
    subscriptions: 1,
    digits: 2,
    tick_size: '0.01',
  };
  const candles = [
    {
      symbol: 'XAUUSD',
      timeframe: 'M15',
      open_time: '2026-09-09T12:45:00Z',
      open: '4110.00',
      high: '4130.00',
      low: '4105.00',
      close: '4123.45',
      volume: '300',
      bid_close: '4123.45',
      ask_close: '4123.78',
      source: 'mt5_demo_iux',
      is_closed: true,
    },
  ];
  const analysis = {
    symbol: 'XAUUSD',
    timeframe: 'M15',
    source: 'mt5_demo_iux',
    algorithm_version: 'structure-1.0.0',
    config_id: 'cfg_1',
    input_id: 'inp_1',
    window_start: '2026-09-08T00:00:00Z',
    history: { requested: 300, returned: 300, closed: 300, status: 'COMPLETE' },
    as_of: '2026-09-09T13:15:00Z',
    modules: {},
    internal_state: 'BULLISH',
    external_state: 'BULLISH',
    swings: [
      { id: 'sw_1', scope: 'EXTERNAL', kind: 'HIGH', label: 'HH', price: '4130.00', swing_time: '2026-09-09T12:00:00Z', confirmed_at: '2026-09-09T12:15:00Z', confirmation: 'CONFIRMED' },
      { id: 'sw_2', scope: 'EXTERNAL', kind: 'LOW', label: 'HL', price: '4105.00', swing_time: '2026-09-09T11:00:00Z', confirmed_at: '2026-09-09T11:15:00Z', confirmation: 'CONFIRMED' },
    ],
    events: [
      { id: 'ev_1', scope: 'EXTERNAL', kind: 'BOS', direction: 'BULLISH', price: '4125.00', swing_id: 'sw_1', swing_time: '2026-09-09T12:00:00Z', occurred_at: '2026-09-09T12:30:00Z', confirmed_at: '2026-09-09T12:45:00Z', displacement: true, confirmation: 'CONFIRMED' },
    ],
    liquidity: [
      { id: 'lq_1', kind: 'PDH', side: 'HIGH', price: '4150.00', created_at: '2026-09-08T00:00:00Z', confirmed_at: '2026-09-08T00:00:00Z', source_ids: [], status: 'ACTIVE' },
      { id: 'lq_2', kind: 'PDL', side: 'LOW', price: '4090.00', created_at: '2026-09-08T00:00:00Z', confirmed_at: '2026-09-08T00:00:00Z', source_ids: [], status: 'ACTIVE' },
    ],
    zones: [],
    dealing_range: {
      lower_bound: '4090.00',
      equilibrium: '4120.00',
      upper_bound: '4150.00',
      origin_time: '2026-09-08T00:00:00Z',
      confirmed_at: '2026-09-08T00:00:00Z',
      direction: 'BULLISH',
      swing_ids: ['sw_1'],
      location: 'PREMIUM',
      retracement_62: '4112.80',
      retracement_79: '4102.60',
    },
    indicators: {
      ATR: { value: '14.50', minimum_bars_required: 15, status: 'READY' },
      VOLUME_AVERAGE: { value: '450.00', minimum_bars_required: 20, status: 'READY' },
    },
    sessions: [],
    current_sessions: ['LONDON', 'NEW_YORK'],
    regime: 'TRENDING_UP',
    confluence_counts: {},
    generated_at: '2026-09-09T13:15:00Z',
    served_at: '2026-09-09T13:15:00Z',
    cache_age_seconds: 0,
  };
  const mtfContext = {
    symbol: 'XAUUSD',
    source: 'mt5_demo_iux',
    algorithm_version: 'structure-1.0.0',
    bias: 'BULLISH',
    timeframes: [
      { timeframe: 'M5', state: 'BULLISH', history: { requested: 300, returned: 300, closed: 300, status: 'COMPLETE' }, status: 'READY', as_of: null },
      { timeframe: 'M15', state: 'BULLISH', history: { requested: 300, returned: 300, closed: 300, status: 'COMPLETE' }, status: 'READY', as_of: null },
      { timeframe: 'H1', state: 'BULLISH', history: { requested: 300, returned: 300, closed: 300, status: 'COMPLETE' }, status: 'READY', as_of: null },
      { timeframe: 'H4', state: 'BULLISH', history: { requested: 300, returned: 300, closed: 300, status: 'COMPLETE' }, status: 'READY', as_of: null },
      { timeframe: 'D1', state: 'BULLISH', history: { requested: 300, returned: 300, closed: 300, status: 'COMPLETE' }, status: 'READY', as_of: null },
    ],
  };

  return {
    symbol: 'XAUUSD',
    symbols: [{ name: 'XAUUSD', source_available: true, digits: 2 }],
    onSelectSymbol: () => {},
    timeframe: 'M15',
    onSelectTimeframe: () => {},
    quote,
    status: 'CONNECTED',
    provider,
    candles,
    analysis,
    analysisState: 'READY',
    mtfContext,
    systemStatus: null,
    error: '',
    onRetry: () => {},
    layers: {
      Swings: true,
      Labels: true,
      BOS: true,
      CHOCH: true,
      MSS: false,
      Liquidity: true,
      FVG: false,
      OB: false,
      PremiumDiscount: false,
      Sessions: false,
    },
    onToggleLayer: () => {},
    bindChart: () => () => {},
    currentUtc: new Date('2026-09-09T14:30:00Z'),
  };
}

test('MarketOverviewView renders XAUUSD quote, spread, and paper trading invariants', () => {
  const p = defaultProps();
  const t = text(MarketOverviewView, p);
  assert.match(t, /Market Overview/);
  assert.match(t, /4,123.45/); // Bid
  assert.match(t, /4,123.78/); // Ask
  assert.match(t, /0.33/); // Spread
  assert.match(t, /TRADING MODE: PAPER/);
  assert.match(t, /AUTO TRADING: OFF/);
  assert.match(t, /FAIL-CLOSED ACTIVE/);
});

test('truthful market data source labeling for DEMO, REAL, SIMULATED and STALE', () => {
  const p = defaultProps();
  // DEMO broker
  assert.match(text(MarketOverviewView, p), /MT5 DEMO · REAL PRICES/);

  // SIMULATED mode
  p.provider.mode = 'SIMULATED';
  assert.match(text(MarketOverviewView, p), /SIMULATED DATA/);

  // REAL mode
  p.provider.mode = 'LIVE';
  assert.match(text(MarketOverviewView, p), /REAL MARKET DATA/);

  // STALE connection
  p.status = 'STALE';
  assert.match(text(MarketOverviewView, p), /STALE DATA/);

  // DISCONNECTED
  p.status = 'DISCONNECTED';
  assert.match(text(MarketOverviewView, p), /UNAVAILABLE/);
});

test('timeframe selector supports canonical timeframes and truthful W1 partial history', () => {
  const p = defaultProps();
  let t = text(MarketOverviewView, p);
  assert.match(t, /M1/);
  assert.match(t, /M5/);
  assert.match(t, /M15/);
  assert.match(t, /H1/);
  assert.match(t, /H4/);
  assert.match(t, /D1/);
  assert.match(t, /W1/);

  // In M15 with 1 candle, does not claim partial W1 history
  assert.doesNotMatch(t, /PARTIAL HISTORY/);

  // In W1 with 231 candles, truthfully displays partial count without fabricating bars
  p.timeframe = 'W1';
  p.candles = Array.from({ length: 231 }, () => p.candles[0]);
  t = text(MarketOverviewView, p);
  assert.match(t, /PARTIAL HISTORY: 231 \/ 300 bars/);
});

test('market statistics render authoritative OHLC, Day Range, and ATR (14)', () => {
  const p = defaultProps();
  const t = text(MarketOverviewView, p);
  // OHLC
  assert.match(t, /4,110.00/); // Open
  assert.match(t, /4,130.00/); // High
  assert.match(t, /4,105.00/); // Low
  assert.match(t, /4,123.45/); // Close
  // Day Range = 4130 - 4105 = 25.00
  assert.match(t, /25.00 USD/);
  // Authoritative ATR 14
  assert.match(t, /14.50 USD/);
});

test('market structure summary and key levels render authoritative events and nearest distance', () => {
  const p = defaultProps();
  const t = text(MarketOverviewView, p);
  // Regime
  assert.match(t, /แนวโน้มขาขึ้น/);
  // BOS event
  assert.match(t, /BOS ล่าสุด/);
  assert.match(t, /4,125.00/);
  // Liquidity levels
  assert.match(t, /PDH/);
  assert.match(t, /4,150.00/);
  assert.match(t, /PDL/);
  assert.match(t, /4,090.00/);
  // Distance to nearest level: PDH is at 4150.00, bid is 4123.45 -> diff = +26.55
  assert.match(t, /PDH \(\+26.55 USD\)/);
  // Dealing Range
  assert.match(t, /PREMIUM/);
});

test('global sessions strip renders all four sessions and highlights overlap', () => {
  const p = defaultProps();
  const t = text(MarketOverviewView, p);
  assert.match(t, /Asian Session/);
  assert.match(t, /European Session/);
  assert.match(t, /US Session/);
  assert.match(t, /London \/ NY Overlap/);
  assert.match(t, /US Dollar Index \(DXY\)/);
  assert.match(t, /US 10Y Yield/);
});
