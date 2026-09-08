"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/stores/auth";

export default function LoginPage() {
  const router = useRouter();
  const { login, isLoading, error, clearError } = useAuthStore();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    clearError();
    const success = await login(email, password);
    if (success) {
      router.push("/dashboard");
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[#0a0a0a] px-4">
      <div className="w-full max-w-md">
        {/* Brand */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-amber-500">
            AI Gold Trader
          </h1>
          <p className="text-gray-400 mt-2 text-sm">
            AI-Assisted Trading Platform for XAUUSD &amp; Forex
          </p>
        </div>

        {/* Login Card */}
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-8">
          <h2 className="text-xl font-semibold text-white mb-6">
            Sign In
          </h2>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-900/30 border border-red-800 text-red-400 text-sm">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-gray-300 mb-1.5"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                required
                autoComplete="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-2.5 rounded-lg bg-gray-800 border border-gray-700
                           text-white placeholder-gray-500
                           focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500
                           transition-colors"
                placeholder="trader@example.com"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="block text-sm font-medium text-gray-300 mb-1.5"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-2.5 rounded-lg bg-gray-800 border border-gray-700
                           text-white placeholder-gray-500
                           focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500
                           transition-colors"
                placeholder="••••••••"
              />
            </div>

            <button
              type="submit"
              disabled={isLoading}
              className="w-full py-2.5 px-4 rounded-lg font-medium
                         bg-amber-600 hover:bg-amber-500 text-white
                         disabled:opacity-50 disabled:cursor-not-allowed
                         focus:outline-none focus:ring-2 focus:ring-amber-500/50
                         transition-colors"
            >
              {isLoading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg
                    className="animate-spin h-4 w-4"
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                    />
                  </svg>
                  Signing in…
                </span>
              ) : (
                "Sign In"
              )}
            </button>
          </form>

          {/* Safety Notice */}
          <div className="mt-6 p-3 rounded-lg bg-amber-900/20 border border-amber-800/50">
            <p className="text-xs text-amber-400/80 flex items-start gap-2">
              <span className="mt-0.5">⚠️</span>
              <span>
                Trading Mode: <strong>PAPER</strong> — Live auto trading is
                disabled. All trades use virtual money with real market data.
              </span>
            </p>
          </div>
        </div>

        <p className="text-center text-gray-600 text-xs mt-6">
          &copy; {new Date().getFullYear()} AI Gold Trader. Not financial advice.
        </p>
      </div>
    </div>
  );
}
