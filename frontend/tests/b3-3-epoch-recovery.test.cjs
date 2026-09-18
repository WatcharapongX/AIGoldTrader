const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('c:/AI Gold Trader/frontend/node_modules/typescript');

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
      Error,
      TypeError,
      RangeError,
      fetch: (...args) => (overrides.fetch ? overrides.fetch(...args) : fetch(...args)),
      ...overrides,
    };
    vm.runInNewContext(outputText, context, { filename: relPath });
    return exports;
  }
  return loadInternal(file);
}

function createEnv(fetchHandler, extra = {}) {
  const localMap = new Map();
  const sessionMap = new Map();
  const dispatchedEvents = [];

  const env = {
    window: {
      location: { hostname: 'localhost', protocol: 'http:' },
      dispatchEvent: (e) => dispatchedEvents.push(e),
      BroadcastChannel: extra.BroadcastChannel || null,
    },
    navigator: {}, // NO Web Locks by default for strict concurrency testing
    localStorage: {
      getItem: (k) => localMap.get(k) || null,
      setItem: (k, v) => localMap.set(k, String(v)),
      removeItem: (k) => localMap.delete(k),
      clear: () => localMap.clear(),
    },
    sessionStorage: {
      getItem: (k) => sessionMap.get(k) || null,
      setItem: (k, v) => sessionMap.set(k, String(v)),
      removeItem: (k) => sessionMap.delete(k),
      clear: () => sessionMap.clear(),
    },
    fetch: fetchHandler,
    dispatchedEvents,
    modules: new Map(),
    ...extra,
  };
  return env;
}

function getAuthHeader(init) {
  if (!init || !init.headers) return null;
  if (typeof init.headers.get === 'function') {
    return init.headers.get('Authorization') || init.headers.get('authorization');
  }
  return init.headers.Authorization || init.headers.authorization || null;
}

