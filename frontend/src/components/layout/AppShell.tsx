"use client";

import React, { useEffect, useState } from 'react';
import { useAuthStore } from '@/stores/auth';
import { Sidebar } from './Sidebar';
import { usePathname, useRouter } from 'next/navigation';

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { hydrate, isAuthenticated } = useAuthStore();
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let active = true;
    void hydrate().then(() => {
      if (active) {
        setChecked(true);
        if (!useAuthStore.getState().isAuthenticated) router.replace('/login');
      }
    });
    const onExpired = () => {
      useAuthStore.setState({ user: null, isAuthenticated: false });
      router.replace('/login');
    };
    window.addEventListener('auth:expired', onExpired);
    return () => { active = false; window.removeEventListener('auth:expired', onExpired); };
  }, [hydrate, router]);

  if (!checked || !isAuthenticated) return <p className="p-6">Checking session…</p>;
  
  // Format pathname for breadcrumb (e.g., /paper-trading -> Paper Trading)
  const pathParts = pathname?.split('/').filter(Boolean) || [];
  const pageTitle = pathParts.length > 0 
    ? pathParts[pathParts.length - 1].split('-').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
    : 'Dashboard';

  return (
    <div className="flex h-screen w-full bg-[#0a0a0a] text-[#ededed] overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col h-full min-w-0">
        <header className="h-16 flex items-center justify-between px-3 md:px-6 border-b border-gray-800 bg-gray-900/50 backdrop-blur-sm z-10 shrink-0">
          <div className="flex items-center space-x-2 text-sm">
            <span className="text-gray-500">App</span>
            <span className="text-gray-600">/</span>
            <span className="font-semibold text-gray-200">{pageTitle}</span>
          </div>
          <div className="flex items-center space-x-2 md:space-x-4">
            <div className="px-3 py-1 bg-amber-500/20 text-amber-500 border border-amber-500/30 rounded text-xs font-bold tracking-wider">
              PAPER TRADING
            </div>
            <div className="hidden lg:flex items-center space-x-2 text-sm text-gray-400">
              <span className="w-2 h-2 rounded-full bg-gray-500"></span>
              <span>Market workspace · PAPER</span>
            </div>
          </div>
        </header>
        <main className="flex-1 overflow-auto p-3 md:p-6 relative">
          {children}
        </main>
      </div>
    </div>
  );
}
