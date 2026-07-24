import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import PlayerProfilePage from '@/pages/PlayerProfilePage';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn(),
}));

vi.mock('@/state/auth', () => ({
  useAuth: vi.fn(),
}));

import { secureFetch } from '@/utils/secureFetch';
import { useAuth } from '@/state/auth';

const publicProfile = {
  trainer_id: '214D27D0',
  username: 'anorgandroid',
  avatar: 'default.png',
  elo_conquest: 1000,
  elo_war: 1000,
  currency: 0,
  role: 'admin',
};

const ownUser = {
  id: 1,
  trainer_id: '214D27D0',
  username: 'anorgandroid',
  email: 'anorgandroid@gmail.com',
  avatar: 'default.png',
  elo_conquest: 1000,
  elo_war: 1000,
  currency: 0,
  role: 'admin' as const,
};

function mockAuth(overrides: Partial<ReturnType<typeof useAuth>> = {}) {
  vi.mocked(useAuth).mockReturnValue({
    user: null,
    setUser: vi.fn(),
    authPrompt: null,
    clearAuthPrompt: vi.fn(),
    loading: false,
    logout: vi.fn(),
    requestAuthPrompt: vi.fn(),
    ...overrides,
  } as ReturnType<typeof useAuth>);
}

function renderPlayer(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/player/:trainerId" element={<PlayerProfilePage />} />
        <Route path="/" element={<div>Home</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('PlayerProfilePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuth();
  });

  it('loads a public profile by trainer id without email', async () => {
    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => publicProfile,
    } as Response);

    renderPlayer('/player/214d27d0');

    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith('/api/players/214D27D0');
      expect(screen.getByRole('heading', { name: 'anorgandroid' })).toBeInTheDocument();
    });
    expect(screen.getByText('214D27D0')).toBeInTheDocument();
    expect(screen.getByText('Conquest Elo')).toBeInTheDocument();
    expect(screen.getByText('War Elo')).toBeInTheDocument();
    expect(screen.getAllByText('1000')).toHaveLength(2);
    expect(screen.queryByText('Email')).not.toBeInTheDocument();
  });

  it('defaults missing elo fields to 1000', async () => {
    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        trainer_id: '214D27D0',
        username: 'anorgandroid',
        avatar: 'default.png',
        currency: 0,
        role: 'admin',
      }),
    } as Response);

    renderPlayer('/player/214D27D0');

    await waitFor(() => {
      expect(screen.getByText('Conquest Elo')).toBeInTheDocument();
    });
    expect(screen.getAllByText('1000')).toHaveLength(2);
  });

  it('shows email when viewing your own trainer profile', async () => {
    mockAuth({ user: ownUser });
    vi.mocked(secureFetch).mockImplementation(async (input) => {
      const url = String(input);
      if (url.startsWith('/api/players/')) {
        return {
          ok: true,
          status: 200,
          json: async () => publicProfile,
        } as Response;
      }
      if (url === '/api/me') {
        return {
          ok: true,
          status: 200,
          json: async () => ownUser,
        } as Response;
      }
      return { ok: false, status: 500, json: async () => ({}) } as Response;
    });

    renderPlayer('/player/214D27D0');

    await waitFor(() => {
      expect(screen.getByText('Email')).toBeInTheDocument();
      expect(screen.getByText('anorgandroid@gmail.com')).toBeInTheDocument();
    });
  });

  it('shows not found for missing players', async () => {
    vi.mocked(secureFetch).mockResolvedValue({
      ok: false,
      status: 404,
      json: async () => ({ detail: 'Player not found' }),
    } as Response);

    renderPlayer('/player/DEADBEEF');

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /player not found/i })).toBeInTheDocument();
    });
  });
});
