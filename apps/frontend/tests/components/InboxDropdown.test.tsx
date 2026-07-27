import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import InboxDropdown from '@/components/InboxDropdown';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn(),
}));

vi.mock('@/state/WebSocketContext', () => ({
  useWebSocket: () => ({
    subscribe: () => () => undefined,
    lastInvitationEvent: null,
    socket: null,
  }),
}));

import { secureFetch } from '@/utils/secureFetch';

const pendingInvite = {
  id: 11,
  game_id: 5,
  game_name: 'Ranked Lobby',
  game_link: 'abc123',
  gamemode: 'Conquest',
  inviter_id: 2,
  inviter_username: 'hosty',
  invitee_id: 1,
  invitee_username: 'me',
  status: 'pending',
  created_at: '2026-07-27T00:00:00Z',
};

describe('InboxDropdown', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('loads pending invites and accepts join', async () => {
    const user = userEvent.setup();
    vi.mocked(secureFetch).mockImplementation(async (input, init) => {
      const url = String(input);
      if (url === '/api/invitations/inbox') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ invitations: [pendingInvite], pending_count: 1 }),
        } as Response;
      }
      if (url === '/api/invitations/11/accept' && init?.method === 'POST') {
        return {
          ok: true,
          status: 200,
          json: async () => ({ ...pendingInvite, status: 'accepted' }),
        } as Response;
      }
      return { ok: false, status: 500, json: async () => ({}) } as Response;
    });

    render(
      <MemoryRouter>
        <InboxDropdown />
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: /inbox/i }));
    await waitFor(() => {
      expect(screen.getByText(/hosty invited you/i)).toBeInTheDocument();
    });

    await user.click(screen.getByRole('button', { name: /^join$/i }));
    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith(
        '/api/invitations/11/accept',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });
});
