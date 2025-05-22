import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";
import UnitIdleSprite from "@/components/units/UnitIdleSprite";
import ConquestGame from "./modes/ConquestGame";
import WarGame from "./modes/WarGame";
import CaptureTheFlagGame from "./modes/CaptureTheFlagGame";

export default function GamePage() {
  const { gameId } = useParams();
  const [userId, setUserId] = useState<number | null>(null);
  const [gameData, setGameData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedTile, setSelectedTile] = useState<[number, number] | null>(null);
  const [availableUnits, setAvailableUnits] = useState<any[]>([]);

  const isPreparationPhase = gameData?.status === "preparation";

  const typeColors: { [key: string]: string } = {
    Normal: "#a6a77c",
    Fire: "#d68543",
    Water: "#7890e5",
    Electric: "#e9cf54",
    Grass: "#8fc361",
    Ice: "#abd5d4",
    Fighting: "#a73c30",
    Poison: "#90479a",
    Ground: "#d4bf74",
    Flying: "#a492e5",
    Psychic: "#d96387",
    Bug: "#a9b543",
    Rock: "#b0a04b",
    Ghost: "#6c5a92",
    Dragon: "#6c41ea",
    Dark: "#695949",
    Steel: "#b7b7cb",
    Fairy: "#d99daa",
  };

  // Fetch game data
  useEffect(() => {
    const fetchGame = async () => {
      try {
        const res = await secureFetch(`/api/games/${gameId}`);
        if (!res.ok) throw new Error("Game not found");
        const data = await res.json();
        setGameData(data);
      } catch (err: any) {
        setError(err.message);
      }
    };
    fetchGame();
  }, [gameId]);

  // Fetch user
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

  // Fetch units during preparation
  useEffect(() => {
    if (!isPreparationPhase) return;

    const fetchUnits = async () => {
      const res = await secureFetch("/api/units/summary");
      if (!res.ok) return;

      const units = await res.json();

      const EXCEPTION_SPECIES = new Set([17, 42, 78, 103]); // Lycanroc, Marowak, Raichu, Sneasel

      // Group by species_id
      const speciesGroups: { [speciesId: number]: any[] } = {};
      for (const unit of units) {
        if (!speciesGroups[unit.species_id]) {
          speciesGroups[unit.species_id] = [];
        }
        speciesGroups[unit.species_id].push(unit);
      }

      // Filter logic
      const filteredUnits: any[] = [];
      for (const [speciesIdStr, group] of Object.entries(speciesGroups)) {
        const speciesId = parseInt(speciesIdStr);
        if (group.length === 1) {
          filteredUnits.push(group[0]);
        } else if (EXCEPTION_SPECIES.has(speciesId)) {
          filteredUnits.push(...group);
        } else {
          // Non-exception with multiple forms: only first unit is kept
          const preferredForm = group.find(u => u.form_id === 1);
          filteredUnits.push(preferredForm || group[0]);
        }
      }

      filteredUnits.sort((a, b) => a.id - b.id);
      setAvailableUnits(filteredUnits);
    };

    fetchUnits();
  }, [isPreparationPhase]);

  // WebSocket
  useEffect(() => {
    if (!gameData?.link) return;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const hostname = window.location.hostname;
    const ws = new WebSocket(`${protocol}://${hostname}/api/ws/game/${gameData.link}`);

    ws.onopen = () => console.log("[Game WS] Connected");
    ws.onclose = () => console.log("[Game WS] Disconnected");
    ws.onerror = (e) => console.error("[Game WS] Error", e);

    ws.onmessage = (event) => {
      if (["player_joined", "game_started"].includes(event.data)) {
        secureFetch(`/api/games/${gameData.link}`).then(async (res) => {
          if (res.ok) setGameData(await res.json());
        });
      }
    };

    return () => ws.close();
  }, [gameData?.link]);

  const mapWidth = gameData?.map?.width * 32;
  const mapHeight = gameData?.map?.height * 32;

  const isHost = userId === gameData?.host?.id;
  const isFull = gameData?.players?.length >= gameData?.max_players;

  let statusMessage = "";
  if (!gameData) {
    statusMessage = "";
  } else if (gameData.status === "in_progress") {
    statusMessage = "Game in progress...";
  } else if (gameData.status === "preparation") {
    statusMessage = "Preparation phase — pick your team!";
  } else if (!isFull) {
    statusMessage = "Waiting for players...";
  } else if (isHost) {
    statusMessage = "Players have been found!";
  } else {
    statusMessage = "Waiting for host to start the match...";
  }

  const handleStartGame = async () => {
    const res = await secureFetch(`/api/games/start/${gameData.id}`, { method: "POST" });
    if (res.ok) {
      const updated = await secureFetch(`/api/games/${gameData.link}`);
      setGameData(await updated.json());
    } else {
      alert("Unable to start game.");
    }
  };

  if (error) return <div className="p-8 text-red-500">Error: {error}</div>;
  if (!gameData || userId === null) return <div className="p-8 text-white">Loading game...</div>;

  return (
    <div className="p-8 text-white flex flex-row items-start gap-6">
      {/* LEFT SIDE */}
      <div className="flex-1">
        <h1 className="text-3xl font-bold mb-2">
          {gameData.game_name || "Untitled Game"}{" "}
          <span className="text-sm text-gray-400">({gameData.gamemode})</span>
        </h1>

        <p className="text-lg font-semibold mb-2 text-yellow-400">{statusMessage}</p>

        {isHost && gameData.status !== "in_progress" && gameData.status !== "preparation" && (
          <button
            className="mt-2 mb-4 bg-green-600 text-white px-4 py-2 rounded disabled:opacity-50"
            disabled={!isFull}
            onClick={handleStartGame}
          >
            Start Game
          </button>
        )}

        <canvas id="mapCanvas" width={mapWidth} height={mapHeight} className="mb-4" />

        <p><strong>Map:</strong> {gameData.map_name}</p>
        <p><strong>Host:</strong> {gameData.host.username}</p>
        <p><strong>Players:</strong> {gameData.players.length}/{gameData.max_players}</p>

        {/* Gamemode logic components */}
        {gameData.gamemode === "Conquest" && (
          <ConquestGame gameData={gameData} userId={userId} onTileSelect={setSelectedTile} />
        )}
        {gameData.gamemode === "War" && <WarGame gameData={gameData} userId={userId} />}
        {gameData.gamemode === "Capture The Flag" && <CaptureTheFlagGame gameData={gameData} userId={userId} />}
      </div>

      {/* RIGHT SIDE: Unit Panel */}
      {isPreparationPhase && selectedTile && (
        <div className="w-72 bg-gray-800 text-white p-4 border border-yellow-500 rounded-lg shadow-lg">
          <h2 className="text-lg font-bold mb-2">Select a Unit</h2>
          <ul className="max-h-64 overflow-y-auto space-y-1">
            {availableUnits.map(unit => (
              <li key={unit.id} className="flex items-center justify-between px-2 py-1 hover:bg-gray-700 rounded cursor-pointer">
                <div className="flex items-center gap-2">
                  <UnitIdleSprite assetFolder={unit.asset_folder} />
                  <div>
                    <span>{unit.name}</span>{" "}
                    {unit.types && unit.types.length > 0 && (
                      <span>(
                        {unit.types.map((type: string, idx: number) => (
                          <span key={idx}>
                            <span style={{ color: typeColors[type] || "#fff", fontWeight: 500 }}>{type}</span>
                            {idx < unit.types.length - 1 && <span style={{ color: "#fff" }}>/</span>}
                          </span>
                        ))}
                      )</span>
                    )}
                  </div>
                </div>
                <span>${unit.cost}</span>
              </li>

            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
