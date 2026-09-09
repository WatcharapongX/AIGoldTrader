const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

async function main() {
  const output = process.env.E2E_OUTPUT_DIR;
  fs.mkdirSync(output, { recursive: true });
  const credentials = JSON.parse(fs.readFileSync(process.env.E2E_CREDENTIALS_PATH, 'utf8'));
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  await context.addInitScript(() => {
    const Original = window.WebSocket;
    window.__analysisSockets = [];
    window.WebSocket = class extends Original {
      constructor(...args) { super(...args); window.__analysisSockets.push(this); }
    };
  });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);
  const errors = [], failedAssets = [], payloads = {}, candles = {};
  let analysisRequests = 0, stage = 'login';
  const result = { source:'mt5_demo_iux', timeframes:{}, screenshots:[] };
  page.on('pageerror', e => errors.push(e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('response', async response => {
    const url = new URL(response.url());
    if (url.pathname.includes('/_next/') && response.status() >= 400) failedAssets.push(response.status());
    if (url.pathname.endsWith('/analysis/structure')) {
      analysisRequests++;
      if (response.ok()) payloads[url.searchParams.get('timeframe')] = await response.json().catch(() => null);
    }
    if (url.pathname.endsWith('/market/candles') && response.ok()) {
      candles[url.searchParams.get('timeframe')] = await response.json().catch(() => null);
    }
  });
  const ready = async tf => {
    await page.waitForFunction(timeframe => {
      const value = document.querySelector('[data-testid="analysis-summary"]');
      return value && document.querySelector('.analysis-version')?.textContent.includes(timeframe);
    }, tf);
    assert.equal(payloads[tf].source, 'mt5_demo_iux');
    assert.equal(payloads[tf].timeframe, tf);
    assert.ok(payloads[tf].as_of);
  };
  try {
    await page.goto(process.env.E2E_BASE_URL + '/trading');
    await page.waitForURL(url => url.pathname === '/login');
    await page.getByLabel('Email', { exact:true }).fill(credentials.email);
    await page.getByLabel('Password', { exact:true }).fill(credentials.password);
    await page.getByRole('button', { name:'Sign In', exact:true }).click();
    await page.waitForURL(url => url.pathname === '/dashboard');
    await page.locator('a[href="/trading"]').first().click();
    await ready('M5');
    await page.locator('.market-chart canvas').first().evaluate(el => { el.dataset.phase3 = 'original'; });
    for (const tf of ['M5','M1','M3','M15','M30','H1','H4','D1','W1']) {
      stage = 'timeframe-' + tf;
      if (tf !== 'M5') await page.getByRole('button', { name:tf, exact:true }).click();
      await ready(tf);
      const value = payloads[tf];
      assert.equal(value.history.requested, 300);
      assert.equal(value.history.returned, tf === 'W1' ? 231 : 300);
      assert.equal(value.history.status, tf === 'W1' ? 'PARTIAL' : 'COMPLETE');
      assert.ok(value.history.closed >= (tf === 'W1' ? 230 : 299));
      assert.notEqual(value.modules.external_structure.status, 'INSUFFICIENT_DATA');
      assert.ok(value.swings.length && value.liquidity.length);
      assert.equal(await page.locator('.market-chart canvas').first().getAttribute('data-phase3'), 'original');
      assert.equal(await page.locator('.analysis-timeframes>div').count(), 9);
      assert.ok((await page.getByTestId('context-W1').innerText()).includes('PARTIAL'));
      for (const item of [...value.swings, ...value.events, ...value.zones, ...value.liquidity]) {
        assert.ok(Date.parse(item.confirmed_at) <= Date.parse(value.as_of));
      }
      result.timeframes[tf] = { history:value.history, states:[value.internal_state,value.external_state],
        swings:value.swings.length, events:value.events.length, liquidity:value.liquidity.length,
        zones:value.zones.length, as_of:value.as_of, version:value.algorithm_version, input_id:value.input_id };
      if (['M15','H1','W1'].includes(tf)) {
        for (const name of ['MSS','FVG','OB','Premium / Discount']) {
          const button = page.getByRole('button', { name, exact:true });
          if (await button.getAttribute('aria-pressed') === 'false') await button.click();
        }
        await page.locator('.chart-panel').scrollIntoViewIfNeeded();
        const file = tf + '-desktop.png';
        await page.screenshot({ path:path.join(output,file), fullPage:true });
        result.screenshots.push(file);
      }
    }
    stage = 'toggles';
    const buttons = page.getByRole('group', { name:'Chart overlays' }).getByRole('button');
    for (const button of await buttons.all()) if (await button.getAttribute('aria-pressed') === 'true') await button.click();
    assert.equal(await page.getByTestId('analysis-summary').getAttribute('data-shapes'), '0');
    for (const button of await buttons.all()) await button.click();
    assert.ok(Number(await page.getByTestId('analysis-summary').getAttribute('data-shapes')) > 0);
    result.toggles = 'PASS';
    stage = 'reload';
    const before = payloads.W1;
    await page.reload();
    await ready('M5');
    await page.getByRole('button', { name:'W1', exact:true }).click();
    await ready('W1');
    assert.equal(payloads.W1.input_id, before.input_id);
    assert.deepEqual(payloads.W1.swings, before.swings);
    assert.deepEqual(payloads.W1.events, before.events);
    result.reload_same_input = 'PASS';
    stage = 'mobile';
    await page.setViewportSize({ width:390, height:844 });
    await page.locator('.analysis-workspace').scrollIntoViewIfNeeded();
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({ path:path.join(output,'W1-mobile.png'), fullPage:true });
    result.screenshots.push('W1-mobile.png'); result.mobile = 'PASS';
    stage = 'reconnect';
    await page.evaluate(() => window.__analysisSockets.at(-1)?.close());
    await page.waitForFunction(() => document.querySelector('[data-testid="connection"]')?.textContent.includes('CONNECTED'));
    await ready('W1');
    result.reconnect = 'PASS';
    stage = 'closed-refresh';
    await page.getByRole('button', { name:'M1', exact:true }).click();
    await ready('M1');
    const asOf = payloads.M1.as_of;
    const initialRequests = analysisRequests;
    await page.waitForTimeout(2500);
    // Forming ticks do not cause structure REST refresh; crossing a close boundary may cause exactly one.
    assert.ok(analysisRequests - initialRequests <= 1);
    await page.waitForFunction(old => {
      const text = document.querySelector('[data-testid="analysis-as-of"]')?.textContent;
      return text && !text.includes(old);
    }, asOf, { timeout:75000 });
    await ready('M1');
    assert.ok(Date.parse(payloads.M1.as_of) > Date.parse(asOf));
    result.closed_bar_refresh = 'PASS';
    assert.equal(errors.length, 0); assert.equal(failedAssets.length, 0);
    result.console_errors = errors; result.failed_assets = failedAssets; result.status = 'PASS';
    fs.writeFileSync(path.join(output,'analysis-payloads.json'),JSON.stringify({ payloads,candles },null,2));
    fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify(result,null,2));
    console.log(JSON.stringify(result));
  } catch (error) {
    await page.screenshot({ path:path.join(output,'failure.png'),fullPage:true }).catch(() => {});
    fs.writeFileSync(path.join(output,'browser-results.json'),JSON.stringify({ ...result,status:'FAIL',stage,
      reason:error.message,errors,failedAssets },null,2));
    throw new Error(stage + ': ' + error.message);
  } finally {
    await page.evaluate(async () => {
      const token = localStorage.getItem('access_token');
      if (token) await fetch('/api/auth/logout', { method:'POST',headers:{ Authorization:'Bearer ' + token } });
    }).catch(() => {});
    await browser.close();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
