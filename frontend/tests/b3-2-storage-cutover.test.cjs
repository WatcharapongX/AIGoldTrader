const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadModule(file, overrides = {}, mocks = {}) {
  const modules = overrides.modules || (overrides.modules = new Map());
  function loadInternal(relPath) {
    if (modules.has(relPath)) return modules.get(relPath);
    const fullPath = path.join(__dirname, '../src', relPath);
    const source = fs.readFileSync(fullPath, 'utf8');
    const { outputText } = ts.transpileModule(source, {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.React },
    });
    const exports = {};
    modules.set(relPath, exports);
    const context = {
      exports,
      require: (name) => {
        if (mocks[name]) return mocks[name];
        if (name.startsWith('@/')) {
          const target = name.slice(2) + (name.endsWith('.ts') || name.endsWith('.tsx') ? '' : '.ts');
          const finalTarget = fs.existsSync(path.join(__dirname, '../src', target))
            ? target
            : target.replace(/\.ts$/, '.tsx');
          return loadInternal(finalTarget);
        }
        if (name.endsWith('.json')) {
          const dir = path.dirname(relPath);
          const jsonPath = name.startsWith('.') ? path.join(dir, name) : name;
          const raw = require(
            path.join(__dirname, '../src', jsonPath.startsWith('@/') ? jsonPath.slice(2) : jsonPath),
          );
          return { ...raw, default: raw };
        }
        if (name.startsWith('./') || name.startsWith('../')) {
          const dir = path.dirname(relPath);
          const resolved = path.join(dir, name).replace(/\\/g, '/');
          const target = resolved + (resolved.endsWith('.ts') || resolved.endsWith('.tsx') ? '' : '.ts');
          const finalTarget = fs.existsSync(path.join(__dirname, '../src', target))
            ? target
            : target.replace(/\.ts$/, '.tsx');
          return loadInternal(finalTarget);
        }
        if (name === 'react') {
          return {
            useEffect: (cb) => cb(),
            useState: (initial) => [initial, () => {}],
            useMemo: (cb) => cb(),
            useCallback: (cb) => cb,
            useRef: (initial) => ({ current: initial }),
          };
        }
        return require(name);
      },
      process,
      Headers,
      Event,
      setTimeout,
      clearTimeout,
      setInterval,
      clearInterval,
      Date,
      Math,
      JSON,
      Number,
      String,
      Boolean,
      fetch: (...args) => (overrides.fetch ? overrides.fetch(...args) : fetch(...args)),
      ...overrides,
    };
    vm.runInNewContext(outputText, context, { filename: relPath });
    return exports;
  }
  return loadInternal(file);
}

function createStorageTestEnv(initialStorage = {}) {
  const localItems = new Map(Object.entries(initialStorage.localStorage || {}));
  const sessionItems = new Map(Object.entries(initialStorage.sessionStorage || {}));
  const storageOperations = {
    localGet: [],
    localSet: [],
    localRemove: [],
    sessionGet: [],
    sessionSet: [],
    sessionRemove: [],
  };

  const dispatchedEvents = [];
  const networkCalls = [];

  const env = {
    window: {
      location: { hostname: 'localhost', protocol: 'http:' },
      dispatchEvent: (e) => dispatchedEvents.push(e),
    },
    document: { cookie: '' },
    localStorage: {
      getItem: (k) => {
        storageOperations.localGet.push(k);
        return localItems.get(k) || null;
      },
      setItem: (k, v) => {
        storageOperations.localSet.push({ key: k, value: v });
        localItems.set(k, String(v));
      },
      removeItem: (k) => {
        storageOperations.localRemove.push(k);
        localItems.delete(k);
      },
      clear: () => localItems.clear(),
    },
    sessionStorage: {
      getItem: (k) => {
        storageOperations.sessionGet.push(k);
        return sessionItems.get(k) || null;
      },
      setItem: (k, v) => {
        storageOperations.sessionSet.push({ key: k, value: v });
        sessionItems.set(k, String(v));
      },
      removeItem: (k) => {
        storageOperations.sessionRemove.push(k);
        sessionItems.delete(k);
      },
      clear: () => sessionItems.clear(),
    },
    fetch: async (...args) => {
      networkCalls.push(args);
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    },
    storageOperations,
    dispatchedEvents,
    networkCalls,
    modules: new Map(),
  };

  return env;
}

