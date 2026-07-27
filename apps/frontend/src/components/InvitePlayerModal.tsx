import { useEffect, useState } from 'react';
import { secureFetch } from '@/utils/secureFetch';
import type { PlayerSearchHit } from '../types/invitation';

type InvitePlayerModalProps = {
  gameId: number;
  open: boolean;
  onClose: () => void;
  onInvited?: (username: string) => void;
};

function apiErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  return fallback;
}

export default function InvitePlayerModal({
  gameId,
  open,
  onClose,
  onInvited,
}: InvitePlayerModalProps) {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<PlayerSearchHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [invitingId, setInvitingId] = useState<number | null>(null);
  const [message, setMessage] = useState<{ type: 'error' | 'success'; text: string } | null>(
    null,
  );

  useEffect(() => {
    if (!open) {
      setQuery('');
      setResults([]);
      setMessage(null);
      setInvitingId(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const trimmed = query.trim();
    if (trimmed.length < 1) {
      setResults([]);
      return;
    }

    let cancelled = false;
    const timer = window.setTimeout(async () => {
      setSearching(true);
      try {
        const res = await secureFetch(`/api/players/search?q=${encodeURIComponent(trimmed)}`);
        if (!res?.ok) {
          if (!cancelled) setResults([]);
          return;
        }
        const data = (await res.json()) as PlayerSearchHit[];
        if (!cancelled) setResults(Array.isArray(data) ? data : []);
      } catch {
        if (!cancelled) setResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, open]);

  if (!open) return null;

  const invitePlayer = async (player: PlayerSearchHit) => {
    setInvitingId(player.id);
    setMessage(null);
    try {
      const res = await secureFetch('/api/invitations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ game_id: gameId, invitee_id: player.id }),
      });
      const payload = await res?.json().catch(() => null);
      if (!res?.ok) {
        setMessage({
          type: 'error',
          text: apiErrorMessage(payload, 'Could not send invitation.'),
        });
        return;
      }
      setMessage({ type: 'success', text: `Invited ${player.username}.` });
      onInvited?.(player.username);
    } catch {
      setMessage({ type: 'error', text: 'Could not send invitation.' });
    } finally {
      setInvitingId(null);
    }
  };

  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 px-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Invite player"
        className="w-full max-w-md rounded-lg border border-gray-700 bg-gray-900 p-5 text-white shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Invite a player</h2>
            <p className="mt-1 text-sm text-gray-400">
              Search by username or trainer ID.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-sm text-gray-400 hover:text-white"
          >
            Close
          </button>
        </div>

        <label className="mt-4 block text-xs font-medium uppercase tracking-wide text-gray-400">
          Search
          <input
            className="mt-1 w-full rounded border border-gray-600 bg-gray-800 px-3 py-2 text-sm text-white focus:border-blue-500 focus:outline-none"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Username or trainer ID"
            autoFocus
          />
        </label>

        {message ? (
          <p
            className={`mt-3 text-sm ${message.type === 'error' ? 'text-red-400' : 'text-green-400'}`}
            role="status"
          >
            {message.text}
          </p>
        ) : null}

        <ul className="mt-4 max-h-64 space-y-2 overflow-y-auto">
          {searching ? <li className="text-sm text-gray-400">Searching…</li> : null}
          {!searching && query.trim() && results.length === 0 ? (
            <li className="text-sm text-gray-400">No players found.</li>
          ) : null}
          {results.map((player) => (
            <li
              key={player.id}
              className="flex items-center justify-between gap-3 rounded border border-gray-700 bg-gray-800/80 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate font-medium">{player.username}</p>
                <p className="font-mono text-xs text-gray-400">{player.trainer_id}</p>
              </div>
              <button
                type="button"
                disabled={invitingId === player.id}
                onClick={() => void invitePlayer(player)}
                className="shrink-0 rounded bg-blue-600 px-3 py-1.5 text-xs font-medium hover:bg-blue-500 disabled:opacity-60"
              >
                {invitingId === player.id ? 'Inviting…' : 'Invite'}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
