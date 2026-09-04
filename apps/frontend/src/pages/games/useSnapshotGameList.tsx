import { useCallback, useEffect, useRef, useState } from "react";
import { secureFetch } from "@/utils/secureFetch";

export type GameListItem = {
  id: number;
  link: string;
  game_name?: string;
  map_name: string;
  max_players: number;
  host_id: number;
  host_username?: string | null;
  players: Array<{ player_id: number; username: string }>;
  gamemode: string;
  status: string;
  timestamp: string;
};

type GameListPageResponse = {
  items: GameListItem[];
  page: number;
  page_size: number;
  total: number;
  as_of: string;
};

const PAGE_SIZE = 10;
const MAP_FILTER_DEBOUNCE_MS = 300;

function buildListUrl(
  listPath: string,
  opts: {
    page: number;
    asOf: string | null;
    playerFilter: string;
    mapFilter: string;
    reload: boolean;
  }
): string {
  const params = new URLSearchParams();
  params.set("page", String(opts.page));
  params.set("page_size", String(PAGE_SIZE));
  if (!opts.reload && opts.asOf) {
    params.set("as_of", opts.asOf);
  }
  if (opts.playerFilter !== "All") {
    params.set("max_players", opts.playerFilter);
  }
  const map = opts.mapFilter.trim();
  if (map && map.toLowerCase() !== "all") {
    params.set("map_name", map);
  }
  return `/api${listPath}?${params.toString()}`;
}

function filterKey(playerFilter: string, mapFilter: string): string {
  return `${playerFilter}::${mapFilter.trim().toLowerCase()}`;
}

/**
 * Snapshot-based game list: Reload (or first load) freezes `as_of`.
 * Pagination and filters reuse that snapshot until the next Reload.
 */
export function useSnapshotGameList(listPath: string) {
  const [games, setGames] = useState<GameListItem[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [playerFilter, setPlayerFilter] = useState("All");
  const [mapFilter, setMapFilter] = useState("");
  const [debouncedMapFilter, setDebouncedMapFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const asOfRef = useRef<string | null>(null);
  const appliedFilterKeyRef = useRef<string | null>(null);
  const playerFilterRef = useRef(playerFilter);
  const mapFilterRef = useRef(debouncedMapFilter);
  const requestIdRef = useRef(0);

  playerFilterRef.current = playerFilter;
  mapFilterRef.current = debouncedMapFilter;

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setDebouncedMapFilter(mapFilter);
    }, MAP_FILTER_DEBOUNCE_MS);
    return () => window.clearTimeout(handle);
  }, [mapFilter]);

  const fetchPage = useCallback(
    async (opts: { page: number; reload?: boolean }) => {
      const requestId = ++requestIdRef.current;
      setLoading(true);
      try {
        const reload = Boolean(opts.reload);
        const url = buildListUrl(listPath, {
          page: opts.page,
          asOf: asOfRef.current,
          playerFilter: playerFilterRef.current,
          mapFilter: mapFilterRef.current,
          reload,
        });
        const res = await secureFetch(url);
        if (!res?.ok) return;
        const data = (await res.json()) as GameListPageResponse;
        if (requestId !== requestIdRef.current) return;
        if (!data || !Array.isArray(data.items)) return;

        asOfRef.current = data.as_of;
        appliedFilterKeyRef.current = filterKey(
          playerFilterRef.current,
          mapFilterRef.current
        );
        setGames(data.items);
        setTotal(Number(data.total) || 0);
        setPage(Number(data.page) || opts.page);
      } catch (err) {
        console.error("Failed to fetch games:", err);
      } finally {
        if (requestId === requestIdRef.current) {
          setLoading(false);
        }
      }
    },
    [listPath]
  );

  useEffect(() => {
    void fetchPage({ page: 1, reload: true });
  }, [fetchPage]);

  // Filters re-query page 1 against the existing snapshot (no new as_of).
  useEffect(() => {
    if (!asOfRef.current) return;
    const nextKey = filterKey(playerFilter, debouncedMapFilter);
    if (appliedFilterKeyRef.current === nextKey) return;
    void fetchPage({ page: 1 });
  }, [playerFilter, debouncedMapFilter, fetchPage]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const reload = useCallback(() => {
    asOfRef.current = null;
    appliedFilterKeyRef.current = null;
    void fetchPage({ page: 1, reload: true });
  }, [fetchPage]);

  const goToPage = useCallback(
    (nextPage: number) => {
      const clamped = Math.min(Math.max(1, nextPage), totalPages);
      void fetchPage({ page: clamped });
    },
    [fetchPage, totalPages]
  );

  return {
    games,
    page,
    total,
    totalPages,
    loading,
    playerFilter,
    setPlayerFilter,
    mapFilter,
    setMapFilter,
    reload,
    goToPage,
    goFirstPage: () => goToPage(1),
    goPrevPage: () => goToPage(page - 1),
    goNextPage: () => goToPage(page + 1),
    goLastPage: () => goToPage(totalPages),
  };
}

export function GameListFilters(props: {
  playerFilter: string;
  setPlayerFilter: (value: string) => void;
  mapFilter: string;
  setMapFilter: (value: string) => void;
  onReload: () => void;
  loading?: boolean;
}) {
  const {
    playerFilter,
    setPlayerFilter,
    mapFilter,
    setMapFilter,
    onReload,
    loading,
  } = props;

  return (
    <div className="flex flex-wrap gap-4 mb-6 items-center">
      <select
        value={playerFilter}
        onChange={(e) => setPlayerFilter(e.target.value)}
        className="border p-2 rounded"
      >
        <option value="All">All Players</option>
        {[...Array(7)].map((_, i) => (
          <option key={i + 2} value={i + 2}>
            {i + 2} Players
          </option>
        ))}
      </select>

      <input
        type="text"
        placeholder="Filter by Map"
        value={mapFilter}
        onChange={(e) => setMapFilter(e.target.value)}
        className="border p-2 rounded"
      />
      <button
        type="button"
        onClick={onReload}
        disabled={loading}
        title="Reload games"
        className="flex items-center gap-1 border p-2 rounded bg-gray-700 hover:bg-gray-600 text-white disabled:opacity-50"
      >
        Reload
      </button>
    </div>
  );
}

export function GameListPagination(props: {
  page: number;
  totalPages: number;
  hasItems: boolean;
  onFirst: () => void;
  onPrev: () => void;
  onNext: () => void;
  onLast: () => void;
}) {
  const { page, totalPages, hasItems, onFirst, onPrev, onNext, onLast } = props;
  if (!hasItems) return null;

  return (
    <div className="flex justify-center items-center gap-4 mb-4">
      <button type="button" onClick={onFirst} disabled={page === 1}>
        &lt;&lt;
      </button>
      <button type="button" onClick={onPrev} disabled={page === 1}>
        &lt;
      </button>
      <span>
        Page {page}
        {totalPages > 0 ? ` / ${totalPages}` : ""}
      </span>
      <button type="button" onClick={onNext} disabled={page >= totalPages}>
        &gt;
      </button>
      <button type="button" onClick={onLast} disabled={page >= totalPages}>
        &gt;&gt;
      </button>
    </div>
  );
}
