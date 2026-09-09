'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Timeframe } from '@/types/market.generated';
import type { AnalysisResponse, MultiTimeframeContext } from '@/types/analysis.generated';
import { parseAnalysis, parseContext } from './contracts';
import { AnalysisPrimitive, defaultLayers, type Layers, shapes } from './primitive';


const thai: Record<string,string> = {
 BULLISH:'โครงสร้างขาขึ้น', BEARISH:'โครงสร้างขาลง', NEUTRAL:'ยังไม่ชัดเจน', UNKNOWN:'ข้อมูลไม่เพียงพอ',
 MIXED:'หลายกรอบเวลาขัดแย้งกัน', TRENDING_UP:'มีแนวโน้มขึ้น', TRENDING_DOWN:'มีแนวโน้มลง',
 RANGING:'เคลื่อนในกรอบ', VOLATILE:'ผันผวนสูง', TRANSITION:'กำลังเปลี่ยนภาวะ',
 HIGH_VOLATILITY:'ผันผวนสูง', LOW_VOLATILITY:'ผันผวนต่ำ', CHOPPY:'แกว่งสลับทิศ',
 PREMIUM:'เหนือสมดุล', DISCOUNT:'ต่ำกว่าสมดุล', EQUILIBRIUM:'ใกล้สมดุล',
 READY:'พร้อมประเมิน', PARTIAL_HISTORY:'ประวัติยังไม่ครบ', INSUFFICIENT_DATA:'ข้อมูลไม่เพียงพอ',
 NO_STRUCTURE:'ยังไม่มีโครงสร้าง', ERROR:'ประเมินไม่ได้', COMPLETE:'ข้อมูลครบ', PARTIAL:'ข้อมูลบางส่วน',
 EMPTY:'ไม่มีข้อมูล', EXTERNAL:'โครงสร้างหลัก', INTERNAL:'โครงสร้างภายใน',
 internal_structure:'โครงสร้างภายใน', external_structure:'โครงสร้างหลัก', swings:'จุดกลับตัว',
 liquidity:'สภาพคล่อง', zones:'พื้นที่ราคา', dealing_range:'กรอบราคา', sessions:'ช่วงตลาด',
 indicators:'ตัวชี้วัด', regime:'ภาวะตลาด', fvg:'ช่องว่างราคา FVG', order_blocks:'พื้นที่คำสั่ง OB',
};
const describe = (code:string) => thai[code] ? thai[code]+' ('+code+')' : 'สถานะ '+code.replaceAll('_',' ');

