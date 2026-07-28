import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AnnouncementsDropdown from '@/components/AnnouncementsDropdown';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn(),
}));

vi.mock('@/state/WebSocketContext', () => ({
  useWebSocket: () => ({
    subscribe: () => () => undefined,
    socket: null,
    lastInvitationEvent: null,
  }),
}));

import { secureFetch } from '@/utils/secureFetch';

const posts = [
  {
    id: 2,
    title: 'Patch 0.2',
    message: 'Long details about balance changes go here.',
    author_id: 9,
    author_username: 'moddy',
    created_at: '2026-07-27T12:00:00Z',
    starred: false,
  },
  {
    id: 1,
    title: 'Keep this',
    message: 'Pinned for later.',
    author_id: 9,
    author_username: 'moddy',
    created_at: '2026-07-26T12:00:00Z',
    starred: false,
  },
];

describe('AnnouncementsDropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => posts,
    } as Response);
  });

  it('shows title and author collapsed, expands message on click', async () => {
    const user = userEvent.setup();
    render(<AnnouncementsDropdown />);

    await user.click(screen.getByRole('button', { name: /^announcements$/i }));
    await waitFor(() => {
      expect(screen.getByText('Patch 0.2')).toBeInTheDocument();
    });
    expect(screen.queryByText(/Long details about balance/)).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: /patch 0\.2/i }));
    expect(screen.getByText(/Long details about balance/)).toBeInTheDocument();
  });

  it('stars an announcement and clears non-starred', async () => {
    const user = userEvent.setup();
    let listed = posts.map((row) => ({ ...row }));

    vi.mocked(secureFetch).mockImplementation(async (url, init) => {
      const method = init?.method ?? 'GET';
      if (url === '/api/announcements' && method === 'GET') {
        return {
          ok: true,
          status: 200,
          json: async () => listed,
        } as Response;
      }
      if (typeof url === 'string' && url.endsWith('/1/star') && method === 'POST') {
        listed = listed.map((row) =>
          row.id === 1 ? { ...row, starred: true } : row,
        );
        return {
          ok: true,
          status: 200,
          json: async () => listed.find((row) => row.id === 1),
        } as Response;
      }
      if (url === '/api/announcements/clear' && method === 'POST') {
        listed = listed.filter((row) => row.starred);
        return {
          ok: true,
          status: 200,
          json: async () => ({ cleared: 1 }),
        } as Response;
      }
      return { ok: false, status: 500, json: async () => ({}) } as Response;
    });

    render(<AnnouncementsDropdown />);

    await user.click(screen.getByRole('button', { name: /^announcements$/i }));
    await waitFor(() => {
      expect(screen.getByText('Keep this')).toBeInTheDocument();
    });

    const starButtons = screen.getAllByRole('button', { name: /^star announcement$/i });
    expect(starButtons).toHaveLength(2);
    await user.click(starButtons[1]);

    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith('/api/announcements/1/star', {
        method: 'POST',
      });
      expect(screen.getByRole('button', { name: /^unstar announcement$/i })).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /^clear all$/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith('/api/announcements/clear', {
        method: 'POST',
      });
      expect(screen.getByText('Keep this')).toBeInTheDocument();
      expect(screen.queryByText('Patch 0.2')).not.toBeInTheDocument();
    });
  });
});
