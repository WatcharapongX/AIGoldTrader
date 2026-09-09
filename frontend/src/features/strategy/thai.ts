export const names: Record<string,string> = {
 READY:'ผ่านเงื่อนไขเพื่อเสนอแผน', BLOCKED_CONTEXT:'บริบทยังไม่พร้อม', NO_TRADE:'ยังไม่พบ Setup ที่ผ่านเกณฑ์',
 WAITING_CONFIRMATION:'รอการยืนยัน', DETECTED:'พบเงื่อนไขเบื้องต้น', INVALIDATED:'เงื่อนไขใช้ไม่ได้แล้ว',
 EXPIRED:'หมดอายุ', SUPERSEDED:'มี revision ใหม่', LONG:'ฝั่งซื้อ (LONG)', SHORT:'ฝั่งขาย (SHORT)',
 CONFIRMED:'ยืนยันแล้ว', PROVISIONAL:'ยังไม่สิ้นสุดหรือข้อมูลไม่ครบ', CANDIDATE:'รอราคาปิดยืนยัน',
 FORMING:'กำลังก่อตัว', FAILED:'รูปแบบล้มเหลว', WARMUP:'ประวัติยังไม่ครบ', UNAVAILABLE:'ไม่มีข้อมูล',
 ASIA:'เอเชีย', LONDON:'ลอนดอน', NEW_YORK:'นิวยอร์ก', OVERLAP:'ช่วงเวลาทับซ้อน', OFF_HOURS:'นอกช่วงหลัก',
 SCALP:'เก็งกำไรระยะสั้น', DAY_TRADE:'ภายในวัน', SWING:'ถือเป็นรอบ', RUN_TREND:'ติดตามแนวโน้ม',
 SINGLE_STRATEGY:'กลยุทธ์เดียว', MULTI_STRATEGY:'เปรียบเทียบกลยุทธ์', MULTI_TRADER:'เปรียบเทียบผู้เทรด',
 DOUBLE_TOP:'ยอดคู่', DOUBLE_BOTTOM:'ฐานคู่', TRIPLE_TOP:'ยอดสามจุด', TRIPLE_BOTTOM:'ฐานสามจุด',
 HEAD_AND_SHOULDERS:'ศีรษะและไหล่', INVERSE_HEAD_AND_SHOULDERS:'ศีรษะและไหล่กลับหัว',
 ASCENDING_TRIANGLE:'สามเหลี่ยมขาขึ้น', DESCENDING_TRIANGLE:'สามเหลี่ยมขาลง',
 SYMMETRICAL_TRIANGLE:'สามเหลี่ยมสมมาตร', RISING_WEDGE:'ลิ่มขาขึ้น', FALLING_WEDGE:'ลิ่มขาลง',
 BULLISH_FLAG:'ธงขาขึ้น', BEARISH_FLAG:'ธงขาลง',
 BULLISH:'โครงสร้างขาขึ้น', BEARISH:'โครงสร้างขาลง', NEUTRAL:'เป็นกลาง', UNKNOWN:'ยังไม่ยืนยัน',
 PDH:'จุดสูงสุดวันก่อน (PDH)', PDL:'จุดต่ำสุดวันก่อน (PDL)', PWH:'จุดสูงสุดสัปดาห์ก่อน (PWH)',
 PWL:'จุดต่ำสุดสัปดาห์ก่อน (PWL)', DAILY_OPEN:'ราคาเปิดวัน', WEEKLY_OPEN:'ราคาเปิดสัปดาห์'
};
export const label=(value:string) => names[value] || value;
export const price=(value:string|null|undefined) => value == null ? '—' :
 Number(value).toLocaleString('en-US',{maximumFractionDigits:4});
export const utc=(value:string) => new Date(value).toLocaleString('th-TH',{timeZone:'UTC',hour12:false})+' UTC';
