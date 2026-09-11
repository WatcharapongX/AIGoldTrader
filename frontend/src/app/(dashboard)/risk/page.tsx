import { RiskWorkspace } from '@/features/risk/RiskWorkspace';

export default function RiskPage() {
  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-100 flex items-center gap-2">
            <span>🛡️</span>
            <span>Risk Management & Kill Switch</span>
          </h1>
          <p className="text-sm text-gray-400 mt-1">
            ระบบบริหารจัดการความเสี่ยงระดับพอร์ตโฟลิโอ Fail-Closed Protection และสวิตช์ฉุกเฉิน (Phase 5)
          </p>
        </div>
        <span className="px-3 py-1 bg-emerald-500/20 text-emerald-400 text-xs font-semibold rounded-full border border-emerald-500/30">
          Phase 5 Active
        </span>
      </div>

      <RiskWorkspace />
    </div>
  );
}
