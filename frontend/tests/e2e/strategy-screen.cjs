const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
async function main(){
 const out=process.env.E2E_OUTPUT_DIR;fs.mkdirSync(out,{recursive:true});
 const credentials=JSON.parse(fs.readFileSync(process.env.E2E_CREDENTIALS_PATH,'utf8'));
 const browser=await chromium.launch({headless:true}),page=await browser.newPage({viewport:{width:1440,height:1100}});
 page.setDefaultTimeout(60000);
 const errors=[],assets=[],apiErrors=[],result={screenshots:[]};let stage='login';
 page.on('pageerror',e=>errors.push(e.message));
 page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
 page.on('response',r=>{if(r.status()>=400&&r.url().includes('/_next/'))assets.push(r.status());
   if(r.status()>=400&&r.url().includes('/strategy/'))apiErrors.push(r.status());});
 try{
  await page.goto(process.env.E2E_BASE_URL+'/trading');await page.waitForURL(u=>u.pathname==='/login');
  await page.getByLabel('Email',{exact:true}).fill(credentials.email);await page.getByLabel('Password',{exact:true}).fill(credentials.password);
  await page.getByRole('button',{name:'Sign In',exact:true}).click();await page.waitForURL(u=>u.pathname==='/dashboard');
  await page.locator('a[href="/trading"]').first().click();
  await page.getByTestId('strategy-no-trade').waitFor();
  await page.getByTestId('analysis-summary').waitFor();await page.getByTestId('news-regime').waitFor();
  const workspace=page.getByTestId('strategy-workspace');
  assert.match(await workspace.innerText(),/mt5_demo_iux/);
  assert.match(await page.getByTestId('news-panel').innerText(),/STRAT05–06/);
  assert.match(await page.getByTestId('news-provider-health').innerText(),/forex_factory/);
  assert.equal(await workspace.locator('.strategy-card').count(),13);
  stage='modes';await page.getByLabel('Strategy mode',{exact:true}).selectOption('MULTI_STRATEGY');
  assert.equal(await workspace.locator('.strategy-card').count(),6);
  await page.getByLabel('Strategy mode',{exact:true}).selectOption('SINGLE_STRATEGY');
  assert.equal(await workspace.locator('.strategy-card').count(),1);
  await page.getByLabel('Strategy mode',{exact:true}).selectOption('MULTI_TRADER');
  const boxes=page.getByRole('group',{name:'Strategy overlays'}).getByRole('checkbox');
  for(let i=0;i<await boxes.count();i++){await boxes.nth(i).check();assert.equal(await boxes.nth(i).isChecked(),true);}
  stage='responsive';
  for(const [name,width,height] of [['desktop',1440,1100],['tablet',820,1100],['mobile',390,844]]){
    await page.setViewportSize({width,height});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    for(const [region,selector] of [['header','.strategy-header'],['candidates','.strategy-cards'],['detail','.strategy-detail']]){
      await workspace.locator(selector).scrollIntoViewIfNeeded();
      const file=path.join(out,'strategy-'+name+'-'+region+'.png');await page.screenshot({path:file});result.screenshots.push(file);
    }
  }
  stage='reload';await page.reload();await page.getByTestId('strategy-no-trade').waitFor();
  assert.equal(await page.locator('.strategy-card').count(),13);
  assert.deepEqual(errors,[]);assert.deepEqual(assets,[]);assert.deepEqual(apiErrors,[]);
  result.status='PASS';result.console_errors=0;result.asset_errors=0;result.api_errors=0;
  result.modes=['SINGLE_STRATEGY','MULTI_STRATEGY','MULTI_TRADER'];result.actual_market='mt5_demo_iux';
  result.no_fabricated_plan=true;
 }catch(error){result.status='FAIL';result.stage=stage;result.error=error.message;result.errors=errors;
   result.api_errors=apiErrors;await page.screenshot({path:path.join(out,'failure.png')}).catch(()=>{});process.exitCode=1;
 }finally{
  await page.evaluate(async()=>{const token=localStorage.getItem('access_token');if(token)await fetch('http://localhost:8000/api/auth/logout',
    {method:'POST',headers:{Authorization:'Bearer '+token}}).catch(()=>{});}).catch(()=>{});
  await browser.close();fs.writeFileSync(path.join(out,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }
}
main().catch(()=>{console.error('Strategy browser acceptance failed');process.exitCode=1;});
