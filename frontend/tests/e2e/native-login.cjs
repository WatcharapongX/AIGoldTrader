/* Native browser acceptance: uses installed Playwright, real API and PostgreSQL. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function main() {
  const baseURL = process.env.E2E_BASE_URL;
  const credentials = JSON.parse(fs.readFileSync(process.env.E2E_CREDENTIALS_PATH, 'utf8'));
  const output = process.env.E2E_OUTPUT_DIR;
  assert.ok(baseURL && output);
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.setDefaultTimeout(15000);
  const pageErrors = [];
  const failedAssets = [];
  const results = {};
  let stage = 'initial_login';
  page.on('pageerror', () => pageErrors.push('browser_runtime_error'));
  page.on('response', (response) => {
    if (response.url().includes('/_next/') && response.status() >= 400) failedAssets.push(response.status());
  });
  try {
    await page.goto(baseURL + '/dashboard');
    await page.waitForURL(url => url.pathname === '/login');
    results.protected_redirect = 'PASS';
    await page.getByLabel('Email', { exact: true }).fill(credentials.email);
    await page.getByLabel('Password', { exact: true }).fill('incorrect-test-password');
    const failedLogin = page.waitForResponse(r => r.url().endsWith('/api/auth/login'));
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    assert.equal((await failedLogin).status(), 401);
    await page.getByText('Invalid email or password', { exact: true }).waitFor();
    results.invalid_password = 'PASS';
    stage = 'successful_login';
    await page.getByLabel('Password', { exact: true }).fill(credentials.password);
    const login = page.waitForResponse(r => r.url().endsWith('/api/auth/login'));
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    const loginResponse = await login;
    assert.equal(loginResponse.status(), 200);
    results.login_correlation_id = loginResponse.headers()['x-correlation-id'];
    await page.waitForURL(url => url.pathname === '/dashboard');
    await page.getByText('Market data not connected', { exact: true }).waitFor();
    assert.ok(await page.evaluate(() => Boolean(localStorage.getItem('access_token') && localStorage.getItem('refresh_token'))));
    assert.ok((await page.context().cookies()).some(c => c.name === 'access_token'));
    results.login_authenticated_shell = 'PASS';
    await page.screenshot({ path: path.join(output, 'dashboard.png'), fullPage: true });
    stage = 'session_reload';
    await page.reload();
    await page.getByText('Market data not connected', { exact: true }).waitFor();
    results.session_reload = 'PASS';
    stage = 'token_refresh';
    await page.evaluate(() => localStorage.setItem('access_token', 'expired-test-access-token'));
    const refresh = page.waitForResponse(r => r.url().endsWith('/api/auth/refresh'));
    await page.reload();
    assert.equal((await refresh).status(), 200);
    await page.getByText('Market data not connected', { exact: true }).waitFor();
    results.token_refresh = 'PASS';
    stage = 'logout';
    // Click the real UI control: do not call the store or endpoint to bypass it.
    const logout = page.waitForResponse(r => r.url().endsWith('/api/auth/logout'));
    await page.getByTitle('Logout', { exact: true }).click();
    assert.equal((await logout).status(), 200);
    await page.waitForURL(url => url.pathname === '/login');
    assert.ok(await page.evaluate(() => !localStorage.getItem('access_token') && !localStorage.getItem('refresh_token')));
    assert.ok(!(await page.context().cookies()).some(c => c.name === 'access_token'));
    await page.goto(baseURL + '/dashboard');
    await page.waitForURL(url => url.pathname === '/login');
    results.logout_and_session_clear = 'PASS';
    assert.equal(pageErrors.length, 0);
    assert.equal(failedAssets.length, 0);
    results.browser_errors = 0;
    results.failed_assets = 0;
    results.status = 'PASS';
  } catch (error) {
    results.error_kind = error.name;
    results.error_summary = String(error.message).replaceAll(credentials.password, "[redacted]").split("\n")[0];
    results.current_path = new URL(page.url()).pathname;
    results.status = 'FAIL';
    results.failed_stage = stage;
    await page.screenshot({ path: path.join(output, 'failure.png'), fullPage: true });
    process.exitCode = 1;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(output, 'browser-results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results)); // Never print credentials, token bodies or browser storage.
  }
}
main().catch(() => { console.error('Browser gate setup failed; inspect configuration locally.'); process.exitCode = 1; });
