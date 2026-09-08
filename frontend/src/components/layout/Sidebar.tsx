"use client";

import React, { useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/stores/auth';

const navItems = [
  { href: '/dashboard', label: 'Dashboard', icon: '📊' },
  { href: '/trading', label: 'Trading', icon: '📈' },
  { href: '/scanner', label: 'Market Scanner', icon: '🔍' },
  { href: '/signals', label: 'AI Signals', icon: '🤖' },
  { href: '/analysis', label: 'Analysis', icon: '📐' },
  { href: '/orders', label: 'Orders', icon: '📋' },
  { href: '/positions', label: 'Positions', icon: '💼' },
  { href: '/journal', label: 'Trade Journal', icon: '📓' },
  { href: '/backtesting', label: 'Backtesting', icon: '⏪' },
  { href: '/paper-trading', label: 'Paper Trading', icon: '📝' },
  { href: '/risk', label: 'Risk Management', icon: '🛡️' },
  { href: '/analytics', label: 'Analytics', icon: '📉' },
  { href: '/calendar', label: 'Economic Calendar', icon: '📅' },
  { href: '/alerts', label: 'Alerts', icon: '🔔' },
  { href: '/settings', label: 'Settings', icon: '⚙️' },
];

export function Sidebar() {
  const pathname = usePathname();
  const logout = useAuthStore((state) => state.logout);
  const [collapsed, setCollapsed] = useState(false);

  return (
    <div
      className={`bg-gray-900 text-white h-screen flex flex-col transition-all duration-300 border-r border-gray-800 ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      <div className="flex items-center justify-between p-4 border-b border-gray-800 h-16">
        {!collapsed && (
          <div className="font-bold text-xl tracking-tight text-amber-500 whitespace-nowrap">
            AI Gold Trader
          </div>
        )}
        <button
          onClick={() => setCollapsed(!collapsed)}
          className="p-1.5 rounded-md hover:bg-gray-800 text-gray-400 focus:outline-none"
        >
          ☰
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-4 space-y-1">
        {navItems.map((item) => {
          const isActive = pathname?.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex items-center px-4 py-2.5 transition-colors ${
                isActive
                  ? 'bg-amber-500/10 text-amber-500 border-r-2 border-amber-500'
                  : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
              }`}
              title={collapsed ? item.label : undefined}
            >
              <span className="text-xl leading-none">{item.icon}</span>
              {!collapsed && (
                <span className="ml-3 font-medium whitespace-nowrap">
                  {item.label}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="p-4 border-t border-gray-800">
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'justify-between'}`}>
          {!collapsed && (
            <div className="flex items-center">
              <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center text-sm font-bold">
                U
              </div>
              <div className="ml-3">
                <p className="text-sm font-medium">User</p>
                <p className="text-xs text-gray-500">Pro Plan</p>
              </div>
            </div>
          )}
          <button
            className={`text-gray-400 hover:text-red-400 transition-colors ${collapsed ? '' : 'ml-2'}`}
            title="Logout"
            onClick={() => void logout()}
          >
            🚪
          </button>
        </div>
      </div>
    </div>
  );
}
