'use client';

import React from 'react';
import Link from 'next/link';
import { TradingNewsPanel } from '@/features/news/TradingNewsPanel';

export function NewsSentimentScreen() {
  return (
    <div className="trading-workspace space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-gray-800/80 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <p className="market-eyebrow tracking-widest text-xs font-semibold text-gray-400">
              MACROECONOMIC INTELLIGENCE &amp; REACTION
            </p>
          </div>
          <h1 className="text-2xl lg:text-3xl font-bold text-white tracking-tight mt-1">
            News & Sentiment
          </h1>
          <p className="text-xs text-amber-300/90 font-mono mt-0.5">
            Macro Context &amp; Market Reaction
          </p>
          <p className="text-xs text-gray-400 mt-0.5">
            วิเคราะห์ผลประกาศเศรษฐกิจ ภาพรวม USD ปฏิกิริยาราคาทอง และการยืนยันจากโครงสร้างตลาด
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <span className="px-3 py-1.5 bg-emerald-500/10 text-emerald-400 font-semibold rounded-md border border-emerald-500/20">
            PAPER MODE · ADVISORY / CONTEXT ONLY · EXECUTION DISABLED
          </span>
          <Link
            href="/calendar"
            className="px-3 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-400 font-medium rounded-md border border-amber-500/30 transition-colors flex items-center gap-1"
          >
            <span>📅</span>
            <span>เปิดปฏิทินเศรษฐกิจฉบับเต็ม →</span>
          </Link>
          <Link
            href="/trading"
            className="px-3 py-1.5 bg-white/10 hover:bg-white/15 text-gray-300 hover:text-white font-medium rounded-md border border-white/10 transition-colors flex items-center gap-1"
          >
            <span>←</span>
            <span>Market Overview</span>
          </Link>
        </div>
      </div>

      {/* Main News Panel */}
      <TradingNewsPanel />
    </div>
  );
}
