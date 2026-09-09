'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { AnalysisPrimitive } from '@/features/analysis/primitive';
import type { StrategyResponse } from '@/types/strategy.generated';
import { parseStrategy } from './contracts';
import { defaultLayers, strategyShapes, type StrategyLayers } from './overlays';
import { label, price, utc } from './thai';

export function StrategyWorkspace({timeframe,source,revision,primitive}:{
 timeframe:string;source:string;revision:string;primitive:AnalysisPrimitive;
}) {
 const [response,setResponse]=useState<StrategyResponse|null>(null);
 const [error,setError]=useState(''),[busy,setBusy]=useState(false),[refresh,setRefresh]=useState(0);
 const [mode,setMode]=useState('MULTI_TRADER'),[profileId,setProfileId]=useState('research');
 const [strategyId,setStrategyId]=useState('STRAT01'),[selectedId,setSelectedId]=useState('');
 const [layers,setLayers]=useState<StrategyLayers>(defaultLayers);
 const [clock,setClock]=useState(0);
 useEffect(()=>{
   const timer=setInterval(()=>{setClock(Date.now());setRefresh(v=>v+1);},60000);
   return()=>clearInterval(timer);
 },[]);
 useEffect(()=>{
   if(!source || !revision) return;
   const abort=new AbortController(); let active=true;
   const load=async()=>{
     setBusy(true);
     try{
       const value=parseStrategy(await api.get('/strategy/context',{signal:abort.signal}));
       if(value.evaluation.context.source!==source)throw new Error('แหล่งข้อมูลไม่ตรงกับกราฟ');
       if(active){setResponse(value);setError('');setClock(Date.now());}
     }catch(cause){if(active){setError(cause instanceof Error?cause.message:'โหลดบริบทไม่สำเร็จ');setResponse(null);}}
     finally{if(active)setBusy(false);}
   };
   void load();
   return()=>{active=false;abort.abort();};
 },[source,revision,refresh]);
 const ev=response?.evaluation,ctx=ev?.context;
 const available=(ev?.candidates || []).filter(c=>mode==='MULTI_TRADER' ||
   c.profile_id===profileId && (mode==='MULTI_STRATEGY' || c.strategy_id===strategyId));
 const selected=available.find(c=>c.id===selectedId) || available[0] || null;
 const expired=!!selected && Date.parse(selected.expires_at)<=clock;
 const stale=!!response && (response.stale || clock-Date.parse(response.evaluation.context.as_of)>120000);
 useEffect(()=>{
   primitive.updateShapes(strategyShapes(ctx || null,timeframe,stale || expired?null:selected,layers));
   return()=>primitive.updateShapes([]);
 },[ctx,timeframe,selected,layers,primitive,stale,expired]);
 const frame=ctx?.frames.find(f=>f.timeframe===timeframe);
 const news=ctx?.news_json?JSON.parse(ctx.news_json) as {source_mode:string;calendar_state:string;macro_bias:string;news_regime:string;spread_state:string}:null;
 const overlayNames:Record<keyof StrategyLayers,string>={periods:'ระดับวัน / สัปดาห์',sessions:'ระดับ Session',patterns:'รูปแบบราคา',plan:'Entry / SL / TP'};
 return <section className="strategy-workspace" aria-label="Strategy workspace" data-testid="strategy-workspace">
   <header className="strategy-header"><div><p className="market-eyebrow">PHASE 4 · ANALYSIS ONLY</p>
     <h2>กลยุทธ์และแผนการเทรด</h2><p>พิจารณาโครงสร้างและหลักฐานร่วมกัน · ไม่มีคำสั่งซื้อขาย</p></div>
     <span className="strategy-chip">PAPER · ปิดการส่งคำสั่ง</span></header>
   <div className="strategy-controls">
     <label>โหมดเปรียบเทียบ<select aria-label="Strategy mode" value={mode} onChange={e=>setMode(e.target.value)}>
       {['SINGLE_STRATEGY','MULTI_STRATEGY','MULTI_TRADER'].map(m=><option key={m} value={m}>{label(m)}</option>)}
     </select></label>
     <label>โปรไฟล์ผู้เทรด<select aria-label="Trader profile" value={profileId} onChange={e=>setProfileId(e.target.value)}>
       {(ev?.profiles || []).map(p=><option key={p.id} value={p.id}>{p.name} · {label(p.style)}</option>)}
     </select></label>
     <label>กลยุทธ์<select aria-label="Strategy selection" value={strategyId} onChange={e=>setStrategyId(e.target.value)}>
       {(ev?.strategies || []).map(s=><option key={s.id} value={s.id}>{s.name}</option>)}
     </select></label>
     <button onClick={()=>setRefresh(v=>v+1)} disabled={busy}>{busy?'กำลังประเมิน…':'ประเมินใหม่'}</button>
   </div>
   <p className="strategy-note">Adaptive: ยังไม่เปิดใช้งาน · คะแนนแสดงหลักฐานตามกฎ ไม่ใช่ความน่าจะเป็นกำไร</p>
   {error && <p role="alert" className="strategy-warning">ยังโหลดผลประเมินไม่ได้: {error}</p>}
   {!response && !error && <p role="status">กำลังรวบรวมบริบทตลาดชุดเดียวสำหรับทุกโปรไฟล์…</p>}
   {ctx && <>
     <div className="strategy-context">
       <div><span>ข้อมูล ณ เวลา</span><strong>{utc(ctx.as_of)}</strong></div>
       <div><span>บริบทเดียวกัน</span><strong title={ctx.id}>{ctx.id.slice(0,16)}</strong></div>
       <div><span>Session</span><strong>{label(ctx.current_session)}</strong></div>
       <div><span>แหล่งราคา</span><strong>{ctx.source}</strong></div>
     </div>
     {ctx.mode==='REPLAY' && <p className="strategy-warning">ข้อมูลทดสอบ · ไม่ใช่ Setup จากราคาจริง</p>}
     {(news?.source_mode!=='LIVE' || news.calendar_state!=='AVAILABLE') && <p className="strategy-warning" data-testid="strategy-news-block">
       ข่าวยังไม่พร้อมสำหรับ STRAT05–06 · STRAT01–04 ประเมินจากราคาและโครงสร้างตามปกติ</p>}
     {stale && <p className="strategy-warning">ผลนี้ล้าสมัยหรือข้อมูลราคาขาดการเชื่อมต่อ รอข้อมูลใหม่ก่อนพิจารณาแผน</p>}
     {!available.some(c=>c.status==='READY') && <p className="strategy-empty" data-testid="strategy-no-trade">ยังไม่พบ Setup ที่ผ่านเกณฑ์</p>}
     <div className="strategy-cards">
       {available.map(c=>{
         const p=ev!.profiles.find(p=>p.id===c.profile_id),s=ev!.strategies.find(s=>s.id===c.strategy_id);
         return <button className={'strategy-card'+(selected?.id===c.id?' selected':'')} key={c.id}
           aria-pressed={selected?.id===c.id} onClick={()=>setSelectedId(c.id)}>
           <span className="strategy-card-top">{p?.name}<b>{c.score}/100</b></span>
           <strong>{s?.name}</strong><span>{label(p?.style || '')}</span>
           <span className={'strategy-state '+c.status.toLowerCase()}>{label(c.status)}</span>
           <small>{label(c.direction)} · revision {c.context_id.slice(0,8)}</small>
         </button>;
       })}
     </div>
     {selected && <div className="strategy-detail" data-testid="strategy-detail">
       <div><h3>เงื่อนไขและหลักฐาน</h3>
         <p>{ev!.strategies.find(s=>s.id===selected.strategy_id)?.description_th}</p>
         <ul>{selected.evidence.map((e,i)=><li key={e.code+i}>{e.description_th} <b>{e.weight || 0} คะแนน</b>
           {e.source_ids?.length ? <small>อ้างอิง {e.source_ids.map(id=>id.slice(0,8)).join(' · ')}</small>:null}</li>)}</ul>
         {!!selected.missing_conditions.length && <><h4>เงื่อนไขที่ยังขาด</h4><ul>{selected.missing_conditions.map(m=><li key={m}>{m}</li>)}</ul></>}
         {!!selected.conflicts.length && <><h4>ข้อจำกัดที่บล็อก Setup</h4><ul>{selected.conflicts.map(m=><li key={m}>{m}</li>)}</ul></>}
       </div>
       <div><h3>ข้อเสนอแผนราคา</h3>
         {selected.plan && !expired && !stale ? <dl className="strategy-plan" data-testid="strategy-plan">
           <div><dt>ทิศทาง</dt><dd>{label(selected.plan.direction)}</dd></div>
           <div><dt>โซนเข้า</dt><dd>{price(selected.plan.entry_lower)} – {price(selected.plan.entry_upper)}</dd></div>
           <div><dt>จุดหยุดเชิงโครงสร้าง (SL)</dt><dd>{price(selected.plan.stop_loss)}</dd></div>
           {selected.plan.targets.map(t=><div key={t.name}><dt>{t.name}</dt><dd>{price(t.price)} · RR {price(t.rr)}</dd></div>)}
         </dl>:<p>ยังไม่มีแผน Entry / SL / TP ที่ผ่านเงื่อนไขครบถ้วน</p>}
         <p className="strategy-note">หมดอายุ {utc(selected.expires_at)}</p>
         <p>{selected.invalidation_th}</p>
         <p className="strategy-note">ไม่มี lot, ความเสี่ยงบัญชี หรือปุ่มส่งคำสั่ง</p>
       </div>
     </div>}
     <details className="strategy-section" open><summary>ความสอดคล้องกรอบใหญ่ / กรอบเล็ก</summary>
       <div className="strategy-frame-grid">{ctx.frames.map(f=>{
         const a=JSON.parse(f.analysis_json) as {external_state:string;regime:string};
         return <div key={f.timeframe}><b>{f.timeframe}</b><span>{label(a.external_state)}</span>
           <small>{f.bars}/{f.requested} แท่งปิด {f.bars<f.requested?'· ประวัติบางส่วน':''}</small></div>;
       })}</div>
       <p className="strategy-note">{ev!.profiles.find(p=>p.id===profileId)?.timeframe_map &&
         (()=>{const m=ev!.profiles.find(p=>p.id===profileId)!.timeframe_map;return 'โปรไฟล์ที่เลือก: '+m.context+' บริบท → '+m.bias+' ทิศทาง → '+m.setup+' Setup → '+m.trigger+' ยืนยัน · ขั้นต่ำ '+m.minimum_bars+' แท่ง';})()}</p>
     </details>
     <details className="strategy-section"><summary>ระดับสำคัญ รูปแบบราคา และ Indicator · {timeframe}</summary>
       <div className="strategy-analysis-grid">
         <div><h4>ระดับสำคัญ</h4><ul>{ctx.key_levels.filter(l=>['PDH','PDL','PWH','PWL','DAILY_OPEN','WEEKLY_OPEN'].includes(l.kind)).slice(-16)
           .map(l=><li key={l.id}>{label(l.kind)} <b>{price(l.price)}</b><small>{label(l.status)} · {l.timeframe}</small></li>)}</ul></div>
         <div><h4>รูปแบบราคา</h4>{!frame?.patterns.length && <p>ยังไม่พบรูปแบบที่ผ่านเกณฑ์เรขาคณิต</p>}
           <ul>{frame?.patterns.slice(-8).map(p=><li key={p.id}>{label(p.kind)} · {label(p.status)}<small>{p.reason_th}</small></li>)}</ul></div>
         <div><h4>Indicator ประกอบ</h4><ul>{frame?.indicators.map(i=><li key={i.name}>{i.name} <b>{price(i.value)}</b>
           <small>{label(i.status)} · ขั้นต่ำ {i.minimum_bars} แท่ง</small></li>)}</ul></div>
       </div>
     </details>
     <div className="strategy-overlays" role="group" aria-label="Strategy overlays">
       <span>แสดงบนกราฟ</span>{(Object.keys(layers) as (keyof StrategyLayers)[]).map(key=><label key={key}>
         <input type="checkbox" checked={layers[key]} onChange={e=>setLayers(v=>({...v,[key]:e.target.checked}))}/>{overlayNames[key]}</label>)}
     </div>
     <p className="strategy-note">ข้อมูลที่หายจากหน้าต่างย้อนหลังไม่ได้หมายถึง Setup ถูกยกเลิก · เก็บหลักฐานและประวัติ revision แยกกัน</p>
   </>}
 </section>;
}
