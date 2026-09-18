const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(file, overrides = {}, mocks = {}) {
  const modules = new Map();
  function loadInternal(relPath) {
    if (modules.has(relPath)) return modules.get(relPath);
    const fullPath = path.join(__dirname, '../src', relPath);
    const source = fs.readFileSync(fullPath, 'utf8');
    const { outputText } = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    });
    const exports = {};
    modules.set(relPath, exports);
    const context = {
      exports,
      require: name => {
        if (mocks[name]) return mocks[name];
        if (name.startsWith('@/')) {
          const target = name.slice(2) + (name.endsWith('.ts') ? '' : '.ts');
          return loadInternal(target);
        }
        return require(name);
      },
      process,
      Headers,
      Event,
      ...overrides,
    };
    vm.runInNewContext(outputText, context, { filename: relPath });
    return exports;
  }
  return loadInternal(file);
}

function browser() {
  const items = new Map();
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
  assert.equal(env.localStorage.getItem('access_token'), null);
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
  const user = { id: 'u1', email: 'user@example.com', role: 'VIEWER', is_active: true };
  const env = browser();
  env.fetch = async url => {
    if (url.endsWith('/auth/login')) {
      return response(200, { access_token: 'login-token', token_type: 'bearer', expires_at: '2030-01-01T00:00:00Z' });
    }
    if (url.endsWith('/auth/me')) {
      return response(200, user);
    }
    return response(404, {});
  };
  const { useAuthStore } = load('stores/auth.ts', env);
  assert.equal(useAuthStore.getState().isLoading, false);
  assert.equal(await useAuthStore.getState().login('user@example.com', 'test-password'), true);
  assert.equal(useAuthStore.getState().isAuthenticated, true);
  assert.equal(useAuthStore.getState().user.email, user.email);
  assert.equal(env.localStorage.getItem('access_token'), null);
});

test('hydration failure clears the stale cookie and authentication state', async () => {
  const env = browser();
  env.fetch = async () => response(401, {});
  const { useAuthStore } = load('stores/auth.ts', env);
  await useAuthStore.getState().hydrate();
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

test('hydrate unconditionally purges legacy access_token and refresh_token from browser storage without reading it', async () => {
  const env = browser();
  env.localStorage.setItem('refresh_token', 'legacy-secret-token');
  env.localStorage.setItem('access_token', 'legacy-access');
  env.sessionStorage.setItem('access_token', 'legacy-session-access');
  env.sessionStorage.setItem('refresh_token', 'legacy-session-refresh');
  const requestedUrls = [];
  env.fetch = async (url, options) => {
    requestedUrls.push({ url, options });
    if (url.endsWith('/auth/refresh')) {
      return response(200, { access_token: 'fresh-access', token_type: 'bearer', expires_at: '2030-01-01T00:00:00Z' });
    }
    return response(200, { id: 'u1', email: 'user@example.com', role: 'VIEWER', is_active: true });
  };
  const { useAuthStore } = load('stores/auth.ts', env);
  await useAuthStore.getState().hydrate();
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.sessionStorage.getItem('refresh_token'), null);
  assert.equal(env.sessionStorage.getItem('access_token'), null);
  // Verify legacy values were never sent in any request
  assert.equal(JSON.stringify(requestedUrls).includes('legacy-secret-token'), false);
  assert.equal(JSON.stringify(requestedUrls).includes('legacy-access'), false);
  assert.equal(useAuthStore.getState().isAuthenticated, true);
});

test('hydrate purges legacy tokens even when refresh cookie fails', async () => {
  const env = browser();
  env.localStorage.setItem('access_token', 'orphan-access');
  env.localStorage.setItem('refresh_token', 'orphan-refresh');
  env.fetch = async () => response(401, {});
  const { useAuthStore } = load('stores/auth.ts', env);
  await useAuthStore.getState().hydrate();
  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  assert.equal(useAuthStore.getState().isAuthenticated, false);
});

test('clearSession purges access_token and legacy refresh_token defense-in-depth', () => {
  const env = browser();
  env.localStorage.setItem('access_token', 'active-access');
  env.localStorage.setItem('refresh_token', 'stale-refresh');
  env.sessionStorage.setItem('access_token', 'active-session');
  env.sessionStorage.setItem('refresh_token', 'stale-session');
  const { clearSession } = load('lib/api.ts', env);
  clearSession();
  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  assert.equal(env.sessionStorage.getItem('access_token'), null);
  assert.equal(env.sessionStorage.getItem('refresh_token'), null);
});
