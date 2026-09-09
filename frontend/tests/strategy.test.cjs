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
const parser=load('features/strategy/contracts.ts'),overlay=load('features/strategy/overlays.ts');
const fixture=require('./fixtures/strategy.json'),ready=require('./fixtures/strategy-ready.json');
test('canonical strategy context and seven isolated profiles',()=>{
 assert.equal(parser.parseStrategy(fixture).evaluation.profiles.length,7);
 assert.equal(parser.parseStrategy(ready).evaluation.context.mode,'REPLAY');
 assert.ok(ready.evaluation.candidates.some(c=>c.status==='READY'));
});
for(const [name,change] of [
 ['extra execution',v=>v.evaluation.order={side:'BUY'}],
 ['future context',v=>v.evaluation.context.as_of='2099-01-01T00:00:00Z'],
 ['mismatched context',v=>v.evaluation.candidates[0].context_id='wrong'],
 ['duplicate profiles',v=>v.evaluation.profiles.push(v.evaluation.profiles[0])],
 ['duplicate candidates',v=>v.evaluation.candidates.push(v.evaluation.candidates[0])],
 ['future indicator context',v=>v.evaluation.context.frames[0].as_of='2099-01-01T00:00:00Z'],
 ['invalid decimal',v=>v.evaluation.context.key_levels[0].price='NaN'],
 ['missing required context',v=>delete v.evaluation.context.news_json],
 ['unknown status',v=>v.evaluation.candidates[0].status='BUY_NOW'],
 ['ready without plan',v=>v.evaluation.candidates[0].status='READY'],
 ['future key level',v=>v.evaluation.context.key_levels[0].confirmed_at='2099-01-01T00:00:00Z'],
 ['same user profile duplicate',v=>v.evaluation.profiles[1].id=v.evaluation.profiles[0].id],
])test('rejects '+name,()=>{const v=structuredClone(fixture);change(v);assert.throws(()=>parser.parseStrategy(v));});
test('actual market cannot be ready from fixture news',()=>{
 const v=structuredClone(ready);v.evaluation.context.mode='ACTUAL';assert.throws(()=>parser.parseStrategy(v));
});
test('invalid structural stop rejected at browser boundary',()=>{
 const v=structuredClone(ready),c=v.evaluation.candidates.find(c=>c.plan);c.plan.stop_loss=c.plan.entry_upper;
 assert.throws(()=>parser.parseStrategy(v));
});
test('overlays keep chart data immutable and require a ready candidate',()=>{
 const ctx=ready.evaluation.context,c=ready.evaluation.candidates.find(c=>c.plan),before=JSON.stringify(ctx);
 const shapes=overlay.strategyShapes(ctx,'M5',c,{periods:true,sessions:true,patterns:true,plan:true});
 assert.ok(shapes.some(s=>s.label==='SL'));assert.equal(JSON.stringify(ctx),before);
 assert.ok(!overlay.strategyShapes(ctx,'M5',null,{periods:false,sessions:false,patterns:false,plan:true}).length);
});

test('general ready plans remain valid on actual market with unavailable calendar',()=>{
 const v=structuredClone(ready);
 v.evaluation.context.mode='ACTUAL';
 v.evaluation.candidates=v.evaluation.candidates.filter(c=>!['STRAT05','STRAT06'].includes(c.strategy_id));
 v.evaluation.component_ids=Object.fromEntries(v.evaluation.candidates.map(c=>[c.id,v.evaluation.component_ids[c.id]]));
 const n=JSON.parse(v.evaluation.context.news_json);n.calendar_state='CALENDAR_UNAVAILABLE';
 v.evaluation.context.news_json=JSON.stringify(n);
 assert.ok(parser.parseStrategy(v).evaluation.candidates.some(c=>c.status==='READY'));
 assert.ok(v.evaluation.candidates.every(c=>!c.evidence.some(e=>e.code==='NEWS')));
});

test('news candidate provenance rejects future event knowledge',()=>{
 const v=structuredClone(ready),c=v.evaluation.candidates.find(c=>c.news_provenance?.event_vintages.length);
 c.news_provenance.event_vintages[0].available_at='2099-01-01T00:00:00Z';
 assert.throws(()=>parser.parseStrategy(v));
});


test('persisted general projection is valid without any news payload',()=>{
 const v=require('./fixtures/strategy-projection.json');
 assert.equal(parser.parseStrategy(v).evaluation.context.news_json,null);
 assert.equal(v.evaluation.scope,'STRATEGY');
 assert.equal(v.evaluation.component_ids[v.evaluation.candidates[0].id],v.evaluation.id);
});
for(const [name,change] of [
 ['missing component',v=>v.evaluation.component_ids={}],
 ['wrong canonical owner',v=>v.evaluation.id='wrong-owner'],
 ['news attached to general projection',v=>v.evaluation.context.news_json=ready.evaluation.context.news_json],
])test('projection rejects '+name,()=>{
 const v=structuredClone(require('./fixtures/strategy-projection.json'));change(v);assert.throws(()=>parser.parseStrategy(v));
});
