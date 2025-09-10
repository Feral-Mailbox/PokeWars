import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";

const CreateGame = () => {
  const [availableMaps, setAvailableMaps] = useState<{ id: number; name: string; width: number; height: number; allowed_modes: string[]; }[]>([]);
  const [gamemode, setGamemode] = useState("conquest");
  const [mapName, setMapName] = useState("");
  const [maxPlayers, setMaxPlayers] = useState(2);
  const [startingCash, setStartingCash] = useState<number>(3000);
  const [cashPerTurn, setCashPerTurn] = useState<number>(100);
  const [maxTurns, setMaxTurns] = useState<number>(99);
  const [unitLimit, setUnitLimit] = useState<number>(30);
  const [turnSeconds, setTurnSeconds] = useState<number>(300);
  const [isPrivate, setIsPrivate] = useState(false);
  const [gameName, setGameName] = useState("");
  const [userId, setUserId] = useState<number | null>(null);

  const navigate = useNavigate();

  const TURN_PRESETS = [
  { label: "30 seconds", value: 30 },
  { label: "1 minute",   value: 60 },
  { label: "2 minutes",  value: 120 },
  { label: "5 minutes",  value: 300 },   // default value
  { label: "10 minutes", value: 600 },
  { label: "15 minutes", value: 900 },
  { label: "30 minutes", value: 1800 },
  { label: "1 hour",     value: 3600 },
  { label: "2 hours",    value: 7200 },
  { label: "4 hours",    value: 14400 },
  { label: "8 hours",    value: 28800 },
  { label: "12 hours",   value: 43200 },
  { label: "24 hours",   value: 86400 },
];

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
      applyGamemodeDefaults(selectedMap.allowed_modes[0]);
    }
  }, [mapName]);

  useEffect(() => {
    if (selectedMap && !selectedMap.allowed_player_counts.includes(maxPlayers)) {
      setMaxPlayers(selectedMap.allowed_player_counts[0]);
    }
  }, [mapName]);

  const selectedMap = availableMaps.find((map) => map.name === mapName);
  const availableModes = selectedMap?.allowed_modes ?? [];
  const allowedPlayerCounts = selectedMap?.allowed_player_counts ?? [2, 3, 4, 5, 6, 7, 8];

  const applyGamemodeDefaults = (selected: string) => {
    setGamemode(selected);
    if (selected === "War") {
      setStartingCash(100);
      setCashPerTurn(100);
      setMaxTurns(99);
      setUnitLimit(30);
    } else {
      setStartingCash(3000);
      setCashPerTurn(undefined);
      setUnitLimit(undefined);
      setMaxTurns(selected === "Capture The Flag" ? 99 : undefined);
    }
  };
  
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const payload = {
      game_name: gameName,
      map_name: mapName,
      gamemode,
      max_players: maxPlayers,
      is_private: isPrivate,
      starting_cash: startingCash,
      cash_per_turn: cashPerTurn,
      max_turns: maxTurns,
      unit_limit: unitLimit,  
      turn_seconds: turnSeconds,
    };

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
          <label htmlFor="gameName" className="block text-sm font-medium mb-1">Game Name</label>
          <input
            id="gameName"
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
            onChange={(e) => applyGamemodeDefaults(e.target.value)}
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
            {allowedPlayerCounts.map((count) => (
              <option key={count} value={count}>
                {count} Players
              </option>
            ))}
          </select>
        </div>

        {(gamemode === "War" || gamemode === "Conquest" || gamemode === "Capture The Flag") && (
          <div>
            <label className="block text-sm font-medium mb-1">Starting Cash</label>
            <select
              value={startingCash}
              onChange={(e) => setStartingCash(Number(e.target.value))}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
            >
              {[...Array(51)].map((_, i) => {
                const val = i * 100;
                return <option key={val} value={val}>{val}</option>;
              })}
            </select>
          </div>
        )}

        <div>
          <label className="block text-sm font-medium mb-1">Turn Timer</label>
          <select
            value={turnSeconds}
            onChange={(e) => setTurnSeconds(Number(e.target.value))}
            className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
          >
            {TURN_PRESETS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
          <p className="text-xs text-gray-400 mt-1">
            When time runs out, the next player’s turn begins automatically.
          </p>
        </div>

        {gamemode === "War" && (
          <>
            <div>
              <label className="block text-sm font-medium mb-1">Cash Per Turn</label>
              <select
                value={cashPerTurn}
                onChange={(e) => setCashPerTurn(Number(e.target.value))}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
              >
                {[...Array(11)].map((_, i) => {
                  const val = i * 50;
                  return <option key={val} value={val}>{val}</option>;
                })}
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium mb-1">Unit Limit</label>
              <select
                value={unitLimit}
                onChange={(e) => setUnitLimit(Number(e.target.value))}
                className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
              >
                {[...Array(18)].map((_, i) => {
                  const val = 15 + i * 5;
                  return <option key={val} value={val}>{val}</option>;
                })}
              </select>
            </div>
          </>
        )}

        {(gamemode === "War" || gamemode === "Capture The Flag") && (
          <div>
            <label className="block text-sm font-medium mb-1">Max Turns</label>
            <select
              value={maxTurns}
              onChange={(e) => setMaxTurns(Number(e.target.value))}
              className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded"
            >
              {[...Array(95)].map((_, i) => {
                const val = i + 5;
                return <option key={val} value={val}>{val}</option>;
              })}
            </select>
          </div>
        )}

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
