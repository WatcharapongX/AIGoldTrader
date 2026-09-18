const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function main(){
 const out=process.env.E2E_OUTPUT_DIR;fs.mkdirSync(out,{recursive:true});
 const browser=await chromium.launch({headless:true});
 const credentials=JSON.parse(fs.readFileSync(process.env.E2E_CREDENTIALS_PATH,'utf8'));
 const result={pages:[],errors:[],assets:[]};
 let stage='login'; let activePage;
 try{
  const page=await browser.newPage();activePage=page;
  page.on('pageerror',e=>result.errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')result.errors.push(m.text())});
  page.on('response',r=>{if(r.status()>=400&&(r.url().includes('/_next/')||r.url().includes('/images/')))result.assets.push(r.status()+' '+r.url())});
  page.setDefaultTimeout(60000);
  const base=process.env.E2E_BASE_URL||'http://localhost:3001';
  await page.goto(base+'/login');
  const illustration=await page.request.get(base+'/images/login-bg.jpg');
  assert.equal(illustration.status(),200);
  assert.match(illustration.headers()['content-type'],/image/);
  for(const width of [1440,820,390]){
   await page.setViewportSize({width,height:1000});
   await page.getByLabel('Username',{exact:true}).waitFor();
   await page.getByTestId('trading-status').filter({hasText:'PAPER'}).waitFor();
   const body=await page.locator('body').innerText();
   assert.doesNotMatch(body,/3,642.18|12.35|AI-Powered|high-probability/);
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   await page.screenshot({path:path.join(out,'login-'+width+'.png'),fullPage:true});
   result.pages.push({page:'login',width,status:'PASS'});
  }
  await page.getByLabel('Username',{exact:true}).fill(credentials.email);
  await page.getByLabel('Password',{exact:true}).fill(credentials.password);
  await page.getByRole('button',{name:'Sign In',exact:true}).click();
  await page.waitForURL(u=>u.pathname==='/dashboard');
  await page.locator('header').getByTestId('trading-status').filter({hasText:'PAPER'}).waitFor();
  for(const route of ['dashboard','trading','analysis']){
   stage=route;
   const summaryResponse=route==='dashboard'?page.waitForResponse(r=>new URL(r.url()).pathname==='/api/dashboard/summary'&&r.status()===200):null;
   await page.goto(base+'/'+route);
   if(summaryResponse)await summaryResponse;
   await page.locator('header').getByTestId('trading-status').filter({hasText:'PAPER'}).waitFor();
   await page.locator('header').getByText('Auto Trading: OFF',{exact:true}).waitFor();
   if(route==='dashboard'){
    await page.getByTestId('quote-provenance').filter({hasText:/mt5|simulated/}).waitFor();
    await page.getByText(/^M5 candle:.*(CLOSED|FORMING)/).waitFor();
    await page.locator('img').evaluateAll(images=>Promise.all(images.map(img=>img.decode())));
   }
   if(route==='trading')await page.locator('.strategy-workspace').waitFor();
   if(route==='analysis')await page.getByTestId('analysis-summary').waitFor();
   for(const width of [1440,820,390]){
    await page.setViewportSize({width,height:1000});
    await page.locator('header').getByTestId('trading-status').waitFor();
    await page.evaluate(()=>{window.scrollTo(0,0);document.querySelector('main').scrollTop=0;});
    const body=await page.locator('body').innerText();
    assert.doesNotMatch(body,/AI Trading Signal|AI Confidence|Live Mode|12,450.32|57,321|68% Bullish|Coming in Phase 3/);
    const overflow=await page.evaluate(()=>({document:document.documentElement.scrollWidth>innerWidth,main:document.querySelector('main').scrollWidth>document.querySelector('main').clientWidth+1}));
    assert.deepEqual(overflow,{document:false,main:false},route+' '+width+' overflow');
    await page.screenshot({path:path.join(out,route+'-'+width+'.png'),fullPage:true});
    result.pages.push({page:route,width,status:'PASS'});
   }
  }
  assert.deepEqual(result.errors,[]);assert.deepEqual(result.assets,[]);
  // A separate, explicitly failed-data scenario must never display fake values.
  stage='unavailable';
  const failures=await browser.newPage();activePage=failures;
  await failures.context().addCookies(await page.context().cookies());
  await failures.route('**/api/**',route=>{
   const p=new URL(route.request().url()).pathname;
   if(['/api/dashboard/summary','/api/healthz','/api/readyz','/api/market/status'].includes(p))
    return route.fulfill({status:503,contentType:'application/json',body:'{}'});
   return route.continue();
  });
  await failures.routeWebSocket('**/ws/market',socket=>socket.close());
  await failures.goto(base+'/dashboard');
  await failures.getByTestId('dashboard').waitFor({timeout:60000});
  await failures.getByTestId('dashboard').getByRole('alert').waitFor({timeout:60000});
  const failedBody=await failures.locator('body').innerText();
  assert.match(failedBody,/Trading: UNKNOWN/);assert.match(failedBody,/Auto Trading: UNKNOWN/);
  assert.match(failedBody,/Setup Score/);assert.doesNotMatch(failedBody,/Live Market Data|12,450|3,642|HEALTHY/);
  await failures.screenshot({path:path.join(out,'unavailable.png'),fullPage:true});
  result.unavailable='PASS';result.status='PASS';
 }catch(e){if(activePage){result.body=await activePage.locator('body').innerText().catch(()=>'');await activePage.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});}result.status='FAIL';result.stage=stage;result.error=e.message;throw e}
 finally{fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2));await browser.close()}
 console.log(JSON.stringify(result));
}
main().catch(e=>{console.error(e.message);process.exit(1)});
