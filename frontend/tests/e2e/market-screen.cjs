const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function main() {
  const base = process.env.E2E_BASE_URL;
  const credentials = JSON.parse(fs.readFileSync(process.env.E2E_CREDENTIALS_PATH, 'utf8'));
  const output = process.env.E2E_OUTPUT_DIR;
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
  await context.addInitScript(() => {
    const Original = window.WebSocket;
    window.__marketSockets = [];
    window.WebSocket = class extends Original {
      constructor(...args) { super(...args); window.__marketSockets.push(this); }
    };
  });
  const page = await context.newPage();
  page.setDefaultTimeout(25000);
  const errors = [], failedAssets = [], urls = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('response', response => {
    if (response.url().includes('/_next/') && response.status() >= 400) failedAssets.push(response.status());
  });
  const realtimeCloses = {};
  page.on('websocket', ws => {
    urls.push(ws.url());
    ws.on('framereceived', event => {
      try {
        const frame = JSON.parse(String(event.payload));
        if (frame.type === 'update' && frame.status?.source === 'mt5_demo_iux') {
          const forming = frame.candles.find(c => !c.is_closed);
          if (forming) {
            const values = realtimeCloses[frame.timeframe] ||= [];
            values.push(forming.close);
            if (values.length > 20) values.shift();
          }
        }
      } catch {}
    });
  });
  const real = process.env.E2E_MARKET_SOURCE === 'mt5_demo_iux';
  const result = { source: real ? 'mt5_demo_iux' : 'simulated', history_counts: {} };
  const minimum = timeframe => real && timeframe === 'W1' ? 1 : 300;
  let stage = 'login';
  try {
    await page.goto(base + '/trading');
    await page.waitForURL(url => url.pathname === '/login');
    await page.getByLabel('Email', { exact: true }).fill(credentials.email);
    await page.getByLabel('Password', { exact: true }).fill(credentials.password);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await page.waitForURL(url => url.pathname === '/dashboard');
    result.login = 'PASS';
    stage = 'open_trading';
    await page.locator('a[href="/trading"]').click();
    await page.locator('.market-mode').filter({ hasText: real ? 'REAL MARKET DATA / DEMO CONNECTION' : 'SIMULATED DATA' }).waitFor();
    await page.waitForFunction(() => document.querySelector('[data-testid="connection"]')?.textContent.includes('CONNECTED'));
    await page.waitForFunction(() => Number(document.querySelector('[data-testid="candle-count"]')?.textContent.split(' ')[0]) >= 300);
    assert.equal(await page.locator('#market-symbol').inputValue(), 'XAUUSD');
    assert.ok(await page.locator('.market-chart canvas').count() > 0);
    result.open_trading = result.chart_render = result.historical_candles = 'PASS';
    stage = 'realtime';
    const bid = await page.getByTestId('bid').innerText();
    const update = await page.getByTestId('last-update').innerText();
    await page.waitForFunction(previous => document.querySelector('[data-testid="last-update"]')?.textContent !== previous, update);
    await page.waitForFunction(previous => document.querySelector('[data-testid="bid"]')?.textContent !== previous, bid);
    const spread = Number((await page.getByTestId('spread').innerText()).replaceAll(',', ''));
    if (real) assert.ok(spread >= 0);
    else assert.equal(spread, 0.30);
    const ask = await page.getByTestId('ask').innerText();
    await page.waitForFunction(previous => document.querySelector('[data-testid="ask"]')?.textContent !== previous, ask);
    result.realtime_quote_and_candle = 'PASS';
    // Verify a timeframe change reuses the chart's actual DOM/canvas instance.
    await page.locator('.market-chart canvas').first().evaluate(el => { el.dataset.lifecycle = 'original'; });
    stage = 'timeframes';
    for (const timeframe of ['M1', 'M3', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1', 'M5']) {
      realtimeCloses[timeframe] = [];
      const response = page.waitForResponse(r => r.url().includes('/market/candles?') && r.url().includes('timeframe=' + timeframe));
      await page.getByRole('button', { name: timeframe, exact: true }).click();
      const historyResponse = await response;
      assert.equal(historyResponse.status(), 200);
      const history = await historyResponse.json();
      assert.ok(history.candles.length >= minimum(timeframe));
      assert.ok(history.candles.every(c => c.source === result.source));
      result.history_counts[timeframe] = history.candles.length;
      await page.waitForFunction(count => Number(document.querySelector('[data-testid="candle-count"]')?.textContent.split(' ')[0]) >= count, minimum(timeframe));
      await page.waitForFunction(() => document.querySelector('[data-testid="connection"]')?.textContent.includes('CONNECTED'));
      assert.equal(await page.locator('.market-chart canvas').first().getAttribute('data-lifecycle'), 'original');
      if (real) {
        for (let attempt = 0; attempt < 40 && new Set(realtimeCloses[timeframe]).size < 2; attempt++) {
          await page.waitForTimeout(300);
        }
        assert.ok(new Set(realtimeCloses[timeframe]).size >= 2, timeframe + ' must receive moving real forming candles');
      }
    }
    result.timeframes = real ? '9/9 source/history/subscription + moving forming candle PASS' : '9/9 PASS'; result.chart_lifecycle = 'PASS';
    await page.screenshot({ path: path.join(output, 'trading-desktop.png'), fullPage: true });
    stage = 'responsive';
    for (const [name, width, height] of [['tablet', 820, 1180], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height });
      await page.waitForTimeout(400);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      assert.ok(await page.locator('.market-chart').evaluate(el => el.getBoundingClientRect().width > 200));
      await page.screenshot({ path: path.join(output, 'trading-' + name + '.png'), fullPage: true });
    }
    result.responsive = 'Desktop / tablet / mobile PASS';
    await page.setViewportSize({ width: 1440, height: 1080 });
    stage = 'reconnect';
    await page.evaluate(() => window.__marketSockets.filter(ws => ws.readyState === 1).forEach(ws => ws.close()));
    await page.waitForFunction(() => document.querySelector('[data-testid="connection"]')?.textContent.includes('RECONNECTING'));
    await page.waitForFunction(() => document.querySelector('[data-testid="connection"]')?.textContent.includes('CONNECTED'));
    result.reconnect = 'PASS';
    stage = 'reload';
    await page.reload();
    await page.waitForFunction(() => document.querySelector('[data-testid="connection"]')?.textContent.includes('CONNECTED'));
    await page.waitForFunction(() => Number(document.querySelector('[data-testid="candle-count"]')?.textContent.split(' ')[0]) >= 300);
    result.reload_session_recovery = 'PASS';
    assert.ok(urls.every(url => !url.includes('?') && !url.includes(credentials.password)));
    result.ws_auth_url = 'No token in URL';
    result.console_errors = errors.length;
    result.failed_critical_assets = failedAssets.length;
    assert.equal(errors.length, 0, errors.join('; '));
    assert.equal(failedAssets.length, 0);
    await page.getByTitle('Logout', { exact: true }).click();
    await page.waitForURL(url => url.pathname === '/login');
    result.logout = 'PASS';
    result.history_300_all_timeframes = Object.values(result.history_counts).every(count => count >= 300);
    result.status = result.history_300_all_timeframes ? 'PASS' : 'PARTIAL — real history below 300';
  } catch (error) {
    result.status = 'FAIL'; result.stage = stage;
    result.error = String(error.message).replaceAll(credentials.password, '[redacted]').split('\n')[0];
    result.runtime_errors = errors.map(text => text.replaceAll(credentials.password, '[redacted]'));
    await page.screenshot({ path: path.join(output, 'trading-failure.png'), fullPage: true });
    process.exitCode = 1;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(output, 'market-browser-results.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
  }
}
main().catch(() => { console.error('Market browser setup failed; inspect local configuration.'); process.exitCode = 1; });
