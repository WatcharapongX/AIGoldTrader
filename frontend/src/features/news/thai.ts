import type { EconomicEvent } from '@/types/news.generated';
export const labels: Record<string, string> = {
  USD:'ค่าเงินดอลลาร์', INTEREST_RATES:'แนวโน้มอัตราดอกเบี้ย', CROSS_CURRENCY:'ความสัมพันธ์ระหว่างสกุลเงิน', RISK_SENTIMENT:'ความต้องการรับความเสี่ยง',
  NORMAL:'ภาวะข่าวปกติ', PRE_NEWS:'เตรียมรับข่าว', NEWS_LOCK:'ช่วงข่าวเสี่ยงสูง',
  RELEASE:'กำลังประกาศ', POST_NEWS_VOLATILITY:'สังเกตความผันผวนหลังข่าว',
  POST_NEWS_CONFIRMATION:'รอการยืนยันหลังข่าว', NORMALIZED:'ผ่านช่วงสังเกตข่าว', UNKNOWN:'ยังสรุปไม่ได้',
  USD_STRONG_POSITIVE:'ข้อมูลสนับสนุนดอลลาร์มาก', USD_POSITIVE:'ข้อมูลสนับสนุนดอลลาร์',
  USD_NEUTRAL:'ข้อมูลใกล้เคียงคาดการณ์', USD_NEGATIVE:'ข้อมูลกดดันดอลลาร์',
  USD_STRONG_NEGATIVE:'ข้อมูลกดดันดอลลาร์มาก', CONFLICTING:'ข้อมูลขัดแย้งกัน',
  STRONG:'ชัดเจน', MODERATE:'ปานกลาง', MIXED:'ผสมกัน',
  HIGH:'สูง', MEDIUM:'ปานกลาง', LOW:'ต่ำ', EMPLOYMENT:'การจ้างงาน', INFLATION:'เงินเฟ้อ',
  CENTRAL_BANK:'ธนาคารกลาง', GROWTH:'การเติบโต', CONSUMER:'ผู้บริโภค', MANUFACTURING:'การผลิต',
  SERVICES:'บริการ', HOUSING:'ที่อยู่อาศัย', LABOR:'ตลาดแรงงาน', OTHER:'อื่น ๆ',
  SCHEDULED:'มีกำหนดประกาศ', UPCOMING:'ใกล้ประกาศ', RELEASED:'ประกาศแล้ว', REVISED:'ปรับปรุงข้อมูล',
  CANCELLED:'ยกเลิก', DELAYED:'เลื่อนประกาศ', ALIGNED:'สอดคล้อง', WAITING:'รอข้อมูลยืนยัน',
  STRUCTURE_UNAVAILABLE:'ข้อมูลโครงสร้างไม่เพียงพอ', REACTION_UNAVAILABLE:'ข้อมูลราคาไม่เพียงพอ',
  UNAVAILABLE:'ข้อมูลไม่เพียงพอ', READY:'พร้อมประเมิน', UNCONFIRMED:'ยังไม่ยืนยันทิศทาง',
  STRONG_DIRECTIONAL:'ราคาเคลื่อนทางเดียวชัดเจน', WHIPSAW:'ราคาสะบัดสองทาง',
  LIQUIDITY_SWEEP_REVERSAL:'กวาดสภาพคล่องแล้วกลับทิศ', BREAKOUT:'ทะลุโครงสร้าง',
  FAILED_BREAKOUT:'ทะลุแล้วกลับเข้ากรอบ', MUTED:'ปฏิกิริยาราคาจำกัด',
  SPREAD_NORMAL:'ส่วนต่างราคาปกติ', SPREAD_ELEVATED:'ส่วนต่างราคาสูง', SPREAD_EXTREME:'ส่วนต่างราคาสูงมาก',
  ELEVATED:'ผันผวนสูง', EXTREME:'ผันผวนสูงมาก', INFORMATIONAL:'ใช้ประกอบบริบท',
  CAUTION:'ต้องระมัดระวัง', RESTRICTED:'จำกัดสิทธิ์จากบริบทข่าว',
  ALLOWED:'ผ่านเงื่อนไขข่าวเบื้องต้น', BLOCKED:'ไม่ผ่านเงื่อนไขข่าว', ELIGIBLE:'มีบริบทให้ประเมินต่อ',
  TREND_CONTINUATION:'ตามแนวโน้ม', MEAN_REVERSION:'กลับสู่ค่าเฉลี่ย', NEWS_MOMENTUM:'แรงส่งหลังข่าว',
  NEWS_REVERSAL:'กลับทิศหลังข่าว', ALL_ALIGNED:'องค์ประกอบสอดคล้องกันทั้งหมด',
  MOSTLY_ALIGNED:'ส่วนใหญ่สอดคล้องกัน', COMPLETE:'องค์ประกอบครบ', PARTIAL:'องค์ประกอบยังไม่ครบ',
};
const names: Record<string, string> = {
 NFP:'การจ้างงานนอกภาคเกษตร (NFP)', UNEMPLOYMENT:'อัตราว่างงาน', WAGES:'ค่าจ้างเฉลี่ยรายชั่วโมง',
 CPI:'ดัชนีราคาผู้บริโภค (CPI)', CORE_CPI:'เงินเฟ้อพื้นฐาน (Core CPI)', PCE:'ดัชนีราคาการบริโภค (PCE)',
 CORE_PCE:'เงินเฟ้อการบริโภคพื้นฐาน (Core PCE)', FOMC_RATE:'มติอัตราดอกเบี้ย Fed',
 FED_PRESS:'แถลงข่าวหลังประชุม Fed', POWELL_SPEECH:'ถ้อยแถลงประธาน Fed', GDP:'ผลิตภัณฑ์มวลรวม (GDP)',
 PPI:'ดัชนีราคาผู้ผลิต (PPI)', RETAIL_SALES:'ยอดค้าปลีก', ISM_MANUFACTURING:'ภาคการผลิต ISM',
 ISM_SERVICES:'ภาคบริการ ISM', ADP:'การจ้างงานภาคเอกชน ADP', JOLTS:'ตำแหน่งงานเปิดรับ JOLTS',
 JOBLESS_CLAIMS:'ผู้ขอรับสวัสดิการว่างงาน',
};
export const label = (value: string | undefined) => labels[value || 'UNKNOWN'] || 'ยังไม่มีคำอธิบาย';
export const eventName = (e: EconomicEvent) => (names[e.event_code] || e.event_name) + (e.event_name.includes('(YoY)') ? ' (เทียบปีก่อน)' : '');
export const bangkok = (value: string | null) => value ? new Intl.DateTimeFormat('th-TH', {
  timeZone:'Asia/Bangkok', day:'2-digit', month:'short', hour:'2-digit', minute:'2-digit', second:'2-digit'
}).format(new Date(value)) : 'ยังไม่มีข้อมูล';
export function numeric(value: string | null | undefined, unit?: string) {
  if (value === null || value === undefined) return 'ยังไม่มีผลประกาศ';
  return new Intl.NumberFormat('th-TH', { maximumFractionDigits: 4 }).format(Number(value)) +
    (unit === 'PERCENT' || unit === 'RATE' ? '%' : unit === 'THOUSANDS' ? ' พัน' : '');
}
export function countdown(target: string, at: number) {
 const seconds = Math.max(0, Math.ceil((Date.parse(target)-at)/1000));
 return Math.floor(seconds/3600)+' ชม. '+Math.floor(seconds%3600/60)+' นาที '+seconds%60+' วินาที';
}
