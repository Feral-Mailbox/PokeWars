import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";

const CreateGame = () => {
  const [mapName, setMapName] = useState("Route 224");
  const [maxPlayers, setMaxPlayers] = useState(2);
  const [isPrivate, setIsPrivate] = useState(false);
  const [gameName, setGameName] = useState("");
  const [userId, setUserId] = useState<number | null>(null);

  const navigate = useNavigate();

  useEffect(() => {
    const fetchMe = async () => {
      try {
        const data = await secureFetch<{ id: number }>("/me");
        setUserId(data.id);
      } catch (err) {
        console.error("User not authenticated or /me failed", err);
      }
    };
    fetchMe();
  }, []);
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = {
      game_name: gameName,
      map_name: mapName,
      max_players: maxPlayers,
      is_private: isPrivate
    };
    console.log(payload)

    const res = await secureFetch("/api/games/create", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });

    console.log(res)

    if (res?.ok) {
      const game = await res.json();
      navigate(`/games/${game.link}`);
    } else {
      console.error("Failed to create game");
    }    
  };

  return (
    <div className="pt-20 px-4 text-white max-w-xl mx-auto">
      <h1 className="text-3xl font-bold mb-4">Create a Game</h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Game Name */}
        <div>
          <label className="block text-sm font-medium mb-1">Game Name</label>
          <input
            type="text"
            value={gameName}
            onChange={(e) => setGameName(e.target.value)}
            placeholder="My Awesome Match"
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
            required
          />
        </div>

        {/* Player Count */}
        <div>
          <label className="block text-sm font-medium mb-1">Number of Players</label>
          <select
            value={maxPlayers}
            onChange={(e) => setMaxPlayers(Number(e.target.value))}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
          >
            {[...Array(7)].map((_, i) => (
              <option key={i + 2} value={i + 2}>
                {i + 2} Players
              </option>
            ))}
          </select>
        </div>

        {/* Tileset Selector */}
        <div>
          <label className="block text-sm font-medium mb-1">Map Name</label>
          <select
            value={mapName}
            onChange={(e) => setMapName(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
          >
            <option value="" disabled>-- Select a Map --</option>
            <option value="Route 224">Route 224</option>
            {/* Add more tilemaps when needed */}
          </select>
        </div>

        {/* Private Game Option */}
        <div className="flex items-center">
          <input
            type="checkbox"
            id="private"
            checked={isPrivate}
            onChange={() => setIsPrivate((prev) => !prev)}
            className="mr-2"
          />
          <label htmlFor="private">Private Game</label>
        </div>

        {/* Submit Button */}
        <button
          type="submit"
          className="w-full bg-indigo-600 hover:bg-indigo-700 px-4 py-2 rounded text-white font-bold"
        >
          Create Game
        </button>
      </form>
    </div>
  );
};

export default CreateGame;
