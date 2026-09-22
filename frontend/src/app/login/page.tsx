"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { TradingStatus, useRuntimeStatus } from "@/components/layout/RuntimeStatus";
import { useAuthStore } from "@/stores/auth";

export default function LoginPage() {
  const router = useRouter();
  const runtime = useRuntimeStatus(false);
  const { login, isLoading, error, clearError } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    clearError();
    const success = await login(email, password);
    if (success) {
      const requested = new URLSearchParams(window.location.search).get("redirect");
      const safeRedirect = requested?.startsWith("/") && !requested.startsWith("//") ? requested : "/dashboard";
      router.push(safeRedirect);
    }
  }

  return (
    <div className="min-h-screen lg:h-screen lg:max-h-screen lg:overflow-hidden flex flex-col lg:flex-row bg-[#0a0f1a]">
      {/* Left Hero Section (60%) */}
      <div className="relative w-full lg:w-[60%] h-full flex-col justify-between p-6 lg:p-8 xl:p-10 hidden lg:flex overflow-hidden">
        {/* Background Image with Overlay */}
        <div 
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: "url('/images/login-bg.jpg')" }}
        />
        <div className="absolute inset-0 bg-gradient-to-br from-[#0a0f1a]/95 via-[#0a0f1a]/85 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0a0f1a] via-transparent to-transparent" />

        {/* Top Header Badge */}
        <div className="relative z-10">
          <div className="inline-flex items-center gap-3 bg-black/40 backdrop-blur-md border border-white/10 rounded-xl px-4 py-2">
            <div className="flex flex-col">
              <span className="text-gray-400 text-[10px] font-semibold uppercase tracking-wider">XAUUSD</span>
              <span className="text-white text-xs lg:text-sm font-bold">Gold Trading Platform</span>
            </div>
            <div className="w-px h-6 bg-white/15" />
            <div className="text-gray-400 text-xs">
              เข้าสู่ระบบเพื่อดูข้อมูลและสถานะผู้ให้บริการ
            </div>
          </div>
        </div>

        {/* Center Content */}
        <div className="relative z-10 max-w-2xl my-auto py-2">
          <h1 className="text-3xl lg:text-4xl xl:text-5xl font-extrabold text-white tracking-tight leading-tight">
            Smarter Trading <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 via-amber-500 to-orange-500">
              Brighter Opportunities
            </span>
          </h1>
          
          <p className="text-xs lg:text-sm text-gray-300 mt-2 mb-4 xl:mb-5 max-w-lg leading-relaxed">
            Combine verified market data, deterministic analysis, and disciplined trading workflows.
          </p>

          {/* Features Grid */}
          <div className="grid grid-cols-2 gap-2.5 lg:gap-3 max-w-xl">
            {/* Feature 1 */}
            <div className="bg-[#131b2c]/60 backdrop-blur-md border border-white/10 rounded-xl p-3 xl:p-3.5 hover:bg-white/10 transition-colors">
              <div className="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center mb-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className="text-white font-semibold text-xs lg:text-sm">Deterministic Analysis</h3>
              <p className="text-gray-400 text-[11px] lg:text-xs mt-0.5">ตรวจสอบ setup พร้อมแหล่งที่มาของข้อมูล</p>
            </div>
            
            {/* Feature 2 */}
            <div className="bg-[#131b2c]/60 backdrop-blur-md border border-white/10 rounded-xl p-3 xl:p-3.5 hover:bg-white/10 transition-colors">
              <div className="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center mb-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <h3 className="text-white font-semibold text-xs lg:text-sm">XAUUSD Market Data</h3>
              <p className="text-gray-400 text-[11px] lg:text-xs mt-0.5">ข้อมูลจากผู้ให้บริการ พร้อมสถานะความสด</p>
            </div>

            {/* Feature 3 */}
            <div className="bg-[#131b2c]/60 backdrop-blur-md border border-white/10 rounded-xl p-3 xl:p-3.5 hover:bg-white/10 transition-colors">
              <div className="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center mb-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 8v8m-4-5v5m-4-2v2m-2 4h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </div>
              <h3 className="text-white font-semibold text-xs lg:text-sm">Multiple Trading Styles</h3>
              <p className="text-gray-400 text-[11px] lg:text-xs mt-0.5">Day Trade | Swing Trade | SMC/ICT</p>
            </div>

            {/* Feature 4 */}
            <div className="bg-[#131b2c]/60 backdrop-blur-md border border-white/10 rounded-xl p-3 xl:p-3.5 hover:bg-white/10 transition-colors">
              <div className="w-7 h-7 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center mb-2">
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <h3 className="text-white font-semibold text-xs lg:text-sm">Analysis Only</h3>
              <p className="text-gray-400 text-[11px] lg:text-xs mt-0.5">ไม่มีการส่งคำสั่งซื้อขาย</p>
            </div>
          </div>
        </div>

        {/* Bottom Content */}
        <div className="relative z-10 w-full">
          <div className="text-amber-500/40 font-serif font-bold text-2xl lg:text-3xl xl:text-4xl tracking-[0.2em] uppercase leading-tight mb-3 select-none">
            Discipline<br />Creates Freedom
          </div>
          <div className="flex justify-between items-center text-[11px] lg:text-xs text-gray-400 border-t border-white/10 pt-2.5">
            <p className="italic text-gray-400">
              &quot;The best trade is a well-prepared trade.&quot;
            </p>
            <div className="flex items-center gap-3 text-gray-500">
              <span className="cursor-pointer hover:text-amber-500 transition-colors">Privacy Policy</span>
              <span>|</span>
              <span className="cursor-pointer hover:text-amber-500 transition-colors">Terms of Service</span>
              <span>|</span>
              <span className="cursor-pointer hover:text-amber-500 transition-colors">Support</span>
            </div>
          </div>
        </div>
      </div>

      {/* Right Login Form Section (40%) */}
      <div className="w-full lg:w-[40%] h-full flex flex-col justify-center items-center p-4 lg:p-6 xl:p-8 relative bg-[#0a0f1a] lg:bg-transparent overflow-y-auto lg:overflow-hidden">
        {/* Mobile Header (Hidden on desktop / notebook) */}
        <div className="lg:hidden w-full max-w-sm mb-6 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <svg className="w-7 h-7 text-amber-500" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L2 22h20L12 2zm0 3.5l7 14h-14l7-14z" />
            </svg>
            <span className="text-white font-bold text-lg">AIGoldTrader</span>
          </div>
          <div className="flex items-center gap-2 bg-white/5 px-3 py-1 rounded-full border border-white/10">
            <span className="text-white text-xs">🇹🇭 ไทย</span>
          </div>
        </div>

        {/* Login Card */}
        <div className="w-full max-w-[370px] xl:max-w-[390px] bg-[#121824]/90 lg:bg-[#121824]/80 backdrop-blur-2xl border border-white/10 rounded-2xl p-5 lg:p-6 shadow-2xl relative z-10">
          <div className="text-center mb-4">
            <div className="w-12 h-12 bg-amber-500/10 rounded-2xl flex items-center justify-center mx-auto mb-2.5 border border-amber-500/20">
              <svg className="w-6 h-6 text-amber-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2L2 22h20L12 2zm0 3.5l7 14h-14l7-14z" />
                <path d="M12 9l-3 6h6l-3-6z" fill="currentColor" opacity="0.5" />
              </svg>
            </div>
            <h2 className="text-xl lg:text-2xl font-bold text-white mb-0.5">Welcome Back</h2>
            <p className="text-gray-400 text-xs">Sign in to your account and trade smarter</p>
          </div>

          {error && (
            <div className="mb-3 p-2.5 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-2">
              <svg className="w-4 h-4 text-red-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-red-400 text-xs">{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="space-y-1">
              <label htmlFor="email" className="block text-xs font-medium text-gray-300">
                Username
              </label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-500 group-focus-within:text-amber-500 transition-colors">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
                <input
                  id="email"
                  type="email"
                  required
                  autoComplete="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-9 pr-3 py-2 rounded-xl bg-black/25 border border-white/10
                             text-white text-xs lg:text-sm placeholder-gray-500
                             focus:outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50
                             transition-all"
                  placeholder="admin@aigoldtrader.com"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label htmlFor="password" className="block text-xs font-medium text-gray-300">
                Password
              </label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-gray-500 group-focus-within:text-amber-500 transition-colors">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8V7a4 4 0 00-8 0v4h8z" />
                  </svg>
                </div>
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  required
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-9 pr-10 py-2 rounded-xl bg-black/25 border border-white/10
                             text-white text-xs lg:text-sm placeholder-gray-500
                             focus:outline-none focus:ring-1 focus:ring-amber-500/50 focus:border-amber-500/50
                             transition-all"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-500 hover:text-white transition-colors focus:outline-none"
                >
                  {showPassword ? (
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.29 3.29m0 0a10.05 10.05 0 015.71-3.29c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0l-3.29-3.29" />
                    </svg>
                  ) : (
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between text-xs pt-0.5">
              <label className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  className="w-3.5 h-3.5 rounded border-gray-600 bg-gray-800 text-amber-500 focus:ring-amber-500/50 focus:ring-offset-gray-900"
                />
                <span className="text-gray-400 group-hover:text-gray-300 transition-colors">Keep me signed in</span>
              </label>
              <a href="#" className="text-amber-500 hover:text-amber-400 font-medium transition-colors">
                Forgot password?
              </a>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 px-4 rounded-xl font-semibold text-xs lg:text-sm
                         bg-gradient-to-r from-amber-500 to-orange-500 hover:from-amber-400 hover:to-orange-400
                         text-white shadow-md shadow-amber-500/20
                         disabled:opacity-50 disabled:cursor-not-allowed
                         focus:outline-none focus:ring-2 focus:ring-amber-500/50
                         transition-all flex items-center justify-center gap-2 group"
            >
              {isLoading ? (
                <>
                  <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing in…
                </>
              ) : (
                <>
                  Sign In
                  <svg className="w-4 h-4 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </>
              )}
            </button>
          </form>

          {/* Safety Notice */}
          <div className="mt-3.5 p-2.5 rounded-xl bg-black/40 border border-white/5 text-center">
            <div className="flex items-center justify-center gap-1.5 text-xs">
              <span className="text-amber-400 font-bold tracking-wide">
                {runtime.health?.trading_mode ?? 'PAPER'}
              </span>
              <span className="text-gray-400 font-medium">
                Auto Trading: {runtime.health ? (runtime.health.live_auto_trading ? 'ON' : 'OFF') : 'OFF'}
              </span>
            </div>
            <div data-testid="trading-status" className="hidden">
              <TradingStatus health={runtime.health} />
            </div>
            <p className="text-[11px] text-amber-400/90 mt-1">วิเคราะห์เท่านั้น · ไม่มีการส่งคำสั่งซื้อขาย</p>
          </div>
        </div>

        {/* Trade Smarter signature */}
        <div className="mt-3 text-center hidden lg:block">
          <p className="text-amber-500/80 font-serif text-sm italic tracking-wide">
            Trade Smarter, Live Better
          </p>
        </div>
      </div>
    </div>
  );
}