// 1. DIRECT /login APPLICATION ENTRY PURGES LEGACY STORAGE (SECTION 22)
test('direct entry on /login triggers global sanitizer and purges legacy auth storage', () => {
  const env = createStorageTestEnv({
    localStorage: {
      access_token: 'legacy-access-token',
      refresh_token: 'legacy-refresh-token',
      aigold_ui_preferences: '{"theme":"dark"}', // non-auth key should be preserved
    },
    sessionStorage: {
      access_token: 'legacy-session-access',
      refresh_token: 'legacy-session-refresh',
    },
  });

  // Render/execute the global AuthStorageSanitizer component
  const { AuthStorageSanitizer } = loadModule('components/auth/AuthStorageSanitizer.tsx', env);
  const res = AuthStorageSanitizer();
  assert.equal(res, null);

  // Assert all legacy auth tokens are completely removed
  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  assert.equal(env.sessionStorage.getItem('access_token'), null);
  assert.equal(env.sessionStorage.getItem('refresh_token'), null);

  // Invariant: Non-auth keys remain untouched
  assert.equal(env.localStorage.getItem('aigold_ui_preferences'), '{"theme":"dark"}');
});

// 2. NO LEGACY TOKEN READ BEFORE PURGE (SECTION 23)
test('storage sanitizer calls removeItem directly and NEVER reads or decodes legacy token values', () => {
  const env = createStorageTestEnv({
    localStorage: {
      access_token: 'legacy-raw-secret',
      refresh_token: 'legacy-raw-refresh',
    },
    sessionStorage: {
      access_token: 'legacy-session-secret',
      refresh_token: 'legacy-session-refresh',
    },
  });

  const { purgeLegacyAuthStorage } = loadModule('lib/auth-token-memory.ts', env);
  purgeLegacyAuthStorage();

  // removeItem called for access_token and refresh_token
  assert.ok(env.storageOperations.localRemove.includes('access_token'));
  assert.ok(env.storageOperations.localRemove.includes('refresh_token'));
  assert.ok(env.storageOperations.sessionRemove.includes('access_token'));
  assert.ok(env.storageOperations.sessionRemove.includes('refresh_token'));

  // getItem was NEVER called for access_token or refresh_token
  assert.equal(env.storageOperations.localGet.includes('access_token'), false);
  assert.equal(env.storageOperations.localGet.includes('refresh_token'), false);
  assert.equal(env.storageOperations.sessionGet.includes('access_token'), false);
  assert.equal(env.storageOperations.sessionGet.includes('refresh_token'), false);
});

// 3. NO NETWORK TRANSMISSION OR SIDE EFFECTS (SECTION 24)
test('storage sanitizer makes 0 network calls and does not transmit legacy tokens anywhere', () => {
  const env = createStorageTestEnv({
    localStorage: {
      access_token: 'untrusted-residue-access',
      refresh_token: 'untrusted-residue-refresh',
    },
  });

  const { AuthStorageSanitizer } = loadModule('components/auth/AuthStorageSanitizer.tsx', env);
  AuthStorageSanitizer();

  // Exactly 0 network requests
  assert.equal(env.networkCalls.length, 0);
  assert.equal(env.dispatchedEvents.length, 0);
});

