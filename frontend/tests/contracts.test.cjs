const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const contract = require('./fixtures/api-contract.json');

function load(file, overrides = {}) {
  const { outputText } = ts.transpileModule(
    fs.readFileSync(path.join(__dirname, '../src', file), 'utf8'),
    { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } },
  );
  const exports = {};
  vm.runInNewContext(outputText, {
    exports, process, Headers, Event,
    require: name => name.startsWith('@/') ? load(name.slice(2) + (name.endsWith('.ts') ? '' : '.ts'), overrides) : require(name),
    ...overrides,
  }, { filename: file });
  return exports;
}
const parsers = load('lib/contracts.ts');
function sample(schema) {
  if (schema.$ref) return sample(contract.schemas[schema.$ref.split('/').pop()]);
  if (schema.anyOf) return sample(schema.anyOf.at(-1));
  if (schema.enum) return schema.enum[0];
  if ('const' in schema) return schema.const;
  if ('default' in schema) return schema.default;
  if (schema.type === 'object') return Object.fromEntries(
    Object.entries(schema.properties).map(([key, child]) => [key, sample(child)]),
  );
  if (schema.type === 'string') return schema.format === 'date-time' ? '2030-01-01T00:00:00Z' : 'fixture';
  if (schema.type === 'boolean') return false;
  if (schema.type === 'number' || schema.type === 'integer') return 1;
  if (schema.type === 'null') return null;
  throw Error('Uncovered authoritative schema construct');
}
const mappings = {
  MeResponse: 'parseUser', AccessTokenResponse: 'parseAccessTokenResponse',
  HealthResponse: 'parseHealth', ReadyResponse: 'parseReady',
};
for (const [name, parserName] of Object.entries(mappings)) {
  test(name + ' runtime parser accepts the authoritative OpenAPI fixture', () => {
    const fixture = sample(contract.schemas[name]);
    assert.equal(JSON.stringify(parsers[parserName](fixture)), JSON.stringify(fixture));
  });
  test(name + ' rejects missing/wrong required fields without exposing payloads', () => {
    for (const field of contract.schemas[name].required) {
      const missing = sample(contract.schemas[name]);
      delete missing[field];
      assert.throws(() => parsers[parserName](missing), /Invalid API response contract/);
      const malformed = sample(contract.schemas[name]);
      malformed[field] = { secret: 'fixture-sensitive-token' };
      assert.throws(() => parsers[parserName](malformed), error =>
        error.message === 'Invalid API response contract' && !error.message.includes('fixture-sensitive-token'));
    }
  });
}
test('readiness covers enabled/disabled Redis and rejects health-shaped data', () => {
  for (const redis of [true, false, null]) {
    const value = { status: 'not_ready', checks: { database: false, redis }, redis_enabled: redis !== null };
    assert.equal(parsers.parseReady(value).checks.redis, redis);
  }
  assert.throws(() => parsers.parseReady(sample(contract.schemas.HealthResponse)));
  assert.throws(() => parsers.parseReady({ status: 'ready', checks: { database: true }, redis_enabled: false }));
  assert.throws(() => parsers.parseUser({ ...sample(contract.schemas.MeResponse), role: 'OWNER' }));
});
test('endpoint methods validate real response boundaries', async () => {
  const payloads = new Map([
    ['/auth/me', sample(contract.schemas.MeResponse)],
    ['/healthz', sample(contract.schemas.HealthResponse)],
    ['/readyz', sample(contract.schemas.ReadyResponse)],
  ]);
  const { ApiClient } = load('lib/api.ts', {
    fetch: async url => new Response(JSON.stringify(payloads.get(new URL(url).pathname)), { status: 200 }),
  });
  const api = new ApiClient('http://test');
  assert.equal((await api.getMe()).is_active, false);
  assert.equal((await api.healthz()).env, 'fixture');
  assert.equal((await api.readyz()).checks.redis, null);
  payloads.set('/auth/me', { role: 'ADMIN' });
  await assert.rejects(api.getMe(), /Invalid API response contract/);
});
test('invalid token response never writes browser credentials', async () => {
  let writes = 0;
  const { ApiClient } = load('lib/api.ts', {
    window: {}, document: { cookie: '' },
    localStorage: { getItem: () => null, setItem: () => { writes++; } },
    fetch: async () => new Response(JSON.stringify({ access_token: 'fixture-sensitive-token' }), { status: 200 }),
  });
  await assert.rejects(new ApiClient('http://test').login('user@example.com', 'fixture-password'),
    /Invalid API response contract/);
  assert.equal(writes, 0);
});