export function AnalysisWorkspace({ symbol, timeframe, source, revision, primitive }: {
  symbol: string; timeframe: Timeframe; source: string; revision: string; primitive: AnalysisPrimitive;
}) {
  const [layers, setLayers] = useState<Layers>(defaultLayers);
  const [loaded, setLoaded] = useState<{ identity: string; value: AnalysisResponse; context: MultiTimeframeContext } | null>(null);
  const [failure, setFailure] = useState<{ identity: string; message: string } | null>(null);
  const identity = [symbol, timeframe, source, revision].join('|');
  const current = loaded?.identity === identity ? loaded : null;
  const error = failure?.identity === identity ? failure.message : '';
  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    if (source && revision) {
      void Promise.all([
        api.get('/analysis/structure?symbol=' + encodeURIComponent(symbol) + '&timeframe=' + timeframe, { signal: abort.signal }),
        api.get('/analysis/context?symbol=' + encodeURIComponent(symbol), { signal: abort.signal }),
      ]).then(([raw, rawContext]) => {
        const value = parseAnalysis(raw), context = parseContext(rawContext);
        if (value.symbol !== symbol || value.timeframe !== timeframe || value.source !== source ||
            context.symbol !== symbol || context.source !== source || context.algorithm_version !== value.algorithm_version) {
          throw new Error('Analysis source mismatch');
        }
        if (active) { setLoaded({ identity, value, context }); setFailure(null); }
      }).catch(() => {
        if (active) setFailure({ identity, message: 'โหลดการวิเคราะห์ไม่ได้ กรุณาเชื่อมต่อใหม่' });
      });
    }
    return () => { active = false; abort.abort(); };
  }, [identity, symbol, timeframe, source, revision]);
  useEffect(() => {
    primitive.update(current?.value ?? null, layers);
    return () => primitive.update(null, layers);
  }, [primitive, current, layers]);
  const value = current?.value;
  return <section className="analysis-workspace" aria-label="Market structure analysis">
    <div className="analysis-title"><div><p className="market-eyebrow">วิเคราะห์จากแท่งที่ปิดแล้ว</p><h2>โครงสร้างราคาและสภาพคล่อง</h2></div>
      <span className="analysis-version">{value?.algorithm_version || 'กำลังโหลด'} · {timeframe}</span></div>
    <div className="analysis-layers" role="group" aria-label="Chart overlays">
      {(Object.keys(layers) as Array<keyof Layers>).map(name =>
        <button key={name} aria-pressed={layers[name]} onClick={() => setLayers(old => ({ ...old, [name]: !old[name] }))}>
          {name === 'PremiumDiscount' ? 'Premium / Discount' : name}</button>)}
    </div>
    <p className="analysis-note">แสดงจุดกลับตัวเมื่อแท่งด้านขวาปิดยืนยันแล้ว พื้นที่ราคาเริ่ม ณ เวลายืนยัน ช่วงตลาดอ้างอิง UTC</p>
    {error ? <p role="alert">{error}</p> : !value ? <p role="status">กำลังโหลดโครงสร้างที่ยืนยันแล้ว…</p> : <>
      <div className="analysis-summary" data-testid="analysis-summary" data-shapes={shapes(value, layers).length}>
        <div><small>โครงสร้างหลัก</small><strong>{describe(value.external_state)}</strong></div>
        <div><small>โครงสร้างภายใน</small><strong>{describe(value.internal_state)}</strong></div>
        <div><small>ภาวะตลาด</small><strong>{describe(value.regime)}</strong></div>
        <div><small>ตำแหน่งในกรอบราคา</small><strong>{describe(value.dealing_range?.location || 'NO_STRUCTURE')}</strong></div>
      </div>
      <p className={'analysis-history ' + (value.history.status === 'PARTIAL' ? 'partial' : '')} data-testid="analysis-history">
        {describe(value.history.status)} · {value.history.returned}/{value.history.requested} แท่ง · ปิดแล้ว {value.history.closed} แท่ง
      </p>
      <p className="analysis-note" data-testid="analysis-as-of">ข้อมูลถึง {value.as_of || '—'} · {source} · config {value.config_id}</p>
      <p className="analysis-note">ขอบเขตเริ่ม {value.window_start || '—'}. เมื่อขอบเขตหรือข้อมูลต้นทางเปลี่ยน ระบบจะคำนวณใหม่ · input {value.input_id}</p>
      <p className="analysis-note">วัตถุที่หายจาก snapshot มีสถานะ “ยังไม่ทราบ” ไม่ถือว่า INVALIDATED จนมีข้อมูลระบุชัดเจน</p>
      <p className="analysis-note">สร้างผล {value.generated_at} · ส่งผล {value.served_at} · อายุแคช {value.cache_age_seconds.toFixed(1)} วินาที (UTC)</p>
      <details><summary>ความพร้อมและตัวชี้วัด</summary>
        <div className="analysis-table-wrap"><table><thead><tr><th>ส่วนวิเคราะห์</th><th>สถานะ</th><th>แท่งปิด / ขั้นต่ำ</th></tr></thead><tbody>
          {Object.entries(value.modules).map(([name, item]) => <tr key={name}><td>{describe(name)}</td>
            <td>{describe(item.status)}</td><td>{item.available_bars} / {item.minimum_bars_required}</td></tr>)}
        </tbody></table></div>
        <dl className="analysis-indicators">{Object.entries(value.indicators).map(([name, item]) =>
          <div key={name}><dt>{name.replaceAll('_', ' ')}</dt><dd>{item.value === null ? describe(item.status) : Number(item.value).toFixed(2)}</dd></div>)}</dl>
        <p className="analysis-note">ช่วงตลาด: {value.current_sessions.join(' + ') || 'นอกช่วงที่กำหนด'} · บริบทข่าว: ดูแผงข่าวด้านบน</p>
      </details>
      <details><summary>วัตถุที่ยืนยันแล้ว · {value.swings.length} จุดกลับตัว / {value.events.length} เหตุการณ์</summary>
        <div className="analysis-table-wrap"><table><thead><tr><th>วัตถุ</th><th>ราคา</th><th>เวลาเกิด UTC</th><th>เวลายืนยัน UTC</th></tr></thead><tbody>
          {[...value.swings.slice(-8).map(s => ({ id: s.id, label: s.label + ' ' + describe(s.scope), price: s.price, origin: s.swing_time, confirmed: s.confirmed_at })),
            ...value.events.slice(-6).map(e => ({ id: e.id, label: e.kind + ' ' + describe(e.direction), price: e.price, origin: e.occurred_at, confirmed: e.confirmed_at }))].map(item =>
              <tr key={item.id}><td>{item.label}</td><td>{Number(item.price).toFixed(2)}</td><td>{item.origin}</td><td>{item.confirmed}</td></tr>)}
        </tbody></table></div>
      </details>
      <div className="analysis-context"><h3>บริบทหลายกรอบเวลา <span>{describe(current.context.bias)}</span></h3>
        <div className="analysis-timeframes">{current.context.timeframes.map(row => <div key={row.timeframe} data-testid={'context-' + row.timeframe}>
          <b>{row.timeframe}</b><strong>{describe(row.state)}</strong><small>{row.history.returned}/{row.history.requested} · {describe(row.history.status)}</small>
          <small>{describe(row.status)}</small></div>)}</div>
      </div>
      <p className="analysis-note">เป็นคำอธิบายโครงสร้างราคาเท่านั้น · โหมด PAPER ยังไม่ส่งคำสั่งซื้อขาย</p>
    </>}
  </section>;
}
