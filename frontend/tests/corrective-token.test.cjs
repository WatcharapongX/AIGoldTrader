const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

const NOW = Date.UTC(2029, 0, 1);
class FixedDate extends Date { static now() { return NOW; } }
const valid = {
  access_token: 'fixture-access',
  token_type: 'bearer', expires_at: '2029-01-01T00:01:00.123456Z',
};
const cases = [
  ['empty access', { ...valid, access_token: '' }],
  ['whitespace access', { ...valid, access_token: ' \t\n' }],
  ['Basic type', { ...valid, token_type: 'Basic' }],
  ['case variant type', { ...valid, token_type: 'Bearer' }],
  ['arbitrary type', { ...valid, token_type: 'other' }],
  ['malformed expiry', { ...valid, expires_at: 'not-a-date' }],
  ['numeric-like expiry', { ...valid, expires_at: '1' }],
  ['expired', { ...valid, expires_at: '2028-01-01T00:00:00Z' }],
  ['exactly now', { ...valid, expires_at: '2029-01-01T00:00:00Z' }],
  ['one millisecond past', { ...valid, expires_at: '2028-12-31T23:59:59.999Z' }],
  ['invalid calendar', { ...valid, expires_at: '2030-02-30T00:00:00Z' }],
  ['date only', { ...valid, expires_at: '2030-01-01' }],
  ['missing zone', { ...valid, expires_at: '2030-01-01T00:00:00' }],
  ['invalid offset', { ...valid, expires_at: '2030-01-01T00:00:00+24:00' }],
  ['null object', null], ['array object', []],
  ...Object.keys(valid).map(key => ['missing ' + key, Object.fromEntries(Object.entries(valid).filter(([k]) => k !== key))]),
];
function harness(mode, payload) {
  const items = new Map([['unrelated', 'keep']]);
  const sessionItems = new Map();
  const document = { cookie: 'unrelated=keep' };
  const before = { items: JSON.stringify([...items]), cookie: document.cookie };
  const modules = new Map();
  const env = {
    Date: FixedDate, window: { dispatchEvent() {} }, document,
    localStorage: {
      getItem: key => items.get(key) || null, setItem: (key, value) => items.set(key, value),
      removeItem: key => items.delete(key),
    },
    sessionStorage: {
      getItem: key => sessionItems.get(key) || null, setItem: (key, value) => sessionItems.set(key, value),
      removeItem: key => sessionItems.delete(key),
    },
    fetch: async (url, options) => {
      if (url.endsWith('/auth/login') || url.endsWith('/auth/refresh')) {
        return new Response(JSON.stringify(payload), { status: 200 });
      }
      const authHeader = options?.headers instanceof Headers
        ? options.headers.get('Authorization')
        : options?.headers?.Authorization;
      const accepted = authHeader === 'Bearer ' + valid.access_token;
      return new Response(JSON.stringify(accepted ?
        { id: 'fixture-id', email: 'user@example.com', role: 'VIEWER', is_active: true } : {}),
      { status: accepted ? 200 : 401 });
    },
  };
  function load(file) {
    if (modules.has(file)) return modules.get(file);
    const exports = {}; modules.set(file, exports);
    const { outputText } = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src', file), 'utf8'),
      { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } });
    vm.runInNewContext(outputText, { exports, process, Headers, Event, ...env,
      require: name => name.startsWith('@/') ? load(name.slice(2) + '.ts') : require(name),
    }, { filename: file });
    return exports;
  }
  const store = load('stores/auth.ts').useAuthStore;
  return { items, document, before, store, contracts: load('lib/contracts.ts') };
}
for (const [name, payload] of cases) {
  test('reject ' + name + ' atomically in login, refresh and recovery', async () => {
    for (const mode of ['login', 'refresh', 'hydrate']) {
      const h = harness(mode, payload);
      assert.throws(() => h.contracts.parseTokenPair(payload), /Invalid API response contract/);
      if (mode === 'login') {
        assert.equal(await h.store.getState().login('user@example.com', 'fixture-password'), false);
      } else if (mode === 'refresh') {
        await h.store.getState().fetchUser();
      } else {
        await h.store.getState().hydrate();
      }
      assert.equal(h.items.has('access_token'), false, mode + ': no access_token in storage');
      assert.equal(h.items.has('refresh_token'), false, mode + ': no refresh_token in storage');
      assert.equal(h.document.cookie, h.before.cookie, mode + ': cookie unchanged');
      assert.equal(h.store.getState().isAuthenticated, false);
      assert.equal(h.store.getState().user, null);
    }
  });
}
test('valid future bearer responses authenticate in memory and never write to storage', async () => {
  for (const mode of ['login', 'refresh', 'hydrate']) {
    const h = harness(mode, valid);
    if (mode === 'login') assert.equal(await h.store.getState().login('user@example.com', 'fixture-password'), true);
    else if (mode === 'refresh') await h.store.getState().fetchUser();
    else await h.store.getState().hydrate();
    assert.equal(h.items.has('access_token'), false);
    assert.equal(h.items.has('refresh_token'), false);
    assert.equal(h.store.getState().isAuthenticated, true);
  }
});
test('strict timestamp handles offsets, leap days and the acceptance clock', () => {
  const { contracts } = harness('login', valid);
  for (const expiry of ['2029-01-01T07:01:00+07:00', '2028-12-31T19:01:00-05:00', '2032-02-29T00:00:00Z']) {
    assert.equal(contracts.parseTokenPair({ ...valid, expires_at: expiry }).expires_at, expiry);
  }
  for (const expiry of ['2029-02-29T00:00:00Z', '2029-01-01T24:00:00Z', '2029-01-01T00:60:00Z',
    '2029-01-01T00:00:60Z', '0000-01-01T00:00:00Z', '2029-01-01T07:00:00+07:00']) {
    assert.throws(() => contracts.parseTokenPair({ ...valid, expires_at: expiry }));
  }
});
