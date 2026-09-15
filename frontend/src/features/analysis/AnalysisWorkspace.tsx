'use client';

import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import type { Timeframe } from '@/types/market.generated';
import type { AnalysisResponse, MultiTimeframeContext } from '@/types/analysis.generated';
import { parseAnalysis, parseContext } from './contracts';
import { AnalysisPrimitive, defaultLayers, type Layers, shapes } from './primitive';

const thai: Record<string, string> = {
  BULLISH: 'โครงสร้างขาขึ้น',
  BEARISH: 'โครงสร้างขาลง',
  NEUTRAL: 'ยังไม่ชัดเจน',
  UNKNOWN: 'ข้อมูลไม่เพียงพอ',
  MIXED: 'หลายกรอบเวลาขัดแย้งกัน',
  ALIGNED_BULLISH: 'สอดคล้องขาขึ้น (ALIGNED BULLISH)',
  ALIGNED_BEARISH: 'สอดคล้องขาลง (ALIGNED BEARISH)',
  TRENDING_UP: 'มีแนวโน้มขึ้น',
  TRENDING_DOWN: 'มีแนวโน้มลง',
  RANGING: 'เคลื่อนในกรอบ',
  VOLATILE: 'ผันผวนสูง',
  TRANSITION: 'กำลังเปลี่ยนภาวะ',
  HIGH_VOLATILITY: 'ผันผวนสูง',
  LOW_VOLATILITY: 'ผันผวนต่ำ',
  CHOPPY: 'แกว่งสลับทิศ',
  PREMIUM: 'เหนือสมดุล (Premium)',
  DISCOUNT: 'ต่ำกว่าสมดุล (Discount)',
  EQUILIBRIUM: 'ใกล้สมดุล (Equilibrium)',
  READY: 'พร้อมประเมิน',
  PARTIAL_HISTORY: 'ประวัติยังไม่ครบ',
  INSUFFICIENT_DATA: 'ข้อมูลไม่เพียงพอ',
  NO_STRUCTURE: 'ยังไม่มีโครงสร้าง',
  ERROR: 'ประเมินไม่ได้',
  COMPLETE: 'ข้อมูลครบ',
  PARTIAL: 'ข้อมูลบางส่วน',
  EMPTY: 'ไม่มีข้อมูล',
  EXTERNAL: 'โครงสร้างหลัก',
  INTERNAL: 'โครงสร้างภายใน',
  internal_structure: 'โครงสร้างภายใน',
  external_structure: 'โครงสร้างหลัก',
  swings: 'จุดกลับตัว Swings',
  liquidity: 'สภาพคล่อง Liquidity',
  zones: 'พื้นที่ราคา Zones',
  dealing_range: 'กรอบราคา Dealing Range',
  sessions: 'ช่วงเวลาตลาด Sessions',
  indicators: 'ตัวชี้วัด Indicators',
  regime: 'ภาวะตลาด Regime',
  fvg: 'ช่องว่างราคา FVG',
  order_blocks: 'พื้นที่คำสั่ง Order Block',
};

const describe = (code: string) =>
  thai[code] ? thai[code] + ' (' + code + ')' : 'สถานะ ' + code.replaceAll('_', ' ');

