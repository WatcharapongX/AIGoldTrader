const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function main(){
 const out=process.env.E2E_OUTPUT_DIR;fs.mkdirSync(out,{recursive:true});
 const credentials=JSON.parse(fs.readFileSync(process.env.E2E_CREDENTIALS_PATH,'utf8'));
 const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:1440,height:1100}});
 page.setDefaultTimeout(60000);
 const errors=[],assets=[],results={screenshots:[]};let stage='login',activeSockets=0,maximumSockets=0,latest=null;const quotes=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 page.on('response',async r=>{
  if(r.status()>=400&&r.url().includes('/_next/'))assets.push(r.status());
  if(r.url().includes('/api/dashboard/summary')&&r.status()===200)latest=await r.json().catch(()=>null);
 });
 page.on('websocket',socket=>{activeSockets++;maximumSockets=Math.max(maximumSockets,activeSockets);socket.on('close',()=>activeSockets--);
  socket.on('framereceived',frame=>{try{const v=JSON.parse(String(frame.payload));if(v.quote){quotes.push(v.quote);if(quotes.length>100)quotes.shift();}}catch{}});});
 try{
  await page.goto(process.env.E2E_BASE_URL+'/dashboard');await page.waitForURL(u=>u.pathname==='/login');
  await page.getByLabel('Email',{exact:true}).fill(credentials.email);await page.getByLabel('Password',{exact:true}).fill(credentials.password);
  await page.getByRole('button',{name:'Sign In',exact:true}).click();await page.waitForURL(u=>u.pathname==='/dashboard');
  stage='dashboard';
  await page.waitForFunction(()=>document.querySelectorAll('.dc-strategies article').length===6);
  assert.equal(await page.locator('.dc-profiles>div').count(),7);
  assert.ok(await page.getByTestId('dashboard-event').count()>=5);
  assert.match(await page.getByTestId('dashboard').innerText(),/REAL.*ข่าวจริง/);
  assert.match(await page.getByTestId('dashboard').innerText(),/Forex Factory/);
  assert.ok(latest);assert.equal(latest.news_provider.source_mode,'LIVE');
  const cards=page.getByTestId('dashboard-event');
  for(let i=0;i<latest.calendar_events.length;i++){
    const e=latest.calendar_events[i],text=await cards.nth(i).innerText();
    assert.ok(text.includes(e.currency));
    assert.ok(text.includes(Number(e.forecast).toLocaleString('en-US',{maximumFractionDigits:4})) ||
      text.includes(String(e.forecast)),'Forecast displayed from canonical API');
  }
  results.forecast_rows_crosschecked=latest.calendar_events.length;
  assert.equal(latest.current_plan,null);
  assert.equal(await page.locator('[aria-label="โครงสร้างตลาด"] .dc-structure article').count(),4);
  for(const [name,width,height] of [['desktop',1440,1100],['tablet',820,1100],['mobile',390,844]]){
   await page.setViewportSize({width,height});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   for(const [region,selector] of [['market','[aria-label="ราคาตลาด"]'],['news','[aria-label="ข่าวเศรษฐกิจ"]'],['strategies','[aria-label="สรุปกลยุทธ์"]'],['health','[aria-label="สุขภาพระบบ"]']]){
    await page.locator(selector).scrollIntoViewIfNeeded();const file=path.join(out,'dashboard-'+name+'-'+region+'.png');
    await page.screenshot({path:file});results.screenshots.push(file);
   }
  }
  await page.setViewportSize({width:1440,height:1100});
  await page.getByTestId('dashboard-bid').scrollIntoViewIfNeeded();
  const visibleBid=await page.getByTestId('dashboard-bid').innerText();
  assert.ok(quotes.some(q=>q.bid===visibleBid&&q.source==='mt5_demo_iux'),'Dashboard bid equals canonical MT5 WebSocket quote');
  results.dashboard_quote_websocket_crosscheck=true;
  stage='trading';await page.locator('a[href="/trading"]').first().click();
  await page.getByTestId('strategy-no-trade').waitFor();await page.getByTestId('news-provider-health').waitFor();
  assert.match(await page.getByTestId('news-provider-health').innerText(),/forex_factory/);
  assert.match(await page.getByTestId('news-panel').innerText(),/STRAT05–06/);
  for(const [name,width,height] of [['desktop',1440,1100],['tablet',820,1100],['mobile',390,844]]){
   await page.setViewportSize({width,height});await page.getByTestId('news-provider-health').scrollIntoViewIfNeeded();
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   await page.screenshot({path:path.join(out,'trading-'+name+'.png')});
  }
  stage='calendar';await page.locator('a[href="/calendar"]').first().click();
  await page.getByLabel('วันที่ข่าว').fill('2026-09-11');
  await page.getByRole('button',{name:'CPI m/m',exact:true}).waitFor();
  assert.match(await page.locator('.calendar-events').innerText(),/19:30/);
  assert.match(await page.locator('.calendar-events').innerText(),/0.4/);
  await page.getByRole('button',{name:'CPI m/m',exact:true}).click();
  await page.getByRole('region',{name:'ประวัติปรับปรุงข่าว'}).waitFor();
  await page.screenshot({path:path.join(out,'calendar-real.png')});
  stage='navigation cleanup';await page.locator('a[href="/dashboard"]').first().click();
  await page.waitForFunction(()=>document.querySelectorAll('.dc-strategies article').length===6);
  await page.reload();await page.waitForFunction(()=>document.querySelectorAll('.dc-strategies article').length===6);
  assert.deepEqual(errors,[]);assert.deepEqual(assets,[]);
  assert.ok(maximumSockets<=2); // old socket close handshake can overlap a route mount.
  results.status='PASS';results.console_errors=0;results.asset_errors=0;results.viewports=['1440','820','390'];
  results.real_news=true;results.cpi_bangkok_time='19:30';results.no_fake_plan=true;
  results.active_sockets_after_reload=activeSockets;results.maximum_sockets_during_navigation=maximumSockets;
 }catch(e){results.status='FAIL';results.stage=stage;results.error=e.message;results.errors=errors;
  await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});process.exitCode=1;
 }finally{
  await page.evaluate(async()=>{const token=localStorage.getItem('access_token');if(token)await fetch('http://localhost:8000/api/auth/logout',
   {method:'POST',headers:{Authorization:'Bearer '+token}}).catch(()=>{});}).catch(()=>{});
  await browser.close();fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
 }
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
