 'use client';
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { CalendarPage, EventDetail } from '@/types/news.generated';
import { parseCalendar, parseEvent } from './contracts';
import { bangkok, eventName, label, labels, numeric } from './thai';
import './news.css';
import {ProviderStatus} from './ProviderStatus';

export function CalendarWorkspace() {
  const [impact, setImpact] = useState(''), [status, setStatus] = useState(''), [category, setCategory] = useState('');
  const [currency, setCurrency] = useState(''), [relevant, setRelevant] = useState(true), [date, setDate] = useState('');
  const [data, setData] = useState<{key: string; value: CalendarPage} | null>(null);
  const [detail, setDetail] = useState<EventDetail | null>(null), [error, setError] = useState('');
  const query = new URLSearchParams({relevant_only:String(relevant)});
  if (impact) query.set('impact',impact); if (status) query.set('status',status);
  if (category) query.set('category',category); if (currency) query.set('currency',currency);
  if (date) { const start = new Date(date+'T00:00:00+07:00'); query.set('start',start.toISOString());
    query.set('end',new Date(start.getTime()+86400000).toISOString()); }
  const key = query.toString();
  useEffect(() => {
    const abort = new AbortController(); let busy = false;
    const load = async () => { if (busy) return; busy = true;
      try { const value = parseCalendar(await api.get('/calendar/economic?'+key,{signal:abort.signal}));
        if (!abort.signal.aborted) { setData({key,value}); setError(''); }
      } catch { if (!abort.signal.aborted) setError('โหลดปฏิทินไม่ได้ กรุณาตรวจการเชื่อมต่อ'); }
      finally { busy = false; }
    };
    void load(); const timer = setInterval(load,30000);
    return () => { abort.abort(); clearInterval(timer); };
  },[key]);
  const current = data?.key === key ? data.value : null;
  async function openEvent(id:string) {
    try { setDetail(parseEvent(await api.get('/news/events/'+encodeURIComponent(id)+'?as_of='+encodeURIComponent(current!.as_of)))); }
    catch { setError('โหลดรายละเอียดข่าวไม่ได้'); }
  }
  return <div className="calendar-workspace news-panel">
    <header className="news-heading"><div><p className="news-kicker">ปฏิทินเศรษฐกิจ</p><h1>ข่าวที่ต้องติดตาม</h1></div>
      <span>Asia/Bangkok · UTC+7</span></header>
    <ProviderStatus/>
    <div className="news-source">{current?.source_mode === 'FIXTURE' ? 'ข้อมูลข่าวสาธิต · DEMO NEWS DATA — ไม่ใช่กำหนดการหรือผลประกาศจริง' :
      current?.source_mode === 'LIVE' ? 'REAL · ข้อมูลข่าวจริง · ตรวจข้อจำกัดของแหล่งข่าวด้านบน' : 'ผู้ให้บริการปฏิทินไม่พร้อมใช้งาน'}</div>
    <div className="news-filters">
      <label>วันที่<input type="date" aria-label="วันที่ข่าว" value={date} onChange={e => setDate(e.target.value)} /></label>
      <label>สกุลเงิน<select aria-label="สกุลเงิน" value={currency} onChange={e=>setCurrency(e.target.value)}><option value="">ทั้งหมด</option><option>USD</option><option>EUR</option></select></label>
      <label>ผลกระทบ<select aria-label="ผลกระทบ" value={impact} onChange={e=>setImpact(e.target.value)}><option value="">ทั้งหมด</option>{['HIGH','MEDIUM','LOW'].map(v=><option key={v} value={v}>{label(v)}</option>)}</select></label>
      <label>ประเภท<select aria-label="ประเภท" value={category} onChange={e=>setCategory(e.target.value)}><option value="">ทั้งหมด</option>{['EMPLOYMENT','INFLATION','CENTRAL_BANK','GROWTH','CONSUMER','MANUFACTURING','SERVICES','HOUSING','LABOR','OTHER'].map(v=><option key={v} value={v}>{labels[v]}</option>)}</select></label>
      <label>สถานะ<select aria-label="สถานะ" value={status} onChange={e=>setStatus(e.target.value)}><option value="">ทั้งหมด</option><option value="upcoming">ยังไม่ประกาศ</option><option value="released">ประกาศแล้ว</option></select></label>
      <label className="news-check"><input type="checkbox" checked={relevant} onChange={e=>setRelevant(e.target.checked)}/>เกี่ยวข้องกับทอง</label>
    </div>
    {error && <p role="alert" className="news-warning">{error}</p>}
    {!current ? <p role="status">กำลังโหลดปฏิทิน…</p> : <>
      <p className="news-muted">ข้อมูลที่ทราบ ณ {bangkok(current.as_of)} · {current.events.length} เหตุการณ์
        {current.truncated && ' · แสดงบางส่วน กรุณาจำกัดตัวกรอง'}</p>
      {!current.events.length && <p data-testid="calendar-empty">ไม่มีข่าวตามเงื่อนไขในช่วงข้อมูลนี้</p>}
      <div className="calendar-events">{current.events.map(e=><article className="calendar-event" key={e.id}>
        <div><time>{bangkok(e.scheduled_at)}</time><p>{e.currency} · ผลกระทบ{label(e.impact)}</p></div>
        <div><button className="news-event-link" onClick={()=>void openEvent(e.id)}>{eventName(e)}</button><p>{label(e.status)} · {label(e.category)}</p></div>
        <dl><div><dt>ผลจริง</dt><dd>{numeric(e.actual,e.unit)}</dd></div><div><dt>คาดการณ์</dt><dd>{e.forecast == null ? 'ไม่มีคาดการณ์จากแหล่งนี้' : numeric(e.forecast,e.unit)}</dd></div>
        <div><dt>ครั้งก่อน</dt><dd>{e.previous == null ? 'ไม่มีข้อมูลครั้งก่อน' : numeric(e.previous,e.unit)}</dd></div><div><dt>ปรับครั้งก่อน</dt><dd>{e.revised_previous == null ? 'ไม่มีข้อมูล' : numeric(e.revised_previous,e.unit)}</dd></div></dl>
      </article>)}</div>
    </>}
    {detail && <section className="news-revisions" aria-label="ประวัติปรับปรุงข่าว"><div className="news-heading"><h2>{eventName(detail.event)}</h2>
      <button onClick={()=>setDetail(null)}>ปิดรายละเอียด</button></div><p>ประวัติที่รับรู้ถึง {bangkok(detail.as_of)}</p>
      {detail.revisions.map(e=><p key={e.revision_version}>รุ่น {e.revision_version} · {label(e.status)} · กำหนด {bangkok(e.scheduled_at)} ·
        รับรู้ {bangkok(e.available_at)} · ผลจริง {numeric(e.actual,e.unit)} · ปรับครั้งก่อน {e.revised_previous == null ? 'ไม่มีข้อมูล' : numeric(e.revised_previous,e.unit)}</p>)}</section>}
  </div>;
}
