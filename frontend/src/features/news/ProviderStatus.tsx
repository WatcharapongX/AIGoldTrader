"use client";
import {useEffect,useState} from 'react';
import {api} from '@/lib/api';
import type {ProviderHealth} from '@/types/news.generated';
import {parseProviderHealth} from './contracts';
import {bangkok} from './thai';

export function ProviderStatus() {
 const [health,setHealth]=useState<ProviderHealth|null>(null);
 useEffect(()=>{
  const abort=new AbortController();let busy=false;
  const load=async()=>{
   if(busy)return;busy=true;
   try{const h=parseProviderHealth(await api.get('/news/provider/status',{signal:abort.signal}));
    if(!abort.signal.aborted)setHealth(h);
   }catch{if(!abort.signal.aborted)setHealth(null);}
   finally{busy=false;}
  };
  void load();const timer=setInterval(load,30000);
  return()=>{abort.abort();clearInterval(timer);};
 },[]);
 return <div className="news-warning" role="note" data-testid="news-provider-health">
  <strong>{health?.source || 'ยังไม่ทราบผู้ให้บริการ'} · {health?.state || 'UNAVAILABLE'}</strong>
  <p>{health?.detail_th || 'ตรวจความพร้อมของผู้ให้บริการไม่ได้'}</p>
  <small>Sync: {health?.last_sync_at ? bangkok(health.last_sync_at) : 'ยังไม่เคยรับข้อมูล'} ·
   {health?.connected ? ' เชื่อมต่อได้' : ' การเชื่อมต่อไม่พร้อม'} · ข่าวพร้อมใช้กับกลยุทธ์:
   {health?.calendar_usable_for_trading ? ' ผ่านเงื่อนไขข่าวเบื้องต้น' : ' ยังไม่พร้อม'}</small>
 </div>;
}
