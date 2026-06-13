import { create } from 'zustand';
import type { User } from '../types/user';

export type AuthPromptMode = 'login' | 'register';

type AuthState = {
  user: User | null;
  loading: boolean;
  authPrompt: AuthPromptMode | null;
  setUser: (user: User | null) => void;
  logout: () => void;
  requestAuthPrompt: (mode: AuthPromptMode) => void;
  clearAuthPrompt: () => void;
};

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: true,
  authPrompt: null,
  setUser: (user) => set({ user, loading: false }),
  logout: () => set({ user: null, loading: false }),
  requestAuthPrompt: (mode) => set({ authPrompt: mode }),
  clearAuthPrompt: () => set({ authPrompt: null }),
}));
