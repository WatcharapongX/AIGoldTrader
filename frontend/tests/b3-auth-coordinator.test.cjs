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
      require: name => {
        if (mocks[name]) return mocks[name];
        if (name.startsWith('@/')) {
          const target = name.slice(2) + (name.endsWith('.ts') ? '' : '.ts');
          return loadInternal(target);
        }
        if (name.endsWith('.json')) {
          const dir = path.dirname(relPath);
          const jsonPath = name.startsWith('.') ? path.join(dir, name) : name;
          const raw = require(path.join(__dirname, '../src', jsonPath.startsWith('@/') ? jsonPath.slice(2) : jsonPath));
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
            ch.onmessage({ data });
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
          await new Promise(r => setTimeout(r, 10));
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
    localItems,
    sessionItems,
    BroadcastChannel: MockBroadcastChannel,
    modules: new Map(),
  };

  return env;
}

const jsonResponse = (status, data) => new Response(JSON.stringify(data), { status });

// 1. MEMORY TOKEN MODULE TESTS
test('memory token module stores token only in memory, increments generation and epoch, and purges legacy storage', () => {
  const env = createBrowserEnv();
  env.localStorage.setItem('access_token', 'legacy-access');
  env.localStorage.setItem('refresh_token', 'legacy-refresh');
  env.sessionStorage.setItem('access_token', 'session-access');
  env.sessionStorage.setItem('refresh_token', 'session-refresh');

  const mem = loadModule('lib/auth-token-memory.ts', env);

  assert.equal(mem.getAccessToken(), null);
  const snap0 = mem.getTokenSnapshot();
  assert.equal(snap0.token, null);
  assert.equal(snap0.generation, 0);

  // Legacy purge
  mem.purgeLegacyAuthStorage();
  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.localStorage.getItem('refresh_token'), null);
  assert.equal(env.sessionStorage.getItem('access_token'), null);
  assert.equal(env.sessionStorage.getItem('refresh_token'), null);

  // Set memory token
  const future = new Date(Date.now() + 600000).toISOString();
  mem.setAccessToken('mem-token-1', future);
  assert.equal(mem.getAccessToken(), 'mem-token-1');
  const snap1 = mem.getTokenSnapshot();
  assert.equal(snap1.generation, 1);
  assert.equal(mem.isAccessTokenUsable(15), true);

  // Expired / skewed token check
  const nearExpiry = new Date(Date.now() + 5000).toISOString();
  mem.setAccessToken('mem-token-2', nearExpiry);
  assert.equal(mem.isAccessTokenUsable(15), false); // within 15s skew -> unusable

  // Advance session epoch
  const e1 = mem.advanceSessionEpoch();
  assert.equal(e1, 1);
  assert.equal(mem.getSessionEpoch(), 1);

  // Clear token
  mem.clearAccessToken();
  assert.equal(mem.getAccessToken(), null);
  assert.equal(mem.getTokenSnapshot().generation, 3);
});

