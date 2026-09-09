 'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { api } from '@/lib/api';
import type { NewsResponse } from '@/types/news.generated';
import { parseNews } from './contracts';
import { bangkok, countdown, eventName, label, numeric } from './thai';
import './news.css';
import {ProviderStatus} from './ProviderStatus';

export function TradingNewsPanel() {
  const [view, setView] = useState('current');
  const [data, setData] = useState<{view: string; value: NewsResponse; received: number} | null>(null);
  const [error, setError] = useState('');
  const [clock, setClock] = useState(0);
  useEffect(() => {
    const abort = new AbortController(); let busy = false;
    const fetchData = async () => {
      if (busy) return; busy = true;
      try {
        const value = parseNews(await api.get('/news/context?view='+view, {signal:abort.signal}));
        if (!abort.signal.aborted) { setData({view, value, received: Date.now()}); setError(''); }
      } catch { if (!abort.signal.aborted) setError('โหลดบริบทข่าวไม่ได้ กรุณารอการเชื่อมต่ออีกครั้ง'); }
      finally { busy = false; }
    };
    void fetchData();
    const timer = setInterval(fetchData, 15000), ticker = setInterval(() => setClock(Date.now()), 1000);
    return () => { abort.abort(); clearInterval(timer); clearInterval(ticker); };
  }, [view]);
  const current = data?.view === view ? data : null;
  const n = current?.value;
  const next = n?.upcoming_events[0];
  const active = n?.events.find(e => e.id === n.active_event_id);
  const at = n ? Date.parse(n.as_of) + (view === 'current' ? Math.max(0, clock-(current?.received || clock)) : 0) : 0;
  return <section className="news-panel" aria-label="บริบทข่าวเศรษฐกิจ" data-testid="news-panel">
    <header className="news-heading"><div><p className="news-kicker">ข่าวเศรษฐกิจ · XAUUSD</p>
      <h2>บริบทข่าวและเศรษฐกิจมหภาค</h2></div><Link href="/calendar">เปิดปฏิทินข่าว →</Link></header>
    <ProviderStatus/>
    <div className="news-source" role="note">{n?.source_mode === 'FIXTURE' ?
      'ข้อมูลข่าวสาธิต · DEMO NEWS DATA — กำหนดเวลาและตัวเลขนี้ไม่ใช่ข่าวจริง' :
      n?.source_mode === 'LIVE' ? 'ข้อมูลข่าวจริง · ตรวจความครอบคลุมและสถานะพร้อมใช้ด้านล่าง' : 'กำลังตรวจสอบแหล่งข่าว'}</div>
    <p className="news-muted">{n?.market_source === 'mt5_demo_iux' ? 'ราคา XAUUSD จริงจาก IUX Demo · ' : 'แหล่งราคา: '}{n?.market_source || 'รอยืนยัน'} · ข่าวและราคาเป็นคนละแหล่งข้อมูล
      {n?.source_mode === 'FIXTURE' && ' · ปฏิกิริยาราคาในช่วงสาธิตไม่ได้พิสูจน์ว่าข่าวเป็นสาเหตุ'}</p>
    {n?.source_mode === 'FIXTURE' && <label className="news-view">มุมมองสาธิต
      <select aria-label="มุมมองสาธิต" value={view} onChange={e => setView(e.target.value)}>
        <option value="current">ตามเวลาปัจจุบัน</option><option value="pre">ก่อนประกาศ</option>
        <option value="release">เพิ่งประกาศ</option><option value="post">หลังประกาศ</option>
        <option value="none">ไม่มีข่าว</option></select></label>}
    {error && <p role="alert" className="news-warning">{error} · ข้อมูลเดิมอาจล้าสมัย หยุดใช้สถานะสิทธิ์ด้านล่าง</p>}
    <p className="news-muted">เงื่อนไขข่าวใช้เฉพาะ STRAT05–06 · STRAT01–04 ใช้ข่าวเป็นข้อควรระวังแยกต่างหาก</p>
    {n && <p data-testid="news-release-status">{n.release_status === 'WAITING_FOR_ACTUAL' ? 'รอผลประกาศจริง · WAITING_FOR_ACTUAL' :
      n.release_status === 'PRE_NEWS' ? 'ก่อนประกาศ · PRE_NEWS' : n.release_status === 'NO_EVENT' ? 'ไม่มีเหตุการณ์ที่กำลังประเมิน' :
      n.release_status === 'WAITING_FOR_RELEASE' ? 'รอยืนยันการประกาศ' : 'รับผลประกาศแล้ว'} · คุณภาพชุดข้อมูล: {label(n.data_quality || 'UNAVAILABLE')}</p>}
    {!n ? <p role="status">กำลังโหลดข้อมูลข่าว…</p> : <>
      <div className="news-summary-grid">
        <article><span>สถานะข่าว</span><h3 data-testid="news-regime">{label(n.news_regime)}</h3>
          <p>{n.calendar_state === 'CALENDAR_UNAVAILABLE' ? 'ข่าวไม่พร้อมใช้ประกอบกลยุทธ์: ข้อมูลอาจไม่ครบหรือผู้ให้บริการขัดข้อง' :
            n.multiple_event_risk ? 'มีหลายกลุ่มข่าวใกล้กัน ต้องประเมินความเสี่ยงร่วมกัน' : 'ประเมินตามข้อมูลที่ทราบ ณ เวลานี้'}</p></article>
        <article><span>ภาพรวมดอลลาร์</span><h3>{label(n.macro_bias)}</h3><p>ความชัดเจน: {label(n.macro_strength)}</p></article>
        <article><span>ข่าวสำคัญถัดไป</span><h3>{next ? eventName(next) : 'ไม่มีข่าวในช่วงข้อมูล'}</h3>
          <p>{next ? countdown(next.scheduled_at, at) : 'ติดตามเมื่อมีข้อมูลเพิ่มเติม'}</p>
          {next && <small>{bangkok(next.scheduled_at)} · ผลกระทบ{label(next.impact)}</small>}</article>
      </div>
      <div className="news-explanation">{n.macro_bias === 'CONFLICTING' ?
        'ตัวเลขในชุดข่าวให้ผลต่างกัน รวมถึงการปรับข้อมูลเดิม จึงยังสรุปทิศทางไม่ได้' :
        n.macro_bias === 'UNKNOWN' ? 'ผลประกาศยังไม่ครบ หรือทิศทางต้องตีความตามบริบท เช่น เงินเฟ้อและนโยบายดอกเบี้ย' :
        'ภาพรวมนี้สรุปความต่างระหว่างผลจริงกับคาดการณ์ตามกฎที่ตั้งไว้ ต้องตรวจปฏิกิริยาราคาและโครงสร้างประกอบ'}
        <strong> ข้อมูลสนับสนุนดอลลาร์ไม่ใช่คำสั่งขายทอง และหน้านี้ไม่มีสัญญาณซื้อขาย</strong></div>
      {active && <div className="news-release"><h3>ชุดข่าวที่กำลังประเมิน · {bangkok(active.scheduled_at)}</h3>
        <p>{n.active_group && label(n.active_group.alignment)} · {n.active_group && label(n.active_group.completeness)}</p>
        <div className="news-event-grid">{n.events.filter(e => e.group_id === active.group_id).map(e =>
          <article key={e.id}><h4>{eventName(e)}</h4><small>ช่องทางต่อทอง: {n.xauusd_relevance[e.id]?.channels.map(label).join(' / ') || 'ยังไม่กำหนด'} · ระดับความเกี่ยวข้อง {n.xauusd_relevance[e.id]?.score ?? 0}/3</small><p>{label(e.status)} · ผลกระทบ{label(e.impact)}</p><dl>
            <div><dt>ผลจริง (Actual)</dt><dd>{numeric(e.actual,e.unit)}</dd></div>
            <div><dt>คาดการณ์ (Forecast)</dt><dd>{e.forecast == null ? 'ไม่มีคาดการณ์จากแหล่งนี้' : numeric(e.forecast,e.unit)}</dd></div>
            <div><dt>ครั้งก่อน (Previous)</dt><dd>{e.previous == null ? 'ไม่มีข้อมูลครั้งก่อน' : numeric(e.previous,e.unit)}</dd></div>
            <div><dt>ปรับครั้งก่อน</dt><dd>{e.revised_previous == null ? 'ไม่มีข้อมูลปรับปรุง' : numeric(e.revised_previous,e.unit)}</dd></div>
          </dl><small>รุ่นข้อมูล {e.revision_version} · รับรู้ {bangkok(e.available_at)}</small></article>)}</div></div>}
      <div className="news-detail-grid"><article><h3>ปฏิกิริยาราคา</h3><p>{label(n.reaction_state)}</p>
        <p>{label(n.spread_state)} · {n.spread_ratio === null ? 'ไม่มี spread ย้อนหลังเพียงพอ' : Number(n.spread_ratio).toFixed(2)+' เท่าของฐาน'}</p>
        <p>ความผันผวน: {label(n.volatility_state)}</p>
        {n.reaction_windows.map(w => <p key={w.seconds}>T+{w.seconds/60} นาที · {label(w.status)}
          {w.status === 'READY' && ' · ราคาเปลี่ยน '+numeric(w.return_percent)+'% · '+label(w.classification)}</p>)}
        <small>ประเมินจากแท่ง M1 ปิดครบช่วงเวลา ระดับวินาทีที่ไม่มีข้อมูลจะไม่ประมาณขึ้นเอง</small></article>
        <article><h3>การยืนยันโครงสร้าง</h3><p>{label(n.structure_confirmation.status)}</p>
          <p>ใช้ BOS / CHOCH / MSS ที่ยืนยันแล้ว และสภาพคล่องที่สังเกตได้</p>
          <small>วัตถุที่ไม่อยู่ใน snapshot = ยังไม่ทราบสถานะ ไม่ถือว่ายกเลิก</small>
          <p>ขอบเขตข้อมูล: {bangkok(n.structure_confirmation.upstream_window_start)} ถึง {bangkok(n.structure_confirmation.upstream_as_of)}</p></article>
        <article><h3>สิทธิ์จากบริบทข่าวเบื้องต้น</h3><p>{label(n.trade_policy_state)}</p>
          <dl>{Object.entries(n.strategy_eligibility).map(([key,value]) => <div key={key}><dt>{label(key)}</dt><dd>{error ? 'ข้อมูลล้าสมัย' : label(value)}</dd></div>)}</dl>
          <small>STRAT05–06 ยังต้องผ่านเงื่อนไขตลาดและโครงสร้างก่อนมีแผนวิเคราะห์ ไม่มีการส่งคำสั่ง</small></article></div>
      <footer className="news-metadata"><span>{view === 'current' ? 'เวลาข้อมูล' : 'เวลาสาธิต'}: {bangkok(n.as_of)} · Asia/Bangkok (UTC+7)</span>
        <span>สร้าง: {bangkok(n.generated_at)} · ส่ง: {bangkok(n.served_at)} · อายุแคช {n.cache_age_seconds.toFixed(1)} วินาที</span>
        <details><summary>ที่มาของการคำนวณ</summary><p>แหล่งข่าว {n.source} · รุ่น {n.news_engine_version}</p>
          <p>Config {n.config_id}</p><p>Fingerprint {n.fingerprint}</p>
          <p>Structure input {n.structure_confirmation.upstream_input_id || 'ไม่มีข้อมูล'}</p></details></footer>
    </>}
  </section>;
}
