import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#0a0a0a] p-6 text-center">
      <h1 className="text-xl font-bold text-white">ไม่พบหน้าที่ต้องการ (404)</h1>
      <p className="text-sm text-gray-400">เส้นทางนี้ไม่มีอยู่ในระบบ กรุณาตรวจสอบ URL อีกครั้ง</p>
      <Link href="/dashboard" className="rounded-lg bg-amber-500/20 px-4 py-2 text-sm font-bold text-amber-300 border border-amber-500/40">
        กลับสู่ Dashboard
      </Link>
    </main>
  );
}
