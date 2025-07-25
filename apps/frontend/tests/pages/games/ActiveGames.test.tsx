import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import ActiveGames from '@/pages/games/ActiveGames';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn().mockResolvedValue({ json: () => Promise.resolve([]), ok: true }),
}));

describe('ActiveGames', () => {
  it('renders the ActiveGames page', async () => {
    render(
      <MemoryRouter>
        <ActiveGames />
      </MemoryRouter>
    );
    expect(screen.getByText(/In-Progress Games/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText(/Untitled Game/i)).not.toBeInTheDocument();
    });
  });
});
