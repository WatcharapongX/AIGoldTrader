const {test} = require('node:test');
const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), ts = require('typescript');
function load(file) {
 const exports = {};
 const source = fs.readFileSync(path.join(__dirname,'../src/features/news',file),'utf8');
 const output = ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText;
 vm.runInNewContext(output,{exports,Date,Number,Set,Intl,require:n=>n.endsWith('.json') ? require('../src/features/news/news-contract.generated.json') : require(n)});
 return exports;
}
const parser=load('contracts.ts'), thai=load('thai.ts'), fixture=require('./fixtures/news.json');
test('canonical news response and Thai descriptions',()=>{
 assert.equal(parser.parseNews(fixture).macro_bias,'CONFLICTING');
 assert.equal(thai.label('CONFLICTING'),'ข้อมูลขัดแย้งกัน');
 assert.equal(thai.numeric(null),'ยังไม่มีผลประกาศ');
 assert.match(thai.eventName(fixture.events.find(e=>e.event_code==='NFP')),/การจ้างงาน/);
 assert.equal(thai.countdown('2026-09-09T00:01:00Z',Date.parse('2026-09-09T00:00:00Z')),'0 ชม. 1 นาที 0 วินาที');
});
for(const [name,change] of [
 ['extra trading action',v=>v.signal='BUY'],
 ['unknown regime',v=>v.news_regime='BUY_NOW'],
 ['future revision',v=>v.events[0].available_at='2099-01-01T00:00:00Z'],
 ['actual before release',v=>v.events[0].released_at='2000-01-01T00:00:00Z'],
 ['duplicate event',v=>v.events.push(v.events[0])],
 ['wrong news source',v=>v.events[0].source='other'],
 ['wrong provider mode',v=>v.events[0].source_mode='LIVE'],
 ['invalid decimal',v=>v.events[0].actual='NaN'],
 ['future market cutoff',v=>v.market_as_of='2099-01-01T00:00:00Z'],
 ['future structure cutoff',v=>v.structure_confirmation.upstream_as_of='2099-01-01T00:00:00Z'],
 ['missing UTC',v=>v.as_of='2026-09-09T12:40:01'],
 ['negative cache age',v=>v.cache_age_seconds=-1],
 ['early served time',v=>v.served_at='2000-01-01T00:00:00Z'],
 ['oversized event array',v=>v.events=Array(201).fill(v.events[0])]
]) test('news rejects '+name,()=>{const v=structuredClone(fixture);change(v);assert.throws(()=>parser.parseNews(v),/Invalid news contract/);});
test('calendar and detail use the same canonical point-in-time event',()=>{
 const v={events:fixture.events,source:fixture.source,source_mode:'FIXTURE',state:'AVAILABLE',as_of:fixture.as_of,generated_at:fixture.generated_at,truncated:false};
 assert.equal(parser.parseCalendar(v).events.length,3);
 const event=fixture.events[0];
 assert.equal(parser.parseEvent({event,revisions:[event],as_of:fixture.as_of}).event.id,event.id);
});
