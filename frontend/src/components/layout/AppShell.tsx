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
  const [currentDateTime, setCurrentDateTime] = useState('');

  // Hydration & Auth Check
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

  // Clock
  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const formatter = new Intl.DateTimeFormat('en-US', {
        weekday: 'short',
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: false,
      });
      // e.g. "Thu, Sep 10, 2026, 03:01" -> we want "Thu, 10 Sep 2026 03:01"
      // Simplest way is to just format manually
      const days = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
      const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      
      const dayName = days[now.getDay()];
      const day = String(now.getDate()).padStart(2, '0');
      const monthName = months[now.getMonth()];
      const year = now.getFullYear();
      const hours = String(now.getHours()).padStart(2, '0');
      const minutes = String(now.getMinutes()).padStart(2, '0');
      
      setCurrentDateTime(`${dayName}, ${day} ${monthName} ${year} ${hours}:${minutes}`);
    };
    
    updateTime();
    const interval = setInterval(updateTime, 1000 * 60);
    return () => clearInterval(interval);
  }, []);

  if (!checked || !isAuthenticated) return <p className="p-6 text-gray-400">Checking session…</p>;
  
  // Format pathname for breadcrumb
  const pathParts = pathname?.split('/').filter(Boolean) || [];
  const pageTitle = pathParts.length > 0 
    ? pathParts[pathParts.length - 1].split('-').map(word => word.charAt(0).toUpperCase() + word.slice(1)).join(' ')
    : 'Dashboard';

  return (
    <div className="flex h-screen w-full bg-[#080c14] text-gray-100 overflow-hidden font-sans">
      <Sidebar />
      <div className="flex-1 flex flex-col h-full min-w-0">
        <header className="h-[56px] flex items-center justify-between px-6 border-b border-gray-800 bg-[#0d1117] shrink-0">
          {/* Left Side: Breadcrumb */}
          <div className="flex items-center space-x-2 text-sm">
            <span className="text-gray-500">Platform</span>
            <span className="text-gray-600">/</span>
            <span className="font-medium text-gray-300">{pageTitle}</span>
          </div>

          {/* Right Side */}
          <div className="flex items-center space-x-5 text-sm text-gray-400">
            <div className="hidden md:flex items-center gap-1.5">
              <span className="text-base" role="img" aria-label="Thailand">🇹🇭</span>
              <span>Bangkok, Thailand</span>
            </div>
            
            <div className="hidden md:block w-px h-4 bg-gray-700/50"></div>
            
            <div className="hidden sm:block font-mono text-xs">
              {currentDateTime || 'Loading...'}
            </div>
            
            <div className="hidden sm:block w-px h-4 bg-gray-700/50"></div>

            <div className="flex items-center gap-4">
              <button className="relative hover:text-white transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
                <span className="absolute -top-1 -right-1 w-2 h-2 bg-amber-500 rounded-full border border-[#0d1117]"></span>
              </button>
              
              <button className="hover:text-white transition-colors">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/></svg>
              </button>
              
              <div className="flex items-center gap-2 px-2.5 py-1 bg-gray-800/80 rounded-full border border-gray-700/50">
                <span className="w-1.5 h-1.5 rounded-full bg-green-500 shadow-[0_0_6px_rgba(34,197,94,0.8)]"></span>
                <span className="text-xs font-semibold text-gray-200 tracking-wide">Live Mode</span>
              </div>
            </div>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6 relative">
          {children}
        </main>
      </div>
    </div>
  );
}
