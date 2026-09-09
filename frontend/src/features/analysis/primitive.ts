import type { IPrimitivePaneRenderer, IPrimitivePaneView, ISeriesPrimitive, Logical, SeriesAttachedParameter, UTCTimestamp } from 'lightweight-charts';
import type { AnalysisSnapshot } from '@/types/analysis.generated';

export const defaultLayers = { Swings: true, Labels: true, BOS: true, CHOCH: true, MSS: false,
  Liquidity: true, FVG: false, OB: false, PremiumDiscount: false, Sessions: false };
export type Layers = typeof defaultLayers;
export type Shape = { kind: 'point' | 'line' | 'zone'; time: string; end?: string | null;
  price: number; upper?: number; endPrice?: number; label: string; color: string; muted?: boolean };
const up = '#5ce0ba', down = '#ff9aaa', gold = '#e8bd65';

export function shapes(value: AnalysisSnapshot | null, layers: Layers): Shape[] {
  if (!value) return [];
  const output: Shape[] = [];
  if (layers.Swings) for (const swing of value.swings.filter(s => s.scope === 'EXTERNAL').slice(-40)) {
    output.push({ kind: 'point', time: swing.swing_time, price: Number(swing.price),
      label: layers.Labels ? swing.label : '', color: swing.kind === 'HIGH' ? down : up });
  }
  for (const event of value.events.filter(e => layers[e.kind]).slice(-20)) {
    output.push({ kind: 'line', time: event.swing_time, end: event.occurred_at, price: Number(event.price),
      label: event.kind + ' · ' + event.scope[0], color: event.direction === 'BULLISH' ? up : down });
  }
  if (layers.Liquidity) for (const level of value.liquidity.slice(-24)) {
    output.push({ kind: 'line', time: level.confirmed_at, end: level.ended_at, price: Number(level.price),
      label: level.kind + ' · ' + level.status, color: gold, muted: level.status !== 'ACTIVE' });
    if (level.status === 'SWEPT' && level.sweep_price && level.swept_at) output.push({
      kind: 'point', time: new Date(Date.parse(level.swept_at) -
        ({ M1:60, M3:180, M5:300, M15:900, M30:1800, H1:3600, H4:14400, D1:86400, W1:604800 }[value.timeframe]) * 1000).toISOString(), price: Number(level.sweep_price), label: 'SWEEP', color: gold });
  }
  for (const zone of value.zones.filter(z => ['FVG', 'IFVG'].includes(z.kind) ? layers.FVG : layers.OB).slice(-16)) {
    output.push({ kind: 'zone', time: zone.confirmed_at, end: zone.ended_at, price: Number(zone.lower_bound),
      upper: Number(zone.upper_bound), label: zone.kind + ' · ' + zone.status,
      color: zone.direction === 'BULLISH' ? up : down, muted: ['FILLED', 'INVALIDATED'].includes(zone.status) });
  }
  const range = value.dealing_range;
  if (layers.PremiumDiscount && range) {
    output.push({ kind: 'zone', time: range.confirmed_at, price: Number(range.equilibrium),
      upper: Number(range.upper_bound), label: 'PREMIUM', color: down });
    output.push({ kind: 'zone', time: range.confirmed_at, price: Number(range.lower_bound),
      upper: Number(range.equilibrium), label: 'DISCOUNT', color: up });
    output.push({ kind: 'line', time: range.confirmed_at, price: Number(range.equilibrium), label: 'EQUILIBRIUM', color: gold });
  }
  if (layers.Sessions) for (const session of value.sessions.slice(-8)) output.push({
    kind: 'zone', time: session.start, end: session.end, price: Number(session.low),
    upper: Number(session.high), label: session.name + ' · CLOSED', color: '#9dacf5' });
  return output;
}

export class AnalysisPrimitive implements ISeriesPrimitive {
  private attachedTo: SeriesAttachedParameter | null = null;
  private items: Shape[] = [];
  private renderer: IPrimitivePaneRenderer = { draw: target => {
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const owner = this.attachedTo;
      if (!owner) return;
      const scale = owner.chart.timeScale();
      // Anchor to existing chart timestamps, including missing-session boundaries.
      const x = (time: string): number | null => {
        const utc = Date.parse(time) / 1000 as UTCTimestamp;
        const index = scale.timeToIndex(utc, true);
        return index === null ? null : scale.logicalToCoordinate(Number(index) as Logical);
      };
      ctx.save(); ctx.beginPath(); ctx.rect(0, 0, mediaSize.width, mediaSize.height); ctx.clip();
      ctx.font = '10px sans-serif'; ctx.lineWidth = 1;
      const occupied: Array<[number, number]> = [];
      for (const item of this.items) {
        const left = x(item.time), y = owner.series.priceToCoordinate(item.price);
        const right = item.end ? x(item.end) : mediaSize.width - 6;
        if (left === null || y === null || right === null) continue;
        ctx.strokeStyle = item.color; ctx.fillStyle = item.color;
        ctx.globalAlpha = item.muted ? .35 : .8;
        ctx.setLineDash(item.muted ? [2, 4] : item.kind === 'line' ? [5, 4] : []);
        if (item.kind === 'point') {
          ctx.beginPath(); ctx.arc(left, y, 3, 0, Math.PI * 2); ctx.fill();
        } else if (item.kind === 'line') {
          ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, item.endPrice === undefined ? y : (owner.series.priceToCoordinate(item.endPrice) ?? y)); ctx.stroke();
        } else {
          const top = owner.series.priceToCoordinate(item.upper!);
          if (top === null) continue;
          ctx.globalAlpha = item.muted ? .025 : .08;
          ctx.fillRect(left, top, right - left, y - top);
          ctx.globalAlpha = item.muted ? .25 : .5;
          ctx.strokeRect(left, top, right - left, y - top);
        }
        const tx = Math.max(4, Math.min(left + 5, mediaSize.width - 110)), ty = y - 7;
        if (item.label && ty > 12 && ty < mediaSize.height &&
            !occupied.some(([a, b]) => Math.abs(a - tx) < 105 && Math.abs(b - ty) < 13)) {
          ctx.globalAlpha = item.muted ? .45 : .9; ctx.fillText(item.label, tx, ty); occupied.push([tx, ty]);
        }
      }
      ctx.restore();
    });
  }};
  private view: IPrimitivePaneView = { renderer: () => this.renderer, zOrder: () => 'normal' };
  attached(parameters: SeriesAttachedParameter) { this.attachedTo = parameters; parameters.requestUpdate(); }
  detached() { this.attachedTo = null; this.items = []; }
  paneViews() { return [this.view]; }
  updateShapes(items: Shape[]) { this.items = items; this.attachedTo?.requestUpdate(); }
  update(value: AnalysisSnapshot | null, layers: Layers) {
    this.items = shapes(value, layers); this.attachedTo?.requestUpdate();
  }
}
