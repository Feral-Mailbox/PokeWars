import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import CreateGame from '@/pages/games/CreateGame';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn().mockImplementation((url: string) => {
    if (url.includes('/maps')) {
      return Promise.resolve({
        json: () => Promise.resolve([
          { id: 1, name: 'TestMap', width: 10, height: 10, allowed_modes: ['conquest'], allowed_player_counts: [2, 4] },
        ]),
        ok: true,
      });
    }
    if (url.includes('/me')) {
      return Promise.resolve({ json: () => Promise.resolve({ id: 123 }), ok: true });
    }
    return Promise.resolve({ json: () => Promise.resolve([]), ok: true });
  }),
}));

describe('CreateGame', () => {
  it('renders the Create Game form', async () => {
    render(
      <MemoryRouter>
        <CreateGame />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText(/Create a Game/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/Game Name/i)).toBeInTheDocument();
    });
  });
});
