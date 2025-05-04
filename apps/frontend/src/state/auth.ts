import { create } from 'zustand';

type AuthState = {
  user: string | null;
  setUser: (user: string) => void;
  logout: () => void;
};

export const useAuth = create<AuthState>((set) => ({
  user: null,
  setUser: (user) => set({ user }),
  logout: () => set({ user: null }),
}));
