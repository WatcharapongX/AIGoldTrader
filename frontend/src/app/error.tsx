"use client";

export default function ErrorPage({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4 bg-[#0a0a0a] p-6 text-center" role="alert">
      <h1 className="text-xl font-bold text-white">เกิดข้อผิดพลาดในการแสดงผล</h1>
      <p className="text-sm text-gray-400">ระบบไม่สามารถแสดงหน้านี้ได้ในขณะนี้ ข้อมูลเดิมไม่ได้ถูกเปลี่ยนแปลง</p>
      <button
        type="button"
        onClick={() => reset()}
        className="rounded-lg bg-amber-500/20 px-4 py-2 text-sm font-bold text-amber-300 border border-amber-500/40"
      >
        ลองอีกครั้ง
      </button>
    </main>
  );
}
