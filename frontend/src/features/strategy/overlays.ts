import type { Shape } from '@/features/analysis/primitive';
import type { SetupCandidate, StrategyMarketContext } from '@/types/strategy.generated';
export const defaultLayers={periods:true,sessions:false,patterns:false,plan:false};
export type StrategyLayers=typeof defaultLayers;
export function strategyShapes(ctx:StrategyMarketContext|null,tf:string,candidate:SetupCandidate|null,layers:StrategyLayers):Shape[] {
 if (!ctx) return [];
 const output:Shape[]=[];
 for(const level of ctx.key_levels.filter(l=>
   layers.periods && ['PDH','PDL','PWH','PWL','DAILY_OPEN','WEEKLY_OPEN'].includes(l.kind) ||
   layers.sessions && ['ASIA_','LONDON_','NEW_YORK_'].some(prefix=>l.kind.startsWith(prefix))).slice(-24)) {
   output.push({kind:'line',time:level.valid_from,price:Number(level.price),label:level.kind,
     color:'#dcc389',muted:level.status!=='CONFIRMED'});
 }
 if(layers.patterns) for(const pattern of (ctx.frames.find(f=>f.timeframe===tf)?.patterns || []).slice(-4)) {
   for(let i=0;i<pattern.points.length;i++) {
     const point=pattern.points[i],next=pattern.points[i+1];
     output.push({kind:'point',time:point.time,price:Number(point.price),label:'P'+(i+1),color:'#ac9ef2'});
     if(next)output.push({kind:'line',time:point.time,end:next.time,price:Number(point.price),
       endPrice:Number(next.price),label:'',color:'#ac9ef2'});
   }
   output.push({kind:'line',time:pattern.detected_at,end:pattern.expires_at,price:Number(pattern.neckline),
     label:pattern.status==='CONFIRMED'?'ยืนยัน · แนวคอ':'รอยืนยัน · แนวคอ',color:'#ac9ef2',muted:pattern.status!=='CONFIRMED'});
   if(pattern.confirmed_at)output.push({kind:'point',time:pattern.confirmed_at,price:Number(pattern.neckline),
     label:'ยืนยัน',color:'#ac9ef2'});
 }
 const plan=candidate?.status==='READY'?candidate.plan:null;
 if(layers.plan && plan){
   output.push({kind:'zone',time:plan.as_of,end:plan.expires_at,price:Number(plan.entry_lower),
     upper:Number(plan.entry_upper),label:plan.direction+' · ENTRY',color:'#69d9ba'});
   output.push({kind:'line',time:plan.as_of,end:plan.expires_at,price:Number(plan.stop_loss),label:'SL',color:'#fb8d9f'});
   for(const target of plan.targets)output.push({kind:'line',time:plan.as_of,end:plan.expires_at,
     price:Number(target.price),label:target.name,color:'#69d9ba'});
 }
 return output;
}
