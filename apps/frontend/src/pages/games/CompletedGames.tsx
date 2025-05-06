import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";

export default function CompletedGames() {
  const [userId, setUserId] = useState<number | null>(null);
  const [games, setGames] = useState([]);
  const [playerFilter, setPlayerFilter] = useState("All");
  const [mapFilter, setMapFilter] = useState("All");

  const navigate = useNavigate();

  useEffect(() => {
    const fetchGames = async () => {
      try {
        const res = await secureFetch("/api/games/completed");
        const data = await res.json();
        setGames(data);
      } catch (err) {
        console.error("Failed to fetch games:", err);
      }
    };
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

  const filteredGames = games
  .filter((game: any) => {
    const playerMatch =
      playerFilter === "All" || game.max_players.toString() === playerFilter;
    const mapMatch =
      mapFilter === "All" || game.map_name.toLowerCase() === mapFilter.toLowerCase();
    return playerMatch && mapMatch;
  })
  .sort((a: any, b: any) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
  .slice(0, 10);

  return (
    <div>
      <h1 className="text-3xl font-bold mb-6">Completed Games</h1>

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
      </div>

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
              className="px-4 py-2 bg-gray-500 text-white rounded"
              onClick={() => navigate(`/games/${game.link}`)}
            >
              Review
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
