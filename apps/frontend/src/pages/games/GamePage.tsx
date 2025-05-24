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
  const [availableUnits, setAvailableUnits] = useState<any[]>([]);
  const [placedUnits, setPlacedUnits] = useState<{ unit: any; tile: [number, number] }[]>([]);
  const [cash, setCash] = useState<number>(0);
  const [spriteHeight, setSpriteHeight] = useState<number>(48);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const placedUnitsRef = useRef(placedUnits);

  const isPreparationPhase = gameData?.status === "preparation";
  const unitLimit = gameData?.unit_limit ?? 6;

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
        setCash(data.starting_cash ?? 0);
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

  useEffect(() => {
    placedUnitsRef.current = placedUnits;
  }, [placedUnits]);

  useEffect(() => {
    if (toastMessage) {
      const timeout = setTimeout(() => setToastMessage(null), 3000);
      return () => clearTimeout(timeout);
    }
  }, [toastMessage]);

  const handleTileSelect = (tile: [number, number] | null) => {
    const liveUnits = placedUnitsRef.current;
    const liveUnitCount = liveUnits.length;

    if (tile && liveUnitCount >= unitLimit) {
      setSelectedTile(null);
      setToastMessage("You’ve reached the maximum number of units!");
      return;
    }

    if (tile && liveUnits.some(u => u.tile[0] === tile[0] && u.tile[1] === tile[1])) {
      setToastMessage("This tile is already occupied!");
      return;
    }

    setSelectedTile(prev => {
      if (prev && tile && prev[0] === tile[0] && prev[1] === tile[1]) {
        return [...tile];
      }
      return tile;
    });
  };

  const isHost = userId === gameData?.host?.id;
  const isFull = gameData?.players?.length >= gameData?.max_players;

  return (
    <div className="p-8 text-white flex flex-row items-start gap-6">
      {toastMessage && (
        <div className="fixed top-4 left-1/2 transform -translate-x-1/2 bg-red-600 text-white px-4 py-2 rounded shadow-lg z-50">
          {toastMessage}
        </div>
      )}

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

        <div className="flex items-center justify-start gap-8 mb-2">
          <div className="text-white font-semibold">
            Cash: <span className="text-green-400">${cash}</span>
          </div>
          <div className="text-white font-semibold">
            Units:{" "}
            <span className={placedUnits.length >= unitLimit ? "text-red-400" : "text-yellow-300"}>
              {placedUnits.length}/{unitLimit}
            </span>
          </div>
        </div>

        <div className="relative" style={{ width: mapWidth, height: mapHeight }}>
          <canvas ref={canvasRef} id="mapCanvas" width={mapWidth} height={mapHeight} />

          {placedUnits.map(({ unit, tile }, idx) => (
            <div
              key={idx}
              onClick={() => {
                const unitToRemove = placedUnits[idx];
                setPlacedUnits(prev =>
                  prev.filter((u, i) => i !== idx)
                );
                setCash(prev => prev + unitToRemove.unit.cost);
                setSelectedTile(null);
              }}
              style={{
                position: "absolute",
                left: tile[0] * TILE_DRAW_SIZE,
                top: tile[1] * TILE_DRAW_SIZE,
                width: TILE_DRAW_SIZE,
                height: TILE_DRAW_SIZE,
                pointerEvents: "auto",
                cursor: "pointer",
              }}
            >
              <UnitIdleSprite
                assetFolder={unit.asset_folder}
                onFrameSize={([, h]) => setSpriteHeight(h)}
                isMapPlacement
              />
            </div>
          ))}
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
            onTileSelect={handleTileSelect}
            selectedTile={selectedTile}
            selectedUnit={null}
            occupiedTile={null}
          />
        )}
        {gameData?.gamemode === "War" && <WarGame gameData={gameData} userId={userId} />}
        {gameData?.gamemode === "Capture The Flag" && (
          <CaptureTheFlagGame gameData={gameData} userId={userId} />
        )}
      </div>

      {isPreparationPhase && selectedTile && placedUnits.length < unitLimit && (
        <div className="w-72 bg-gray-800 text-white p-4 border border-yellow-500 rounded-lg shadow-lg">
          <h2 className="text-lg font-bold mb-2">Select a Unit</h2>
          <ul className="max-h-64 overflow-y-auto space-y-1">
            {availableUnits.map(unit => (
              <li
                key={unit.id}
                className="flex items-center justify-between px-2 py-1 hover:bg-gray-700 rounded cursor-pointer"
                onClick={() => {
                  if (!selectedTile) return;

                  if (unit.cost > cash) {
                    setToastMessage("You don't have enough cash to buy this unit!");
                    return;
                  }

                  const tileToPlace = selectedTile;
                  setPlacedUnits(prev => [...prev, { unit, tile: tileToPlace }]);
                  setCash(prev => prev - unit.cost);
                  setSelectedTile(null);
                }}
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
