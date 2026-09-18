const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function main(){
 const out=process.env.E2E_OUTPUT_DIR;fs.mkdirSync(out,{recursive:true});
 const credentials=JSON.parse(fs.readFileSync(process.env.E2E_CREDENTIALS_PATH,'utf8'));
 const browser=await chromium.launch({headless:true});
 const page=await browser.newPage({viewport:{width:1440,height:1100}});
 page.setDefaultTimeout(40000);
 const errors=[],assets=[],apiErrors=[],results={screenshots:[],views:{}};
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 page.on('response',r=>{if(r.url().includes('/_next/')&&r.status()>=400)assets.push(r.status());
   if((r.url().includes('/news/')||r.url().includes('/calendar/economic'))&&r.status()>=400)apiErrors.push(r.status());});
 let stage='login';
 try{
  await page.goto(process.env.E2E_BASE_URL+'/trading');
  await page.waitForURL(u=>u.pathname==='/login');
  await page.getByLabel('Email',{exact:true}).fill(credentials.email);
  await page.getByLabel('Password',{exact:true}).fill(credentials.password);
  await page.getByRole('button',{name:'Sign In',exact:true}).click();
  await page.waitForURL(u=>u.pathname==='/dashboard');
  await page.locator('a[href="/trading"]').click();
  await page.getByTestId('news-regime').waitFor();
  await page.getByTestId('analysis-summary').waitFor();
  const panel=page.getByTestId('news-panel');
  assert.match(await panel.innerText(),/DEMO NEWS DATA/);
  assert.match(await panel.innerText(),/mt5_demo_iux/);
  assert.ok(Number((await page.getByTestId('bid').innerText()).replace(/,/g,''))>0);
  for(const [view,expected] of [['pre','PRE_NEWS'],['release','RELEASE'],['post','POST_NEWS_CONFIRMATION'],['none','NORMAL']]){
   stage=view;
   const response=page.waitForResponse(r=>r.url().includes('/news/context?view='+view));
   await page.getByLabel('มุมมองสาธิต',{exact:true}).selectOption(view);
   const payload=await (await response).json();
   assert.equal(payload.news_regime,expected);
   await page.waitForFunction(v=>document.querySelector('[data-testid="news-panel"] select')?.value===v &&
     !document.querySelector('[data-testid="news-panel"]')?.textContent.includes('กำลังโหลดข้อมูลข่าว'),view);
   if(view==='pre')assert.ok(payload.events.filter(e=>e.scheduled_at>payload.as_of).every(e=>e.actual===null));
   results.views[view]={regime:payload.news_regime,mode:payload.source_mode,market_source:payload.market_source,
     fingerprint:payload.fingerprint,reaction:payload.reaction_state,spread:payload.spread_state};
  }
  await page.getByLabel('มุมมองสาธิต',{exact:true}).selectOption('post');
  await page.waitForResponse(r=>r.url().includes('/news/context?view=post'));
  for(const [name,width,height] of [['desktop',1440,1100],['tablet',820,1100],['mobile',390,844]]){
   stage='trading-'+name;await page.setViewportSize({width,height});
   await panel.scrollIntoViewIfNeeded();
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   const file=path.join(out,'trading-news-'+name+'.png');
   await page.screenshot({path:file});results.screenshots.push(file);
  }
  stage='calendar';await page.setViewportSize({width:1440,height:1100});
  await page.goto(process.env.E2E_BASE_URL+'/calendar');
  await page.locator('.calendar-event').first().waitFor();
  assert.match(await page.locator('.calendar-workspace').innerText(),/DEMO NEWS DATA/);
  await page.locator('.news-event-link').first().click();
  await page.getByRole('region',{name:'ประวัติปรับปรุงข่าว'}).waitFor();
  assert.match(await page.locator('.news-revisions').innerText(),/รุ่น 1/);
  await page.getByRole('button',{name:'ปิดรายละเอียด'}).click();
  for(const [name,width,height] of [['desktop',1440,1100],['tablet',820,1100],['mobile',390,844]]){
   stage='calendar-'+name;await page.setViewportSize({width,height});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   const file=path.join(out,'calendar-'+name+'.png');await page.screenshot({path:file});results.screenshots.push(file);
  }
  await page.getByLabel('สกุลเงิน',{exact:true}).selectOption('EUR');
  await page.getByTestId('calendar-empty').waitFor();
  results.empty_filter='PASS';
  assert.deepEqual(errors,[]);assert.deepEqual(assets,[]);assert.deepEqual(apiErrors,[]);
  results.status='PASS';results.console_errors=errors.length;results.asset_errors=assets.length;results.api_errors=apiErrors.length;
 }catch(error){results.status='FAIL';results.stage=stage;results.error=error.message;results.errors=errors;results.api_errors=apiErrors;
   await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});process.exitCode=1;
 }finally{
   await page.evaluate(async()=>{await fetch('http://localhost:8000/api/auth/logout',{method:'POST',credentials:'same-origin'}).catch(()=>{});}).catch(()=>{});
  await browser.close();fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(results));
 }
}
main().catch(()=>{console.error('News browser acceptance failed');process.exitCode=1;});
