import { create } from 'zustand';
import { api, clearSession } from '@/lib/api';
import { ApiContractError } from '@/lib/contracts';
import type { User } from '@/types';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;
  
  login: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<void>;
  clearError: () => void;
  hydrate: () => Promise<void>; // check stored tokens on app load
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  isAuthenticated: false,
  isLoading: false,
  error: null,
  
  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      await api.login(email, password);
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
      return true;
    } catch (err) {
      set({ error: (err as Error).message, isLoading: false });
      return false;
    }
  },
  
  logout: async () => {
    try { await api.logout(); } catch {} 
    if (typeof window !== 'undefined') {
      clearSession();
    }
    set({ user: null, isAuthenticated: false, error: null });
  },
  
  fetchUser: async () => {
    try {
      const user = await api.getMe();
      set({ user, isAuthenticated: true });
    } catch {
      set({ user: null, isAuthenticated: false });
    }
  },
  
  clearError: () => set({ error: null }),
  
  hydrate: async () => {
    set({ isLoading: true });
    if (typeof window === 'undefined') {
      set({ isLoading: false });
      return;
    }
    const token = localStorage.getItem('access_token');
    if (!token) {
      set({ isLoading: false });
      return;
    }
    try {
      const user = await api.getMe();
      set({ user, isAuthenticated: true, isLoading: false });
    } catch (error) {
      if (!(error instanceof ApiContractError)) clearSession();
      set({ user: null, isAuthenticated: false, isLoading: false });
    }
  },
}));
