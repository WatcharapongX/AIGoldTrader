"use client";
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import { MarketConnection, type ConnectionState } from '@/features/chart/transport';
import type { DashboardSummary, EconomicEvent } from '@/types/dashboard.generated';
import type { Quote } from '@/types/market.generated';
import { bangkok, countdown, eventName, label as newsLabel, numeric } from '@/features/news/thai';
import { names as strategyLabels } from '@/features/strategy/thai';
import { parseDashboard } from './contracts';
import './dashboard.css';

const states: Record<string,string> = {
 HEALTHY:'พร้อมใช้งาน', DEGRADED:'ข้อมูลบางส่วน / ต้องตรวจสอบ', STALE:'ข้อมูลล้าสมัย', UNAVAILABLE:'ไม่พร้อมใช้งาน',
 UNKNOWN:'ยังยืนยันไม่ได้', DISABLED:'ปิดใช้งาน', CONNECTED:'เชื่อมต่อแล้ว', CONNECTING:'กำลังเชื่อมต่อ',
 RECONNECTING:'กำลังเชื่อมต่อใหม่', DISCONNECTED:'ขาดการเชื่อมต่อ', ERROR:'เชื่อมต่อผิดพลาด',
 BULLISH:'แนวโน้มขึ้น', BEARISH:'แนวโน้มลง', NEUTRAL:'เป็นกลาง', RANGE:'แกว่งในกรอบ', RANGING:'แกว่งในกรอบ',
 TRENDING_UP:'แนวโน้มขึ้น', TRENDING_DOWN:'แนวโน้มลง', HIGH_VOLATILITY:'ผันผวนสูง',
 LOW_VOLATILITY:'ผันผวนต่ำ', BREAKOUT:'ทะลุกรอบ', PULLBACK:'พักตัว', FULL:'ครบ', LIMITED:'ครอบคลุมบางส่วน',
 SCHEDULED:'รอประกาศ', RELEASED:'ประกาศแล้ว', REVISED:'มีการแก้ไข', PROVISIONAL:'ข้อมูลยังไม่ครบ',
 ...strategyLabels,
};
const name = (value: string | null | undefined) => value ? states[value] || value : 'ยังไม่มีข้อมูล';
const clockText = (value: string | null | undefined) => value ? bangkok(value) : 'ยังไม่มีเวลาอัปเดต';
function Badge({state}: {state: string}) {
 return <span className={'dc-badge ' + (['HEALTHY','CONNECTED'].includes(state) ? 'dc-good' : 'dc-caution')}>{name(state)}</span>;
}
function Event({event, clock}: {event: EconomicEvent; clock: number}) {
 return <article className="dc-event" data-testid="dashboard-event">
  <div className="dc-row"><strong>{eventName(event)}</strong><span>{event.currency} · {newsLabel(event.impact)}</span></div>
  <p>{clockText(event.scheduled_at)} · {name(event.status)} · {countdown(event.scheduled_at,clock)}</p>
  <dl className="dc-three"><div><dt>ผลจริง</dt><dd>{numeric(event.actual,event.unit)}</dd></div>
   <div><dt>คาดการณ์</dt><dd>{event.forecast === null ? 'ไม่มีคาดการณ์จากแหล่งนี้' : numeric(event.forecast,event.unit)}</dd></div>
   <div><dt>ค่าก่อนหน้า</dt><dd>{event.previous === null ? 'ไม่มีข้อมูลครั้งก่อน' : numeric(event.previous,event.unit)}</dd></div></dl>
 </article>;
}
export function Dashboard() {
 const [data,setData] = useState<DashboardSummary|null>(null), [error,setError] = useState('');
 const [quote,setQuote] = useState<Quote|null>(null), [ws,setWs] = useState<ConnectionState>('CONNECTING');
 const [clock,setClock] = useState(0);
 useEffect(() => {
  const abort = new AbortController(); let busy = false;
  const refresh = async () => {
   if (busy) return; busy = true;
   try {
    const value = parseDashboard(await api.get('/dashboard/summary',{signal:abort.signal}));
    if (!abort.signal.aborted) {setData(value);setError('');}
   } catch { if (!abort.signal.aborted) setError('โหลดสรุปไม่สำเร็จ ข้อมูลเดิมอาจล้าสมัย'); }
   finally {busy = false;}
  };
  const connection = new MarketConnection(async () => {
   await api.getMe(); const token = localStorage.getItem('access_token');
   if (!token) throw new Error('Session expired'); return token;
  }, message => { if (!abort.signal.aborted && message.quote) setQuote(message.quote); },
  state => {if (!abort.signal.aborted) setWs(state);}, 'XAUUSD','M5');
  connection.start(); void refresh();
  const timer = setInterval(refresh,30000), ticker = setInterval(() => setClock(Date.now()),1000);
  return () => {abort.abort(); clearInterval(timer); clearInterval(ticker); connection.stop();};
 },[]);
 const current = quote && quote.source === data?.market?.source ? quote : data?.quote;
 const old = !!data && (!!error || clock-Date.parse(data.generated_at)>65000);
 const staleQuote = !current || clock-Date.parse(current.timestamp) > (data?.market?.stale_after_seconds || 5)*1000;
 const provider = data?.news_provider;
 const plan = !old && !data?.strategy_stale && data?.current_plan && Date.parse(data.current_plan.expires_at)>clock ? data.current_plan : null;
 const reasons = [...new Set(data?.candidates.flatMap(c => [...c.conflicts,...c.missing_conditions]) || [])].slice(0,5);
 return <main className="dc" data-testid="dashboard">
  <header className="dc-header"><div><p className="dc-kicker">AI GOLD TRADER / COMMAND CENTER</p><h1>ภาพรวมตลาดและระบบ</h1>
   <p>XAUUSD · {data?.market?.source || 'กำลังตรวจสอบแหล่งราคา'} · {clockText(current?.timestamp)}</p></div>
   <div className="dc-actions"><span className="dc-paper">PAPER · ปิด Auto Trading</span><Link href="/trading">เปิดหน้าวิเคราะห์ ↗</Link></div></header>
  {error && <p className="dc-warning" role="alert">{error}</p>}
  {old && <p className="dc-warning" role="status">สรุปล้าสมัย · หยุดใช้สถานะแผนจนกว่าจะอัปเดตสำเร็จ</p>}
  {!data && <p role="status">กำลังรวบรวมข้อมูลตลาด ข่าว และกลยุทธ์…</p>}
  <div className="dc-grid">
   <section className="dc-card dc-wide" aria-label="ราคาตลาด"><div className="dc-row"><h2>ราคาตลาด</h2><Badge state={staleQuote ? 'STALE' : data?.market?.status || 'UNKNOWN'}/></div>
    <dl className="dc-prices"><div><dt>Bid</dt><dd data-testid="dashboard-bid">{current?.bid || '—'}</dd></div><div><dt>Ask</dt><dd>{current?.ask || '—'}</dd></div>
     <div><dt>Spread</dt><dd>{current?.spread || '—'}</dd></div><div><dt>ช่วงตลาด</dt><dd className="dc-small">{name(data?.current_session)}</dd></div></dl>
    <p>สภาวะ M5: {name(data?.structure.find(r=>r.timeframe==='M5')?.regime)} · ราคาจากบัญชี {data?.market?.mode || 'ยังไม่ยืนยัน'}</p>
   </section>
   <section className="dc-card dc-wide" aria-label="โครงสร้างตลาด"><div className="dc-row"><h2>โครงสร้างตลาด</h2><Link href="/trading">ดูโครงสร้างบนกราฟ →</Link></div>
    <div className="dc-structure">{data?.structure.map(r=><article key={r.timeframe}><strong>{r.timeframe}</strong><h3>{name(r.external_state)}</h3>
     <p>ภายใน: {name(r.internal_state)}</p><p>{r.latest_event ? r.latest_event.kind+' · '+name(r.latest_event.direction) : 'ยังไม่พบเหตุการณ์ยืนยัน'}</p>
     <small>{r.history.closed}/{r.history.requested} แท่งปิด · {clockText(r.as_of)}</small>
     <p className="dc-levels">{r.liquidity.map(l=>l.kind+' '+l.price).join(' · ') || 'ยังไม่มีระดับสภาพคล่อง'}</p></article>)}</div>
    {!data?.structure.length && <p>ยังไม่มีข้อมูลโครงสร้างที่ยืนยันได้</p>}
    <details><summary>ระดับราคาสำคัญ PDH / PDL / PWH / PWL / Asia</summary><div className="dc-level-grid">{data?.key_levels.map(k=><span key={k.id}>{k.kind} · {k.price} · {name(k.status)}</span>)}</div>
     {!data?.key_levels.length && <p>ยังไม่มีระดับราคาที่ส่งมาจากบริบทกลยุทธ์</p>}</details>
   </section>
   <section className="dc-card" aria-label="ข่าวเศรษฐกิจ"><div className="dc-row"><h2>ข่าวเศรษฐกิจ</h2><Link href="/calendar">ปฏิทินทั้งหมด →</Link></div>
    <p className="dc-warning">{provider?.source_mode==='LIVE' ? 'REAL · ข่าวจริง' : provider?.source_mode==='FIXTURE' ? 'DEMO NEWS DATA · ข้อมูลสาธิต' : 'ยังไม่มีแหล่งข่าว'} · {provider?.source || 'รอข้อมูล'}</p>
    <Badge state={old ? 'STALE' : provider?.state || 'UNAVAILABLE'}/>
    <p>{provider?.detail_th || 'ตรวจสอบผู้ให้บริการข่าวไม่สำเร็จ'}</p>
    <p>บริบทข่าว: {data?.news ? newsLabel(data.news.news_regime) : 'ยังไม่ทราบ'} · ดอลลาร์: {data?.news ? newsLabel(data.news.macro_bias) : 'ยังไม่ทราบ'}</p>
    <p className="dc-meta">Sync: {clockText(provider?.last_sync_at)} · Snapshot ต้นทาง: {clockText(provider?.provider_updated_at)} · รับข้อมูล: {clockText(provider?.received_at)}</p>
    {data?.calendar_events.map(e=><Event key={e.id} event={e} clock={clock || Date.parse(data.served_at)}/>)}
    {!data?.calendar_events.length && <p>ไม่มีรายการในขอบเขตข้อมูลที่รับมา · ไม่ได้หมายความว่าไม่มีข่าว</p>}
    <p className="dc-meta">ข่าวเป็นข้อควรระวังแยกต่างหากสำหรับ STRAT01–04 · ใช้ตัดสินเงื่อนไขข่าวเฉพาะ STRAT05–06</p>
    {provider?.source==='forex_factory' && <a href="https://www.forexfactory.com/calendar" target="_blank" rel="noreferrer">Forex Factory · Weekly Calendar Export ↗</a>}
    {provider?.source==='xoomar_calendar' && <a href="https://xoomar.com/markets/api/calendar" target="_blank" rel="noreferrer">แหล่งข้อมูล Xoomar · อ้างอิง BLS / Fed / BEA ↗</a>}
   </section>
   <section className="dc-card" aria-label="แผนปัจจุบัน"><div className="dc-row"><h2>แผนที่ผ่านเงื่อนไขปัจจุบัน</h2><span className="dc-paper">ข้อเสนอเท่านั้น</span></div>
    {plan ? <><h3>{name(plan.direction)} · คะแนน {plan.score}/100</h3><dl className="dc-three"><div><dt>Entry</dt><dd>{plan.entry_lower}–{plan.entry_upper}</dd></div>
     <div><dt>Stop loss</dt><dd>{plan.stop_loss}</dd></div>{plan.targets.slice(0,2).map(t=><div key={t.name}><dt>{t.name} · RR {t.rr}</dt><dd>{t.price}</dd></div>)}</dl>
     <p>{plan.invalidation_th}</p>{plan.evidence.map((e,i)=><p key={i}>{e.description_th}</p>)}
     {plan.warnings_th.map((w,i)=><p key={i}>{w}</p>)}</> : <><h3>ยังไม่มีแผนที่ผ่านเงื่อนไขครบ</h3>
      <p>คะแนนสูงเพียงอย่างเดียวไม่อนุมัติแผน ต้องผ่านเงื่อนไขตลาดและโครงสร้าง; เงื่อนไขข่าวใช้เฉพาะ STRAT05–06</p>
      {reasons.length ? <ul>{reasons.map(r=><li key={r}>{r}</li>)}</ul> : <p>รอผลประเมินจากระบบกลยุทธ์</p>}</>}
    <p className="dc-meta">ประเมิน ณ {clockText(data?.strategy_as_of)} · สร้างผล {clockText(data?.strategy_generated_at)}</p>
    <Link href="/trading">เปิดเหตุผลและหลักฐานทั้งหมด →</Link>
   </section>
   <section className="dc-card dc-wide" aria-label="สรุปกลยุทธ์"><div className="dc-row"><h2>กลยุทธ์ทั้ง 6</h2><span>คะแนนตามกฎ · ไม่ใช่โอกาสชนะ</span></div>
    <div className="dc-strategies">{data?.strategies.map(s=>{
     const c=data.candidates.filter(c=>c.strategy_id===s.id).sort((a,b)=>b.score-a.score || a.id.localeCompare(b.id))[0];
     return <article key={s.id}><small>{s.id}</small><h3>{s.name}</h3><p>{s.description_th}</p>
      <strong>{old || data.strategy_stale ? 'ข้อมูลล้าสมัย' : name(c?.status)}</strong><p>{name(c?.direction)} · {c ? c.score+'/100' : 'ยังไม่มีคะแนน'}</p></article>;
    })}</div>
   </section>
   <section className="dc-card" aria-label="โปรไฟล์ผู้เทรด"><h2>Trader Profiles · {data?.profiles.length || 'รอข้อมูล'}</h2>
    <div className="dc-profiles">{data?.profiles.map(p=><div key={p.id}><strong>{p.name}</strong><span>{name(p.style)}</span>
     <small>{p.allowed_strategies.join(' · ')} · {p.enabled ? 'เปิดประเมิน' : 'ปิดประเมิน'}</small></div>)}</div>
    <p className="dc-warning">Adaptive · RESERVED_DISABLED · ยังไม่เปิดใช้การปรับกลยุทธ์อัตโนมัติ</p>
   </section>
   <section className="dc-card" aria-label="สุขภาพระบบ"><h2>สุขภาพระบบและความสดของข้อมูล</h2>
    {data?.health.map(h=><div className="dc-health" key={h.module}><div><strong>{h.module==='market' ? 'MT5 / Market data' : h.module==='database' ? 'PostgreSQL' : h.module}</strong><small>{h.detail_th}</small></div>
     <Badge state={h.module==='websocket' ? ws : old && h.state==='HEALTHY' ? 'STALE' : h.module==='news' ? provider?.state || h.state : h.state}/></div>)}
    <p>WebSocket หน้านี้: <Badge state={ws}/></p><p className="dc-meta">โครงสร้างสร้างเมื่อ {clockText(data?.analysis_generated_at)}<br/>สรุปสร้างเมื่อ {clockText(data?.generated_at)} · อัปเดตทุก 30 วินาที</p>
   </section>
   <section className="dc-safety dc-wide" aria-label="ความปลอดภัยการเทรด"><strong>PAPER · วิเคราะห์เท่านั้น</strong><p>Auto Trading: ปิด · Broker execution: ปิด · ไม่อนุญาตส่งคำสั่งเงินจริง · Risk Engine: ยังไม่พัฒนา</p>
    <p>Phase 5 ยังไม่เริ่ม · รอ Combined Independent Review</p></section>
  </div>
 </main>;
}
