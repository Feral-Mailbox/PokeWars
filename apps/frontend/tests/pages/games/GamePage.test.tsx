import { describe, it, expect, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import GamePage from '@/pages/games/GamePage';
import { GAME_NOT_FOUND_MESSAGE } from '@/utils/gameLink';
import { openBugReportWindow } from '@/utils/bugReport';

const mockNavigate = vi.fn();

vi.mock('@/state/auth', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'testuser' },
  }),
}));

vi.mock('@/utils/bugReport', () => ({
  openBugReportWindow: vi.fn(),
}));

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

  it('opens the bug report window with game context', async () => {
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

    fireEvent.click(screen.getByRole('button', { name: /Report bug/i }));

    expect(openBugReportWindow).toHaveBeenCalledWith(
      expect.objectContaining({
        gameLink: 'test-link',
        gameName: 'Test Game',
        gameMode: 'Conquest',
        gameStatus: 'preparation',
        username: 'testuser',
      }),
    );
  });

  it('renders an in-progress War game shell', async () => {
    const { secureFetch } = await import('@/utils/secureFetch');
    vi.mocked(secureFetch).mockImplementation((url: string) => {
      if (url.includes('/games/') && !url.includes('/units') && !url.includes('/player')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              id: 2,
              link: 'war-link',
              game_name: 'War Match',
              gamemode: 'War',
              status: 'in_progress',
              current_turn: 0,
              player_order: [1, 2],
              cash_per_turn: 100,
              map: {
                width: 2,
                height: 2,
                tileset_names: ['a.png'],
                tile_data: {
                  base: [
                    [
                      [0, 0],
                      [0, 0],
                    ],
                    [
                      [0, 0],
                      [0, 0],
                    ],
                  ],
                  overlay: [
                    [null, null],
                    [null, null],
                  ],
                  spawn_points: [
                    [1, null],
                    [null, 2],
                  ],
                },
              },
              map_state: {
                objective_tiles: [
                  [{ kind: 'pokeball', owner: 1, hp: 20, max_hp: 20 }],
                ],
              },
              max_players: 2,
              players: [
                { id: 1, player_id: 1, username: 'testuser' },
                { id: 2, player_id: 2, username: 'rival' },
              ],
              host_id: 1,
            }),
        } as Response);
      }
      if (url.includes('/units')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve([
              {
                id: 11,
                game_id: 2,
                unit_id: 1,
                user_id: 1,
                unit: { name: 'Pikachu', asset_folder: '025_pikachu', types: ['Electric'] },
                current_x: 0,
                current_y: 0,
                starting_x: 0,
                starting_y: 0,
                current_hp: 30,
                is_fainted: false,
                can_move: true,
                equipped_move_ids: [],
                move_pp: [],
              },
            ]),
        } as Response);
      }
      if (url.includes('/player')) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({ cash_remaining: 200, is_ready: true, game_units: [] }),
        } as Response);
      }
      if (url.includes('/me')) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ id: 1 }) } as Response);
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) } as Response);
    });

    render(
      <MemoryRouter initialEntries={['/games/war-link']}>
        <Routes>
          <Route path="/games/:gameId" element={<GamePage />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/War Match/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/War Mode:/i)).toBeInTheDocument();
  });
});
