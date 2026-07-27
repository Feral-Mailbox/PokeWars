import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { secureFetch } from '@/utils/secureFetch';
import { useWebSocket } from '../state/WebSocketContext';
import type { GameInvitation, InboxPayload, InvitationWsEvent } from '../types/invitation';

function apiErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  return fallback;
}

export default function InboxDropdown() {
  const navigate = useNavigate();
  const { subscribe } = useWebSocket();
  const [open, setOpen] = useState(false);
  const [invitations, setInvitations] = useState<GameInvitation[]>([]);
  const [pendingCount, setPendingCount] = useState(0);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const loadInbox = useCallback(async () => {
    const res = await secureFetch('/api/invitations/inbox');
    if (!res?.ok) return;
    const data = (await res.json()) as InboxPayload;
    setInvitations(data.invitations || []);
    setPendingCount(data.pending_count || 0);
  }, []);

  useEffect(() => {
    void loadInbox();
  }, [loadInbox]);

  useEffect(() => {
    return subscribe((payload) => {
      if (!payload || typeof payload !== 'object') return;
      if ((payload as InvitationWsEvent).event !== 'invitation') return;
      void loadInbox();
    });
  }, [subscribe, loadInbox]);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  const respond = async (invitation: GameInvitation, action: 'accept' | 'cancel') => {
    setBusyId(invitation.id);
    setError(null);
    try {
      const res = await secureFetch(`/api/invitations/${invitation.id}/${action}`, {
        method: 'POST',
      });
      const payload = await res?.json().catch(() => null);
      if (!res?.ok) {
        setError(apiErrorMessage(payload, `Could not ${action} invitation.`));
        return;
      }
      await loadInbox();
      if (action === 'accept') {
        setOpen(false);
        navigate(`/games/${invitation.game_link}`);
      }
    } catch {
      setError(`Could not ${action} invitation.`);
    } finally {
      setBusyId(null);
    }
  };

  const pending = invitations.filter((row) => row.status === 'pending');

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => {
          setOpen((prev) => !prev);
          void loadInbox();
        }}
        className="relative flex items-center justify-center rounded bg-transparent px-2 py-1 text-white shadow-none transition-colors hover:text-blue-400"
        aria-label="Inbox"
        title="Inbox"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-5 w-5"
          aria-hidden="true"
        >
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
        {pendingCount > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
            {pendingCount > 9 ? '9+' : pendingCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 top-10 z-30 w-80 rounded border border-gray-700 bg-gray-800 p-3 text-white shadow-xl">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Inbox</h2>
            <button
              type="button"
              className="text-xs text-gray-400 hover:text-white"
              onClick={() => void loadInbox()}
            >
              Refresh
            </button>
          </div>
          {error ? <p className="mb-2 text-xs text-red-400">{error}</p> : null}
          {pending.length === 0 ? (
            <p className="text-sm text-gray-400">No pending invitations.</p>
          ) : (
            <ul className="max-h-80 space-y-3 overflow-y-auto">
              {pending.map((invite) => (
                <li
                  key={invite.id}
                  className="rounded border border-gray-700 bg-gray-900/70 p-3 text-sm"
                >
                  <p className="font-medium text-white">
                    {invite.inviter_username} invited you
                  </p>
                  <p className="mt-1 text-gray-300">
                    {invite.game_name} · {invite.gamemode}
                  </p>
                  <div className="mt-3 flex gap-2">
                    <button
                      type="button"
                      disabled={busyId === invite.id}
                      onClick={() => void respond(invite, 'accept')}
                      className="rounded bg-blue-600 px-2 py-1 text-xs font-medium hover:bg-blue-500 disabled:opacity-60"
                    >
                      Join
                    </button>
                    <button
                      type="button"
                      disabled={busyId === invite.id}
                      onClick={() => void respond(invite, 'cancel')}
                      className="rounded border border-gray-600 px-2 py-1 text-xs text-gray-200 hover:bg-gray-700 disabled:opacity-60"
                    >
                      Cancel
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