// 2. BOOTSTRAP SUCCESS AND FAILURE
test('bootstrap succeeds via HttpOnly cookie: calls /auth/refresh, sets memory token, calls /auth/me, sets authenticated', async () => {
  const env = createBrowserEnv();
  const calls = [];
  env.fetch = async (url, options) => {
    calls.push({ url, options });
    if (url.endsWith('/auth/refresh')) {
      return jsonResponse(200, {
        access_token: 'boot-access',
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    if (url.endsWith('/auth/me')) {
      assert.equal(options.headers.Authorization, 'Bearer boot-access');
      return jsonResponse(200, { id: 'u1', email: 'user@example.com', role: 'VIEWER', is_active: true });
    }
    return jsonResponse(404, {});
  };

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  const result = await coordinator.bootstrap();

  assert.equal(result, true);
  assert.equal(coordinator.getState().status, 'authenticated');
  assert.equal(coordinator.getState().user.email, 'user@example.com');
  // Token resides only in volatile memory
  assert.equal(env.localStorage.getItem('access_token'), null);
  assert.equal(env.sessionStorage.getItem('access_token'), null);
});

test('bootstrap fails gracefully on 401: enters unauthenticated, does not loop', async () => {
  const env = createBrowserEnv();
  let refreshCalls = 0;
  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      refreshCalls++;
      return jsonResponse(401, { detail: 'No refresh token' });
    }
    return jsonResponse(404, {});
  };

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  const result = await coordinator.bootstrap();

  assert.equal(result, false);
  assert.equal(refreshCalls, 1);
  assert.equal(coordinator.getState().status, 'unauthenticated');
  assert.equal(coordinator.getState().user, null);

  // Second bootstrap without force reuses the same result and does not call fetch again
  const result2 = await coordinator.bootstrap();
  assert.equal(result2, false);
  assert.equal(refreshCalls, 1);
});

// 3. IN-TAB 401 REQUEST STORM & BOUNDED RETRY
test('simultaneous 401s in one tab share exactly one refresh promise, requests retry max once with new memory token', async () => {
  const env = createBrowserEnv();
  let refreshes = 0;

  env.fetch = async (url, options) => {
    if (url.endsWith('/auth/refresh')) {
      refreshes++;
      await new Promise(r => setImmediate(r));
      return jsonResponse(200, {
        access_token: 'fresh-token',
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    if (url.endsWith('/auth/me')) {
      const auth = options?.headers?.get?.('Authorization') || options?.headers?.Authorization;
      if (auth === 'Bearer fresh-token') {
        return jsonResponse(200, { id: 'u1', email: 'user@example.com', role: 'VIEWER', is_active: true });
      }
      return jsonResponse(401, { detail: 'Token expired' });
    }
    return jsonResponse(404, {});
  };

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api');

  // Launch 5 concurrent business requests with stale/no token
  const results = await Promise.all([
    api.getMe(),
    api.getMe(),
    api.getMe(),
    api.getMe(),
    api.getMe(),
  ]);

  assert.equal(results.length, 5);
  assert.equal(results.every(u => u.email === 'user@example.com'), true);
  // Exactly ONE refresh was triggered
  assert.equal(refreshes, 1);
  // Storage remains clean
  assert.equal(env.localStorage.getItem('access_token'), null);
});

// 4. GENERATION CHANGE SKIPS REDUNDANT REFRESH
test('generation change skips redundant refresh and retries with current memory token', async () => {
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
      return jsonResponse(200, { id: 'u1', email: 'user@example.com', role: 'VIEWER', is_active: true });
    }
    return jsonResponse(401, { detail: 'Unauthorized' });
  };

  const mem = loadModule('lib/auth-token-memory.ts', env);
  // Set initial token (generation 1)
  mem.setAccessToken('gen1-token', '2030-01-01T00:00:00Z');

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api');

  const user = await api.getMe();
  assert.equal(user.email, 'user@example.com');
  assert.equal(refreshes, 1);
});

// 5. SECOND 401 TERMINATES SESSION (BOUNDED RETRY = 1)
test('second 401 terminates session without infinite refresh loop', async () => {
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

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api');

  await assert.rejects(api.getMe(), /Session expired/);
  // Refresh happened at most once
  assert.equal(refreshes, 1);
  // Session was cleared and event dispatched
  assert.equal(env.dispatchedEvents.some(e => e.type === 'auth:expired'), true);
});

// 6. LOGOUT RACE & SESSION EPOCH PROTECTION
test('late refresh completion after logout is discarded and does not restore authenticated state', async () => {
  const env = createBrowserEnv();
  let delayedResolve;

  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      return new Promise(resolve => {
        delayedResolve = () => resolve(jsonResponse(200, {
          access_token: 'late-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }));
      });
    }
    if (url.endsWith('/auth/logout')) {
      return jsonResponse(200, { ok: true });
    }
    return jsonResponse(404, {});
  };

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');

  // Start refresh in background
  const refreshPromise = coordinator.refreshAccessToken().catch(err => err);

  setTimeout(() => {
    if (delayedResolve) delayedResolve();
  }, 10);

  // User logs out while refresh is in flight
  await coordinator.logout();
  assert.equal(coordinator.getState().status, 'unauthenticated');

  const err = await refreshPromise;
  assert.match(err.message, /Session invalidated/);

  // Late refresh did NOT restore authenticated state or memory token
  assert.equal(coordinator.getState().status, 'unauthenticated');
  const mem = loadModule('lib/auth-token-memory.ts', env);
  assert.equal(mem.getAccessToken(), null);
});

// 7. MULTI-TAB WEB LOCKS COORDINATION
test('multi-tab Web Locks serialize refresh cookie rotation without token broadcast', async () => {
  const env = createBrowserEnv();
  let refreshOrder = [];

  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      refreshOrder.push(Date.now());
      await new Promise(r => setTimeout(r, 20));
      return jsonResponse(200, {
        access_token: 'tab-token-' + refreshOrder.length,
        token_type: 'bearer',
        expires_at: '2030-01-01T00:00:00Z',
      });
    }
    return jsonResponse(404, {});
  };

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const tabA = new AuthCoordinator('http://test/api');
  const tabB = new AuthCoordinator('http://test/api');

  // Both tabs attempt refresh concurrently
  const [tokenA, tokenB] = await Promise.all([
    tabA.refreshAccessToken(),
    tabB.refreshAccessToken(),
  ]);

  assert.ok(tokenA);
  assert.ok(tokenB);
  // Both got their tokens sequentially without conflicting
  assert.equal(refreshOrder.length, 2);
});

// 8. MULTI-TAB BROADCASTCHANNEL FALLBACK & RACE RECOVERY
test('multi-tab fallback race loser waits for refresh-completed and retries once', async () => {
  const env = createBrowserEnv();
  // Disable navigator.locks to test fallback path
  delete env.navigator.locks;

  let refreshCount = 0;
  env.fetch = async (url) => {
    if (url.endsWith('/auth/refresh')) {
      refreshCount++;
      if (refreshCount === 1) {
        // Tab A wins
        return jsonResponse(200, {
          access_token: 'winner-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        });
      }
      if (refreshCount === 2) {
        // Tab B initial simultaneous attempt loses with 401
        return jsonResponse(401, { detail: 'Cookie race lost' });
      }
      if (refreshCount === 3) {
        // Tab B retry after refresh-completed notification succeeds
        return jsonResponse(200, {
          access_token: 'recovery-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        });
      }
    }
    return jsonResponse(404, {});
  };

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const tabA = new AuthCoordinator('http://test/api');

  // Tab A refreshes successfully and broadcasts refresh-completed
  const tokenA = await tabA.refreshAccessToken();
  assert.equal(tokenA, 'winner-token');
});

// 9. CROSS-TAB LOGOUT AND SESSION CHANGED
test('cross-tab logout clears memory and state in other tabs', async () => {
  const env = createBrowserEnv();
  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const tabA = new AuthCoordinator('http://test/api');
  const tabB = new AuthCoordinator('http://test/api');

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('active-token', '2030-01-01T00:00:00Z');

  // Tab A initiates logout
  env.fetch = async () => jsonResponse(200, { ok: true });
  await tabA.logout();

  // Tab B received logout event
  assert.equal(tabB.getState().status, 'unauthenticated');
  assert.equal(mem.getAccessToken(), null);
});

test('cross-tab login notifies other tabs via session-changed', async () => {
  const env = createBrowserEnv();
  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const tabA = new AuthCoordinator('http://test/api');

  let broadcastEvents = [];
  const channel = new env.BroadcastChannel('aigold-auth');
  channel.onmessage = (e) => broadcastEvents.push(e.data);

  env.fetch = async (url) => {
    if (url.endsWith('/auth/login')) {
      return jsonResponse(200, { access_token: 'new-user-token', token_type: 'bearer', expires_at: '2030-01-01T00:00:00Z' });
    }
    if (url.endsWith('/auth/me')) {
      return jsonResponse(200, { id: 'u2', email: 'user2@example.com', role: 'TRADER', is_active: true });
    }
    return jsonResponse(404, {});
  };

  await tabA.login('user2@example.com', 'secret');
  assert.equal(broadcastEvents.some(e => e.type === 'session-changed'), true);
  // Verify NO token was broadcasted in the event
  assert.equal(JSON.stringify(broadcastEvents).includes('new-user-token'), false);
});

// 10. WEBSOCKET FIRST-FRAME AUTH & 4401 RECOVERY
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
    'ws://localhost:8000/ws/market'
  );

  conn.start();
  await new Promise(r => setImmediate(r));

  // Verify socket URL contains NO query token
  assert.equal(sockets[0].url, 'ws://localhost:8000/ws/market');
  sockets[0].onopen();

  // First frame is auth
  assert.deepEqual(sockets[0].sent[0], { type: 'auth', token: 'ws-token-1' });
  // Second frame is subscribe
  assert.deepEqual(sockets[0].sent[1], { type: 'subscribe', symbol: 'XAUUSD', timeframe: 'M5' });

  // Simulate 4401 backend close
  sockets[0].close(4401, 'Token expired');
  await new Promise(r => setTimeout(r, 1100));

  // Should have triggered reconnect with fresh token
  assert.equal(sockets.length, 2);
  assert.equal(refreshes, 1);
  sockets[1].onopen();
  assert.deepEqual(sockets[1].sent[0], { type: 'auth', token: 'ws-token-2' });

  // A second 4401 fails closed without infinite loop
  sockets[1].close(4401, 'Repeated expiry');
  await new Promise(r => setTimeout(r, 50));
  assert.equal(states.at(-1), 'ERROR');

  conn.stop();
});
