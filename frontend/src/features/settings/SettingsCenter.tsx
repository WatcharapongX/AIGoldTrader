'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '@/lib/api';
import { DataProvenanceLine, type DataCondition } from '@/components/data-provenance';
import type { User } from '@/types';
import {
  DEFAULT_UI_PREFERENCES,
  parseKillSwitch,
  parseMarketStatus,
  parseNewsStatus,
  parseProfiles,
  parseRiskPolicy,
  parseSafeConfiguration,
  parseStrategies,
  parseSystemStatus,
  parseUiPreferences,
  type KillSwitchStatus,
  type MarketStatus,
  type NewsStatus,
  type RiskPolicy,
  type SafeConfiguration,
  type StrategyDefinition,
  type SystemStatus,
  type TraderProfile,
  type UiPreferences,
} from './contracts';

type SectionId = 'general' | 'trading' | 'market' | 'news' | 'ai' | 'strategies' | 'risk' | 'system' | 'security' | 'provenance';
interface SettingsData {
  configuration: SafeConfiguration | null;
  system: SystemStatus | null;
  market: MarketStatus | null;
  news: NewsStatus | null;
  risk: RiskPolicy | null;
  strategies: StrategyDefinition[] | null;
  profiles: TraderProfile[] | null;
  killSwitch: KillSwitchStatus | null;
  user: User | null;
}

const EMPTY: SettingsData = { configuration:null, system:null, market:null, news:null, risk:null, strategies:null, profiles:null, killSwitch:null, user:null };
const PREF_KEY = 'aigoldtrader.ui-preferences.v1';
const sections: { id: SectionId; label: string; icon: string }[] = [
  {id:'general',label:'General',icon:'◫'}, {id:'trading',label:'Trading & Safety',icon:'◆'},
  {id:'market',label:'Market Data',icon:'⌁'}, {id:'news',label:'News / Macro',icon:'▤'},
  {id:'ai',label:'AI Provider',icon:'✦'}, {id:'strategies',label:'Strategies',icon:'⌘'},
  {id:'risk',label:'Risk Policy',icon:'⬡'}, {id:'system',label:'System & Infrastructure',icon:'▦'},
  {id:'security',label:'Security / Session',icon:'◈'}, {id:'provenance',label:'Data Provenance',icon:'◎'},
];

