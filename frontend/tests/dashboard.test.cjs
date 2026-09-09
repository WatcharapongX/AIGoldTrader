const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const cache=new Map();
function load(file) {
 const full=path.resolve(__dirname,'../src',file);
 if(cache.has(full))return cache.get(full);
 const exports={};cache.set(full,exports);
 const code=ts.transpileModule(fs.readFileSync(full,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
 vm.runInNewContext(code,{exports,Date,Number,Set,Intl,JSON,require:n=>{
   const resolved=n.startsWith('@/')?path.resolve(__dirname,'../src',n.slice(2)):path.resolve(path.dirname(full),n);
   return n.endsWith('.json')?JSON.parse(fs.readFileSync(resolved,'utf8')):load(path.relative(path.resolve(__dirname,'../src'),resolved+'.ts'));
 }});return exports;
}

const parser=load('features/dashboard/contracts.ts');
const fixture=require('./fixtures/dashboard.json');
test('real limited calendar dashboard agrees with authoritative API contract',()=>{
 const d=parser.parseDashboard(fixture);
 assert.equal(d.news_provider.source_mode,'LIVE');assert.equal(d.news_provider.coverage,'LIMITED');
 assert.equal(d.strategies.length,6);assert.equal(d.profiles.length,7);assert.equal(d.current_plan,null);
});
for(const [name,change] of [
 ['unexpected execution',d=>d.execution={side:'BUY'}],
 ['live trading',d=>d.live_auto_trading=true],
 ['future receipt',d=>d.calendar_events[0].available_at='2099-01-01T00:00:00Z'],
 ['future actual schedule',d=>d.calendar_events[0].scheduled_at='2099-01-01T00:00:00Z'],
 ['fixture leak',d=>d.calendar_events[0].source_mode='FIXTURE'],
 ['provider mismatch',d=>d.calendar_events[0].source='other'],
 ['duplicate event',d=>d.calendar_events.push(d.calendar_events[0])],
 ['future strategy',d=>d.strategy_as_of='2099-01-01T00:00:00Z'],
 ['duplicate profiles',d=>d.profiles[1]=d.profiles[0]],
 ['candidate context mismatch',d=>d.candidates[0].context_id='wrong'],
 ['fake ready',d=>d.candidates[0].status='READY'],
 ['unknown health',d=>d.health[0].state='FAKE_OK'],
 ['future summary',d=>d.generated_at='2099-01-01T00:00:00Z'],
 ['negative count',d=>d.news_provider.event_count=-1],
 ['wrong type quote',d=>d.quote.bid=100],
]) test('reject '+name,()=>{const d=structuredClone(fixture);change(d);assert.throws(()=>parser.parseDashboard(d));});
test('independent unavailable modules remain valid',()=>{
 const d=structuredClone(fixture);
 Object.assign(d,{market:null,quote:null,news:null,news_provider:null,calendar_events:[],structure:[],profiles:[],candidates:[],
 strategy_context_id:null,strategy_generated_at:null,strategy_as_of:null,strategy_stale:true,current_plan:null});
 assert.ok(parser.parseDashboard(d));
});
test('dashboard transport uses shared cleanup and never calls outside economic provider',()=>{
 const code=fs.readFileSync(path.resolve(__dirname,'../src/features/dashboard/Dashboard.tsx'),'utf8');
 assert.match(code,/new MarketConnection/);assert.match(code,/connection.stop\(\)/);
 assert.match(code,/abort.abort\(\)/);assert.match(code,/clearInterval\(timer\)/);
 assert.doesNotMatch(code,/api\.tradingeconomics|fetch\(['"]https:\/\/xoomar/);
});