export function AnalysisWorkspace({
  symbol,
  timeframe,
  source,
  revision,
  primitive,
}: {
  symbol: string;
  timeframe: Timeframe;
  source: string;
  revision: string;
  primitive: AnalysisPrimitive;
}) {
  const [layers, setLayers] = useState<Layers>(defaultLayers);
  const [loaded, setLoaded] = useState<{
    identity: string;
    value: AnalysisResponse;
    context: MultiTimeframeContext;
  } | null>(null);
  const [failure, setFailure] = useState<{ identity: string; message: string } | null>(null);
  const identity = [symbol, timeframe, source, revision].join('|');
  const current = loaded?.identity === identity ? loaded : null;
  const error = failure?.identity === identity ? failure.message : '';

  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    if (source && revision) {
      void Promise.all([
        api.get('/analysis/structure?symbol=' + encodeURIComponent(symbol) + '&timeframe=' + timeframe, {
          signal: abort.signal,
        }),
        api.get('/analysis/context?symbol=' + encodeURIComponent(symbol), { signal: abort.signal }),
      ])
        .then(([raw, rawContext]) => {
          const value = parseAnalysis(raw);
          const context = parseContext(rawContext);
          if (
            value.symbol !== symbol ||
            value.timeframe !== timeframe ||
            value.source !== source ||
            context.symbol !== symbol ||
            context.source !== source ||
            context.algorithm_version !== value.algorithm_version
          ) {
            throw new Error('Analysis source mismatch');
          }
          if (active) {
            setLoaded({ identity, value, context });
            setFailure(null);
          }
        })
        .catch(() => {
          if (active) setFailure({ identity, message: 'โหลดการวิเคราะห์ไม่ได้ กรุณาเชื่อมต่อใหม่' });
        });
    }
    return () => {
      active = false;
      abort.abort();
    };
  }, [identity, symbol, timeframe, source, revision]);

  useEffect(() => {
    primitive.update(current?.value ?? null, layers);
    return () => primitive.update(null, layers);
  }, [primitive, current, layers]);

  const value = current?.value;

  // Active SMC objects priority (nearest / still valid)
  const activeLiquidity = (value?.liquidity || []).filter((l) => !l.ended_at);
  const buySideLiquidity = activeLiquidity.filter((l) => l.kind === 'BSL');
  const sellSideLiquidity = activeLiquidity.filter((l) => l.kind === 'SSL');
  const activeZones = (value?.zones || []).filter((z) => !z.ended_at);
  const fvgZones = activeZones.filter((z) => z.kind === 'FVG');
  const obZones = activeZones.filter((z) => z.kind === 'OB');

  // MTF Confluence label
  const mtfBias = current?.context.bias || 'MIXED';

  return (
    <section className="analysis-workspace" aria-label="Market structure analysis">
      <div className="analysis-title">
        <div>
          <p className="market-eyebrow">วิเคราะห์จากแท่งที่ปิดแล้ว</p>
          <h2>โครงสร้างราคาและสภาพคล่อง</h2>
        </div>
        <span className="analysis-version">
          {value?.algorithm_version || 'กำลังโหลด'} · {timeframe}
        </span>
      </div>

      <div className="analysis-layers" role="group" aria-label="Chart overlays">
        {(Object.keys(layers) as Array<keyof Layers>).map((name) => (
          <button
            key={name}
            aria-pressed={layers[name]}
            onClick={() => setLayers((old) => ({ ...old, [name]: !old[name] }))}
          >
            {name === 'PremiumDiscount' ? 'Premium / Discount' : name}
          </button>
        ))}
      </div>

      <p className="analysis-note">
        แสดงจุดกลับตัวเมื่อแท่งด้านขวาปิดยืนยันแล้ว พื้นที่ราคาเริ่ม ณ เวลายืนยัน ช่วงตลาดอ้างอิง UTC
      </p>

      {error ? (
        <p role="alert">{error}</p>
      ) : !value ? (
        <p role="status">กำลังโหลดโครงสร้างที่ยืนยันแล้ว…</p>
      ) : (
        <>
          {/* Main Structural State Summary */}
          <div
            className="analysis-summary"
            data-testid="analysis-summary"
            data-shapes={shapes(value, layers).length}
          >
            <div>
              <small>โครงสร้างหลัก</small>
              <strong>{describe(value.external_state)}</strong>
            </div>
            <div>
              <small>โครงสร้างภายใน</small>
              <strong>{describe(value.internal_state)}</strong>
            </div>
            <div>
              <small>ภาวะตลาด</small>
              <strong>{describe(value.regime)}</strong>
            </div>
            <div>
              <small>ตำแหน่งในกรอบราคา</small>
              <strong>{describe(value.dealing_range?.location || 'NO_STRUCTURE')}</strong>
            </div>
          </div>

          {/* Active SMC / ICT Summary Grid */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 my-4 p-4 bg-black/30 rounded-xl border border-white/5 text-xs">
            {/* Liquidity State */}
            <div className="space-y-1.5">
              <span className="text-gray-400 font-semibold block text-[11px]">
                💧 สภาพคล่องคงเหลือ (Active Liquidity):
              </span>
              <div className="flex items-center justify-between text-gray-200">
                <span>Buy-Side (BSL):</span>
                <strong className="text-emerald-400 font-mono">
                  {buySideLiquidity.length > 0
                    ? `$${Number(buySideLiquidity[0].price).toFixed(2)} (${buySideLiquidity.length} จุด)`
                    : 'ไม่มี BSL ค้าง'}
                </strong>
              </div>
              <div className="flex items-center justify-between text-gray-200">
                <span>Sell-Side (SSL):</span>
                <strong className="text-rose-400 font-mono">
                  {sellSideLiquidity.length > 0
                    ? `$${Number(sellSideLiquidity[0].price).toFixed(2)} (${sellSideLiquidity.length} จุด)`
                    : 'ไม่มี SSL ค้าง'}
                </strong>
              </div>
            </div>

            {/* FVG & Order Blocks */}
            <div className="space-y-1.5">
              <span className="text-gray-400 font-semibold block text-[11px]">
                📦 โซนราคาสำคัญ (Active Zones):
              </span>
              <div className="flex items-center justify-between text-gray-200">
                <span>Fair Value Gaps (FVG):</span>
                <strong className="text-amber-400 font-mono">
                  {fvgZones.length > 0
                    ? `${fvgZones.length} โซน (ใกล้สุด: $${Number(fvgZones[0].lower_bound).toFixed(2)})`
                    : 'ไม่มี FVG แอ็กทิฟ'}
                </strong>
              </div>
              <div className="flex items-center justify-between text-gray-200">
                <span>Order Blocks (OB):</span>
                <strong className="text-blue-400 font-mono">
                  {obZones.length > 0
                    ? `${obZones.length} โซน (ใกล้สุด: $${Number(obZones[0].lower_bound).toFixed(2)})`
                    : 'ไม่มี OB แอ็กทิฟ'}
                </strong>
              </div>
            </div>

            {/* Dealing Range Boundaries */}
            <div className="space-y-1.5">
              <span className="text-gray-400 font-semibold block text-[11px]">
                ⚖️ Dealing Range &amp; Equilibrium:
              </span>
              {value.dealing_range ? (
                <>
                  <div className="flex items-center justify-between text-gray-200">
                    <span>Equilibrium (50%):</span>
                    <strong className="text-amber-300 font-mono">
                      ${Number(value.dealing_range.equilibrium).toFixed(2)}
                    </strong>
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-gray-400">
                    <span>High: ${Number(value.dealing_range.upper_bound).toFixed(2)}</span>
                    <span>Low: ${Number(value.dealing_range.lower_bound).toFixed(2)}</span>
                  </div>
                </>
              ) : (
                <p className="text-gray-500 italic">ยังไม่มี Dealing Range ที่ยืนยัน</p>
              )}
            </div>
          </div>

          <p
            className={'analysis-history ' + (value.history.status === 'PARTIAL' ? 'partial' : '')}
            data-testid="analysis-history"
          >
            {describe(value.history.status)} · {value.history.returned}/{value.history.requested} แท่ง ·
            ปิดแล้ว {value.history.closed} แท่ง
          </p>

          <p className="analysis-note" data-testid="analysis-as-of">
            ข้อมูลถึง {value.as_of || '—'} · {source} · config {value.config_id}
          </p>
          <p className="analysis-note">
            ขอบเขตเริ่ม {value.window_start || '—'}. เมื่อขอบเขตหรือข้อมูลต้นทางเปลี่ยน ระบบจะคำนวณใหม่ ·
            input {value.input_id}
          </p>
          <p className="analysis-note">
            วัตถุที่หายจาก snapshot มีสถานะ “ยังไม่ทราบ” ไม่ถือว่า INVALIDATED จนมีข้อมูลระบุชัดเจน
          </p>
          <p className="analysis-note">
            สร้างผล {value.generated_at} · ส่งผล {value.served_at} · อายุแคช{' '}
            {value.cache_age_seconds.toFixed(1)} วินาที (UTC)
          </p>

          {/* Details 1: Technical Indicators and Module Readiness */}
          <details>
            <summary>ความพร้อมและตัวชี้วัดเชิงเทคนิค (Authoritative Indicators)</summary>
            <div className="analysis-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>ส่วนวิเคราะห์</th>
                    <th>สถานะ</th>
                    <th>แท่งปิด / ขั้นต่ำ</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(value.modules).map(([name, item]) => (
                    <tr key={name}>
                      <td>{describe(name)}</td>
                      <td>{describe(item.status)}</td>
                      <td>
                        {item.available_bars} / {item.minimum_bars_required}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Authoritative backend indicators (ATR, etc.) */}
            <dl className="analysis-indicators">
              {Object.entries(value.indicators).map(([name, item]) => (
                <div key={name}>
                  <dt>{name.replaceAll('_', ' ')}</dt>
                  <dd>
                    {item.value === null ? describe(item.status) : Number(item.value).toFixed(2)}
                  </dd>
                </div>
              ))}
            </dl>
            <p className="analysis-note">
              ช่วงตลาด: {value.current_sessions.join(' + ') || 'นอกช่วงที่กำหนด'} · บริบทข่าว:
              ดูแผงข่าวด้านบน
            </p>
          </details>

          {/* Details 2: Confirmed Structural Objects & Events with Occurrence vs Confirmation clocks */}
          <details>
            <summary>
              วัตถุที่ยืนยันแล้ว · {value.swings.length} จุดกลับตัว / {value.events.length} เหตุการณ์
            </summary>
            <div className="analysis-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>วัตถุ / เหตุการณ์</th>
                    <th>ราคา</th>
                    <th>เวลาเกิด (Occurred UTC)</th>
                    <th>เวลายืนยัน (Confirmed UTC)</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ...value.swings.slice(-8).map((s) => ({
                      id: s.id,
                      label: s.label + ' ' + describe(s.scope),
                      price: s.price,
                      origin: s.swing_time,
                      confirmed: s.confirmed_at,
                    })),
                    ...value.events.slice(-6).map((e) => ({
                      id: e.id,
                      label: e.kind + ' ' + describe(e.direction),
                      price: e.price,
                      origin: e.occurred_at,
                      confirmed: e.confirmed_at,
                    })),
                  ].map((item) => (
                    <tr key={item.id}>
                      <td>{item.label}</td>
                      <td className="font-mono">${Number(item.price).toFixed(2)}</td>
                      <td className="font-mono text-gray-400">{item.origin}</td>
                      <td className="font-mono text-emerald-400">{item.confirmed}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="analysis-note">
              * ความแตกต่างระหว่างเวลาเกิด (Occurred) และเวลายืนยัน (Confirmed) ยืนยันว่าไม่มี Lookahead Bias
            </p>
          </details>

          {/* Multi-Timeframe Context */}
          <div className="analysis-context">
            <div className="flex items-center justify-between mb-2">
              <h3>
                บริบทหลายกรอบเวลา <span>{describe(mtfBias)}</span>
              </h3>
              <span className="text-xs px-2.5 py-0.5 rounded font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30">
                MTF CONFLUENCE: {mtfBias}
              </span>
            </div>

            <div className="analysis-timeframes">
              {current.context.timeframes.map((row) => (
                <div key={row.timeframe} data-testid={'context-' + row.timeframe}>
                  <b>{row.timeframe}</b>
                  <strong>{describe(row.state)}</strong>
                  <small>
                    {row.history.returned}/{row.history.requested} · {describe(row.history.status)}
                  </small>
                  <small>{describe(row.status)}</small>
                </div>
              ))}
            </div>
          </div>

          <p className="analysis-note">
            เป็นคำอธิบายโครงสร้างราคาเท่านั้น · โหมด PAPER ยังไม่ส่งคำสั่งซื้อขาย
          </p>
        </>
      )}
    </section>
  );
}