function value<T>(result: PromiseSettledResult<T>): T | null { return result.status === 'fulfilled' ? result.value : null; }
function shown(item: unknown): string { return item === null || item === undefined || item === '' ? 'UNAVAILABLE' : String(item); }
function when(item: string | null | undefined): string {
  if (!item) return 'UNAVAILABLE';
  const date = new Date(item); return Number.isNaN(date.getTime()) ? 'UNAVAILABLE' : date.toLocaleString('th-TH', { timeZone:'Asia/Bangkok' });
}
function condition(state: string | null | undefined): DataCondition {
  if (!state) return 'UNAVAILABLE';
  if (['HEALTHY','CONNECTED','NORMAL','EXTERNAL_READY'].includes(state)) return 'FRESH';
  if (state === 'STALE') return 'STALE';
  if (['DEGRADED','FIXTURE_READY','DISABLED','EXTERNAL_NOT_CONFIGURED'].includes(state)) return 'DEGRADED';
  return 'UNAVAILABLE';
}
function tone(state: string): string {
  if (['HEALTHY','CONNECTED','NORMAL','CONFIGURED','LOADED','SAFE'].includes(state)) return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
  if (['PAPER','FIXTURE','DEMO','READ ONLY','SERVER MANAGED','NOT_REQUIRED','NOT EXPOSED'].includes(state)) return 'border-amber-500/30 bg-amber-500/10 text-amber-300';
  if (['MISSING','DEGRADED','STALE','ACTIVE'].includes(state)) return 'border-orange-500/30 bg-orange-500/10 text-orange-300';
  if (['UNAVAILABLE','NONE','NOT IMPLEMENTED','DISABLED'].includes(state)) return 'border-gray-600 bg-gray-800/70 text-gray-300';
  return 'border-blue-500/30 bg-blue-500/10 text-blue-300';
}
function Badge({children}:{children:string}) { return <span className={`inline-flex rounded border px-2 py-1 text-[10px] font-bold tracking-wide ${tone(children.replaceAll('_',' '))}`}>{children.replaceAll('_',' ')}</span>; }
function Panel({title,subtitle,children,action}:{title:string;subtitle?:string;children:React.ReactNode;action?:React.ReactNode}) {
  return <section className="rounded-xl border border-gray-800 bg-[#0f1723] p-4 sm:p-5">
    <div className="mb-4 flex flex-wrap items-start justify-between gap-3"><div><h2 className="font-semibold text-gray-100">{title}</h2>{subtitle&&<p className="mt-1 text-xs leading-5 text-gray-500">{subtitle}</p>}</div>{action}</div>{children}
  </section>;
}
function Grid({children}:{children:React.ReactNode}) { return <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">{children}</dl>; }
function Row({label,value:content,help,badge=false}:{label:string;value:React.ReactNode;help?:string;badge?:boolean}) {
  const rendered=typeof content==='string'&&badge?<Badge>{content}</Badge>:content;
  return <div className="min-w-0 rounded-lg border border-gray-800/80 bg-[#0b121c] p-3"><dt className="text-[10px] font-semibold uppercase tracking-widest text-gray-500" title={help}>{label}</dt><dd className="mt-2 break-words text-sm text-gray-200">{rendered}</dd>{help&&<p className="mt-2 text-[11px] leading-4 text-gray-500">{help}</p>}</div>;
}
function Unavailable({label='CONFIGURATION STATUS UNAVAILABLE'}:{label?:string}) { return <div className="rounded-lg border border-gray-700 bg-gray-900/60 p-5 text-sm text-gray-400"><Badge>UNAVAILABLE</Badge><p className="mt-3">{label} — ไม่มีการแทนค่าด้วยค่าเริ่มต้น</p></div>; }
function ReadOnly() { return <div className="flex flex-wrap gap-2"><Badge>READ ONLY</Badge><Badge>SERVER MANAGED</Badge><Badge>RESTART REQUIRED</Badge></div>; }

function Summary({data}:{data:SettingsData}) {
  const config=data.configuration, modules=data.system?.modules;
  const items=[
    ['Trading',config?config.trading.mode:'UNAVAILABLE'],
    ['Market',config?(config.market.provider==='mt5'?config.market.terminal==='MISSING'?'MISSING':'CONFIGURED':'CONFIGURED'):'UNAVAILABLE'],
    ['News',config?(config.news.provider==='unavailable'?'MISSING':'CONFIGURED'):'UNAVAILABLE'],
    ['AI',config?(config.ai.mode==='external'&&config.ai.credential==='MISSING'?'MISSING':'CONFIGURED'):'UNAVAILABLE'],
    ['Risk',modules?.risk_engine?.state==='HEALTHY'?'LOADED':modules?.risk_engine?.state||'UNAVAILABLE'],
    ['System',modules?.backend?.state||'UNAVAILABLE'],
  ];
  return <div className="grid grid-cols-2 gap-2 md:grid-cols-3 xl:grid-cols-6" data-testid="settings-health-summary">{items.map(([label,state])=><div key={label} className="rounded-lg border border-gray-800 bg-[#0c1420] p-3"><p className="text-[10px] uppercase tracking-widest text-gray-500">{label}</p><div className="mt-2"><Badge>{state}</Badge></div></div>)}</div>;
}

export function SettingsCenter() {
  const [active,setActive]=useState<SectionId>('general');
  const [data,setData]=useState<SettingsData>(EMPTY);
  const [loading,setLoading]=useState(true);
  const [failures,setFailures]=useState<string[]>([]);
  const [fetchedAt,setFetchedAt]=useState<string|null>(null);
  const [preferences,setPreferences]=useState<UiPreferences>(DEFAULT_UI_PREFERENCES);
  const [preferenceNotice,setPreferenceNotice]=useState('');

  useEffect(() => {
    const timer = window.setTimeout(() => {
      try { const stored=localStorage.getItem(PREF_KEY); if(stored) setPreferences(parseUiPreferences(JSON.parse(stored))); }
      catch { setPreferences({...DEFAULT_UI_PREFERENCES}); }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const refresh=useCallback(async()=>{
    setLoading(true); const signal=AbortSignal.timeout(10000);
    const results=await Promise.allSettled([
      api.get('/configuration/safe',{signal}).then(parseSafeConfiguration),
      api.get('/system/status',{signal}).then(parseSystemStatus),
      api.get('/market/status',{signal}).then(parseMarketStatus),
      api.get('/news/provider/status',{signal}).then(parseNewsStatus),
      api.get('/risk/policy',{signal}).then(parseRiskPolicy),
      api.get('/strategies',{signal}).then(parseStrategies),
      api.get('/trader-profiles',{signal}).then(parseProfiles),
      api.get('/risk/kill-switch',{signal}).then(parseKillSwitch),
      api.getMe(),
    ]);
    const labels=['configuration','system','market','news','risk','strategies','profiles','kill switch','session'];
    setData({ configuration:value(results[0]),system:value(results[1]),market:value(results[2]),news:value(results[3]),risk:value(results[4]),strategies:value(results[5]),profiles:value(results[6]),killSwitch:value(results[7]),user:value(results[8]) });
    setFailures(results.flatMap((result,index)=>result.status==='rejected'?[labels[index]]:[]));
    setFetchedAt(new Date().toISOString()); setLoading(false);
  },[]);
  useEffect(() => {
    const timer = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);

  const issues=useMemo(()=>{
    const found:string[]=[]; const config=data.configuration;
    if(!config) found.push('Configuration status unavailable');
    if(config?.ai.mode==='external'&&config.ai.credential==='MISSING') found.push('External AI selected but credential is missing');
    if(config?.market.provider==='mt5'&&config.market.terminal==='MISSING') found.push('MT5 selected but terminal is missing');
    if(config?.news.provider==='unavailable') found.push('News provider is unavailable');
    for(const [name,module] of Object.entries(data.system?.modules||{})) if(['DEGRADED','STALE','UNAVAILABLE','EXTERNAL_NOT_CONFIGURED'].includes(module.state)) found.push(`${name.replaceAll('_',' ')}: ${module.state}`);
    if(!data.risk) found.push('Risk policy unavailable');
    return [...new Set(found)];
  },[data]);

  const savePreferences=()=>{ localStorage.setItem(PREF_KEY,JSON.stringify(preferences)); setPreferenceNotice('บันทึก Local UI Preference ในเบราว์เซอร์นี้แล้ว'); };
  const resetPreferences=()=>{ localStorage.removeItem(PREF_KEY); setPreferences({...DEFAULT_UI_PREFERENCES}); setPreferenceNotice('รีเซ็ตเฉพาะ Local UI Preference แล้ว'); };
  const config=data.configuration;

  return <main className="mx-auto max-w-[1600px] space-y-5 p-4 sm:p-6" data-testid="settings-center">
    <header className="flex flex-wrap items-start justify-between gap-4">
      <div><p className="text-[10px] font-semibold uppercase tracking-[.22em] text-amber-400">Operations / Configuration Governance</p><h1 className="mt-1 text-2xl font-bold text-gray-100">Settings & Configuration Center</h1><p className="mt-1 max-w-3xl text-sm text-gray-400">ศูนย์ตรวจสอบค่าระบบแบบ Read Only แยกจาก Local UI Preference อย่างชัดเจน ไม่มีสิทธิ์เปิด Live Trading หรือแก้ Server Configuration</p></div>
      <button type="button" onClick={()=>void refresh()} disabled={loading} className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-2 text-xs font-semibold text-amber-300 disabled:opacity-50">{loading?'กำลังโหลด…':'Refresh Configuration Status'}</button>
    </header>
    {loading&&<div className="rounded-lg border border-blue-500/30 bg-blue-500/10 p-3 text-xs text-blue-300">LOADING · กำลังอ่านค่าจากแหล่งอ้างอิงของแต่ละระบบ</div>}
    {failures.length>0&&<div className="rounded-lg border border-orange-500/30 bg-orange-500/10 p-3 text-xs text-orange-300">PARTIAL / DEGRADED · ไม่พร้อมใช้งาน: {failures.join(', ')} · ไม่เติมค่าเริ่มต้นแทนข้อมูลที่หาย</div>}
    <Summary data={data}/>
    <Panel title="Configuration Issues" subtitle="สร้างจากสถานะจริงเท่านั้น ไม่สร้างคำเตือนสมมติ" action={<span className="text-[10px] text-gray-500">Fetched: {when(fetchedAt)}</span>}>
      {issues.length?<ul className="grid gap-2 text-sm text-orange-200 md:grid-cols-2">{issues.map(issue=><li key={issue} className="rounded border border-orange-500/20 bg-orange-500/5 p-3">⚠ {issue}</li>)}</ul>:<div className="text-sm text-emerald-300">ไม่พบ Configuration Issue จากข้อมูลที่โหลดได้</div>}
    </Panel>
    <div className="grid min-w-0 gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
      <nav aria-label="Settings sections" className="flex gap-2 overflow-x-auto rounded-xl border border-gray-800 bg-[#0d1520] p-2 lg:block lg:space-y-1 lg:overflow-visible">
        {sections.map(item=><button key={item.id} type="button" onClick={()=>setActive(item.id)} aria-pressed={active===item.id} className={`flex shrink-0 items-center gap-3 rounded-lg px-3 py-2 text-left text-xs transition lg:w-full ${active===item.id?'bg-amber-500/15 text-amber-300':'text-gray-400 hover:bg-white/5 hover:text-gray-200'}`}><span className="text-base">{item.icon}</span><span>{item.label}</span></button>)}
      </nav>
      <div className="min-w-0 space-y-4">
        {active==='general'&&<>
          <Panel title="General · Local UI Preference" subtitle="มีผลเฉพาะการแสดงผลในเบราว์เซอร์นี้ ไม่เปลี่ยนพฤติกรรมของ Server" action={<Badge>LOCAL PREFERENCE</Badge>}>
            <div className="grid gap-4 sm:grid-cols-2"><label className="grid gap-2 text-xs text-gray-400">ภาษา<select value={preferences.language} onChange={e=>setPreferences({...preferences,language:e.target.value as UiPreferences['language']})} className="rounded border border-gray-700 bg-gray-900 p-2 text-gray-200"><option value="th">ไทย</option></select></label><label className="grid gap-2 text-xs text-gray-400">Display Timezone<select value={preferences.timezone} onChange={e=>setPreferences({...preferences,timezone:e.target.value as UiPreferences['timezone']})} className="rounded border border-gray-700 bg-gray-900 p-2 text-gray-200"><option value="Asia/Bangkok">Asia/Bangkok</option><option value="UTC">UTC</option></select></label><label className="grid gap-2 text-xs text-gray-400">Page Density<select value={preferences.density} onChange={e=>setPreferences({...preferences,density:e.target.value as UiPreferences['density']})} className="rounded border border-gray-700 bg-gray-900 p-2 text-gray-200"><option value="comfortable">Comfortable</option><option value="compact">Compact</option></select></label><label className="grid gap-2 text-xs text-gray-400">Default Chart Timeframe<select value={preferences.default_timeframe} onChange={e=>setPreferences({...preferences,default_timeframe:e.target.value as UiPreferences['default_timeframe']})} className="rounded border border-gray-700 bg-gray-900 p-2 text-gray-200"><option>M5</option><option>M15</option><option>H1</option></select></label></div>
            <div className="mt-5 flex flex-wrap items-center gap-3"><button onClick={savePreferences} className="rounded bg-amber-500 px-4 py-2 text-xs font-semibold text-black">Save UI Preferences</button><button onClick={resetPreferences} className="rounded border border-gray-700 px-4 py-2 text-xs text-gray-300">Reset UI Preferences</button>{preferenceNotice&&<span className="text-xs text-emerald-300">{preferenceNotice}</span>}</div>
          </Panel>
          <Panel title="Server Authority" subtitle="Pydantic Settings · Environment Variables · Domain Configuration"><ReadOnly/><p className="mt-4 text-sm leading-6 text-gray-400">การเปลี่ยนค่าฝั่ง Server ต้องทำผ่านกระบวนการปฏิบัติการภายนอกเว็บ และโดยทั่วไปต้อง Restart Service หลังเปลี่ยนค่า</p></Panel>
        </>}

        {active==='trading'&&<Panel title="Trading & Safety" subtitle="Safety-critical configuration · ไม่มี Toggle หรือ Save"><ReadOnly/>{config?<Grid><Row label="Trading Mode" value={config.trading.mode} badge/><Row label="Live Auto Trading" value={config.trading.live_auto_trading?'ON':'OFF'} badge help="การเปิด Live Auto Trading ต้องผ่าน Production Approval แยกต่างหาก"/><Row label="Broker Execution" value={config.trading.broker_execution} badge help="ไม่มี Connect & Trade หรือ Test Order ใน FC-10"/><Row label="Paper Account Provenance" value={config.trading.account_provenance} badge/><Row label="Kill Switch" value={data.killSwitch?.state||'UNAVAILABLE'} badge/><Row label="Risk Engine" value={data.system?.modules.risk_engine?.state||'UNAVAILABLE'} badge/></Grid>:<Unavailable/>}<Link href="/risk" className="mt-4 inline-flex text-xs text-amber-300 underline">View Risk Controls →</Link></Panel>}

        {active==='market'&&<Panel title="Market Data" subtitle="Configuration และ runtime feed แสดงแยกกัน"><ReadOnly/>{config?<div className="mt-4 space-y-4"><Grid><Row label="Provider Type" value={config.market.provider} badge/><Row label="MT5 Account Mode" value={config.market.provider==='mt5'?`${config.market.account_mode} ACCOUNT`:'NOT REQUIRED'} badge/><Row label="Market Provenance" value={config.market.provenance} badge/><Row label="Runtime Connection" value={data.market?.status||'UNAVAILABLE'} badge/><Row label="Configured Symbol" value={shown(data.market?.provider_symbol||config.market.configured_symbol)}/><Row label="Server Timezone" value={config.market.server_timezone}/><Row label="Poll Interval" value={`${config.market.poll_seconds}s`}/><Row label="Stale Threshold" value={`${config.market.stale_after_seconds}s`}/><Row label="Terminal" value={config.market.terminal} badge/><Row label="Account Validation" value={config.market.account_validation} badge/><Row label="Server Validation" value={config.market.server_validation} badge/><Row label="Tick Archive" value={config.market.archive_real_ticks?'ENABLED':'DISABLED'} badge/></Grid><DataProvenanceLine source={data.market?.source} mode={data.market?.mode||config.market.provenance} condition={condition(data.market?.status)} asOf={data.market?.last_quote}/><div className="rounded-lg border border-gray-800 p-3 text-xs text-gray-400">Historical coverage: {data.market?`${Object.keys(data.market.history_counts).length} timeframes · ${data.market.history_complete?'COMPLETE':'PARTIAL'}`:'UNAVAILABLE'} · Last candle: {when(data.market?.last_candle)}</div></div>:<Unavailable/>}<Link href="/trading" className="mt-4 inline-flex text-xs text-amber-300 underline">Open Market Overview →</Link></Panel>}

        {active==='news'&&<Panel title="News / Macro" subtitle="Provider configuration และ runtime freshness"><ReadOnly/>{config?<div className="mt-4 space-y-4"><Grid><Row label="Provider" value={config.news.provider} badge/><Row label="Configured Mode" value={config.news.provenance} badge/><Row label="Runtime Mode" value={data.news?.source_mode||'UNAVAILABLE'} badge/><Row label="Provider Health" value={data.news?.state||'UNAVAILABLE'} badge/><Row label="Poll Interval" value={`${data.news?.poll_seconds??config.news.poll_seconds}s`}/><Row label="Stale Threshold" value={`${config.news.stale_after_seconds}s`}/><Row label="Last Sync" value={when(data.news?.last_sync_at)}/><Row label="Provider Updated" value={when(data.news?.provider_updated_at)}/></Grid>{config.news.provenance==='FIXTURE'&&<div className="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-300">FIXTURE / TEST DATA · ไม่ใช่ข่าวจริง</div>}<DataProvenanceLine source={data.news?.source||config.news.provider} mode={data.news?.source_mode||config.news.provenance} condition={condition(data.news?.state)} asOf={data.news?.provider_updated_at||data.news?.last_sync_at}/></div>:<Unavailable/>}<div className="mt-4 flex gap-4 text-xs"><Link href="/calendar" className="text-amber-300 underline">Economic Calendar →</Link><Link href="/scanner" className="text-amber-300 underline">News Workspace →</Link></div></Panel>}

        {active==='ai'&&<Panel title="AI Provider" subtitle="ADVISORY ONLY · Configured, Healthy และ Available เป็นคนละสถานะ"><ReadOnly/>{config?<div className="mt-4 space-y-4"><Grid><Row label="Provider Mode" value={config.ai.mode} badge/><Row label="Provider Type" value={config.ai.provider_type}/><Row label="Runtime Health" value={data.system?.modules.ai_provider?.state||'UNAVAILABLE'} badge/><Row label="API Credential" value={config.ai.credential} badge/><Row label="Endpoint" value={config.ai.endpoint} badge/><Row label="Max Concurrent Calls" value={config.ai.max_concurrent_provider_calls}/><Row label="Queue Timeout" value={`${config.ai.queue_timeout_seconds}s`} help="เวลารอคิวสูงสุด ไม่ใช่ระยะเวลาประมวลผลทั้งหมด"/><Row label="Execution Authority" value="ADVISORY ONLY" badge/></Grid><div className="rounded-lg border border-gray-800 bg-[#0b121c] p-4"><h3 className="text-xs font-semibold uppercase tracking-widest text-gray-400">Model Alias Mapping</h3><dl className="mt-3 grid gap-2 sm:grid-cols-2">{Object.entries(config.ai.model_mapping).map(([alias,model])=><div key={alias} className="flex justify-between gap-3 border-b border-gray-800 pb-2 text-xs"><dt className="text-gray-500">{alias}</dt><dd className="break-all text-gray-200">{model}</dd></div>)}</dl></div>{config.ai.provenance==='FIXTURE'&&<div className="rounded border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-300">FIXTURE ADVISORY / TEST MODE</div>}</div>:<Unavailable/>}<Link href="/analysis" className="mt-4 inline-flex text-xs text-amber-300 underline">Open Analysis →</Link></Panel>}

        {active==='strategies'&&<div className="space-y-4"><Panel title="Strategy Catalog" subtitle="Authoritative GET /strategies · ไม่มี Enable/Disable หรือแก้กฎ"><ReadOnly/>{data.strategies?<div className="mt-4 grid gap-3 xl:grid-cols-2">{data.strategies.map(strategy=><article key={strategy.id} className="rounded-lg border border-gray-800 bg-[#0b121c] p-4"><div className="flex justify-between gap-3"><h3 className="font-semibold text-gray-100">{strategy.id} · {strategy.name}</h3><Badge>{strategy.version}</Badge></div><p className="mt-2 text-xs text-gray-400">{strategy.description_th}</p><p className="mt-3 text-[11px] text-gray-500">{strategy.category} · {strategy.styles.join(', ')} · minimum {strategy.minimum_bars} bars</p><p className="mt-1 text-[11px] text-gray-500">Context: {strategy.required_context.join(', ')}</p></article>)}</div>:<Unavailable label="STRATEGY CATALOG UNAVAILABLE"/>}</Panel><Panel title="Trader Profiles" subtitle="Profiles และ timeframe mapping แบบ Read Only">{data.profiles?<div className="grid gap-3 xl:grid-cols-2">{data.profiles.map(profile=><article key={profile.id} className="rounded-lg border border-gray-800 bg-[#0b121c] p-4"><div className="flex justify-between"><h3 className="font-semibold text-gray-100">{profile.name}</h3><Badge>{profile.execution_mode}</Badge></div><p className="mt-2 text-xs text-gray-400">{profile.description_th}</p><p className="mt-3 text-xs text-gray-300">{profile.style} · {profile.allowed_strategies.join(', ')}</p><p className="mt-2 text-[11px] text-gray-500">Context {profile.timeframe_map.context} → Bias {profile.timeframe_map.bias} → Setup {profile.timeframe_map.setup} → Trigger {profile.timeframe_map.trigger} · minimum {profile.timeframe_map.minimum_bars} bars</p></article>)}</div>:<Unavailable label="TRADER PROFILES UNAVAILABLE"/>}<Link href="/backtesting" className="mt-4 inline-flex text-xs text-amber-300 underline">Open Strategy Lab →</Link></Panel></div>}

        {active==='risk'&&<Panel title="Risk Policy" subtitle="Active policy จาก GET /risk/policy · ไม่มีช่องแก้ไขหรือ Save"><ReadOnly/>{data.risk?<div className="mt-4 space-y-4"><Grid><Row label="Policy Version" value={data.risk.version}/><Row label="Risk per Trade" value={`${data.risk.min_risk_per_trade_pct}% – ${data.risk.max_risk_per_trade_pct}%`} help="ขอบเขตความเสี่ยงที่อนุญาตต่อหนึ่งรายการ"/><Row label="Max Account Risk" value={`${data.risk.max_account_risk_pct}%`}/><Row label="Max Symbol Risk" value={`${data.risk.max_symbol_risk_pct}%`}/><Row label="Directional Risk" value={`${data.risk.max_directional_risk_pct}%`}/><Row label="Concurrent Trades" value={data.risk.max_concurrent_trades}/><Row label="Daily Loss Limit" value={`${data.risk.daily_loss_limit_pct}%`}/><Row label="Weekly Loss Limit" value={`${data.risk.weekly_loss_limit_pct}%`}/><Row label="Max Drawdown" value={`${data.risk.max_drawdown_pct}%`}/><Row label="Spread Limit" value={`${data.risk.max_spread_multiplier}× / ${data.risk.max_spread_absolute}`}/><Row label="Freshness" value={`Quote ${data.risk.quote_freshness_seconds}s · Account ${data.risk.account_freshness_seconds}s`}/><Row label="News Windows" value={`${data.risk.news_high_impact_blackout_pre_minutes}m blackout · ${data.risk.news_high_impact_pre_minutes}m pre · ${data.risk.news_high_impact_post_minutes}m post`}/><Row label="Reservation TTL" value={`${data.risk.reservation_ttl_seconds}s`} help="เวลาที่ระบบสงวน Risk Capacity ก่อนปล่อยคืนอัตโนมัติ"/><Row label="Kill Switch" value={data.killSwitch?.state||'UNAVAILABLE'} badge/></Grid></div>:<Unavailable label="RISK POLICY UNAVAILABLE"/>}<Link href="/risk" className="mt-4 inline-flex text-xs text-amber-300 underline">Open Risk Workspace →</Link></Panel>}

        {active==='system'&&<Panel title="System & Infrastructure" subtitle="Runtime checks จาก System Status; ไม่เปิดเผย topology หรือ credential">{data.system?<div className="space-y-4"><Grid>{Object.entries(data.system.modules).map(([key,module])=><Row key={key} label={key.replaceAll('_',' ')} value={<div><Badge>{module.state}</Badge><p className="mt-2 text-xs text-gray-500">{module.detail_th}</p><p className="mt-1 text-[10px] text-gray-600">Updated {when(module.updated_at)}</p></div>}/>)}</Grid>{config?<Grid><Row label="Environment" value={config.infrastructure.environment}/><Row label="Redis Configuration" value={config.infrastructure.redis_enabled?'ENABLED':'DISABLED'} badge/><Row label="Application Version" value="UNAVAILABLE" badge help="ไม่มี build version ที่ backend เปิดเผยอย่างเป็นทางการ จึงไม่สร้างเลขเวอร์ชันสมมติ"/></Grid>:<Unavailable/>}</div>:<Unavailable label="SYSTEM STATUS UNAVAILABLE"/>}</Panel>}

        {active==='security'&&<Panel title="Security / Session" subtitle="User-safe session metadata เท่านั้น ไม่แสดง token หรือ secret">{config&&data.user?<Grid><Row label="Authenticated User" value={data.user.email}/><Row label="Role" value={data.user.role} badge/><Row label="Access Token Lifetime" value={`${config.session.access_token_minutes} minutes`}/><Row label="Refresh Session Lifetime" value={`${config.session.refresh_session_days} days`}/><Row label="Configuration Authorization" value={data.user.role==='ADMIN'?'ADMIN STATUS VISIBILITY':'CREDENTIAL STATUS NOT EXPOSED'} badge/><Row label="Server Authority" value="READ ONLY" badge/></Grid>:<Unavailable label="SESSION METADATA UNAVAILABLE"/>}<p className="mt-4 text-xs leading-5 text-gray-500">Authentication และ authorization บังคับใช้ที่ Backend; การซ่อน UI ไม่ถือเป็นการควบคุมสิทธิ์</p></Panel>}

        {active==='provenance'&&<Panel title="Data Provenance" subtitle="แต่ละ subsystem มี provenance ของตนเอง ไม่มีป้าย REAL แบบรวมทั้งระบบ">{config?<div className="space-y-4"><DataProvenanceLine source={data.market?.source||config.market.provider} mode={data.market?.mode||config.market.provenance} condition={condition(data.market?.status)} asOf={data.market?.last_quote} derivedFrom="Market provider runtime"/><DataProvenanceLine source={data.news?.source||config.news.provider} mode={data.news?.source_mode||config.news.provenance} condition={condition(data.news?.state)} asOf={data.news?.provider_updated_at||data.news?.last_sync_at} derivedFrom="News provider runtime"/><DataProvenanceLine source={config.ai.provider_type} mode={config.ai.provenance==='EXTERNAL'?'ACTUAL':'FIXTURE'} condition={condition(data.system?.modules.ai_provider?.state)} asOf={data.system?.modules.ai_provider?.updated_at} derivedFrom="AI advisory configuration + runtime health"/><DataProvenanceLine source="risk/account configuration" mode={config.trading.account_provenance==='CONFIGURED_PAPER'?'PAPER':null} condition={config.trading.account_provenance==='CONFIGURED_PAPER'?'FRESH':'UNAVAILABLE'} asOf={config.as_of} derivedFrom="Trading mode; not broker equity"/><div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4"><Row label="Derived" value="Labeled at point of use"/><Row label="Partial / Stale" value="Never promoted to fresh"/><Row label="Unavailable" value="No silent defaults"/><Row label="Not Implemented" value="Broker Execution" badge/></div></div>:<Unavailable/>}</Panel>}
      </div>
    </div>
    <footer className="flex flex-wrap justify-between gap-3 border-t border-gray-800 pt-4 text-[10px] text-gray-600"><span>SERVER CONFIGURATION · READ ONLY · RESTART REQUIRED AFTER SERVER CONFIG CHANGE</span><span>No database migration · No server write endpoint · No execution authority</span></footer>
  </main>;
}
