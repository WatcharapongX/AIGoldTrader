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
    <div className="min-h-screen flex flex-col lg:flex-row bg-[#0a0f1a]">
      {/* Left Hero Section (60%) */}
      <div className="relative w-full lg:w-[60%] flex flex-col justify-between p-8 lg:p-12 hidden md:flex">
        {/* Background Image with Overlay */}
        <div 
          className="absolute inset-0 bg-cover bg-center bg-no-repeat"
          style={{ backgroundImage: "url('/images/login-bg.jpg')" }}
        />
        <div className="absolute inset-0 bg-gradient-to-br from-[#0a0f1a]/95 via-[#0a0f1a]/80 to-transparent" />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0a0f1a] via-transparent to-transparent" />

        {/* Top Header */}
        <div className="relative z-10 flex justify-between items-start w-full">
          <div className="flex items-center gap-3">
            <svg className="w-8 h-8 text-amber-500" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L2 22h20L12 2zm0 3.5l7 14h-14l7-14z" />
              <path d="M12 9l-3 6h6l-3-6z" fill="currentColor" opacity="0.5" />
            </svg>
            <span className="text-gray-300 font-medium tracking-wide text-sm hidden sm:block">
              Market Structure &middot; Strategy Analysis
            </span>
          </div>
          <div className="flex items-center gap-2 bg-white/10 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/5 cursor-pointer hover:bg-white/15 transition-colors">
            <span className="text-lg leading-none">🇹🇭</span>
            <span className="text-white text-sm font-medium">ไทย</span>
          </div>
        </div>

        {/* Center Content */}
        <div className="relative z-10 max-w-3xl mt-12 mb-auto">
          {/* Market Display */}
          <div className="inline-flex items-center gap-4 bg-white/5 backdrop-blur-xl border border-white/10 rounded-2xl px-6 py-3 mb-8">
            <div className="flex flex-col">
              <span className="text-gray-400 text-xs font-semibold uppercase tracking-wider">XAUUSD</span>
              <span className="text-white text-lg font-bold">Gold Trading Platform</span>
            </div>
            <div className="w-px h-8 bg-white/10"></div>
            <div className="flex flex-col text-gray-400">
              <span className="text-xs font-medium">เข้าสู่ระบบเพื่อดูข้อมูลและสถานะผู้ให้บริการ</span>
            </div>
          </div>

          <h1 className="text-5xl lg:text-7xl font-bold text-white mb-4 tracking-tight leading-tight">
            Smarter Trading <br />
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-amber-400 to-amber-600">
              Brighter Opportunities
            </span>
          </h1>
          
          <p className="text-lg text-gray-300 mb-12 max-w-xl leading-relaxed">
            Combine verified market data, deterministic analysis, and disciplined trading workflows.
          </p>

          {/* Features Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Feature 1 */}
            <div className="bg-white/5 backdrop-blur-lg border border-white/10 rounded-xl p-5 hover:bg-white/10 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center mb-3">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </div>
              <h3 className="text-white font-semibold mb-1">Deterministic Analysis</h3>
              <p className="text-gray-400 text-sm">ตรวจสอบ setup พร้อมแหล่งที่มาของข้อมูล</p>
            </div>
            
            {/* Feature 2 */}
            <div className="bg-white/5 backdrop-blur-lg border border-white/10 rounded-xl p-5 hover:bg-white/10 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center mb-3">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                </svg>
              </div>
              <h3 className="text-white font-semibold mb-1">XAUUSD Market Data</h3>
              <p className="text-gray-400 text-sm">ข้อมูลจากผู้ให้บริการ พร้อมสถานะความสด</p>
            </div>

            {/* Feature 3 */}
            <div className="bg-white/5 backdrop-blur-lg border border-white/10 rounded-xl p-5 hover:bg-white/10 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center mb-3">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                </svg>
              </div>
              <h3 className="text-white font-semibold mb-1">Multiple Trading Styles</h3>
              <p className="text-gray-400 text-sm">Day Trade | Swing Trade | SMC/ICT</p>
            </div>

            {/* Feature 4 */}
            <div className="bg-white/5 backdrop-blur-lg border border-white/10 rounded-xl p-5 hover:bg-white/10 transition-colors">
              <div className="w-10 h-10 rounded-lg bg-amber-500/20 text-amber-500 flex items-center justify-center mb-3">
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8V7a4 4 0 00-8 0v4h8z" />
                </svg>
              </div>
              <h3 className="text-white font-semibold mb-1">Analysis Only</h3>
              <p className="text-gray-400 text-sm">ไม่มีการส่งคำสั่งซื้อขาย</p>
            </div>
          </div>
        </div>

        {/* Bottom Content */}
        <div className="relative z-10 w-full mt-12">
          <p className="text-amber-500/40 font-bold text-4xl sm:text-6xl tracking-[0.2em] mb-8 font-serif uppercase">
            Discipline<br/>Creates Freedom
          </p>
          <div className="flex flex-col sm:flex-row justify-between items-end sm:items-center border-t border-white/10 pt-6 gap-4">
            <p className="text-gray-400 text-sm italic w-full sm:w-auto">
              &quot;The best trade is a well-prepared trade.&quot;
            </p>
            <div className="flex gap-4 text-xs text-gray-500 font-medium">
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
      <div className="w-full lg:w-[40%] flex flex-col justify-center items-center p-6 sm:p-12 lg:p-16 relative bg-[#0a0f1a] lg:bg-transparent">
        {/* Mobile Header (Hidden on large screens) */}
        <div className="md:hidden w-full max-w-md mb-8 flex justify-between items-center">
          <div className="flex items-center gap-2">
            <svg className="w-8 h-8 text-amber-500" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2L2 22h20L12 2zm0 3.5l7 14h-14l7-14z" />
            </svg>
            <span className="text-white font-bold text-xl">AIGoldTrader</span>
          </div>
          <div className="flex items-center gap-2 bg-white/5 px-3 py-1.5 rounded-full border border-white/10">
            <span className="text-white text-xs">🇹🇭 ไทย</span>
          </div>
        </div>

        <div className="w-full max-w-md bg-[#131b2c]/80 lg:bg-white/5 backdrop-blur-2xl border border-white/10 rounded-3xl p-8 shadow-2xl relative z-10">
          <div className="text-center mb-8">
            <div className="w-16 h-16 bg-amber-500/10 rounded-2xl flex items-center justify-center mx-auto mb-4 border border-amber-500/20">
              <svg className="w-8 h-8 text-amber-500" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2L2 22h20L12 2zm0 3.5l7 14h-14l7-14z" />
              </svg>
            </div>
            <h2 className="text-2xl font-bold text-white mb-2">Welcome Back</h2>
            <p className="text-gray-400 text-sm">Sign in to your account and trade smarter</p>
          </div>

          {error && (
            <div className="mb-6 p-4 rounded-xl bg-red-500/10 border border-red-500/20 flex items-start gap-3">
              <svg className="w-5 h-5 text-red-500 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <span className="text-red-400 text-sm">{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label htmlFor="email" className="block text-sm font-medium text-gray-300">
                Username
              </label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <svg className="h-5 w-5 text-gray-500 group-focus-within:text-amber-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
                  className="w-full pl-11 pr-4 py-3 rounded-xl bg-black/20 border border-white/10
                             text-white placeholder-gray-500
                             focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50
                             transition-all"
                  placeholder="Enter your username or email"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label htmlFor="password" className="block text-sm font-medium text-gray-300">
                Password
              </label>
              <div className="relative group">
                <div className="absolute inset-y-0 left-0 pl-4 flex items-center pointer-events-none">
                  <svg className="h-5 w-5 text-gray-500 group-focus-within:text-amber-500 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor">
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
                  className="w-full pl-11 pr-12 py-3 rounded-xl bg-black/20 border border-white/10
                             text-white placeholder-gray-500
                             focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500/50
                             transition-all"
                  placeholder="••••••••"
                />
                <button
                  type="button"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute inset-y-0 right-0 pr-4 flex items-center text-gray-500 hover:text-white transition-colors focus:outline-none"
                >
                  {showPassword ? (
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.29 3.29m0 0a10.05 10.05 0 015.71-3.29c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0l-3.29-3.29" />
                    </svg>
                  ) : (
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  )}
                </button>
              </div>
            </div>

            <div className="flex items-center justify-between pt-1">
              <label className="flex items-center gap-2 cursor-pointer group">
                <input
                  type="checkbox"
                  className="w-4 h-4 rounded border-gray-600 bg-gray-800 text-amber-500 focus:ring-amber-500/50 focus:ring-offset-gray-900"
                />
                <span className="text-sm text-gray-400 group-hover:text-gray-300 transition-colors">Keep me signed in</span>
              </label>
              <a href="#" className="text-sm text-amber-500 hover:text-amber-400 font-medium transition-colors">
                Forgot password?
              </a>
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-3.5 px-4 rounded-xl font-semibold
                         bg-gradient-to-r from-amber-600 to-amber-500 hover:from-amber-500 hover:to-amber-400
                         text-white shadow-lg shadow-amber-500/20
                         disabled:opacity-50 disabled:cursor-not-allowed
                         focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:ring-offset-2 focus:ring-offset-[#131b2c]
                         transition-all flex items-center justify-center gap-2 group"
            >
              {isLoading ? (
                <>
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                  Signing in…
                </>
              ) : (
                <>
                  Sign In
                  <svg className="w-5 h-5 group-hover:translate-x-1 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
                  </svg>
                </>
              )}
            </button>
          </form>

          {/* Safety Notice */}
          <div className="mt-8 p-3 rounded-lg bg-amber-500/10 border border-amber-500/20 text-center">
            <TradingStatus health={runtime.health} />
            <p className="text-xs text-amber-400 mt-2">วิเคราะห์เท่านั้น · ไม่มีการส่งคำสั่งซื้อขาย</p>
          </div>
        </div>

        {/* Trade Smarter signature */}
        <div className="mt-8 text-center hidden lg:block">
          <p className="text-amber-500/60 font-serif text-xl italic" style={{ fontFamily: 'var(--font-cursive), cursive' }}>
            Trade Smarter, Live Better
          </p>
        </div>
      </div>
    </div>
  );
}
