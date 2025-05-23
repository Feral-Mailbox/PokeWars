import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";
import UnitIdleSprite from "@/components/units/UnitIdleSprite";
import ConquestGame from "./modes/ConquestGame";
import WarGame from "./modes/WarGame";
import CaptureTheFlagGame from "./modes/CaptureTheFlagGame";

const TILE_SIZE = 16;
const TILE_SCALE = 2;
const TILE_DRAW_SIZE = TILE_SIZE * TILE_SCALE;

export default function GamePage() {
  const { gameId } = useParams();
  const [userId, setUserId] = useState<number | null>(null);
  const [gameData, setGameData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedTile, setSelectedTile] = useState<[number, number] | null>(null);
  const [occupiedTile, setOccupiedTile] = useState<[number, number] | null>(null);
  const [availableUnits, setAvailableUnits] = useState<any[]>([]);
  const [selectedUnit, setSelectedUnit] = useState<any | null>(null);
  const [spriteHeight, setSpriteHeight] = useState<number>(48);

  const canvasRef = useRef<HTMLCanvasElement>(null);

  const isPreparationPhase = gameData?.status === "preparation";

  useEffect(() => {
    if (selectedTile && selectedUnit) {
      setOccupiedTile(selectedTile);
    }
  }, [selectedTile, selectedUnit]);

  const mapWidth = gameData?.map?.width ? gameData.map.width * TILE_DRAW_SIZE : 0;
  const mapHeight = gameData?.map?.height ? gameData.map.height * TILE_DRAW_SIZE : 0;

  const handleStartGame = async () => {
    const res = await secureFetch(`/api/games/start/${gameData.id}`, { method: "POST" });
    if (res.ok) {
      const updated = await secureFetch(`/api/games/${gameData.link}`);
      setGameData(await updated.json());
    } else {
      alert("Unable to start game.");
    }
  };

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

  useEffect(() => {
    if (!isPreparationPhase) return;

    const fetchUnits = async () => {
      const res = await secureFetch("/api/units/summary");
      if (!res.ok) return;
      const units = await res.json();

      const EXCEPTION_SPECIES = new Set([17, 42, 78, 103]);
      const speciesGroups: { [speciesId: number]: any[] } = {};
      for (const unit of units) {
        if (!speciesGroups[unit.species_id]) {
          speciesGroups[unit.species_id] = [];
        }
        speciesGroups[unit.species_id].push(unit);
      }

      const filteredUnits: any[] = [];
      for (const [speciesIdStr, group] of Object.entries(speciesGroups)) {
        const speciesId = parseInt(speciesIdStr);
        if (group.length === 1) {
          filteredUnits.push(group[0]);
        } else if (EXCEPTION_SPECIES.has(speciesId)) {
          filteredUnits.push(...group);
        } else {
          const preferredForm = group.find(u => u.form_id === 1);
          filteredUnits.push(preferredForm || group[0]);
        }
      }

      filteredUnits.sort((a, b) => a.id - b.id);
      setAvailableUnits(filteredUnits);
    };

    fetchUnits();
  }, [isPreparationPhase]);

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

  const isHost = userId === gameData?.host?.id;
  const isFull = gameData?.players?.length >= gameData?.max_players;

  return (
    <div className="p-8 text-white flex flex-row items-start gap-6">
      {/* LEFT SIDE */}
      <div className="flex-1">
        <h1 className="text-3xl font-bold mb-2">
          {gameData?.game_name || "Untitled Game"}{" "}
          <span className="text-sm text-gray-400">({gameData?.gamemode})</span>
        </h1>

        <p className="text-lg font-semibold mb-2 text-yellow-400">
          {gameData?.status === "in_progress"
            ? "Game in progress..."
            : gameData?.status === "preparation"
            ? "Preparation phase — pick your team!"
            : isHost
            ? "Players have been found!"
            : !isFull
            ? "Waiting for players..."
            : "Waiting for host to start the match..."}
        </p>

        {isHost && gameData?.status !== "in_progress" && gameData?.status !== "preparation" && (
          <button
            className="mt-2 mb-4 bg-green-600 text-white px-4 py-2 rounded disabled:opacity-50"
            disabled={!isFull}
            onClick={handleStartGame}
          >
            Start Game
          </button>
        )}

        {/* Canvas and sprite overlay container */}
        <div className="relative" style={{ width: mapWidth, height: mapHeight }}>
          <canvas ref={canvasRef} id="mapCanvas" width={mapWidth} height={mapHeight} />

          {isPreparationPhase && selectedTile && selectedUnit && (
            <div
              style={{
                position: "absolute",
                left: selectedTile[0] * TILE_DRAW_SIZE,
                top: selectedTile[1] * TILE_DRAW_SIZE,
                width: TILE_DRAW_SIZE,
                height: TILE_DRAW_SIZE,
                pointerEvents: "none",
              }}
            >
              <UnitIdleSprite
                assetFolder={selectedUnit.asset_folder}
                onFrameSize={([, h]) => setSpriteHeight(h)}
                isMapPlacement
              />
            </div>
          )}
        </div>

        {gameData && (
          <>
            <p><strong>Map:</strong> {gameData.map_name}</p>
            <p><strong>Host:</strong> {gameData.host.username}</p>
            <p><strong>Players:</strong> {gameData.players.length}/{gameData.max_players}</p>
          </>
        )}

        {gameData?.gamemode === "Conquest" && (
          <ConquestGame
            gameData={gameData}
            userId={userId}
            onTileSelect={setSelectedTile}
            selectedTile={selectedTile}
            selectedUnit={selectedUnit}
            occupiedTile={occupiedTile}
          />
        )}
        {gameData?.gamemode === "War" && <WarGame gameData={gameData} userId={userId} />}
        {gameData?.gamemode === "Capture The Flag" && (
          <CaptureTheFlagGame gameData={gameData} userId={userId} />
        )}
      </div>

      {/* RIGHT SIDE: Unit Panel */}
      {isPreparationPhase && selectedTile && (
        <div className="w-72 bg-gray-800 text-white p-4 border border-yellow-500 rounded-lg shadow-lg">
          <h2 className="text-lg font-bold mb-2">Select a Unit</h2>
          <ul className="max-h-64 overflow-y-auto space-y-1">
            {availableUnits.map(unit => (
              <li
                key={unit.id}
                className="flex items-center justify-between px-2 py-1 hover:bg-gray-700 rounded cursor-pointer"
                onClick={() => setSelectedUnit(unit)}
              >
                <div className="flex items-center gap-2">
                  <UnitIdleSprite assetFolder={unit.asset_folder} />
                  <div>
                    <span>{unit.name}</span>{" "}
                    {unit.types?.length > 0 && (
                      <span>(
                        {unit.types.map((type: string, idx: number) => (
                          <span key={idx}>
                            <span style={{ color: "#fff", fontWeight: 500 }}>{type}</span>
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
