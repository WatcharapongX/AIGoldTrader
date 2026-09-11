const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const React=require('react'),{renderToStaticMarkup}=require('react-dom/server');
const cache=new Map();
function load(relative){
 const full=path.resolve(__dirname,'../src',relative);
 if(cache.has(full))return cache.get(full);
 const exports={};cache.set(full,exports);
 const code=ts.transpileModule(fs.readFileSync(full,'utf8'),{compilerOptions:{
  module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true
 }}).outputText;
 vm.runInNewContext(code,{exports,Date,Number,Set,Intl,JSON,process,AbortSignal,AbortController,
 require:n=>{
  if(n==='react'||n==='react/jsx-runtime')return require(n);
  if(n==='next/link')return {__esModule:true,default:({children,...props})=>React.createElement('a',props,children)};
  if(n==='next/image')return {__esModule:true,default:()=>null};
  if(n==='next/navigation')return {useRouter:()=>({}),usePathname:()=>'/dashboard'};
  if(n.includes('RealtimeMarketChart'))return {RealtimeMarketChart:()=>null};
  if(n==='@/stores/auth')return {useAuthStore:()=>({login:()=>{},isLoading:false,error:null,clearError:()=>{}})};
  const resolved=n.startsWith('@/')?path.resolve(__dirname,'../src',n.slice(2)):path.resolve(path.dirname(full),n);
  if(n.endsWith('.json'))return JSON.parse(fs.readFileSync(resolved,'utf8'));
  return load(path.relative(path.resolve(__dirname,'../src'),fs.existsSync(resolved+'.tsx')?resolved+'.tsx':resolved+'.ts'));
 }});
 return exports;
}
const {DashboardView}=load('features/dashboard/Dashboard.tsx');
const {TradingStatus,RuntimeHealth}=load('components/layout/RuntimeStatus.tsx');
const Login=load('app/login/page.tsx').default;
const fixture=require('./fixtures/dashboard.json');
const now=Date.parse(fixture.served_at);
const text=(component,props)=>renderToStaticMarkup(React.createElement(component,props)).replace(/<[^>]*>/g,' ').replace(/\s+/g,' ');
function props(){
 const data=structuredClone(fixture);
 data.generated_at=data.served_at;
 data.market.status='CONNECTED';data.market.mode='DEMO';data.market.source='mt5_demo_iux';
 data.quote={...data.quote,source:data.market.source,status:'CONNECTED',timestamp:data.served_at,bid:'4123.45',ask:'4123.78',spread:'0.33'};
 return {data,clock:now,ws:'CONNECTED',quote:null,marketStatus:null,marketCandles:[],error:''};
}
test('authoritative quote changes render directly; no daily change or unrelated prices',()=>{
 const a=props(),first=text(DashboardView,a);
 assert.match(first,/4,123.45/);assert.match(first,/Ask 4,123.78/);assert.match(first,/Spread: 0.33/);
 a.data.quote={...a.data.quote,bid:'4234.56',ask:'4235.00',spread:'0.44'};
 const second=text(DashboardView,a);assert.match(second,/4,234.56/);assert.match(second,/Spread: 0.44/);assert.doesNotMatch(second,/4,123.45/);
 for(const v of [first,second])assert.doesNotMatch(v,/12.35|0.34%|57,321|1.084|104.2/);
 assert.match(first,/EURUSD ยังไม่เชื่อมต่อข้อมูล —/);
 for(const symbol of ['DXY','US10Y','BTCUSD'])assert.ok(first.includes(symbol+' ยังไม่เชื่อมต่อข้อมูล —'));
});
test('no candles means unavailable OHLC and MA even with a valid quote',()=>{
 const t=text(DashboardView,props());assert.match(t,/O — H — L — C —/);
 assert.match(t,/MA 20: — MA 50: — MA 200: —/);
});
test('OHLC follows canonical M5 candles and never aliases bid/ask',()=>{
 const p=props();p.marketCandles=[{symbol:'XAUUSD',source:'mt5_demo_iux',timeframe:'M5',
 open_time:'2026-09-09T00:00:00Z',open:'4001',high:'4010',low:'3990',close:'4005',is_closed:true}];
 let t=text(DashboardView,p);assert.match(t,/O 4,001.00 H 4,010.00 L 3,990.00 C 4,005.00/);
 assert.match(t,/CLOSED/);assert.match(t,/MA 20: —/);
 p.marketCandles[0].close='4006';p.marketCandles[0].is_closed=false;
 t=text(DashboardView,p);assert.match(t,/C 4,006.00/);assert.match(t,/FORMING/);
 p.marketCandles[0].source='other';assert.match(text(DashboardView,p),/O — H — L — C —/);
});
test('rule-based Setup Score comes from plan.score, absent plan is not zero confidence',()=>{
 const p=props(),ready=require('./fixtures/strategy-ready.json').evaluation.candidates.find(c=>c.plan);
 p.data.current_plan={...ready.plan,score:73,expires_at:new Date(now+60000).toISOString()};
 p.data.strategy_stale=false;p.data.candidates=[ready];
 let t=text(DashboardView,p);assert.match(t,/Setup Score 73\/100/);
 p.data.current_plan.score=81;assert.match(text(DashboardView,p),/Setup Score 81\/100/);
 p.data.current_plan=null;t=text(DashboardView,p);assert.match(t,/Setup Score —/);
 assert.doesNotMatch(t,/AI Confidence|AI Trading Signal|Win Probability|Confidence|0%/);
});
test('portfolio, performance and sentiment have no invented numbers or charts',()=>{
 const t=text(DashboardView,props());
 assert.match(t,/จะพร้อมใช้งานหลังเปิด Paper Trading/);assert.match(t,/จะพร้อมใช้งานหลังมีประวัติ Paper Trading/);
 assert.doesNotMatch(t,/12,450|285.41|2.35%|68%|24%|8%|Profit Factor|Total Equity|Win Rate/);
});
test('live market label requires real mode, fresh quote and confirmed transport/provider',()=>{
 const p=props();assert.match(text(DashboardView,p),/Live Market Data/);
 for(const state of ['STALE','ERROR','DISCONNECTED','CONNECTING']){
  p.data.market.status=state;assert.doesNotMatch(text(DashboardView,p),/Live Market Data/);
 }
 p.data.market.status='CONNECTED';p.ws='RECONNECTING';assert.doesNotMatch(text(DashboardView,p),/Live Market Data/);
 p.ws='CONNECTED';p.clock+=60000;assert.doesNotMatch(text(DashboardView,p),/Live Market Data/);
 p.clock=now;p.data.market.mode='SIMULATED';assert.match(text(DashboardView,p),/SIMULATED DATA/);
 assert.doesNotMatch(text(DashboardView,p),/Live Market Data/);
});
test('unknown API state cannot invent quotes, mode, AI health or a plan',()=>{
 const p={...props(),data:null,marketStatus:null,error:'โหลดข้อมูลไม่สำเร็จ'};
 const t=text(DashboardView,p);assert.match(t,/Trading: UNKNOWN/);assert.match(t,/Auto Trading: UNKNOWN/);
 assert.match(t,/Market Data: UNKNOWN/);assert.match(t,/Setup Score —/);
 assert.doesNotMatch(t,/4,123|Live Market Data|HEALTHY/);
});
test('API failure after data keeps an explicit stale warning and suppresses live label/plan',()=>{
 const p=props();p.error='โหลดข้อมูลไม่สำเร็จ';
 const t=text(DashboardView,p);assert.match(t,/ข้อมูลเดิมอาจล้าสมัย/);
 assert.doesNotMatch(t,/Live Market Data/);assert.match(t,/Setup Score —/);
});
test('canonical calendar forecast/previous/actual render and change with data',()=>{
 const p=props();p.data.calendar_events[0]={...p.data.calendar_events[0],forecast:'7.7',previous:'6.6',actual:null};
 assert.match(text(DashboardView,p),/Forecast 7.7 · Previous 6.6 · Actual —/);
 p.data.calendar_events[0].actual='8.8';assert.match(text(DashboardView,p),/Actual 8.8/);
});
test('global safety renders backend PAPER/OFF, other values and UNKNOWN honestly',()=>{
 assert.match(text(TradingStatus,{health:{trading_mode:'PAPER',live_auto_trading:false}}),/PAPER Auto Trading: OFF/);
 assert.match(text(TradingStatus,{health:{trading_mode:'LIVE',live_auto_trading:true}}),/LIVE Auto Trading: ON/);
 assert.match(text(TradingStatus,{health:null}),/Trading: UNKNOWN Auto Trading: UNKNOWN/);
});
test('runtime health renders actual database and MT5 configuration failures; AI unimplemented',()=>{
 const p={health:{},ready:{checks:{database:true}},market:props().data.market};
 assert.match(text(RuntimeHealth,p),/Database HEALTHY/);
 p.ready.checks.database=false;p.market={...p.market,status:'ERROR',mode:'UNCONFIRMED',detail:'MT5_CONFIGURATION_REQUIRED'};
 let t=text(RuntimeHealth,p);assert.match(t,/Database UNAVAILABLE/);assert.match(t,/MT5_CONFIGURATION_REQUIRED/);
 assert.match(t,/AI NOT IMPLEMENTED/);assert.doesNotMatch(t,/MT5 OK|AI OK/);
 t=text(RuntimeHealth,{health:null,ready:null,market:null});assert.doesNotMatch(t,/HEALTHY/);assert.match(t,/UNKNOWN/);
});
test('login is decorative, has no static quote or premature AI/risk feature claims',()=>{
 const t=text(Login,{});assert.match(t,/Gold Trading Platform/);
 assert.doesNotMatch(t,/3,642.18|12.35|0.34%|AI-Powered|AI Powered|high-probability|Disciplined Risk Management|Gold, Forex/);
 assert.match(t,/Deterministic Analysis/);
});
