import React, { useEffect } from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import { WebSocketProvider, useWebSocket } from '@/state/WebSocketContext';
import { vi } from 'vitest';

vi.mock('@/state/auth', () => ({
  useAuth: () => ({
    user: { id: 1, trainer_id: 'A1B2C3D4', username: 'tester' },
    loading: false,
  }),
}));

describe('WebSocketContext', () => {
  let mockSocket: any;

  beforeEach(() => {
    mockSocket = {
      onopen: null,
      onclose: null,
      onmessage: null,
      onerror: null,
      close: vi.fn(),
      url: 'ws://poketactics/api/ws/global',
    };
    global.WebSocket = vi.fn(() => mockSocket) as any;
  });

  it('renders children', () => {
    render(
      <WebSocketProvider>
        <div>Connected!</div>
      </WebSocketProvider>,
    );
    expect(screen.getByText('Connected!')).toBeInTheDocument();
  });

  it('sets socket on open and clears on close', async () => {
    function TestComponent() {
      const { socket } = useWebSocket();
      return <div>{socket ? 'Socket Connected' : 'Socket Null'}</div>;
    }

    render(
      <WebSocketProvider>
        <TestComponent />
      </WebSocketProvider>,
    );

    expect(screen.getByText('Socket Null')).toBeInTheDocument();

    act(() => {
      mockSocket.onopen();
    });

    await waitFor(() => {
      expect(screen.getByText('Socket Connected')).toBeInTheDocument();
    });

    act(() => {
      mockSocket.onclose();
    });

    await waitFor(() => {
      expect(screen.getByText('Socket Null')).toBeInTheDocument();
    });
  });

  it('parses invitation events and notifies subscribers', async () => {
    const listener = vi.fn();
    function TestComponent() {
      const { lastInvitationEvent, subscribe } = useWebSocket();
      useEffect(() => subscribe(listener), [subscribe]);
      return (
        <div>
          {lastInvitationEvent
            ? `Invite:${lastInvitationEvent.invitation.game_name}`
            : 'No invite'}
        </div>
      );
    }

    render(
      <WebSocketProvider>
        <TestComponent />
      </WebSocketProvider>,
    );

    act(() => {
      mockSocket.onmessage({
        data: JSON.stringify({
          event: 'invitation',
          action: 'created',
          invitation: {
            id: 1,
            game_id: 2,
            game_name: 'Lobby',
            game_link: 'abc',
            gamemode: 'Conquest',
            inviter_id: 3,
            inviter_username: 'host',
            invitee_id: 1,
            invitee_username: 'tester',
            status: 'pending',
            created_at: '2026-01-01T00:00:00Z',
          },
        }),
      });
    });

    await waitFor(() => {
      expect(screen.getByText('Invite:Lobby')).toBeInTheDocument();
    });
    expect(listener).toHaveBeenCalled();
  });

  it('ignores non-json messages and closes on unmount', () => {
    const { unmount } = render(
      <WebSocketProvider>
        <div />
      </WebSocketProvider>,
    );
    act(() => {
      mockSocket.onmessage({ data: 'hello' });
      mockSocket.onerror(new Event('error'));
    });
    unmount();
    expect(mockSocket.close).toHaveBeenCalled();
  });
});
