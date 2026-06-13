import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import GamePage from '@/pages/games/GamePage';
import { GAME_NOT_FOUND_MESSAGE } from '@/utils/gameLink';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn().mockImplementation((url: string) => {
    if (url.includes('/games/missing') && !url.includes('/units') && !url.includes('/player')) {
      return Promise.resolve({ ok: false, json: () => Promise.resolve({ detail: 'Game not found' }) });
    }
    if (url.includes('/games/') && !url.includes('/units') && !url.includes('/player')) {
      return Promise.resolve({
        json: () => Promise.resolve({
          id: 1,
          link: 'test-link',
          game_name: 'Test Game',
          gamemode: 'Conquest',
          status: 'preparation',
          map: { width: 5, height: 5 },
          max_players: 4,
          players: [],
          host_id: 1,
        }),
        ok: true,
      });
    }
    if (url.includes('/units')) {
      return Promise.resolve({ json: () => Promise.resolve([]), ok: true });
    }
    if (url.includes('/player')) {
      return Promise.resolve({
        json: () => Promise.resolve({ cash_remaining: 3000, is_ready: false, game_units: [] }),
        ok: true,
      });
    }
    if (url.includes('/me')) {
      return Promise.resolve({ json: () => Promise.resolve({ id: 1 }), ok: true });
    }
    return Promise.resolve({ json: () => Promise.resolve([]), ok: true });
  }),
}));

describe('GamePage', () => {
  it('renders game info correctly', async () => {
    render(
      <MemoryRouter initialEntries={['/games/123']}>
        <Routes>
          <Route path="/games/:gameId" element={<GamePage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Test Game/i)).toBeInTheDocument();
    });
  });

  it('redirects home with a toast when the game does not exist', async () => {
    mockNavigate.mockClear();

    render(
      <MemoryRouter initialEntries={['/games/missing']}>
        <Routes>
          <Route path="/games/:gameId" element={<GamePage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith('/', {
        replace: true,
        state: { toastMessage: GAME_NOT_FOUND_MESSAGE },
      });
    });
  });
});
