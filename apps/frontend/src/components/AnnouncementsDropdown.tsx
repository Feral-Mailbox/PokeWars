import { useCallback, useEffect, useRef, useState } from 'react';
import { secureFetch } from '@/utils/secureFetch';
import { useWebSocket } from '../state/WebSocketContext';
import type { AnnouncementWsEvent, StaffAnnouncement } from '../types/announcement';

const SEEN_KEY = 'announcements_last_seen_id';

function readLastSeenId(): number {
  const raw = localStorage.getItem(SEEN_KEY);
  const value = Number(raw);
  return Number.isFinite(value) ? value : 0;
}

function writeLastSeenId(id: number) {
  localStorage.setItem(SEEN_KEY, String(id));
}

export default function AnnouncementsDropdown() {
  const { subscribe } = useWebSocket();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<StaffAnnouncement[]>([]);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [lastSeenId, setLastSeenId] = useState(readLastSeenId);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    const res = await secureFetch('/api/announcements');
    if (!res?.ok) return;
    const data = (await res.json()) as StaffAnnouncement[];
    setItems(Array.isArray(data) ? data : []);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    return subscribe((payload) => {
      if (!payload || typeof payload !== 'object') return;
      if ((payload as AnnouncementWsEvent).event !== 'announcement') return;
      void load();
    });
  }, [subscribe, load]);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, []);

  useEffect(() => {
    if (!open || items.length === 0) return;
    const newest = items[0]?.id ?? 0;
    if (newest > lastSeenId) {
      writeLastSeenId(newest);
      setLastSeenId(newest);
    }
  }, [open, items, lastSeenId]);

  const toggleStar = async (row: StaffAnnouncement) => {
    setBusy(true);
    setError(null);
    try {
      const res = await secureFetch(
        `/api/announcements/${row.id}/star`,
        { method: row.starred ? 'DELETE' : 'POST' },
      );
      if (!res?.ok) {
        setError('Could not update star.');
        return;
      }
      const updated = (await res.json()) as StaffAnnouncement;
      setItems((prev) =>
        prev.map((item) => (item.id === updated.id ? { ...item, starred: updated.starred } : item)),
      );
    } finally {
      setBusy(false);
    }
  };

  const clearAll = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await secureFetch('/api/announcements/clear', { method: 'POST' });
      if (!res?.ok) {
        setError('Could not clear announcements.');
        return;
      }
      await load();
      setExpandedId(null);
    } finally {
      setBusy(false);
    }
  };

  const unreadCount = items.filter((row) => row.id > lastSeenId).length;
  const clearableCount = items.filter((row) => !row.starred).length;

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => {
          setOpen((prev) => {
            const next = !prev;
            if (next) void load();
            return next;
          });
        }}
        className="relative flex items-center justify-center rounded bg-transparent px-2 py-1 text-white shadow-none transition-colors hover:text-blue-400"
        aria-label="Announcements"
        title="Announcements"
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
          <path d="m3 11 18-5v12L3 13v-2z" />
          <path d="M11.6 16.8a3 3 0 1 1-5.8-1.6" />
        </svg>
        {!open && unreadCount > 0 ? (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-amber-500 px-1 text-[10px] font-bold text-black">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className="absolute right-0 top-10 z-30 w-96 max-w-[90vw] rounded border border-gray-700 bg-gray-800 p-3 text-white shadow-xl">
          <div className="mb-2 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Announcements</h2>
            <div className="flex items-center gap-3">
              {items.length > 0 ? (
                <button
                  type="button"
                  className="text-xs text-gray-400 hover:text-white disabled:opacity-50"
                  disabled={busy || clearableCount === 0}
                  onClick={() => void clearAll()}
                >
                  Clear all
                </button>
              ) : null}
              <button
                type="button"
                className="text-xs text-gray-400 hover:text-white disabled:opacity-50"
                disabled={busy}
                onClick={() => void load()}
              >
                Refresh
              </button>
            </div>
          </div>
          {error ? <p className="mb-2 text-xs text-red-400">{error}</p> : null}
          {items.length === 0 ? (
            <p className="text-sm text-gray-400">No announcements yet.</p>
          ) : (
            <ul className="max-h-96 space-y-2 overflow-y-auto">
              {items.map((row) => {
                const expanded = expandedId === row.id;
                return (
                  <li
                    key={row.id}
                    className="rounded border border-gray-700 bg-gray-900/70 text-sm"
                  >
                    <div className="flex items-start gap-1 px-2 py-2">
                      <button
                        type="button"
                        className={`mt-0.5 shrink-0 rounded p-1 transition-colors disabled:opacity-50 ${
                          row.starred
                            ? 'text-amber-400 hover:text-amber-300'
                            : 'text-gray-500 hover:text-amber-400'
                        }`}
                        disabled={busy}
                        aria-label={row.starred ? 'Unstar announcement' : 'Star announcement'}
                        title={row.starred ? 'Unstar' : 'Star'}
                        onClick={() => void toggleStar(row)}
                      >
                        <svg
                          xmlns="http://www.w3.org/2000/svg"
                          viewBox="0 0 24 24"
                          fill={row.starred ? 'currentColor' : 'none'}
                          stroke="currentColor"
                          strokeWidth="2"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          className="h-4 w-4"
                          aria-hidden="true"
                        >
                          <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                        </svg>
                      </button>
                      <button
                        type="button"
                        className="flex min-w-0 flex-1 items-start justify-between gap-3 px-1 text-left hover:bg-gray-900/80"
                        onClick={() => {
                          setExpandedId(expanded ? null : row.id);
                          setError(null);
                        }}
                        aria-expanded={expanded}
                      >
                        <div className="min-w-0">
                          <p className="truncate font-medium text-white">{row.title}</p>
                          <p className="mt-0.5 text-xs text-gray-400">
                            {row.author_username} · {new Date(row.created_at).toLocaleString()}
                          </p>
                        </div>
                        <span className="shrink-0 text-xs text-blue-400">
                          {expanded ? 'Hide' : 'Expand'}
                        </span>
                      </button>
                    </div>
                    {expanded ? (
                      <div className="border-t border-gray-700 px-3 py-2 whitespace-pre-wrap text-gray-200">
                        {row.message}
                      </div>
                    ) : null}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