// 4. MEMORY TOKEN SAFETY: VOLATILE STATE IS NOT DAMAGED (SECTION 25)
test('storage sanitizer does NOT clear memory token, does not advance session epoch, and leaves coordinator unchanged', () => {
  const env = createStorageTestEnv({
    localStorage: {
      access_token: 'stale-disk-token',
    },
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  // Set current active volatile memory token
  mem.setAccessToken('active-valid-token', '2030-01-01T00:00:00Z');
  const initialEpoch = mem.getSessionEpoch();
  assert.equal(mem.getAccessToken(), 'active-valid-token');

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');

  // Invoke global sanitizer
  const { AuthStorageSanitizer } = loadModule('components/auth/AuthStorageSanitizer.tsx', env);
  AuthStorageSanitizer();

  // Memory access token remains intact
  assert.equal(mem.getAccessToken(), 'active-valid-token');
  // Session epoch remains unchanged
  assert.equal(mem.getSessionEpoch(), initialEpoch);
  // Coordinator status remains unchanged
  assert.equal(coordinator.getState().status, 'idle');

  // But legacy persistent disk storage is purged
  assert.equal(env.localStorage.getItem('access_token'), null);
});

// 5. CLIENT NAVIGATION PRESERVES MEMORY TOKEN (SECTION 11)
test('subsequent client-side navigations invoking sanitizer preserve active memory token and epoch', () => {
  const env = createStorageTestEnv();
  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('authenticated-session-token', '2030-01-01T00:00:00Z');
  const initialEpoch = mem.getSessionEpoch();

  const { AuthStorageSanitizer } = loadModule('components/auth/AuthStorageSanitizer.tsx', env);

  // Simulate multiple client-side route navigations
  AuthStorageSanitizer(); // Navigate to /dashboard
  AuthStorageSanitizer(); // Navigate to /analysis
  AuthStorageSanitizer(); // Navigate to /settings

  assert.equal(mem.getAccessToken(), 'authenticated-session-token');
  assert.equal(mem.getSessionEpoch(), initialEpoch);
});

// 6. PROTECTED BOOTSTRAP REGRESSION WITH LEGACY RESIDUE (SECTION 26)
test('protected bootstrap succeeds with legacy storage seeded; storage purged and memory token installed', async () => {
  const env = createStorageTestEnv({
    localStorage: {
      access_token: 'old-b2-access-token',
      refresh_token: 'old-b2-refresh-token',
    },
  });

  let refreshExecuted = false;
  let meExecuted = false;

  env.fetch = async (url, init) => {
    if (url.endsWith('/auth/refresh')) {
      refreshExecuted = true;
      return new Response(
        JSON.stringify({
          access_token: 'new-b3-memory-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/me')) {
      meExecuted = true;
      assert.equal(init?.headers?.Authorization, 'Bearer new-b3-memory-token');
      return new Response(
        JSON.stringify({
          id: 'u-1',
          email: 'user@mahajak.com',
          role: 'TRADER',
          is_active: true,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response('Not found', { status: 404 });
  };

  // 1. Global app start purges legacy residue
  const { AuthStorageSanitizer } = loadModule('components/auth/AuthStorageSanitizer.tsx', env);
  AuthStorageSanitizer();
  assert.equal(env.localStorage.getItem('access_token'), null);

  // 2. Auth coordinator bootstrap runs
  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  const ok = await coordinator.bootstrap();

  assert.equal(ok, true);
  assert.equal(refreshExecuted, true);
  assert.equal(meExecuted, true);

  const mem = loadModule('lib/auth-token-memory.ts', env);
  assert.equal(mem.getAccessToken(), 'new-b3-memory-token');
  assert.equal(coordinator.getState().status, 'authenticated');
  assert.equal(coordinator.getState().user?.email, 'user@mahajak.com');

  // Invariant: Legacy storage remains empty
  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.localStorage.getItem('refresh_token'), null);
});

// 7. LOGIN REGRESSION WITH LEGACY RESIDUE (SECTION 27)
test('direct /login entry with legacy residue: storage purged, login succeeds, token stored only in memory', async () => {
  const env = createStorageTestEnv({
    localStorage: {
      access_token: 'stale-pre-login-access',
      refresh_token: 'stale-pre-login-refresh',
    },
    sessionStorage: {
      access_token: 'stale-pre-login-session',
    },
  });

  env.fetch = async (url, init) => {
    if (url.endsWith('/auth/login')) {
      const body = JSON.parse(init.body);
      assert.equal(body.email, 'trader@mahajak.com');
      assert.equal(body.password, 'correct-password');
      return new Response(
        JSON.stringify({
          access_token: 'post-login-memory-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/me')) {
      assert.equal(init?.headers?.Authorization, 'Bearer post-login-memory-token');
      return new Response(
        JSON.stringify({
          id: 'u-trader',
          email: 'trader@mahajak.com',
          role: 'TRADER',
          is_active: true,
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response('Not found', { status: 404 });
  };

  // 1. User arrives on /login: global sanitizer executes
  const { AuthStorageSanitizer } = loadModule('components/auth/AuthStorageSanitizer.tsx', env);
  AuthStorageSanitizer();

  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  assert.equal(env.sessionStorage.getItem('access_token'), null);

  // 2. User submits credentials
  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  const tokenData = await coordinator.login('trader@mahajak.com', 'correct-password');

  assert.equal(tokenData.access_token, 'post-login-memory-token');
  assert.equal(coordinator.getState().status, 'authenticated');

  const mem = loadModule('lib/auth-token-memory.ts', env);
  assert.equal(mem.getAccessToken(), 'post-login-memory-token');

  // Invariant: Storage was NOT repopulated with any token
  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  assert.equal(env.sessionStorage.getItem('access_token'), null);
});
