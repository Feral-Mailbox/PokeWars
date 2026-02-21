import { create } from 'zustand';

type AuthState = {
  user: string | null;
  loading: boolean;
  setUser: (user: string) => void;
  logout: () => void;
};

export const useAuth = create<AuthState>((set) => ({
  user: null,
  loading: true,
  setUser: (user) => set({ user, loading: false }),
  logout: () => set({ user: null, loading: false }),
}));
