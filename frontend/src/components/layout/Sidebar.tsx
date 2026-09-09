"use client";

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/stores/auth';

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg> },
  { href: '/trading', label: 'Market Overview', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg> },
  { href: '/analysis', label: 'AI Analysis', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 2A2.5 2.5 0 0 1 12 4.5v15a2.5 2.5 0 0 1-4.96.44 2.5 2.5 0 0 1-2.96-3.08 3 3 0 0 1-.34-5.58 2.5 2.5 0 0 1 1.32-4.24 2.5 2.5 0 0 1 1.98-3A2.5 2.5 0 0 1 9.5 2Z"/><path d="M14.5 2A2.5 2.5 0 0 0 12 4.5v15a2.5 2.5 0 0 0 4.96.44 2.5 2.5 0 0 0 2.96-3.08 3 3 0 0 0 .34-5.58 2.5 2.5 0 0 0-1.32-4.24 2.5 2.5 0 0 0-1.98-3A2.5 2.5 0 0 0 14.5 2Z"/></svg> },
  { href: '/signals', label: 'Trading Signals', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg> },
  { href: '/backtesting', label: 'Backtest & Strategy', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 2v2"/><path d="M15 2v2"/><path d="M12 18v-6"/><path d="M12 12a2 2 0 1 0 0-4 2 2 0 0 0 0 4z"/><path d="M4 14l-2 6h20l-2-6"/></svg> },
  { href: '/calendar', label: 'Economic Calendar', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg> },
  { href: '/scanner', label: 'News & Sentiment', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M4 22h16a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2H8a2 2 0 0 0-2 2v16a2 2 0 0 1-2 2Zm0 0a2 2 0 0 1-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8V6Z"/></svg> },
  { href: '/analytics', label: 'Performance', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/><polyline points="16 7 22 7 22 13"/></svg> },
  { href: '/journal', label: 'Reports', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg> },
  { href: '/settings', label: 'Settings', icon: <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg> },
];

const moduleStatuses = [
  { label: 'Market Data', status: 'ok' },
  { label: 'MT5 Connection', status: 'ok' },
  { label: 'AI Analysis', status: 'ok' },
  { label: 'Database', status: 'ok' },
  { label: 'Web Service', status: 'ok' },
];

export function Sidebar() {
  const pathname = usePathname();
  const logout = useAuthStore((state) => state.logout);

  return (
    <div className="w-[240px] shrink-0 bg-[#0d1117] h-screen flex flex-col border-r border-gray-800/60 overflow-hidden text-sm">
      {/* Logo Area */}
      <div className="p-5 flex items-center gap-3">
        <div className="w-8 h-8 rounded-md bg-amber-500/20 text-amber-500 flex items-center justify-center border border-amber-500/30">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M4 22l6-20h4l6 20"/>
            <path d="M7 14h10"/>
          </svg>
        </div>
        <div className="font-bold text-lg tracking-tight text-white whitespace-nowrap">
          AIGoldTrader
        </div>
      </div>

      {/* Search Bar */}
      <div className="px-4 pb-4">
        <div className="relative">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/></svg>
          </span>
          <input 
            type="text" 
            placeholder="Search symbols, news, or strategies..." 
            className="w-full bg-white/5 border border-white/10 rounded-md py-1.5 pl-9 pr-3 text-xs text-gray-300 placeholder:text-gray-500 focus:outline-none focus:border-amber-500/50 focus:bg-white/10 transition-colors"
          />
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-2 space-y-0.5 custom-scrollbar pb-4">
        {navItems.map((item) => {
          const isActive = pathname === item.href || pathname?.startsWith(item.href + '/');
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center gap-3 px-3 py-2 rounded-md transition-all ${
                isActive
                  ? 'bg-amber-500/15 text-amber-400 border-l-2 border-amber-500'
                  : 'text-gray-400 hover:bg-white/5 hover:text-gray-200 border-l-2 border-transparent'
              }`}
            >
              <span className={isActive ? 'text-amber-500' : 'text-gray-500'}>{item.icon}</span>
              <span className="font-medium">{item.label}</span>
            </Link>
          );
        })}
        
        <div className="mx-3 my-4 border-t border-gray-800/50"></div>
        
        {/* Module Statuses */}
        <div className="px-3 py-2">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-2 h-2 rounded-full bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)] animate-pulse"></span>
            <span className="text-xs font-semibold text-gray-300 uppercase tracking-wider">Live System</span>
          </div>
          <div className="space-y-2">
            {moduleStatuses.map((mod) => (
              <div key={mod.label} className="flex items-center justify-between">
                <span className="text-xs text-gray-500">{mod.label}</span>
                <span className={`w-1.5 h-1.5 rounded-full ${mod.status === 'ok' ? 'bg-green-500' : 'bg-yellow-500'}`}></span>
              </div>
            ))}
          </div>
        </div>
      </nav>

      {/* User Profile */}
      <div className="p-4 border-t border-gray-800/60 bg-white/[0.02]">
        <div className="flex items-center justify-between group">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-full bg-gradient-to-tr from-amber-600 to-amber-400 flex items-center justify-center text-white font-bold shadow-lg shadow-amber-500/20">
              W
            </div>
            <div>
              <div className="text-sm font-medium text-gray-200 leading-tight">WatcharapongX</div>
              <div className="text-xs text-amber-500/80 font-medium">Admin</div>
            </div>
          </div>
          <button onClick={() => void logout()} className="text-gray-500 hover:text-red-400 transition-colors p-1.5 rounded-md hover:bg-white/5" title="Logout">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" y1="12" x2="9" y2="12"/></svg>
          </button>
        </div>
      </div>
      
      {/* Footer Bar */}
      <div className="py-2 text-center text-[10px] text-gray-600 border-t border-gray-800/40 bg-[#0a0e14]">
        AIGoldTrader v2.0
      </div>
    </div>
  );
}
