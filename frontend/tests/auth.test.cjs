const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(file, overrides = {}, mocks = {}) {
  const source = fs.readFileSync(path.join(__dirname, '../src', file), 'utf8');
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
  });
  const exports = {};
  const context = { exports, require: name => mocks[name] || (name === '@/lib/contracts' ? load('lib/contracts.ts') : require(name)), process,
    Headers, Event, ...overrides };
  vm.runInNewContext(outputText, context, { filename: file });
  return exports;
}
function browser() {
  const items = new Map([['access_token', 'old']]);
  const sessionItems = new Map();
  return {
    window: { dispatchEvent() {} },
    document: { cookie: '' },
    localStorage: {
      getItem: key => items.get(key) || null,
      setItem: (key, value) => items.set(key, value),
      removeItem: key => items.delete(key),
    },
    sessionStorage: {
      getItem: key => sessionItems.get(key) || null,
      setItem: (key, value) => sessionItems.set(key, value),
      removeItem: key => sessionItems.delete(key),
    },
  };
}
const response = (status, data) => new Response(JSON.stringify(data), { status });

test('simultaneous 401 requests rotate once and retry with the new token', async () => {
  const env = browser();
  let refreshes = 0;
  env.fetch = async (url, options) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++;
      await new Promise(resolve => setImmediate(resolve));
      return response(200, { access_token: 'new', token_type: 'bearer', expires_at: '2030-01-01T00:00:00Z' });
    }
    return options.headers.get('Authorization') === 'Bearer new'
      ? response(200, { ok: true }) : response(401, {});
  };
  const { ApiClient } = load('lib/api.ts', env);
  const api = new ApiClient('http://test/api');
  const values = await Promise.all([api.get('/auth/me'), api.get('/auth/me')]);
  assert.equal(values.every(v => v.ok), true);
  assert.equal(refreshes, 1);
  assert.equal(env.localStorage.getItem('access_token'), 'new');
});

test('failed refresh rejects every waiter and clears session', { timeout: 2000 }, async () => {
  const env = browser();
  env.fetch = async url => {
    if (url.endsWith('/auth/refresh')) await new Promise(resolve => setImmediate(resolve));
    return response(401, {});
  };
  const { ApiClient } = load('lib/api.ts', env);
  const api = new ApiClient('http://test/api');
  const values = await Promise.allSettled([api.get('/auth/me'), api.get('/auth/me')]);
  assert.equal(values.every(v => v.status === 'rejected'), true);
  assert.equal(env.localStorage.getItem('access_token'), null);
});

test('bad login does not refresh an unrelated stored session', async () => {
  const env = browser();
  const urls = [];
  env.fetch = async url => { urls.push(url); return response(401, {}); };
  const { ApiClient } = load('lib/api.ts', env);
  await assert.rejects(new ApiClient('http://test/api').login('user@example.com', 'bad'));
  assert.equal(urls.length, 1);
});

test('login starts enabled and successful login loads the authenticated profile', async () => {
  const user = { email: 'user@example.com', role: 'VIEWER' };
  const api = { login: async () => {}, getMe: async () => user };
  const { useAuthStore } = load('stores/auth.ts', browser(), { '@/lib/api': { api } });
  assert.equal(useAuthStore.getState().isLoading, false);
  assert.equal(await useAuthStore.getState().login('user@example.com', 'test-password'), true);
  assert.equal(useAuthStore.getState().isAuthenticated, true);
  assert.equal(useAuthStore.getState().user, user);
});

test('hydration failure clears the stale cookie and authentication state', async () => {
  let cleared = false;
  const { useAuthStore } = load('stores/auth.ts', browser(), {
    '@/lib/api': { api: { getMe: async () => { throw Error('expired'); } },
      clearSession: () => { cleared = true; } },
  });
  await useAuthStore.getState().hydrate();
  assert.equal(cleared, true);
  assert.equal(useAuthStore.getState().isAuthenticated, false);
  assert.equal(useAuthStore.getState().isLoading, false);
});

test('proxy permits login recovery with stale cookies and protects dashboard', () => {
  const { proxy } = load('proxy.ts', { URL }, {
    'next/server': { NextResponse: { next: () => 'next', redirect: url => url } },
  });
  const request = (pathname, token, search = '') => ({ nextUrl: { pathname, search }, url: `http://localhost${pathname}${search}`,
    cookies: { get: () => token ? { value: token } : undefined }, headers: new Headers() });
  assert.equal(proxy(request('/login', 'expired')), 'next');
  assert.equal(proxy(request('/dashboard')).pathname, '/login');
  assert.equal(proxy(request('/signals', undefined, '?candidate=candidate-1')).searchParams.get('redirect'), '/signals?candidate=candidate-1');
});

test('proxy exposes only the named login illustration without opening protected assets', () => {
  const { proxy } = load('proxy.ts', { URL }, {
    'next/server': { NextResponse: { next: () => 'next', redirect: url => url } },
  });
  const request = pathname => ({ nextUrl: { pathname }, url: 'http://localhost' + pathname,
    cookies: { get: () => undefined }, headers: new Headers() });
  assert.equal(proxy(request('/images/login-bg.jpg')), 'next');
  for (const pathname of ['/images/login-bg.jpg/private', '/images/private.jpg', '/dashboard']) {
    const redirect = proxy(request(pathname));
    assert.equal(redirect.pathname, '/login');
    assert.equal(redirect.searchParams.get('redirect'), pathname);
  }
});

test('hydrate unconditionally purges legacy refresh_token from browser storage without reading it', async () => {
  const env = browser();
  env.localStorage.setItem('refresh_token', 'legacy-secret-token');
  env.localStorage.setItem('access_token', 'valid-access');
  const requestedUrls = [];
  env.fetch = async (url, options) => {
    requestedUrls.push({ url, options });
    return response(200, { id: 'u1', email: 'user@example.com', role: 'VIEWER', is_active: true });
  };
  const { useAuthStore } = load('stores/auth.ts', env, {
    '@/lib/api': load('lib/api.ts', env),
  });
  await useAuthStore.getState().hydrate();
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  // Verify legacy value was never sent in any request
  assert.equal(JSON.stringify(requestedUrls).includes('legacy-secret-token'), false);
  assert.equal(useAuthStore.getState().isAuthenticated, true);
});

test('hydrate purges legacy refresh_token even when access_token is completely absent', async () => {
  const env = browser();
  env.localStorage.removeItem('access_token');
  env.localStorage.setItem('refresh_token', 'legacy-orphan-token');
  const { useAuthStore } = load('stores/auth.ts', env, {
    '@/lib/api': load('lib/api.ts', env),
  });
  await useAuthStore.getState().hydrate();
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  assert.equal(useAuthStore.getState().isAuthenticated, false);
});

test('clearSession purges access_token and legacy refresh_token defense-in-depth', () => {
  const env = browser();
  env.localStorage.setItem('access_token', 'active-access');
  env.localStorage.setItem('refresh_token', 'stale-refresh');
  const { clearSession } = load('lib/api.ts', env);
  clearSession();
  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.localStorage.getItem('refresh_token'), null);
});
