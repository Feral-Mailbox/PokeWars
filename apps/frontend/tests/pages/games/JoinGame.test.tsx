import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import JoinGame from '@/pages/games/JoinGame';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn().mockImplementation((url: string) => {
    if (url.includes('/games/open')) {
      return Promise.resolve({ json: () => Promise.resolve([]), ok: true });
    }
    if (url.includes('/me')) {
      return Promise.resolve({ json: () => Promise.resolve({ id: 123 }), ok: true });
    }
    return Promise.resolve({ json: () => Promise.resolve([]), ok: true });
  }),
}));

describe('JoinGame', () => {
  it('renders Join Game page', async () => {
    render(
      <MemoryRouter>
        <JoinGame />
      </MemoryRouter>
    );

    expect(screen.getByText(/Join Game/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText(/Untitled Game/i)).not.toBeInTheDocument();
    });
  });
});
