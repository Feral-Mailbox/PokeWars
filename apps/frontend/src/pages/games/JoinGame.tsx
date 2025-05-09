import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";

export default function JoinGame() {
  const [userId, setUserId] = useState<number | null>(null);
  const [games, setGames] = useState([]);
  const [playerFilter, setPlayerFilter] = useState("All");
  const [mapFilter, setMapFilter] = useState("All");
  const [page, setPage] = useState(1);

  const navigate = useNavigate();

  const fetchGames = async () => {
    try {
      const res = await secureFetch(`/api/games/open`);
      const data = await res.json();
      setGames(data);
      setPage(1);
    } catch (err) {
      console.error("Failed to fetch games:", err);
    }
  };  
  
  useEffect(() => {
    fetchGames();
  }, []);

  useEffect(() => {
    const fetchUser = async () => {
      try {
        const res = await secureFetch("/api/me");
        const data = await res.json();
        setUserId(data.id);
      } catch (err) {
        console.error("Failed to fetch user:", err);
      }
    };
    fetchUser();
  }, []);

  const isUserInGame = (game: any) => {
    if (!userId || !Array.isArray(game.players)) return false;
    return game.players.some((p: any) => p.id === userId);
  };

  const handleJoinGame = async (gameId: number) => {
    try {
      const res = await secureFetch(`/api/games/join/${gameId}`, { method: "POST" });
      if (res.ok) {
        const updatedGame = await res.json();
        navigate(`/games/${updatedGame.link}`);
      } else {
        alert("Failed to join game");
      }
    } catch (err) {
      console.error("Error joining game:", err);
      alert("An error occurred while trying to join the game.");
    }
  };  

  const filteredGames = games
  .filter((game: any) => {
    const playerMatch =
      playerFilter === "All" || game.max_players.toString() === playerFilter;
    const mapMatch =
      mapFilter === "All" || game.map_name.toLowerCase() === mapFilter.toLowerCase();
    return playerMatch && mapMatch;
  })
  .sort((a: any, b: any) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());
  
  const totalPages = Math.ceil(filteredGames.length / 10);
  const displayedGames = filteredGames.slice((page - 1) * 10, page * 10);

  return (
    <div>
      <h1 className="text-3xl font-bold mb-6">Join Game</h1>

      <div className="flex gap-4 mb-6">
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
          onClick={() => fetchGames(page)}
          title="Reload games"
          className="flex items-center gap-1 border p-2 rounded bg-gray-700 hover:bg-gray-600 text-white"
        >
          Reload
        </button>
      </div>
      {displayedGames.length > 0 && (
        <div className="flex justify-center items-center gap-4 mb-4">
          <button onClick={() => setPage(1)} disabled={page === 1}>&lt;&lt;</button>
          <button onClick={() => setPage(page - 1)} disabled={page === 1}>&lt;</button>
          <span>Page {page}</span>
          <button onClick={() => setPage(page + 1)} disabled={page >= totalPages}>&gt;</button>
          <button onClick={() => setPage(totalPages)} disabled={page >= totalPages}>&gt;&gt;</button>
        </div>
      )}
      <ul className="space-y-4">
        {filteredGames.map((game: any) => (
          <li key={game.id} className="border p-4 rounded shadow">
            <p className="text-lg font-bold mb-2">{game.game_name || "Untitled Game"}</p>
            <p>
              <strong>Host:</strong> {game.host?.username ?? "Unknown"}
            </p>
            <p>
              <strong>Players:</strong> {game.players.length}/{game.max_players}
            </p>
            <p>
              <strong>Map:</strong> {game.map_name}
            </p>
            <button
              className="mt-2 px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
              disabled={isUserInGame(game)}
              onClick={() => handleJoinGame(game.id)}
            >
              Join
            </button>
            <button
              className="px-4 py-2 bg-gray-500 text-white rounded"
              onClick={() => navigate(`/games/${game.link}`)}
            >
              Spectate
            </button>
          </li>
        ))}
      </ul>
      {displayedGames.length > 0 && (
        <div className="flex justify-center items-center gap-4 mb-4">
          <button onClick={() => setPage(1)} disabled={page === 1}>&lt;&lt;</button>
          <button onClick={() => setPage(page - 1)} disabled={page === 1}>&lt;</button>
          <span>Page {page}</span>
          <button onClick={() => setPage(page + 1)} disabled={page >= totalPages}>&gt;</button>
          <button onClick={() => setPage(totalPages)} disabled={page >= totalPages}>&gt;&gt;</button>
        </div>
      )}
    </div>
  );
}
