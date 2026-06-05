import { create } from 'zustand';
import type { User } from '../types/user';

type AuthState = {
  user: User | null;
  loading: boolean;
  setUser: (user: User | null) => void;
  logout: () => void;
};

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: true,
  setUser: (user) => set({ user, loading: false }),
  logout: () => set({ user: null, loading: false }),
}));
