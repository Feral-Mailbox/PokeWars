import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";

const CreateGame = () => {
  const [availableMaps, setAvailableMaps] = useState<{ id: number; name: string; width: number; height: number; allowed_modes: string[]; }[]>([]);
  const [gamemode, setGamemode] = useState("conquest");
  const [mapName, setMapName] = useState("");
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

  useEffect(() => {
    const fetchMaps = async () => {
      try {
        const res = await secureFetch("/api/maps/official");
        const data = await res.json();
        setAvailableMaps(data);
        if (data.length > 0) setMapName(data[0].name);
      } catch (err) {
        console.error("Failed to fetch maps", err);
      }
    };
    fetchMaps();
  }, []);

  useEffect(() => {
    if (selectedMap && !selectedMap.allowed_modes.includes(gamemode)) {
      setGamemode(selectedMap.allowed_modes[0]);
    }
  }, [mapName]);

  const selectedMap = availableMaps.find((map) => map.name === mapName);
  const availableModes = selectedMap?.allowed_modes ?? []; 
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = {
      game_name: gameName,
      map_name: mapName,
      gamemode: gamemode,
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

        {/* Tileset Selector */}
        <div>
          <label className="block text-sm font-medium mb-1">Map Name</label>
          <select
            value={mapName}
            onChange={(e) => setMapName(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
          >
            <option value="" disabled>-- Select a Map --</option>
            {availableMaps.map((map) => (
              <option key={map.id} value={map.name}>
                {map.name} ({map.width}×{map.height})
              </option>
            ))}
          </select>
        </div>

        {/* Game Mode Selector */}
        <div>
          <label className="block text-sm font-medium mb-1">Game Mode</label>
          <select
            value={gamemode}
            onChange={(e) => setGamemode(e.target.value)}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
          >
            {availableModes.map((mode) => (
              <option key={mode} value={mode}>
                {mode.replace(/_/g, " ").replace(/\b\w/g, (l) => l.toUpperCase())}
              </option>
            ))}
          </select>
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
