import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";
import UnitPortrait from "@/components/units/UnitPortrait";
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
  const [placedUnits, setPlacedUnits] = useState<{ id?: number; unit: any; tile: [number, number] }[]>([]);
  const [playerColorMap, setPlayerColorMap] = useState<Record<number, string>>({});
  const [moveMap, setMoveMap] = useState<Record<number, any>>({});
  const [cash, setCash] = useState<number>(0);
  const [isReady, setIsReady] = useState<boolean>(false);
  const [hoveredUnit, setHoveredUnit] = useState<any | null>(null);
  const [lockedUnit, setLockedUnit] = useState<any | null>(null);
  const [spriteHeight, setSpriteHeight] = useState<number>(48);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const placedUnitsRef = useRef(placedUnits);
  const activeUnit = lockedUnit ?? hoveredUnit;

  const isPreparationPhase = gameData?.status === "preparation";
  const unitLimit = gameData?.unit_limit ?? 6;

  const mapWidth = gameData?.map?.width ? gameData.map.width * TILE_DRAW_SIZE : 0;
  const mapHeight = gameData?.map?.height ? gameData.map.height * TILE_DRAW_SIZE : 0;

  const PLAYER_COLORS: string[] = [
    "#0000FF80", // Blue
    "#FF000080", // Red
    "#FFFF0080", // Yellow
    "#00FF0080", // Green
    "#88888880", // Gray
    "#80008080", // Purple
    "#FF00FF80", // Magenta
    "#00FFFF80", // Cyan
  ];

  const TYPE_COLORS: { [key: string]: string } = {
    Normal: "#A8A77A",
    Fire: "#EE8130",
    Water: "#6390F0",
    Electric: "#F7D02C",
    Grass: "#7AC74C",
    Ice: "#96D9D6",
    Fighting: "#C22E28",
    Poison: "#A33EA1",
    Ground: "#E2BF65",
    Flying: "#A98FF3",
    Psychic: "#F95587",
    Bug: "#A6B91A",
    Rock: "#B6A136",
    Ghost: "#735797",
    Dragon: "#6F35FC",
    Dark: "#705746",
    Steel: "#B7B7CE",
    Fairy: "#D685AD",
  };

  function getPlayerColor(playerId: number): string {
    return playerColorMap[playerId] ?? "#00000000";
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

  useEffect(() => {
    const fetchGame = async () => {
      try {
        const res = await secureFetch(`/api/games/${gameId}`);
        if (!res.ok) throw new Error("Game not found");
        const data = await res.json();
        setGameData(data);
        setCash(data.starting_cash ?? 0);

        const sorted = [...data.players].sort((a, b) => a.id - b.id);
        const colorMap: Record<number, string> = {};
        sorted.forEach((p, i) => {
          colorMap[p.player_id] = PLAYER_COLORS[i] ?? "#00000000";
        });
        setPlayerColorMap(colorMap);

        const playerRes = await secureFetch(`/api/games/${data.link}/player`);
        if (playerRes.ok) {
          const player = await playerRes.json();
          setCash(player.cash_remaining);
          setIsReady(player.is_ready);
        }

        const unitsRes = await secureFetch(`/api/games/${gameId}/units`);
        if (unitsRes.ok) {
          const backendUnits = await unitsRes.json();

          let playerUnitIds: number[] = [];
          if (data.status === "preparation") {
            const playerRes = await secureFetch(`/api/games/${data.link}/player`);
            if (playerRes.ok) {
              const player = await playerRes.json();
              setCash(player.cash_remaining);
              playerUnitIds = player.game_units ?? [];
            }
          }

          const visibleUnits = data.status === "preparation"
          ? backendUnits.filter((u: any) => playerUnitIds.includes(u.id))
          : backendUnits;


          const mapped = visibleUnits.map((u: any) => ({
            id: u.id,
            unit: {
              id: u.unit_id,
              asset_folder: u.unit.asset_folder,
              name: u.unit.name,
              types: u.unit.types,
              cost: u.unit.cost,
              base_stats: u.unit.base_stats,
              move_ids: u.unit.move_ids,
            },
            tile: [u.x, u.y],
            current_hp: u.current_hp,
            user_id: u.user_id,
          }));

          setPlacedUnits(mapped);
        }

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
          const preferredForm = group.find((u) => u.form_id === 1);
          filteredUnits.push(preferredForm || group[0]);
        }
      }

      filteredUnits.sort((a, b) => a.id - b.id);
      setAvailableUnits(filteredUnits);
    };

    fetchUnits();
  }, [isPreparationPhase]);

  useEffect(() => {
    const fetchMoves = async () => {
      const res = await secureFetch("/api/moves/all");
      if (res.ok) {
        const moves = await res.json();
        const mapped: Record<number, any> = {};
        for (const move of moves) {
          mapped[move.id] = move;
        }
        setMoveMap(mapped);
      }
    };
    fetchMoves();
  }, []);

  useEffect(() => {
    if (isReady) {
      setSelectedTile(null);
    }
  }, [isReady]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const clickedEl = e.target as HTMLElement;
      const clickedUnit = clickedEl.closest("[data-unit]");
      const clickedMenu = clickedEl.closest("[data-unit-info]");

      // If the click is NOT on a unit or on the menu, clear both
      if (!clickedUnit && !clickedMenu) {
        setLockedUnit(null);
        setHoveredUnit(null); // ✅ hide if hovered only
      }
    };

    document.addEventListener("click", handleClickOutside);
    return () => {
      document.removeEventListener("click", handleClickOutside);
    };
  }, []);

  useEffect(() => {
    if (!gameData?.link) return;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const hostname = window.location.hostname;
    const ws = new WebSocket(`${protocol}://${hostname}/api/ws/game/${gameData.link}`);

    ws.onopen = () => console.log("[Game WS] Connected");
    ws.onclose = () => console.log("[Game WS] Disconnected");
    ws.onerror = (e) => console.error("[Game WS] Error", e);

    ws.onmessage = (event) => {
      if (["player_joined", "game_started", "player_ready", "game_preparation"].includes(event.data)) {
        (async () => {
          const res = await secureFetch(`/api/games/${gameData.link}`);
          if (!res.ok) return;
          const updatedGame = await res.json();
          setGameData(updatedGame);

          const unitsRes = await secureFetch(`/api/games/${gameData.link}/units`);
          if (!unitsRes.ok) return;
          const backendUnits = await unitsRes.json();

          let visibleUnits;
          if (updatedGame.status === "preparation") {
            const playerRes = await secureFetch(`/api/games/${updatedGame.link}/player`);
            const player = await playerRes.json();
            const playerUnitIds = player.game_units ?? [];
            visibleUnits = backendUnits.filter((u: any) => playerUnitIds.includes(u.id));
          } else {
            visibleUnits = backendUnits;
          }

          const mapped = visibleUnits.map((u: any) => ({
            id: u.id,
            unit: {
              id: u.unit_id,
              asset_folder: u.unit.asset_folder,
              name: u.unit.name,
              types: u.unit.types,
              cost: u.unit.cost,
              base_stats: u.unit.base_stats,
              move_ids: u.unit.move_ids,
            },
            tile: [u.x, u.y],
            current_hp: u.current_hp,
            user_id: u.user_id,
          }));

          setPlacedUnits(mapped);
        })();
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

  const handleToggleReady = async () => {
    const res = await secureFetch(`/api/games/${gameData.link}/player/ready`, {
      method: "POST",
    });
    if (res.ok) {
      const data = await res.json();
      setIsReady(data.ready);
    } else {
      setToastMessage("Unable to toggle readiness.");
    }
  };

  const handleTileSelect = (tile: [number, number] | null) => {
    const liveUnits = placedUnitsRef.current;
    const liveUnitCount = liveUnits.length;

    if (tile && liveUnitCount >= unitLimit) {
      setSelectedTile(null);
      setToastMessage("You’ve reached the maximum number of units!");
      return;
    }

    if (tile && liveUnits.some((u) => u.tile[0] === tile[0] && u.tile[1] === tile[1])) {
      setToastMessage("This tile is already occupied!");
      return;
    }

    setSelectedTile((prev) => {
      if (prev && tile && prev[0] === tile[0] && prev[1] === tile[1]) {
        return [...tile];
      }
      return tile;
    });
  };

  const isHost = userId === gameData?.host_id;
  const isFull = gameData?.players?.length >= gameData?.max_players;
  const hostPlayer = gameData?.players?.find((p: any) => p.player_id === gameData.host_id);
  const allPlayersReady = gameData?.players?.every((p: any) => p.is_ready === true);

  const placedUnitAtTile = selectedTile
  ? placedUnits.find(
      (u) => u.tile[0] === selectedTile[0] && u.tile[1] === selectedTile[1]
    )
  : null;

  return (
    <div className="p-8 text-white flex flex-row items-start gap-6">
      {toastMessage && (
        <div className="fixed top-4 left-1/2 transform -translate-x-1/2 bg-red-600 text-white px-4 py-2 rounded shadow-lg z-50">
          {toastMessage}
        </div>
      )}

      <div className="flex-1">
        <h1 className="text-3xl font-bold mb-2">
          {gameData?.game_name || "Untitled Game"} <span className="text-sm text-gray-400">({gameData?.gamemode})</span>
        </h1>

        <p className="text-lg font-semibold mb-2 text-yellow-400">
          {gameData?.status === "in_progress" ? (
            "Game in progress..."
          ) : gameData?.status === "preparation" ? (
            allPlayersReady ? (
              isHost
                ? "All players are ready. Start the game when you're ready!"
                : "All players are ready. Waiting for the host to start the game…"
            ) : isReady ? (
              "You're ready! Waiting on other players..."
            ) : (
              "Preparation phase — pick your team!"
            )
          ) : gameData?.status === "closed" && isHost ? (
            "Players have been found!"
          ) : !isFull ? (
            "Waiting for players..."
          ) : (
            "Waiting for host to start the match..."
          )}
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
        {isHost && isPreparationPhase && (
          <button
            className="mt-2 mb-4 bg-green-600 text-white px-4 py-2 rounded disabled:opacity-50"
            disabled={!allPlayersReady}
            onClick={handleStartGame}
          >
            Start Game
          </button>
        )}

        {gameData?.status === "preparation" && (
          <div className="flex items-center justify-start gap-8 mb-2">
            <div className="text-white font-semibold">
              Cash: <span className="text-green-400">${cash}</span>
            </div>
            <div className="flex items-center gap-4 text-white font-semibold">
              Units: <span className={placedUnits.length >= unitLimit ? "text-red-400" : "text-yellow-300"}>
                {placedUnits.length}/{unitLimit}
              </span>
              <button
                onClick={handleToggleReady}
                disabled={placedUnits.length === 0}
                className={`px-3 py-1 text-sm rounded ${
                  placedUnits.length === 0 ? "bg-gray-600 cursor-not-allowed" : "bg-blue-600 hover:bg-blue-700"
                }`}
              >
                Ready
              </button>
            </div>
          </div>
        )}

        <div className="relative" style={{ width: mapWidth, height: mapHeight }}>
          <canvas ref={canvasRef} id="mapCanvas" width={mapWidth} height={mapHeight} />

          {placedUnits.map(({ id, unit, tile, current_hp, user_id }, idx) => (
            <div
              key={idx}
              data-unit
              onMouseEnter={() => {
                if (gameData.status === "in_progress" && !lockedUnit) {
                  setHoveredUnit({ ...unit, user_id, current_hp });
                }
              }}
              onMouseLeave={() => {
                if (gameData.status === "in_progress" && !lockedUnit) {
                  setHoveredUnit(null);
                }
              }}
              onClick={() => {
                if (gameData.status === "preparation") {
                  if (isReady) return;
                  setSelectedTile(tile);
                } else if (gameData.status === "in_progress") {
                  setLockedUnit(prev => {
                    // Clicking again toggles off the lock
                    const isSame = prev?.id === unit.id;
                    return isSame ? null : { ...unit, user_id, current_hp };
                  });
                }
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
              <div style={{ position: "relative", width: "100%", height: "100%", pointerEvents: "none" }}>
                <div
                  style={{
                    position: "absolute",
                    inset: 0,
                    display: "flex",
                    alignItems: "flex-end",
                    justifyContent: "center",
                    pointerEvents: "none",
                  }}
                >
                </div>

                <UnitIdleSprite
                  assetFolder={unit.asset_folder}
                  onFrameSize={([, h]) => setSpriteHeight(h)}
                  isMapPlacement                  
                  overlayColor={getPlayerColor(user_id)}
                />

                <div
                  style={{
                    position: "absolute",
                    bottom: 1,
                    right: 2,
                    fontSize: "10px",
                    color: "white",
                    fontWeight: 600,
                    zIndex: 2,
                    pointerEvents: "none",
                    textShadow: `
                      -1px -1px 0 #000,
                      1px -1px 0 #000,
                      -1px  1px 0 #000,
                      1px  1px 0 #000
                    `,
                  }}
                >
                  {current_hp ?? "?"}
                </div>
              </div>
            </div>
          ))}
        </div>

        {gameData && (
          <>
            <p><strong>Map:</strong> {gameData.map_name}</p>
            <p><strong>Host:</strong> {hostPlayer?.username ?? "Unknown"}</p>
            <p><strong>Players:</strong> {gameData.players.length}/{gameData.max_players}</p>
          </>
        )}

        {gameData?.gamemode === "Conquest" && (
          <ConquestGame
            gameData={gameData}
            userId={userId!}
            onTileSelect={isReady ? () => {} : handleTileSelect}
            selectedTile={selectedTile}
            selectedUnit={null}
            occupiedTile={null}
            isReady={isReady}
          />
        )}
        {gameData?.gamemode === "War" && <WarGame gameData={gameData} userId={userId!} />}
        {gameData?.gamemode === "Capture The Flag" && <CaptureTheFlagGame gameData={gameData} userId={userId!} />}
      </div>

      {(() => {
        // Case 1: Preparation phase + tile has a unit = show Unit Info
        if (isPreparationPhase && selectedTile && placedUnitAtTile !== undefined) {
          const unit = placedUnitAtTile.unit;
          const currentHp = placedUnitAtTile.current_hp;
          const statusEffects = placedUnitAtTile.status_effects ?? [];

          return (
            <div className="w-72 bg-gray-800 text-white p-4 border border-yellow-500 rounded-lg shadow-lg max-h-[32rem] overflow-y-auto">
              <h2 className="text-lg font-bold mb-2">Unit Info</h2>
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <UnitPortrait assetFolder={unit.asset_folder} />
                  <div className="font-semibold text-lg">{unit.name}</div>
                </div>
                <div className="text-sm text-gray-300 font-medium">
                  {currentHp ?? "?"}/{unit.base_stats?.hp ?? "?"}
                </div>
              </div>

              {unit.types?.length > 0 && (
                <div className="text-sm mb-2">
                  {" "}
                  {unit.types.map((type: string, idx: number) => (
                    <span key={idx} className="font-medium" style={{ color: TYPE_COLORS[type] || "#fff" }}>
                      {type}
                      {idx < unit.types.length - 1 && <span className="text-white">/</span>}
                    </span>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-2 gap-y-1 text-sm mb-2">
                <div><span className="font-semibold">HP:</span> {unit.base_stats?.hp ?? "?"}</div>
                <div><span className="font-semibold">Sp. Atk:</span> {unit.base_stats?.sp_attack ?? "?"}</div>
                <div><span className="font-semibold">Attack:</span> {unit.base_stats?.attack ?? "?"}</div>
                <div><span className="font-semibold">Sp. Def:</span> {unit.base_stats?.sp_defense ?? "?"}</div>
                <div><span className="font-semibold">Defense:</span> {unit.base_stats?.defense ?? "?"}</div>
                <div><span className="font-semibold">Speed:</span> {unit.base_stats?.speed ?? "?"}</div>
              </div>

              {unit.move_ids?.length > 0 && (
                <div className="mt-3">
                  <h3 className="text-md font-semibold mb-1">Moves:</h3>
                  <ul className="space-y-2 text-sm">
                    {unit.move_ids.map((id: number) => {
                      const move = moveMap[id];
                      if (!move) return null;
                      return (
                        <li key={id} className="border border-gray-600 p-2 rounded">
                          <div className="flex justify-between font-bold">
                            <span>{move.name}</span>
                            <span className="text-xs font-medium px-2 py-0.5 rounded" style={{ backgroundColor: TYPE_COLORS[move.type] ?? "#444" }}>
                              {move.type}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span>Power: {move.power ?? "—"}</span>
                            <span>PP: {move.pp ?? "—"}</span>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          );
        }

        // Case 2: Preparation phase + empty tile = Select Unit Menu
        if (isPreparationPhase && selectedTile && placedUnitAtTile === undefined && placedUnits.length < unitLimit) {
          return (
            <div className="w-72 bg-gray-800 text-white p-4 border border-yellow-500 rounded-lg shadow-lg max-h-[32rem] overflow-y-auto">
              <h2 className="text-lg font-bold mb-2">Select a Unit</h2>
              <ul className="space-y-2 text-sm">
                {availableUnits.map((unit) => (
                  <li
                    key={unit.id}
                    className="flex items-center justify-between px-2 py-1 hover:bg-gray-700 rounded cursor-pointer"
                    onClick={async () => {
                      if (!selectedTile) return;
                      if (unit.cost > cash) {
                        setToastMessage("You don't have enough cash to buy this unit!");
                        return;
                      }

                      const payload = {
                        unit_id: unit.id,
                        x: selectedTile[0],
                        y: selectedTile[1],
                        current_hp: unit.base_stats.hp || 100,
                        stat_boosts: {},
                        status_effects: [],
                        is_fainted: false,
                      };

                      const res = await secureFetch(`/api/games/${gameData.link}/units/place`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload),
                      });

                      if (!res.ok) {
                        setToastMessage("Failed to place unit.");
                        return;
                      }

                      const placedUnit = await res.json();
                      setPlacedUnits((prev) => [
                        ...prev,
                        {
                          id: placedUnit.id,
                          unit: placedUnit.unit,
                          tile: [placedUnit.x, placedUnit.y],
                          current_hp: placedUnit.current_hp,
                          user_id: placedUnit.user_id,
                        }
                      ]);
                      setCash((prev) => prev - unit.cost);
                      setSelectedTile(null);
                    }}
                  >
                    <div className="flex items-center gap-2">
                      <UnitPortrait assetFolder={unit.asset_folder} />
                      <div className="leading-tight">
                        <div className="font-semibold">{unit.name}</div>
                        {unit.types?.length > 0 && (
                          <div className="text-sm text-gray-300">
                            (
                            {unit.types.map((type: string, idx: number) => (
                              <span key={idx}>
                                <span className="font-medium" style={{ color: TYPE_COLORS[type] || "#fff" }}>
                                  {type}
                                </span>
                                {idx < unit.types.length - 1 && <span className="text-white">/</span>}
                              </span>
                            ))}
                            )
                          </div>
                        )}
                      </div>
                    </div>
                    <span>${unit.cost}</span>
                  </li>
                ))}
              </ul>
            </div>
          );
        }

        // Case 3: In Progress = Unit Info (via click)
        if (gameData?.status === "in_progress" && activeUnit) {
          const unit = activeUnit;
          const currentHp = activeUnit.current_hp;
          const statusEffects = activeUnit.status_effects ?? [];

          return (
            <div
              data-unit-info
              className="w-72 bg-gray-800 text-white p-4 rounded-lg shadow-lg max-h-[32rem] overflow-y-auto"
              style={{ border: `2px solid ${getPlayerColor(activeUnit.user_id)}` }}
            >
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <UnitPortrait assetFolder={unit.asset_folder} />
                  <div className="font-semibold text-lg">{unit.name}</div>
                </div>
                <div className="text-sm text-gray-300 font-medium">
                  {currentHp ?? "?"}/{unit.base_stats?.hp ?? "?"}
                </div>
              </div>

              {unit.types?.length > 0 && (
                <div className="text-sm mb-2">
                  {" "}
                  {unit.types.map((type: string, idx: number) => (
                    <span key={idx} className="font-medium" style={{ color: TYPE_COLORS[type] || "#fff" }}>
                      {type}
                      {idx < unit.types.length - 1 && <span className="text-white">/</span>}
                    </span>
                  ))}
                </div>
              )}

              <div className="grid grid-cols-2 gap-y-1 text-sm mb-2">
                <div><span className="font-semibold">HP:</span> {unit.base_stats?.hp ?? "?"}</div>
                <div><span className="font-semibold">Sp. Atk:</span> {unit.base_stats?.sp_attack ?? "?"}</div>
                <div><span className="font-semibold">Attack:</span> {unit.base_stats?.attack ?? "?"}</div>
                <div><span className="font-semibold">Sp. Def:</span> {unit.base_stats?.sp_defense ?? "?"}</div>
                <div><span className="font-semibold">Defense:</span> {unit.base_stats?.defense ?? "?"}</div>
                <div><span className="font-semibold">Speed:</span> {unit.base_stats?.speed ?? "?"}</div>
              </div>

              {unit.move_ids?.length > 0 && (
                <div className="mt-3">
                  <h3 className="text-md font-semibold mb-1">Moves:</h3>
                  <ul className="space-y-2 text-sm">
                    {unit.move_ids.map((id: number) => {
                      const move = moveMap[id];
                      if (!move) return null;
                      return (
                        <li key={id} className="border border-gray-600 p-2 rounded">
                          <div className="flex justify-between font-bold">
                            <span>{move.name}</span>
                            <span className="text-xs font-medium px-2 py-0.5 rounded" style={{ backgroundColor: TYPE_COLORS[move.type] ?? "#444" }}>
                              {move.type}
                            </span>
                          </div>
                          <div className="flex justify-between">
                            <span>Power: {move.power ?? "—"}</span>
                            <span>PP: {move.pp ?? "—"}</span>
                          </div>
                        </li>
                      );
                    })}
                  </ul>
                </div>
              )}
            </div>
          );
        }

        return null;
      })()}

    </div>
  );
}