// MANDATORY TEST A: LATE 401 AFTER LOGOUT (NO WEB LOCKS)
// Defect B3.2-NEW-P2-001 regression
test('Mandatory Test A: late 401 after logout does not refresh, does not retry, token remains null, coordinator unauthenticated', async () => {
  let meResolve;
  let logoutResolve;
  let refreshCalls = 0;
  let meCallCount = 0;

  const env = createEnv(async (url) => {
    if (url.endsWith('/auth/me')) {
      meCallCount++;
      if (meCallCount === 1) {
        return new Promise((resolve) => {
          meResolve = () =>
            resolve(new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 }));
        });
      }
      return new Response(
        JSON.stringify({ id: 'u1', email: 'u@test.com', role: 'TRADER', is_active: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/logout')) {
      return new Promise((resolve) => {
        logoutResolve = () =>
          resolve(new Response(JSON.stringify({ ok: true }), { status: 200 }));
      });
    }
    if (url.endsWith('/auth/refresh')) {
      refreshCalls++;
      return new Response(
        JSON.stringify({
          access_token: 'resurrected-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response('Not found', { status: 404 });
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('initial-token', '2030-01-01T00:00:00Z');

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  coordinator.getState().status = 'authenticated';

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api', coordinator);

  // 1. Business request starts in epoch 1
  const reqPromise = api.getMe().catch((err) => err);

  // 2. User logs out: epoch advances 1 -> 2, memory token cleared, state unauthenticated
  const logoutPromise = coordinator.logout();
  assert.equal(mem.getAccessToken(), null);
  assert.equal(coordinator.getState().status, 'unauthenticated');

  // 3. Old business request returns 401
  meResolve();
  await reqPromise;

  // 4. Logout completes
  if (logoutResolve) logoutResolve();
  await logoutPromise;

  // Assert: ZERO refresh calls, ZERO retries of old request, memory token NULL, unauthenticated
  assert.equal(refreshCalls, 0, 'Zero /auth/refresh calls must be made for obsolete request');
  assert.equal(meCallCount, 1, 'Old request must not be retried');
  assert.equal(mem.getAccessToken(), null, 'Memory access token must remain null');
  assert.equal(coordinator.getState().status, 'unauthenticated', 'Coordinator must remain unauthenticated');
});

// MANDATORY TEST B: LATE REFRESH COMPLETION AFTER LOGOUT
test('Mandatory Test B: late refresh completion after logout is discarded and does not restore token', async () => {
  let refreshResolve;
  const env = createEnv(async (url) => {
    if (url.endsWith('/auth/refresh')) {
      return new Promise((resolve) => {
        refreshResolve = () =>
          resolve(
            new Response(
              JSON.stringify({
                access_token: 'late-token',
                token_type: 'bearer',
                expires_at: '2030-01-01T00:00:00Z',
              }),
              { status: 200, headers: { 'Content-Type': 'application/json' } },
            ),
          );
      });
    }
    if (url.endsWith('/auth/logout')) {
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }
    return new Response('Not found', { status: 404 });
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('initial-token', '2030-01-01T00:00:00Z');

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  coordinator.getState().status = 'authenticated';

  // Refresh begins in epoch 1
  const refreshPromise = coordinator.refreshAccessToken().catch((err) => err);

  // User logs out, advancing epoch 1 -> 2
  await coordinator.logout();

  // Late refresh returns 200
  refreshResolve();
  const refreshResult = await refreshPromise;

  assert.ok(refreshResult instanceof Error, 'Late refresh must reject');
  assert.equal(mem.getAccessToken(), null, 'Memory token must remain null');
  assert.equal(coordinator.getState().status, 'unauthenticated');
});

// MANDATORY TEST C: POST-LOGOUT NEW BUSINESS REQUEST 401 (TERMINAL RECOVERY BARRIER)
test('Mandatory Test C: post-logout new business request receives 401 and does NOT invoke refresh', async () => {
  let refreshCalls = 0;
  const env = createEnv(async (url) => {
    if (url.endsWith('/auth/me')) {
      return new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 });
    }
    if (url.endsWith('/auth/logout')) {
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }
    if (url.endsWith('/auth/refresh')) {
      refreshCalls++;
      return new Response(
        JSON.stringify({
          access_token: 'illegal-refresh-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200 },
      );
    }
    return new Response('Not found', { status: 404 });
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('active-token', '2030-01-01T00:00:00Z');

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  coordinator.getState().status = 'authenticated';

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api', coordinator);

  // User logs out
  await coordinator.logout();
  assert.equal(coordinator.getState().status, 'unauthenticated');

  // Component issues protected call during teardown
  const err = await api.getMe().catch((e) => e);

  assert.ok(err instanceof Error);
  assert.equal(refreshCalls, 0, 'Zero refresh calls must be made when terminal state is established');
  assert.equal(mem.getAccessToken(), null);
  assert.equal(coordinator.getState().status, 'unauthenticated');
});

// MANDATORY TEST D: OLD USER A REQUEST AFTER USER B LOGIN
test('Mandatory Test D: old User A request receiving 401 after User B login does NOT retry under User B token or clear User B session', async () => {
  let userARequestResolve;
  let userBLoginCompleted = false;
  let userBTokenUsedForA = false;
  let refreshCalls = 0;

  const env = createEnv(async (url, init) => {
    if (url.endsWith('/auth/me')) {
      const auth = getAuthHeader(init);
      if (auth === 'Bearer user-b-token') {
        if (userBLoginCompleted) {
          userBTokenUsedForA = true;
        }
        return new Response(
          JSON.stringify({ id: 'ub', email: 'userb@test.com', role: 'TRADER', is_active: true }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      return new Promise((resolve) => {
        userARequestResolve = () =>
          resolve(new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 }));
      });
    }
    if (url.endsWith('/auth/logout')) {
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }
    if (url.endsWith('/auth/login')) {
      return new Response(
        JSON.stringify({
          access_token: 'user-b-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/refresh')) {
      refreshCalls++;
      return new Response(
        JSON.stringify({
          access_token: 'new-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200 },
      );
    }
    return new Response('Not found', { status: 404 });
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('user-a-token', '2030-01-01T00:00:00Z');

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  coordinator.getState().status = 'authenticated';

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api', coordinator);

  // 1. User A request starts in epoch 1
  const userAReqPromise = api.getMe().catch((err) => err);

  // 2. User A logs out -> epoch 2
  await coordinator.logout();

  // 3. User B logs in -> epoch 3, token = user-b-token
  await coordinator.login('userb@test.com', 'password123');
  userBLoginCompleted = true;
  assert.equal(mem.getAccessToken(), 'user-b-token');
  assert.equal(coordinator.getState().status, 'authenticated');

  // 4. User A request finally returns 401
  userARequestResolve();
  await userAReqPromise;

  // Assert: User B token was NEVER used to retry User A request
  assert.equal(userBTokenUsedForA, false, 'User B token must NEVER be used to retry User A request');
  assert.equal(refreshCalls, 0, 'Zero refresh calls caused by User A request');
  assert.equal(mem.getAccessToken(), 'user-b-token', 'User B token must remain intact');
  assert.equal(coordinator.getState().status, 'authenticated', 'User B must remain authenticated');
});

// MANDATORY TEST E: SECOND 401 AFTER EPOCH CHANGE DOES NOT LOG OUT NEW SESSION
test('Mandatory Test E: second 401 arriving after epoch change does NOT clear newer session', async () => {
  let retryResolve;
  let meCount = 0;

  const env = createEnv(async (url, init) => {
    if (url.endsWith('/auth/me')) {
      if (init?.headers?.Authorization === 'Bearer new-user-token') {
        return new Response(
          JSON.stringify({ id: 'u2', email: 'user2@test.com', role: 'TRADER', is_active: true }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        );
      }
      meCount++;
      if (meCount === 1) {
        return new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 });
      }
      // Retry request
      return new Promise((resolve) => {
        retryResolve = () =>
          resolve(new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 }));
      });
    }
    if (url.endsWith('/auth/refresh')) {
      return new Response(
        JSON.stringify({
          access_token: 'same-session-refreshed-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/logout')) {
      return new Response(JSON.stringify({ ok: true }), { status: 200 });
    }
    if (url.endsWith('/auth/login')) {
      return new Response(
        JSON.stringify({
          access_token: 'new-user-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response('Not found', { status: 404 });
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('user1-token', '2030-01-01T00:00:00Z');

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  coordinator.getState().status = 'authenticated';

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api', coordinator);

  // 1. Initial request starts in epoch 1
  const reqPromise = api.getMe().catch((err) => err);

  // Allow first 401 to be processed and refresh to complete, sending the retry request
  await new Promise((r) => setTimeout(r, 20));

  // 2. While retry request is in flight, new user logs in (or logout happens), advancing epoch
  await coordinator.login('user2@test.com', 'password123');
  assert.equal(mem.getAccessToken(), 'new-user-token');

  // 3. Retry request returns 401
  retryResolve();
  await reqPromise;

  // Assert: newer session is NOT cleared
  assert.equal(mem.getAccessToken(), 'new-user-token', 'New user token must NOT be cleared by old request second 401');
  assert.equal(coordinator.getState().status, 'authenticated');
});

// MANDATORY TEST F: CROSS-TAB LOGOUT + LATE 401 (ISOLATED TAB MEMORY)
test('Mandatory Test F: cross-tab logout broadcast advances epoch in Tab B; Tab B late 401 does not refresh', async () => {
  const channelBus = [];
  function createMockBroadcastChannel(name) {
    const chan = {
      name,
      onmessage: null,
      postMessage: (data) => {
        queueMicrotask(() => {
          for (const ch of channelBus) {
            if (ch !== chan && ch.onmessage) {
              ch.onmessage({ data });
            }
          }
        });
      },
      close: () => {
        const idx = channelBus.indexOf(chan);
        if (idx !== -1) channelBus.splice(idx, 1);
      },
    };
    channelBus.push(chan);
    return chan;
  }

  let tabBMeResolve;
  let tabBRefreshCalls = 0;

  // Tab A env
  const tabAEnv = createEnv(async (url) => {
    if (url.endsWith('/auth/logout')) return new Response(JSON.stringify({ ok: true }), { status: 200 });
    return new Response('Not found', { status: 404 });
  }, {
    BroadcastChannel: createMockBroadcastChannel,
  });

  // Tab B env with separate isolated modules map
  const tabBEnv = createEnv(async (url) => {
    if (url.endsWith('/auth/me')) {
      return new Promise((resolve) => {
        tabBMeResolve = () =>
          resolve(new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 }));
      });
    }
    if (url.endsWith('/auth/refresh')) {
      tabBRefreshCalls++;
      return new Response(JSON.stringify({ access_token: 'resurrected-b', token_type: 'bearer', expires_at: '2030-01-01T00:00:00Z' }), { status: 200 });
    }
    return new Response('Not found', { status: 404 });
  }, {
    BroadcastChannel: createMockBroadcastChannel,
  });

  const tabAMem = loadModule('lib/auth-token-memory.ts', tabAEnv);
  tabAMem.setAccessToken('tab-a-token', '2030-01-01T00:00:00Z');
  const { AuthCoordinator: AuthCoordA } = loadModule('lib/auth-coordinator.ts', tabAEnv);
  const coordA = new AuthCoordA('http://test/api');

  const tabBMem = loadModule('lib/auth-token-memory.ts', tabBEnv);
  tabBMem.setAccessToken('tab-b-token', '2030-01-01T00:00:00Z');
  const { AuthCoordinator: AuthCoordB } = loadModule('lib/auth-coordinator.ts', tabBEnv);
  const coordB = new AuthCoordB('http://test/api');
  coordB.getState().status = 'authenticated';

  const { ApiClient: ApiClientB } = loadModule('lib/api.ts', tabBEnv);
  const apiB = new ApiClientB('http://test/api', coordB);

  // 1. Tab B business request starts in epoch 1
  const tabBReqPromise = apiB.getMe().catch((err) => err);

  // 2. Tab A logs out, broadcasting 'logout'
  await coordA.logout();

  // Allow cross-tab broadcast to arrive in Tab B
  await new Promise((r) => setTimeout(r, 15));

  // Tab B should have cleared local memory token and transitioned to unauthenticated
  assert.equal(tabBMem.getAccessToken(), null);
  assert.equal(coordB.getState().status, 'unauthenticated');

  // 3. Tab B old request returns 401
  tabBMeResolve();
  await tabBReqPromise;

  // Assert: Tab B performs 0 refresh, token resurrection = NO
  assert.equal(tabBRefreshCalls, 0, 'Tab B must not issue refresh for obsolete request');
  assert.equal(tabBMem.getAccessToken(), null, 'Tab B token must remain null');
  assert.equal(coordB.getState().status, 'unauthenticated');
});

// NORMAL RECOVERY REGRESSION: SAME-EPOCH 401 REFRESH & RETRY
test('Normal recovery regression: same-epoch 401 triggers single refresh and retries to 200', async () => {
  let meCalls = 0;
  let refreshCalls = 0;

  const env = createEnv(async (url, init) => {
    if (url.endsWith('/auth/me')) {
      meCalls++;
      if (meCalls === 1) {
        assert.equal(getAuthHeader(init), 'Bearer expired-token');
        return new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 });
      }
      assert.equal(getAuthHeader(init), 'Bearer fresh-valid-token');
      return new Response(
        JSON.stringify({ id: 'u-legit', email: 'user@legit.com', role: 'TRADER', is_active: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/refresh')) {
      refreshCalls++;
      return new Response(
        JSON.stringify({
          access_token: 'fresh-valid-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response('Not found', { status: 404 });
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('expired-token', '2030-01-01T00:00:00Z');

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  coordinator.getState().status = 'authenticated';

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api', coordinator);

  const user = await api.getMe();
  assert.equal(user.email, 'user@legit.com');
  assert.equal(refreshCalls, 1);
  assert.equal(meCalls, 2);
  assert.equal(mem.getAccessToken(), 'fresh-valid-token');
});

// IN-TAB SINGLE FLIGHT REGRESSION
test('In-tab single flight regression: 5 concurrent same-epoch 401s produce exactly 1 refresh call', async () => {
  let refreshCalls = 0;

  const env = createEnv(async (url, init) => {
    if (url.endsWith('/auth/me')) {
      if (getAuthHeader(init) === 'Bearer stale-token') {
        return new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 });
      }
      return new Response(
        JSON.stringify({ id: 'u-1', email: 'u@test.com', role: 'TRADER', is_active: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/refresh')) {
      refreshCalls++;
      await new Promise((r) => setTimeout(r, 20));
      return new Response(
        JSON.stringify({
          access_token: 'single-flight-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response('Not found', { status: 404 });
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('stale-token', '2030-01-01T00:00:00Z');

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  coordinator.getState().status = 'authenticated';

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api', coordinator);

  // 5 concurrent requests get 401
  const results = await Promise.all([
    api.getMe(),
    api.getMe(),
    api.getMe(),
    api.getMe(),
    api.getMe(),
  ]);

  assert.equal(results.length, 5);
  assert.equal(refreshCalls, 1, 'Concurrent same-epoch 401s must share exactly 1 refresh call');
  assert.equal(mem.getAccessToken(), 'single-flight-token');
});

// GENERATION CHANGE SAME-EPOCH RETRY
test('Generation change in same epoch retries with fresh token without duplicate refresh', async () => {
  let refreshCalls = 0;

  const env = createEnv(async (url, init) => {
    if (url.endsWith('/auth/me')) {
      if (getAuthHeader(init) === 'Bearer token-gen-1') {
        return new Response(JSON.stringify({ detail: 'Unauthorized' }), { status: 401 });
      }
      return new Response(
        JSON.stringify({ id: 'u-gen', email: 'gen@test.com', role: 'TRADER', is_active: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/refresh')) {
      refreshCalls++;
      return new Response(
        JSON.stringify({
          access_token: 'token-gen-2',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response('Not found', { status: 404 });
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  mem.setAccessToken('token-gen-1', '2030-01-01T00:00:00Z');

  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');
  coordinator.getState().status = 'authenticated';

  const { ApiClient } = loadModule('lib/api.ts', env);
  const api = new ApiClient('http://test/api', coordinator);

  // Simulate that another request refreshed token in the SAME epoch
  const req1Promise = api.getMe();
  await req1Promise;
  assert.equal(refreshCalls, 1);
  assert.equal(mem.getAccessToken(), 'token-gen-2');

  // Next request with initialSnapshot capturing token-gen-1 (before it knew of gen-2)
  // When it gets 401, generation has changed in same epoch, so it uses token-gen-2 without refresh
  const user = await api.getMe();
  assert.equal(user.email, 'gen@test.com');
  assert.equal(refreshCalls, 1, 'No duplicate refresh call needed');
});

// COLD BOOTSTRAP REGRESSION
test('Cold bootstrap succeeds and is not blocked by terminal barrier', async () => {
  const env = createEnv(async (url) => {
    if (url.endsWith('/auth/refresh')) {
      return new Response(
        JSON.stringify({
          access_token: 'bootstrap-token',
          token_type: 'bearer',
          expires_at: '2030-01-01T00:00:00Z',
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/me')) {
      return new Response(
        JSON.stringify({ id: 'u-boot', email: 'boot@test.com', role: 'TRADER', is_active: true }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    return new Response('Not found', { status: 404 });
  });

  const mem = loadModule('lib/auth-token-memory.ts', env);
  const { AuthCoordinator } = loadModule('lib/auth-coordinator.ts', env);
  const coordinator = new AuthCoordinator('http://test/api');

  // Starts idle
  assert.equal(coordinator.getState().status, 'idle');
  const ok = await coordinator.bootstrap();

  assert.equal(ok, true);
  assert.equal(mem.getAccessToken(), 'bootstrap-token');
  assert.equal(coordinator.getState().status, 'authenticated');
  assert.equal(coordinator.getState().user?.email, 'boot@test.com');
});
