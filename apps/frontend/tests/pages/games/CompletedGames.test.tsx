import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import CompletedGames from '@/pages/games/CompletedGames';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn().mockResolvedValue({ json: () => Promise.resolve([]), ok: true }),
}));

describe('CompletedGames', () => {
  it('renders the CompletedGames page', async () => {
    render(
      <MemoryRouter>
        <CompletedGames />
      </MemoryRouter>
    );
    expect(screen.getByText(/Completed Games/i)).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText(/Untitled Game/i)).not.toBeInTheDocument();
    });
  });
});
