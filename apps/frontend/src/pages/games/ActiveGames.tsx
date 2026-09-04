import { useNavigate } from "react-router-dom";
import {
  GameListFilters,
  GameListPagination,
  useSnapshotGameList,
} from "./useSnapshotGameList";

export default function ActiveGames() {
  const navigate = useNavigate();
  const list = useSnapshotGameList("/games/in_progress");

  const hostName = (game: (typeof list.games)[number]) =>
    game.host_username ??
    game.players.find((p) => p.player_id === game.host_id)?.username ??
    "Unknown";

  return (
    <div className="pt-20 px-4 pb-8 text-white">
      <h1 className="text-3xl font-bold mb-6">In-Progress Games</h1>

      <GameListFilters
        playerFilter={list.playerFilter}
        setPlayerFilter={list.setPlayerFilter}
        mapFilter={list.mapFilter}
        setMapFilter={list.setMapFilter}
        onReload={list.reload}
        loading={list.loading}
      />
      <GameListPagination
        page={list.page}
        totalPages={list.totalPages}
        hasItems={list.games.length > 0}
        onFirst={list.goFirstPage}
        onPrev={list.goPrevPage}
        onNext={list.goNextPage}
        onLast={list.goLastPage}
      />
      <ul className="space-y-4">
        {list.games.map((game) => (
          <li key={game.id} className="border p-4 rounded shadow">
            <p className="text-lg font-bold mb-2">{game.game_name || "Untitled Game"}</p>
            <p>
              <strong>Host:</strong> {hostName(game)}
            </p>
            <p>
              <strong>Game Mode:</strong> {game.gamemode}
            </p>
            <p>
              <strong>Players:</strong> {game.players.length}/{game.max_players}
            </p>
            <p>
              <strong>Map:</strong> {game.map_name}
            </p>
            <button
              className="px-4 py-2 bg-gray-500 text-white rounded"
              onClick={() => navigate(`/games/${game.link}`)}
            >
              Spectate
            </button>
          </li>
        ))}
      </ul>
      <GameListPagination
        page={list.page}
        totalPages={list.totalPages}
        hasItems={list.games.length > 0}
        onFirst={list.goFirstPage}
        onPrev={list.goPrevPage}
        onNext={list.goNextPage}
        onLast={list.goLastPage}
      />
    </div>
  );
}
