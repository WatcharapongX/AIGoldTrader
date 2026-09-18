import { create } from 'zustand';
import {
  authCoordinator,
  type AuthStatus,
  type AuthCoordinatorState,
} from '@/lib/auth-coordinator';
import type { User } from '@/types';

export type { AuthStatus };

interface AuthState {
  user: User | null;
  status: AuthStatus;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<boolean>;
  logout: () => Promise<void>;
  fetchUser: () => Promise<void>;
  clearError: () => void;
  hydrate: () => Promise<void>; // bootstrap on app load
  bootstrap: (options?: { force?: boolean }) => Promise<boolean>;
}

export const useAuthStore = create<AuthState>((set) => {
  // Synchronize Zustand with AuthCoordinator events
  authCoordinator.subscribe((coordState: AuthCoordinatorState) => {
    set({
      user: coordState.user,
      status: coordState.status,
      error: coordState.error,
      isAuthenticated: coordState.status === 'authenticated',
      isLoading:
        coordState.status === 'bootstrapping' ||
        coordState.status === 'refreshing' ||
        coordState.status === 'logging_out',
    });
  });

  return {
    user: null,
    status: 'idle',
    isAuthenticated: false,
    isLoading: false,
    error: null,

    login: async (email: string, password: string) => {
      try {
        await authCoordinator.login(email, password);
        return true;
      } catch {
        return false;
      }
    },

    logout: async () => {
      await authCoordinator.logout();
    },

    fetchUser: async () => {
      try {
        await authCoordinator.fetchMe();
      } catch {
        // State update handled by coordinator
      }
    },

    clearError: () => set({ error: null }),

    hydrate: async () => {
      await authCoordinator.bootstrap();
    },

    bootstrap: async (options?: { force?: boolean }) => {
      return await authCoordinator.bootstrap(options);
    },
  };
});
