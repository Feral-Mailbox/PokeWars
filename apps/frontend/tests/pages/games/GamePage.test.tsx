import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import GamePage from '@/pages/games/GamePage';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn().mockImplementation((url: string) => {
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
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Test Game/i)).toBeInTheDocument();
    });
  });
});
