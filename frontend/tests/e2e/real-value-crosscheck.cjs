/* Capture only canonical app values; raw provider comparison is done via official Python SDK. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
async function main() {
  const credentials = JSON.parse(fs.readFileSync(process.env.E2E_CREDENTIALS_PATH, 'utf8'));
  const output = process.env.E2E_OUTPUT_DIR;
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  const frames = [];
  page.on('websocket', ws => ws.on('framereceived', event => {
    try {
      const frame = JSON.parse(String(event.payload));
      if (frame.quote?.source === 'mt5_demo_iux') {
        frames.push(frame);
        if (frames.length > 100) frames.shift();
      }
    } catch {}
  }));
  try {
    await page.goto(process.env.E2E_BASE_URL + '/login');
    await page.getByLabel('Email', { exact: true }).fill(credentials.email);
    await page.getByLabel('Password', { exact: true }).fill(credentials.password);
    await page.getByRole('button', { name: 'Sign In', exact: true }).click();
    await page.waitForURL(url => url.pathname === '/dashboard');
    await page.locator('a[href="/trading"]').click();
    await page.waitForFunction(() => document.querySelector('[data-testid="connection"]')?.textContent.includes('CONNECTED'));
    const samples = [];
    let initialChart;
    for (let i = 0; i < 5; i++) {
      await page.waitForTimeout(1100);
      const visible = await page.evaluate(() => {
        const text = name => document.querySelector('[data-testid="' + name + '"]')?.textContent;
        return { bid: text('bid'), ask: text('ask'), spread: text('spread'), timestamp: text('last-update') };
      });
      const price = v => Number(v.replaceAll(',', ''));
      const frame = [...frames].reverse().find(f => Number(f.quote.bid) === price(visible.bid) &&
        Number(f.quote.ask) === price(visible.ask) && Number(f.quote.spread) === price(visible.spread));
      assert.ok(frame, 'Visible quote must equal a canonical WebSocket quote');
      assert.equal(frame.quote.mode, 'DEMO');
      assert.equal(frame.status.source, 'mt5_demo_iux');
      const time = new Date(frame.quote.timestamp).toISOString().slice(11, 19) + ' UTC';
      assert.equal(visible.timestamp, time);
      samples.push({ visible, quote: frame.quote, closed_candle: frame.candles.find(c => c.is_closed) || null,
        forming_candle: frame.candles.find(c => !c.is_closed) || null });
      if (i === 0) initialChart = await page.locator('.market-chart').screenshot();
    }
    assert.ok(new Set(samples.map(s => s.quote.timestamp)).size >= 2);
    assert.ok(samples.some(s => s.closed_candle));
    assert.ok(new Set(samples.map(s => s.forming_candle?.close)).size >= 2, 'Authoritative forming candle must move');
    const finalChart = await page.locator('.market-chart').screenshot();
    assert.ok(!initialChart.equals(finalChart), 'Rendered chart pixels must change with real candle data');
    fs.writeFileSync(path.join(output, 'chart-before.png'), initialChart);
    fs.writeFileSync(path.join(output, 'chart-after.png'), finalChart);
    await page.screenshot({ path: path.join(output, 'real-values-desktop.png'), fullPage: true });
    fs.writeFileSync(path.join(output, 'ui-observed.json'), JSON.stringify({ status: 'APP_FLOW_PASS', samples }, null, 2));
    await page.getByTitle('Logout', { exact: true }).click();
    await page.waitForURL(url => url.pathname === '/login');
    console.log('Canonical WS -> visible UI: 5 samples PASS; awaiting direct SDK cross-check.');
  } finally { await browser.close(); }
}
main().catch(() => { console.error('Real value capture failed; no credentials logged.'); process.exitCode = 1; });
