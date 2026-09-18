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
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 },
    });
    const exports = {};
    modules.set(relPath, exports);
    const context = {
      exports,
      require: (name) => {
        if (mocks[name]) return mocks[name];
        if (name.startsWith('@/')) {
          const target = name.slice(2) + (name.endsWith('.ts') ? '' : '.ts');
          return loadInternal(target);
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
          const target = resolved + (resolved.endsWith('.ts') ? '' : '.ts');
          return loadInternal(target);
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

function createBrowserEnv() {
  const localItems = new Map();
  const sessionItems = new Map();
  const channels = new Map();

  class MockBroadcastChannel {
    constructor(name) {
      this.name = name;
      this.onmessage = null;
      if (!channels.has(name)) channels.set(name, new Set());
      channels.get(name).add(this);
    }
    postMessage(data) {
      const set = channels.get(this.name);
      if (set) {
        for (const ch of set) {
          if (ch !== this && typeof ch.onmessage === 'function') {
            queueMicrotask(() => {
              if (typeof ch.onmessage === 'function') {
                ch.onmessage({ data });
              }
            });
          }
        }
      }
    }
    close() {
      const set = channels.get(this.name);
      if (set) set.delete(this);
    }
  }

  const locksHeld = new Set();
  const mockNavigator = {
    locks: {
      async request(name, callback) {
        while (locksHeld.has(name)) {
          await new Promise((r) => setTimeout(r, 10));
        }
        locksHeld.add(name);
        try {
          return await callback();
        } finally {
          locksHeld.delete(name);
        }
      },
    },
  };

  const dispatchedEvents = [];

  const env = {
    window: {
      location: { hostname: 'localhost', protocol: 'http:' },
      dispatchEvent: (e) => dispatchedEvents.push(e),
      BroadcastChannel: MockBroadcastChannel,
    },
    document: { cookie: '' },
    navigator: mockNavigator,
    localStorage: {
      getItem: (k) => localItems.get(k) || null,
      setItem: (k, v) => localItems.set(k, v),
      removeItem: (k) => localItems.delete(k),
      clear: () => localItems.clear(),
    },
    sessionStorage: {
      getItem: (k) => sessionItems.get(k) || null,
      setItem: (k, v) => sessionItems.set(k, v),
      removeItem: (k) => sessionItems.delete(k),
      clear: () => sessionItems.clear(),
    },
    dispatchedEvents,
    BroadcastChannel: MockBroadcastChannel,
    modules: new Map(),
  };

  return env;
}

/**
 * Creates an isolated multi-tab test cluster.
 * Each tab runs with its OWN independent module context (distinct memory tokens and session epoch).
 * Tabs share ONLY the origin-wide simulated HttpOnly cookie, Web Locks (if enabled), and BroadcastChannel bus.
 */
function createMultiTabCluster(options = {}) {
  const channels = new Map();

  class SharedBroadcastChannel {
    constructor(name) {
      this.name = name;
      this.onmessage = null;
      if (!channels.has(name)) channels.set(name, new Set());
      channels.get(name).add(this);
    }
    postMessage(data) {
      const set = channels.get(this.name);
      if (set) {
        for (const ch of set) {
          if (ch !== this && typeof ch.onmessage === 'function') {
            queueMicrotask(() => {
              if (typeof ch.onmessage === 'function') {
                ch.onmessage({ data });
              }
            });
          }
        }
      }
    }
    close() {
      const set = channels.get(this.name);
      if (set) set.delete(this);
    }
  }

  const locksHeld = new Set();
  const sharedLocks = {
    async request(name, callback) {
      while (locksHeld.has(name)) {
        await new Promise((r) => setTimeout(r, 5));
      }
      locksHeld.add(name);
      try {
        return await callback();
      } finally {
        locksHeld.delete(name);
      }
    },
  };

  const sharedCookieState = {
    cookie: options.initialCookie || 'cookie-v1',
    requestHistory: [],
  };

  function createTab(tabName, fetchHandler) {
    const localItems = new Map();
    const sessionItems = new Map();
    const dispatchedEvents = [];

    const tabEnv = {
      modules: new Map(), // Separate module cache guarantees isolated JavaScript memory per tab!
      window: {
        location: { hostname: 'localhost', protocol: 'http:' },
        dispatchEvent: (e) => dispatchedEvents.push(e),
        BroadcastChannel: SharedBroadcastChannel,
      },
      document: { cookie: '' },
      navigator: {
        ...(options.enableWebLocks !== false ? { locks: sharedLocks } : {}),
      },
      localStorage: {
        getItem: (k) => localItems.get(k) || null,
        setItem: (k, v) => localItems.set(k, String(v)),
        removeItem: (k) => localItems.delete(k),
        clear: () => localItems.clear(),
      },
      sessionStorage: {
        getItem: (k) => sessionItems.get(k) || null,
        setItem: (k, v) => sessionItems.set(k, String(v)),
        removeItem: (k) => sessionItems.delete(k),
        clear: () => sessionItems.clear(),
      },
      dispatchedEvents,
      BroadcastChannel: SharedBroadcastChannel,
      fetch: (...args) => fetchHandler(tabName, ...args),
    };

    const mem = loadModule('lib/auth-token-memory.ts', tabEnv);
    const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', tabEnv);
    const coordinator = new AuthCoordinator('http://test/api');
    const { ApiClient, clearSession } = loadModule('lib/api.ts', tabEnv);
    const api = new ApiClient('http://test/api', coordinator);

    return {
      name: tabName,
      env: tabEnv,
      mem,
      coordinator,
      api,
      clearSession,
      dispatchedEvents,
    };
  }

  return { createTab, sharedCookieState, channels };
}

function jsonResponse(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

// 1. MEMORY TOKEN STORAGE & GENERATION TRACKING
test('in-memory token storage updates volatile memory, increments generation, and clears cleanly', () => {
  const env = createBrowserEnv();
  const mem = loadModule('lib/auth-token-memory.ts', env);

  assert.equal(mem.getAccessToken(), null);
  const snap0 = mem.getTokenSnapshot();
  assert.equal(snap0.token, null);
  assert.equal(snap0.generation, 0);

  mem.setAccessToken('tok-1', '2030-01-01T00:00:00Z');
  assert.equal(mem.getAccessToken(), 'tok-1');
  const snap1 = mem.getTokenSnapshot();
  assert.equal(snap1.token, 'tok-1');
  assert.equal(snap1.generation, 1);

  mem.setAccessToken('tok-2', '2030-01-01T00:00:00Z');
  const snap2 = mem.getTokenSnapshot();
  assert.equal(snap2.generation, 2);

  // Clear resets token to null and keeps monotonic generation intact
  mem.clearAccessToken();
  assert.equal(mem.getAccessToken(), null);
  const snap3 = mem.getTokenSnapshot();
  assert.equal(snap3.token, null);
  assert.equal(snap3.generation, 3);
});

// 2. PROACTIVE CLOCK SKEW (15s)
test('isAccessTokenUsable enforces proactive 15-second clock skew buffer', () => {
  const env = createBrowserEnv();
  const mem = loadModule('lib/auth-token-memory.ts', env);

  const nowSec = Math.floor(Date.now() / 1000);

  // Expiring in 5 seconds -> unusable with 15s skew
  mem.setAccessToken('tok-short', new Date((nowSec + 5) * 1000).toISOString());
  assert.equal(mem.isAccessTokenUsable(15), false);
  // Usable with 0s skew
  assert.equal(mem.isAccessTokenUsable(0), true);

  // Expiring in 30 seconds -> usable with 15s skew
  mem.setAccessToken('tok-long', new Date((nowSec + 30) * 1000).toISOString());
  assert.equal(mem.isAccessTokenUsable(15), true);
});

// 3. BOOTSTRAP SUCCEEDS & FAILS (HTTPONLY REFRESH COOKIE -> AUTHENTICATED)
test('bootstrap authenticates from refresh cookie and populates user profile', async () => {
  const env = createBrowserEnv();
  let refreshCalls = 0;
  let meCalls = 0;

  env.fetch = async (url, init) => {
    if (url.endsWith('/auth/refresh')) {
      refreshCalls++;
      return jsonResponse(200, {
        access_token: 'bootstrap-token',
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    if (url.endsWith('/auth/me')) {
      meCalls++;
      const auth = init?.headers?.Authorization;
      assert.equal(auth, 'Bearer bootstrap-token');
      return jsonResponse(200, {
        id: 'u-1',
        email: 'trader@mahajak.com',
        role: 'TRADER',
        is_active: true,
      });
    }
    return jsonResponse(404, {});
  };

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');

  const ok = await coordinator.bootstrap();
  assert.equal(ok, true);
  assert.equal(refreshCalls, 1);
  assert.equal(meCalls, 1);

  const state = coordinator.getState();
  assert.equal(state.status, 'authenticated');
  assert.equal(state.user?.email, 'trader@mahajak.com');

  const mem = loadModule('lib/auth-token-memory.ts', env);
  assert.equal(mem.getAccessToken(), 'bootstrap-token');
});

test('bootstrap fails gracefully on 401 without throwing', async () => {
  const env = createBrowserEnv();
  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      return jsonResponse(401, { detail: 'No active session' });
    }
    return jsonResponse(404, {});
  };

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');

  const ok = await coordinator.bootstrap();
  assert.equal(ok, false);

  const state = coordinator.getState();
  assert.equal(state.status, 'unauthenticated');
  assert.equal(state.user, null);

  const mem = loadModule('lib/auth-token-memory.ts', env);
  assert.equal(mem.getAccessToken(), null);
});

// 4. LEGACY STORAGE PURGE
test('purgeLegacyAuthStorage unconditionally cleans localStorage and sessionStorage without reads', () => {
  const env = createBrowserEnv();
  env.localStorage.setItem('access_token', 'legacy-at');
  env.localStorage.setItem('refresh_token', 'legacy-rt');
  env.sessionStorage.setItem('access_token', 'legacy-sat');
  env.sessionStorage.setItem('refresh_token', 'legacy-srt');

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.purgeLegacyAuthStorage();

  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  assert.equal(env.sessionStorage.getItem('access_token'), null);
  assert.equal(env.sessionStorage.getItem('refresh_token'), null);
});

// 5. IN-TAB CONCURRENT 401 STORM (SINGLE FLIGHT REFRESH)
test('concurrent 401 requests within a tab single-flight the refresh mutation', async () => {
  const env = createBrowserEnv();
  let refreshCount = 0;

  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      refreshCount++;
      await new Promise((r) => setTimeout(r, 25));
      return jsonResponse(200, {
        access_token: 'storm-new-token',
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    return jsonResponse(401, { detail: 'Unauthorized' });
  };

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');

  // Trigger 5 concurrent refresh requests within the same coordinator
  const results = await Promise.all([
    coordinator.refreshAccessToken(),
    coordinator.refreshAccessToken(),
    coordinator.refreshAccessToken(),
    coordinator.refreshAccessToken(),
    coordinator.refreshAccessToken(),
  ]);

  // Exactly 1 network refresh was executed
  assert.equal(refreshCount, 1);
  for (const token of results) {
    assert.equal(token, 'storm-new-token');
  }
});

// 6. GENERATION CHANGE SKIPS REDUNDANT REFRESH
test('api client skips refresh if generation advanced while awaiting flight', async () => {
  const env = createBrowserEnv();
  let refreshes = 0;

  env.fetch = async (url, options) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++;
      return jsonResponse(200, {
        access_token: 'gen2-token',
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    const auth = options?.headers?.get?.('Authorization') || options?.headers?.Authorization;
    if (auth === 'Bearer gen2-token') {
      return jsonResponse(200, {
        id: 'u1',
        email: 'user@example.com',
        role: 'VIEWER',
        is_active: true,
      });
    }
    return jsonResponse(401, { detail: 'Unauthorized' });
  };

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('gen1-token', '2030-01-01T00:00:00Z');

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api');

  const user = await api.getMe();
  assert.equal(user.email, 'user@example.com');
  assert.equal(refreshes, 1);
});

// 7. SECOND 401 TERMINATES SESSION VIA CANONICAL INVALIDATION (BOUNDED RETRY = 1)
test('second 401 terminates session with canonical invalidation without infinite refresh loop', async () => {
  const env = createBrowserEnv();
  let refreshes = 0;

  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++;
      return jsonResponse(200, {
        access_token: 'dummy-token',
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    // Business endpoint always returns 401
    return jsonResponse(401, { detail: 'Revoked' });
  };

  const mem = loadModule('lib/auth-token-memory.ts', env);
  const initialEpoch = mem.getSessionEpoch();

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api', coordinator);

  await assert.rejects(api.getMe(), /Session expired/);

  // Refresh happened at most once
  assert.equal(refreshes, 1);
  // Canonical invalidation advanced session epoch
  assert.ok(mem.getSessionEpoch() > initialEpoch);
  // Volatile memory token was cleared
  assert.equal(mem.getAccessToken(), null);
  // Coordinator status set to unauthenticated
  assert.equal(coordinator.getState().status, 'unauthenticated');
  assert.equal(coordinator.getState().user, null);
  // auth:expired event was dispatched
  assert.equal(env.dispatchedEvents.some((e) => e.type === 'auth:expired'), true);
});

// 8. STALE COMPLETION TEST (SECTION 13)
test('stale refresh completion after terminal clear is discarded and does not restore authenticated state', async () => {
  const env = createBrowserEnv();
  let delayedResolve;

  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      return new Promise((resolve) => {
        delayedResolve = () =>
          resolve(
            jsonResponse(200, {
              access_token: 'late-token',
              token_type: 'bearer',
              expires_at: '2030-01-01T00:00:00Z',
            }),
          );
      });
    }
    if (url.endsWith('/auth/logout')) {
      return jsonResponse(200, { ok: true });
    }
    return jsonResponse(404, {});
  };

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  const mem = loadModule('lib/auth-token-memory.ts', env);

  // Start refresh in background
  const refreshPromise = coordinator.refreshAccessToken().catch((err) => err);

  // Canonical terminal clear occurs while refresh is pending
  coordinator.clearSession({ broadcast: false });
  assert.equal(coordinator.getState().status, 'unauthenticated');
  assert.equal(mem.getAccessToken(), null);

  // Now the late refresh returns 200
  if (delayedResolve) delayedResolve();

  const err = await refreshPromise;
  assert.match(err.message, /Session invalidated/);

  // Late token was discarded: memory token remains null, coordinator remains unauthenticated
  assert.equal(coordinator.getState().status, 'unauthenticated');
  assert.equal(mem.getAccessToken(), null);
});

// 9. MULTI-TAB WEB LOCKS COORDINATION (SECTION 5)
test('multi-tab Web Locks serialize refresh cookie rotation with isolated tab memory', async () => {
  const cluster = createMultiTabCluster({ enableWebLocks: true });
  let refreshOrder = [];

  const tabA = cluster.createTab('tabA', async (tabName, url) => {
    if (url.endsWith('/auth/refresh')) {
      refreshOrder.push(tabName);
      await new Promise((r) => setTimeout(r, 20));
      return jsonResponse(200, {
        access_token: 'token-' + tabName,
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    return jsonResponse(404, {});
  });

  const tabB = cluster.createTab('tabB', async (tabName, url) => {
    if (url.endsWith('/auth/refresh')) {
      refreshOrder.push(tabName);
      await new Promise((r) => setTimeout(r, 20));
      return jsonResponse(200, {
        access_token: 'token-' + tabName,
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    return jsonResponse(404, {});
  });

  // Both tabs attempt refresh concurrently
  const [tokenA, tokenB] = await Promise.all([
    tabA.coordinator.refreshAccessToken(),
    tabB.coordinator.refreshAccessToken(),
  ]);

  assert.equal(tokenA, 'token-tabA');
  assert.equal(tokenB, 'token-tabB');

  // Verify memory isolation: tabA memory has tokenA, tabB memory has tokenB
  assert.equal(tabA.mem.getAccessToken(), 'token-tabA');
  assert.equal(tabB.mem.getAccessToken(), 'token-tabB');

  // Serialized execution through Web Locks: 2 sequential requests
  assert.equal(refreshOrder.length, 2);
});

// 10. REAL MULTI-TAB FALLBACK TEST (SECTION 17)
test('real multi-tab fallback test without Web Locks: winner rotates cookie, loser retries once and authenticates', async () => {
  const cluster = createMultiTabCluster({ enableWebLocks: false, initialCookie: 'cookie-v1' });
  let totalRefreshRequests = 0;
  let broadcastLogs = [];

  // Monitor BroadcastChannel for token leaks
  const monitorTab = cluster.createTab('monitor', () => {});
  const monitorChannel = new monitorTab.env.window.BroadcastChannel('aigold-auth');
  monitorChannel.onmessage = (e) => broadcastLogs.push(e.data);

  const sharedHandler = async (tabName, url) => {
    if (url.endsWith('/auth/refresh')) {
      totalRefreshRequests++;
      const currentReqIndex = totalRefreshRequests;

      if (currentReqIndex === 1) {
        // Tab A request reaches server first: returns 200, rotates shared cookie to v2
        await new Promise((r) => setTimeout(r, 10));
        cluster.sharedCookieState.cookie = 'cookie-v2';
        return jsonResponse(200, {
          access_token: 'winner-token-A',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        });
      }

      if (currentReqIndex === 2) {
        // Tab B initial simultaneous request sent with stale cookie-v1: returns 401
        return jsonResponse(401, { detail: 'Cookie race lost: stale cookie-v1' });
      }

      if (currentReqIndex === 3) {
        // Tab B bounded retry after waiting for remote refresh-completed:
        // Sent with updated cookie-v2, returns 200, rotates shared cookie to v3
        cluster.sharedCookieState.cookie = 'cookie-v3';
        return jsonResponse(200, {
          access_token: 'recovery-token-B',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        });
      }

      // Any 4th request would indicate unbounded retry failure
      return jsonResponse(401, { detail: 'Unbounded retry exceeded' });
    }
    return jsonResponse(404, {});
  };

  const tabA = cluster.createTab('tabA', sharedHandler);
  const tabB = cluster.createTab('tabB', sharedHandler);

  // Both tabs start refresh concurrently without Web Locks
  const [tokenA, tokenB] = await Promise.all([
    tabA.coordinator.refreshAccessToken(),
    tabB.coordinator.refreshAccessToken(),
  ]);

  assert.equal(tokenA, 'winner-token-A');
  assert.equal(tokenB, 'recovery-token-B');

  // Verify memory isolation between tabs
  assert.equal(tabA.mem.getAccessToken(), 'winner-token-A');
  assert.equal(tabB.mem.getAccessToken(), 'recovery-token-B');

  // Assert both coordinators reached authenticated state
  assert.equal(tabA.coordinator.getState().status, 'authenticated');
  assert.equal(tabB.coordinator.getState().status, 'authenticated');

  // Total requests bounded to exactly 3 (1 winner + 1 stale 401 + 1 recovery 200)
  assert.equal(totalRefreshRequests, 3);

  // Invariant: zero token leakage over BroadcastChannel
  const broadcastString = JSON.stringify(broadcastLogs);
  assert.equal(broadcastString.includes('winner-token-A'), false);
  assert.equal(broadcastString.includes('recovery-token-B'), false);
  assert.equal(broadcastString.includes('cookie-v'), false);
});

// 11. MULTI-TAB COLD BOOTSTRAP TEST (SECTION 18)
test('two tabs cold-bootstrap simultaneously with Web Locks and both authenticate cleanly', async () => {
  const cluster = createMultiTabCluster({ enableWebLocks: true, initialCookie: 'cookie-v1' });
  let bootstrapRequests = 0;

  const sharedHandler = async (tabName, url, init) => {
    if (url.endsWith('/auth/refresh')) {
      bootstrapRequests++;
      const ver = bootstrapRequests;
      cluster.sharedCookieState.cookie = `cookie-v${ver + 1}`;
      return jsonResponse(200, {
        access_token: `boot-token-${tabName}`,
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    if (url.endsWith('/auth/me')) {
      const auth = init?.headers?.Authorization;
      assert.equal(auth, `Bearer boot-token-${tabName}`);
      return jsonResponse(200, {
        id: `u-${tabName}`,
        email: `${tabName}@mahajak.com`,
        role: 'TRADER',
        is_active: true,
      });
    }
    return jsonResponse(404, {});
  };

  const tabA = cluster.createTab('tabA', sharedHandler);
  const tabB = cluster.createTab('tabB', sharedHandler);

  // Cold bootstrap both tabs simultaneously
  const [bootA, bootB] = await Promise.all([
    tabA.coordinator.bootstrap(),
    tabB.coordinator.bootstrap(),
  ]);

  assert.equal(bootA, true);
  assert.equal(bootB, true);
  assert.equal(tabA.coordinator.getState().status, 'authenticated');
  assert.equal(tabB.coordinator.getState().status, 'authenticated');
  assert.equal(tabA.mem.getAccessToken(), 'boot-token-tabA');
  assert.equal(tabB.mem.getAccessToken(), 'boot-token-tabB');
  assert.equal(tabA.coordinator.getState().user?.email, 'tabA@mahajak.com');
  assert.equal(tabB.coordinator.getState().user?.email, 'tabB@mahajak.com');
});

test('two tabs cold-bootstrap simultaneously without Web Locks: winner rotates cookie, loser recovers and authenticates', async () => {
  const cluster = createMultiTabCluster({ enableWebLocks: false, initialCookie: 'cookie-v1' });
  let refreshAttempts = 0;

  const sharedHandler = async (tabName, url, init) => {
    if (url.endsWith('/auth/refresh')) {
      refreshAttempts++;
      if (refreshAttempts === 1) {
        await new Promise((r) => setTimeout(r, 10));
        cluster.sharedCookieState.cookie = 'cookie-v2';
        return jsonResponse(200, {
          access_token: 'boot-winner-A',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        });
      }
      if (refreshAttempts === 2) {
        return jsonResponse(401, { detail: 'Race lost: stale cookie-v1' });
      }
      if (refreshAttempts === 3) {
        cluster.sharedCookieState.cookie = 'cookie-v3';
        return jsonResponse(200, {
          access_token: 'boot-recovery-B',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        });
      }
      return jsonResponse(401, {});
    }
    if (url.endsWith('/auth/me')) {
      const auth = init?.headers?.Authorization;
      const isA = auth === 'Bearer boot-winner-A';
      return jsonResponse(200, {
        id: isA ? 'u-A' : 'u-B',
        email: isA ? 'winnerA@mahajak.com' : 'recoveryB@mahajak.com',
        role: 'TRADER',
        is_active: true,
      });
    }
    return jsonResponse(404, {});
  };

  const tabA = cluster.createTab('tabA', sharedHandler);
  const tabB = cluster.createTab('tabB', sharedHandler);

  const [bootA, bootB] = await Promise.all([
    tabA.coordinator.bootstrap(),
    tabB.coordinator.bootstrap(),
  ]);

  assert.equal(bootA, true);
  assert.equal(bootB, true);
  assert.equal(tabA.coordinator.getState().status, 'authenticated');
  assert.equal(tabB.coordinator.getState().status, 'authenticated');
  assert.equal(tabA.mem.getAccessToken(), 'boot-winner-A');
  assert.equal(tabB.mem.getAccessToken(), 'boot-recovery-B');
});

// 12. SESSION-CHANGED MULTI-TAB FANOUT (SECTION 19)
test('tab A login notifies tabs B and C via session-changed; all converge to authenticated session', async () => {
  const cluster = createMultiTabCluster({ enableWebLocks: true });
  let refreshCount = 0;

  const sharedHandler = async (tabName, url) => {
    if (url.endsWith('/auth/login')) {
      cluster.sharedCookieState.cookie = 'cookie-login-v1';
      return jsonResponse(200, {
        access_token: 'login-token-A',
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    if (url.endsWith('/auth/refresh')) {
      refreshCount++;
      const tok = `sync-token-${tabName}-${refreshCount}`;
      return jsonResponse(200, {
        access_token: tok,
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    if (url.endsWith('/auth/me')) {
      return jsonResponse(200, {
        id: 'u-common',
        email: 'logged_user@mahajak.com',
        role: 'TRADER',
        is_active: true,
      });
    }
    return jsonResponse(404, {});
  };

  const tabA = cluster.createTab('tabA', sharedHandler);
  const tabB = cluster.createTab('tabB', sharedHandler);
  const tabC = cluster.createTab('tabC', sharedHandler);

  // Tab A performs login
  await tabA.coordinator.login('logged_user@mahajak.com', 'secret');
  assert.equal(tabA.coordinator.getState().status, 'authenticated');

  // Allow asynchronous broadcast and subsequent coordinated bootstraps to settle
  await new Promise((r) => setTimeout(r, 100));

  // Tabs B and C both converged to authenticated session without 401 lockout
  assert.equal(tabB.coordinator.getState().status, 'authenticated');
  assert.equal(tabC.coordinator.getState().status, 'authenticated');
  assert.equal(tabB.coordinator.getState().user?.email, 'logged_user@mahajak.com');
  assert.equal(tabC.coordinator.getState().user?.email, 'logged_user@mahajak.com');
});

// 13. CROSS-TAB LOGOUT AND SESSION EXPIRED
test('cross-tab logout performs canonical invalidation across all tabs', async () => {
  const cluster = createMultiTabCluster({ enableWebLocks: true });

  const tabA = cluster.createTab('tabA', async (tabName, url) => {
    if (url.endsWith('/auth/logout')) return jsonResponse(200, { ok: true });
    return jsonResponse(404, {});
  });
  const tabB = cluster.createTab('tabB', async () => jsonResponse(404, {}));

  tabA.mem.setAccessToken('tok-A', '2030-01-01T00:00:00Z');
  tabB.mem.setAccessToken('tok-B', '2030-01-01T00:00:00Z');

  await tabA.coordinator.logout();

  // Allow microtasks for broadcast delivery
  await new Promise((r) => setTimeout(r, 25));

  assert.equal(tabA.coordinator.getState().status, 'unauthenticated');
  assert.equal(tabA.mem.getAccessToken(), null);

  assert.equal(tabB.coordinator.getState().status, 'unauthenticated');
  assert.equal(tabB.mem.getAccessToken(), null);
  assert.equal(tabB.dispatchedEvents.some((e) => e.type === 'auth:expired'), true);
});

// 14. WEBSOCKET FIRST-FRAME AUTH & 4401 BOUNDED RECOVERY
test('websocket authenticates in first frame with memory token, no URL token, and recovers 4401 once', async () => {
  const env = createBrowserEnv();
  const sockets = [];

  class MockWebSocket {
    constructor(url) {
      this.url = url;
      this.sent = [];
      this.readyState = 1; // OPEN
      sockets.push(this);
    }
    send(data) {
      this.sent.push(JSON.parse(data));
    }
    close(code = 1000, reason = '') {
      this.readyState = 3; // CLOSED
      this.onclose?.({ code, reason });
    }
  }

  env.WebSocket = MockWebSocket;
  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('ws-token-1', '2030-01-01T00:00:00Z');

  let refreshes = 0;
  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++;
      mem.setAccessToken('ws-token-2', '2030-01-01T00:00:00Z');
      return jsonResponse(200, {
        access_token: 'ws-token-2',
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    return jsonResponse(404, {});
  };

  const { MarketConnection } = loadModule('features/chart/transport.ts', env);
  const states = [];
  const conn = new MarketConnection(
    async () => mem.getAccessToken(),
    () => {},
    (s) => states.push(s),
    'XAUUSD',
    'M5',
    'ws://localhost:8000/ws/market',
  );

  conn.start();
  await new Promise((r) => setImmediate(r));

  // Verify socket URL contains NO query token
  assert.equal(sockets[0].url, 'ws://localhost:8000/ws/market');
  sockets[0].onopen();

  // First frame is auth
  assert.deepEqual(sockets[0].sent[0], { type: 'auth', token: 'ws-token-1' });
  // Second frame is subscribe
  assert.deepEqual(sockets[0].sent[1], { type: 'subscribe', symbol: 'XAUUSD', timeframe: 'M5' });

  // Simulate 4401 backend close
  sockets[0].close(4401, 'Token expired');
  await new Promise((r) => setTimeout(r, 1100));

  // Should have triggered reconnect with fresh token
  assert.equal(sockets.length, 2);
  assert.equal(refreshes, 1);
  sockets[1].onopen();
  assert.deepEqual(sockets[1].sent[0], { type: 'auth', token: 'ws-token-2' });

  conn.stop();
});

// 15. WEBSOCKET EXHAUSTION CALLS CANONICAL TERMINAL INVALIDATION (SECTION 15)
test('websocket auth failure exhaustion invokes canonical clearSession, advances epoch, and clears token', async () => {
  const env = createBrowserEnv();
  const sockets = [];

  class MockWebSocket {
    constructor(url) {
      this.url = url;
      this.sent = [];
      this.readyState = 1;
      sockets.push(this);
    }
    send(data) {
      this.sent.push(JSON.parse(data));
    }
    close(code = 1000, reason = '') {
      this.readyState = 3;
      this.onclose?.({ code, reason });
    }
  }

  env.WebSocket = MockWebSocket;
  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('ws-token-initial', '2030-01-01T00:00:00Z');
  const initialEpoch = mem.getSessionEpoch();

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');

  let refreshes = 0;
  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++;
      mem.setAccessToken('ws-token-refresh', '2030-01-01T00:00:00Z');
      return jsonResponse(200, {
        access_token: 'ws-token-refresh',
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    return jsonResponse(404, {});
  };

  const { MarketConnection } = loadModule('features/chart/transport.ts', env);
  const states = [];
  const conn = new MarketConnection(
    async () => mem.getAccessToken(),
    () => {},
    (s) => states.push(s),
    'XAUUSD',
    'M5',
    'ws://localhost:8000/ws/market',
    () => coordinator.clearSession({ broadcast: true }),
  );

  conn.start();
  await new Promise((r) => setImmediate(r));
  sockets[0].onopen();

  // 1st 4401 close: triggers bounded refresh
  sockets[0].close(4401, 'First 4401');
  await new Promise((r) => setTimeout(r, 1100));

  assert.equal(sockets.length, 2);
  assert.equal(refreshes, 1);
  sockets[1].onopen();

  // 2nd 4401 close: auth recovery is exhausted
  sockets[1].close(4401, 'Second 4401 exhausted');
  await new Promise((r) => setTimeout(r, 50));

  // Connection marks ERROR
  assert.equal(states.at(-1), 'ERROR');
  // Canonical session invalidation was executed
  assert.ok(mem.getSessionEpoch() > initialEpoch);
  assert.equal(mem.getAccessToken(), null);
  assert.equal(coordinator.getState().status, 'unauthenticated');

  // No 3rd socket was created
  assert.equal(sockets.length, 2);
  conn.stop();
});
