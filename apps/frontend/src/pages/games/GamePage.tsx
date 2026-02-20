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

function getMovementRange(
  start: [number, number],
  range: number,
  movementCosts: number[][],
  width: number,
  height: number
): [number, number][] {
  const visited = new Set<string>();
  const result: [number, number][] = [];
  const queue: Array<{ x: number; y: number; cost: number }> = [{ x: start[0], y: start[1], cost: 0 }];

  const directions = [
    [0, 1], [0, -1],
    [1, 0], [-1, 0]
  ];

  while (queue.length > 0) {
    const { x, y, cost } = queue.shift()!;
    const key = `${x},${y}`;
    if (visited.has(key) || x < 0 || y < 0 || x >= width || y >= height) continue;
    visited.add(key);
    result.push([x, y]);

    for (const [dx, dy] of directions) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx >= 0 && ny >= 0 && nx < width && ny < height) {
        const nextCost = cost + movementCosts[ny][nx];
        if (!visited.has(`${nx},${ny}`) && nextCost <= range) {
          queue.push({ x: nx, y: ny, cost: nextCost });
        }
      }
    }
  }

  return result;
}

export default function GamePage() {
  const { gameId } = useParams();
  const [userId, setUserId] = useState<number | null>(null);
  const [remainingTime, setRemainingTime] = useState<number | null>(null);
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
  const [hoveredMove, setHoveredMove] = useState<any | null>(null);
  const [lockedUnit, setLockedUnit] = useState<any | null>(null);
  const [unitOriginalTile, setUnitOriginalTile] = useState<[number, number] | null>(null);
  const [highlightedTiles, setHighlightedTiles] = useState<[number, number][]>([]);
  const [spriteHeight, setSpriteHeight] = useState<number>(48);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const gameLinkRef = useRef<string | undefined>(undefined);
  const myTurnRef = useRef(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);

  const placedUnitsRef = useRef(placedUnits);
  const activeUnit = lockedUnit ?? hoveredUnit;
  const frozenMovesRef = useRef<Record<number, { origin: [number, number]; tiles: [number, number][] }>>({});
  const isPreparationPhase = gameData?.status === "preparation";
  const unitLimit = gameData?.unit_limit ?? 6;
  const isMyTurn = userId != null && gameData?.current_turn === userId;

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

  function isTileOccupied(x: number, y: number, ignoreUnitId?: number) {
    return placedUnitsRef.current.some(u => {
      if (ignoreUnitId && u.id === ignoreUnitId) return false;
      return u.tile[0] === x && u.tile[1] === y;
    });
  }

  function getActiveOrigin(): [number, number] | null {
    const u = lockedUnit ?? hoveredUnit;
    if (!u) return null;
    const unitId = u.instanceId ?? u.id;
    const live = placedUnitsRef.current.find(p => p.id === unitId);
    return (live?.tile as [number, number]) ?? (u.tile as [number, number]) ?? null;
  }

  /* ----- ATTACK RANGE FUNCTIONS ------ */

  const prevTilesRef = useRef<[number, number][]>([]);
  const mapTilesW = gameData?.map?.width ?? 0;
  const mapTilesH = gameData?.map?.height ?? 0;

  const [attackOverlay, setAttackOverlay] = useState<{
    normal: [number, number][];
    invert: [number, number][];
  }>({ normal: [], invert: [] });

  function inBounds(x:number, y:number) {
    const W = gameData?.map?.width ?? 0;
    const H = gameData?.map?.height ?? 0;
    return x >= 0 && y >= 0 && x < W && y < H;
  }

  function rebuildAttackOverlay(move: any) {
    const origin = getActiveOrigin();
    let next = { normal: [] as [number, number][], invert: [] as [number, number][] };

    if (origin && move) {
      const { kind, offset } = parseRangeSpec(move); // you added this earlier
      if (kind === "adjacent") {
        next.normal = getAdjacentTiles(origin);
      } else if (kind === "dash_attack") {
        const { step, attack } = getDashAttackTiles(origin);
        next.invert = step;  // dash step
        next.normal = attack; // attack tiles
      } else if (kind === "blast") {
        next.normal = getBlastTiles(origin, offset || 1);
      }
    }
    setAttackOverlay(next);
  }

  function parseRangeSpec(move: any): { kind: string; offset: number } {
    // Prefer range_type if provided; fall back to range
    const raw = String(move?.range_type ?? move?.range ?? "").toLowerCase().trim();
    // Supports "blast", "blast:1", "dash_attack", "adjacent", etc.
    const m = raw.match(/^([a-z_]+)(?::(\d+))?$/);
    const kind = m?.[1] ?? "";
    const offset = m?.[2] ? parseInt(m[2], 10) : 0; // default 0 unless provided
    return { kind, offset };
  }

  function getAdjacentTiles([x, y]: [number, number]): [number, number][] {
    const cand: [number, number][] = [
      [x, y - 1], // up
      [x, y + 1], // down
      [x - 1, y], // left
      [x + 1, y], // right
    ];
    return cand.filter(([cx, cy]) => cx >= 0 && cy >= 0 && cx < mapTilesW && cy < mapTilesH);
  }

  function getDashAttackTiles([x, y]: [number, number]) {
    const step: [number, number][] = [
      [x, y - 1], // up
      [x, y + 1], // down
      [x - 1, y], // left
      [x + 1, y], // right
    ].filter(([cx, cy]) => inBounds(cx, cy));

    const attack: [number, number][] = [
      [x, y - 2],
      [x, y + 2],
      [x - 2, y],
      [x + 2, y],
    ].filter(([cx, cy]) => inBounds(cx, cy));

    return { step, attack };
  }
  
  function getBlastTiles([x, y]: [number, number], offset: number) {
    // For up/down: 3 wide (x-1..x+1) by 2 rows, starting 'offset' away
    const tiles: [number, number][] = [];

    const pushIfIn = (tx: number, ty: number) => {
      if (inBounds(tx, ty)) tiles.push([tx, ty]);
    };

    // Up (front is negative y)
    const uy1 = y - offset;
    const uy2 = y - (offset + 1);
    for (let dx = -1; dx <= 1; dx++) {
      pushIfIn(x + dx, uy1);
      pushIfIn(x + dx, uy2);
    }

    // Down (positive y)
    const dy1 = y + offset;
    const dy2 = y + (offset + 1);
    for (let dx = -1; dx <= 1; dx++) {
      pushIfIn(x + dx, dy1);
      pushIfIn(x + dx, dy2);
    }

    // Left (negative x)
    const lx1 = x - offset;
    const lx2 = x - (offset + 1);
    for (let dy = -1; dy <= 1; dy++) {
      pushIfIn(lx1, y + dy);
      pushIfIn(lx2, y + dy);
    }

    // Right (positive x)
    const rx1 = x + offset;
    const rx2 = x + (offset + 1);
    for (let dy = -1; dy <= 1; dy++) {
      pushIfIn(rx1, y + dy);
      pushIfIn(rx2, y + dy);
    }

    return tiles;
  }

  function handleMoveHoverStart(move?: any) {
    prevTilesRef.current = highlightedTiles;
    setHighlightedTiles([]);
    setHoveredMove(move || null);
    rebuildAttackOverlay(move);
  }

  function handleMoveHoverEnd() {
    setHoveredMove(null);
    setAttackOverlay({ normal: [], invert: [] });
    setHighlightedTiles(prevTilesRef.current);
    prevTilesRef.current = [];
  }

  function MoveButton({ move, TYPE_COLORS }: { move: any; TYPE_COLORS: Record<string,string> }) {
    return (
      <button
        type="button"
        onMouseEnter={() => handleMoveHoverStart(move)}
        onMouseLeave={handleMoveHoverEnd}
        className="w-full text-left border border-gray-600 p-2 rounded hover:bg-gray-700 focus:outline-none"
      >
        <div className="flex justify-between font-bold">
          <span>{move.name}</span>
          <span
            className="text-xs font-medium px-2 py-0.5 rounded"
            style={{ backgroundColor: TYPE_COLORS[move.type] ?? "#444" }}
          >
            {move.type}
          </span>
        </div>
        <div className="flex justify-between">
          <span>Power: {move.power ?? "—"}</span>
          <span>PP: {move.pp ?? "—"}</span>
        </div>
      </button>
    );
  }

  function fmt(seconds: number): string {
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (hrs > 0) {
      return `${hrs}:${mins.toString().padStart(2, "0")}:${secs
        .toString()
        .padStart(2, "0")}`;
    } else {
      return `${mins}:${secs.toString().padStart(2, "0")}`;
    }
  }

  async function sendMove(unitId: number, x: number, y: number) {
    try {
      await secureFetch(`/api/games/${gameLinkRef.current}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ unit_id: unitId, x, y }),
      });
    } catch {
      setToastMessage("Move failed; resyncing.");
      const r = await secureFetch(`/api/games/${gameData.link}`);
      if (r.ok) setGameData(await r.json());
    }
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
            tile: [u.current_x, u.current_y],
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

  const advanceRequestedRef = useRef(false);

  useEffect(() => {
    if (!gameData?.turn_deadline) return;
    const deadlineMs = new Date(gameData.turn_deadline).getTime();

    const tick = async () => {
      const now = Date.now();
      const secs = Math.max(0, Math.ceil((deadlineMs - now) / 1000));
      setRemainingTime(secs);

      if (secs === 0 && !advanceRequestedRef.current && gameData?.link) {
        advanceRequestedRef.current = true;
        const res = await secureFetch(`/api/games/${gameData.link}`);

        if (res.ok) {
          const updated = await res.json();
          setGameData(updated);
        }
        
        // Small debounce so spam doesn't occur if clock stays at 0 for a sec
        setTimeout(() => { advanceRequestedRef.current = false; }, 1500);
      }
    };

    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [gameData?.turn_deadline, gameData?.link]);

  useEffect(() => {
    advanceRequestedRef.current = false;
  }, [gameData?.current_turn, gameData?.turn_deadline]);

  const lastOriginRef = useRef<string>("");

  useEffect(() => {
    if (!hoveredMove) return;
    let raf = 0;

    const tick = () => {
      const o = getActiveOrigin();
      const key = o ? `${o[0]},${o[1]}` : "";
      if (key !== lastOriginRef.current) {
        lastOriginRef.current = key;
        rebuildAttackOverlay(hoveredMove);
      }
      raf = requestAnimationFrame(tick);
    };

    tick();
    return () => cancelAnimationFrame(raf);
  }, [hoveredMove, lockedUnit, hoveredUnit, placedUnits]);

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
    if (hoveredMove) rebuildAttackOverlay(hoveredMove);
  }, [placedUnits, hoveredMove]);

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
      const clickedOverlay = clickedEl.closest("#overlayCanvas");

      // If the click is NOT on a unit or on the menu, clear both
      if (!clickedUnit && !clickedMenu && !clickedOverlay) {
        setLockedUnit(null);
        setHoveredUnit(null);
      }
    };

    document.addEventListener("click", handleClickOutside);
    return () => {
      document.removeEventListener("click", handleClickOutside);
    };
  }, []);

  useEffect(() => {
    if (gameData?.status !== "in_progress") return;
    const canvas = overlayRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // movement tiles
    highlightedTiles.forEach(([x, y]) => {
      const color = getPlayerColor(lockedUnit?.user_id ?? 0);
      ctx.fillStyle = color;
      ctx.fillRect(x * TILE_DRAW_SIZE, y * TILE_DRAW_SIZE, TILE_DRAW_SIZE, TILE_DRAW_SIZE);
    });

    // attack tiles
    attackOverlay.normal.forEach(([x, y]) => {
      const color = getPlayerColor(lockedUnit?.user_id ?? 0);
      ctx.fillStyle = color;
      ctx.fillRect(x * TILE_DRAW_SIZE, y * TILE_DRAW_SIZE, TILE_DRAW_SIZE, TILE_DRAW_SIZE);
    });

    if (attackOverlay.invert.length) {
      ctx.save();
      ctx.globalCompositeOperation = "difference";
      ctx.fillStyle = "#FFFFFF";
      attackOverlay.invert.forEach(([x, y]) => {
        ctx.fillRect(x * TILE_DRAW_SIZE, y * TILE_DRAW_SIZE, TILE_DRAW_SIZE, TILE_DRAW_SIZE);
      });
      ctx.restore();
    }
  }, [
    highlightedTiles,
    lockedUnit,
    unitOriginalTile,
    isMyTurn,
    userId,
    gameData?.link,
    gameData?.status,
    attackOverlay
  ]);

  useEffect(() => {
    if (gameData?.status !== "in_progress") return;

    const canvas = overlayRef.current;
    if (!canvas) return;

    const handleClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = Math.floor((e.clientX - rect.left) / TILE_DRAW_SIZE);
      const y = Math.floor((e.clientY - rect.top) / TILE_DRAW_SIZE);
      const clickedTile: [number, number] = [x, y];
      
      if (!lockedUnit || !unitOriginalTile || !myTurnRef.current) return;

      // Only allow landing inside the PRECOMPUTED tiles
      const isInRange = highlightedTiles.some(([hx, hy]) => hx === x && hy === y);

      if (!isInRange) {
        setLockedUnit(null);
        setHoveredUnit(null);
        setHighlightedTiles([]);
        setUnitOriginalTile(null);
        return;
      }

      if (lockedUnit.user_id !== userId) {
        setToastMessage("You can only move your own units.");
        return;
      }

      if (isTileOccupied(x, y, lockedUnit.instanceId)) {
        setToastMessage("That tile is occupied.");
        return;
      }
      
      setPlacedUnits(prev =>
        prev.map(u => (u.id === lockedUnit.instanceId ? { ...u, tile: clickedTile } : u))
      );

      lastOriginRef.current = "";

      if (hoveredMove) {
        // wait one frame so placedUnitsRef is updated by the effect
        requestAnimationFrame(() => rebuildAttackOverlay(hoveredMove));
      }

      sendMove(lockedUnit.instanceId, clickedTile[0], clickedTile[1]);
    };

    canvas.addEventListener("click", handleClick);
    return () => canvas.removeEventListener("click", handleClick);
  }, [highlightedTiles, lockedUnit, unitOriginalTile]);

  useEffect(() => {
    setLockedUnit(null);
    setHighlightedTiles([]);
    setUnitOriginalTile(null);
    frozenMovesRef.current = {};
  }, [gameData?.current_turn]);

  useEffect(() => {
    if (!gameData?.link || !gameData?.current_turn) return;
    (async () => {
      const res = await secureFetch(`/api/games/${gameData.link}/turnlock`);
      if (!res.ok) return;
      const locks = await res.json() as Record<string, {origin:[number,number], tiles:[number,number][]}>;
      const next: Record<number, {origin:[number,number], tiles:[number,number][]}> = {};
      for (const [k, v] of Object.entries(locks)) next[Number(k)] = v;
      frozenMovesRef.current = next;
    })();
  }, [gameData?.link, gameData?.current_turn]);

  useEffect(() => {
    if (!gameData?.link) return;
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const hostname = window.location.hostname;
    const ws = new WebSocket(`${protocol}://${hostname}/api/ws/game/${gameData.link}`);

    ws.onopen = () => console.log("[Game WS] Connected");
    ws.onclose = () => console.log("[Game WS] Disconnected");
    ws.onerror = (e) => console.error("[Game WS] Error", e);

    ws.onmessage = (event) => {
      if (typeof event.data === "string" && event.data.startsWith("unit_moved:")) {
        const [, unitIdStr, , xStr, yStr] = event.data.split(":");
        const unitId = Number(unitIdStr);
        const x = Number(xStr);
        const y = Number(yStr);
        setPlacedUnits(prev =>
          prev.map(u => (u.id === unitId ? { ...u, tile: [x, y] as [number, number] } : u))
        );
        return;
      }
      
      if (["player_joined", "game_started", "player_ready", "game_preparation", "turn_started", "turn_advanced"].includes(event.data)) {
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
            tile: [u.current_x, u.current_y],
            current_hp: u.current_hp,
            user_id: u.user_id,
          }));

          setPlacedUnits(mapped);

          try {
            const lockRes = await secureFetch(`/api/games/${updatedGame.link}/turnlock`);
            if (lockRes.ok) {
              const locks = await lockRes.json() as Record<string, {origin:[number,number], tiles:[number,number][]}>;
              const next: Record<number, {origin:[number,number], tiles:[number,number][]}> = {};
              for (const [k, v] of Object.entries(locks)) next[Number(k)] = v;
              frozenMovesRef.current = next;
            }
          } catch {}
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

  useEffect(() => { gameLinkRef.current = gameData?.link; }, [gameData?.link]);
  useEffect(() => { myTurnRef.current = isMyTurn; }, [isMyTurn]);

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
            (() => {
              const current = gameData.players.find(
                (p: any) => p.player_id === gameData.current_turn
              );
              const name = current?.username ?? "Player";
              return (
                <>
                  {name}'s Turn{" "}
                  {typeof remainingTime === "number" && (
                    <span className="text-gray-400">({fmt(remainingTime)})</span>
                  )}
                </>
              );
            })()
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
          <canvas
            ref={overlayRef}
            id="overlayCanvas"
            width={mapWidth}
            height={mapHeight}
            style={{
              position: "absolute",
              top: 0,
              left: 0,
              pointerEvents: lockedUnit && isMyTurn ? "auto" : "none",
            }}
          />

          {placedUnits.map(({ id, unit, tile, current_hp, user_id }) => (
            <div
              key={id}
              data-unit
              onMouseEnter={() => {
                if (gameData.status === "in_progress" && !lockedUnit) {
                  setHoveredUnit({ unit, user_id, current_hp, instanceId: id, tile });
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
                    const isSameInstance = prev?.instanceId === id;
                    if (isSameInstance) {
                      setHighlightedTiles([]);
                      setUnitOriginalTile(null);
                      return null;
                    }

                    const cached = frozenMovesRef.current[id];
                    if (cached) {
                      setHighlightedTiles(cached.tiles);
                      setUnitOriginalTile(cached.origin);
                      return { unit, user_id, current_hp, instanceId: id, tile };
                    }

                    const movement = unit?.base_stats?.range ?? 0;
                    const costMap = gameData.map.tile_data.movement_cost;
                    const width = gameData.map.width;
                    const height = gameData.map.height;

                    const newOrigin: [number, number] = tile;
                    const newTiles = getMovementRange(newOrigin, movement, costMap, width, height);

                    frozenMovesRef.current[id] = { origin: newOrigin, tiles: newTiles };
                    setHighlightedTiles(newTiles);
                    
                    setUnitOriginalTile(newOrigin);
                    return { unit, user_id, current_hp, instanceId: id, tile };
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
                <div><span className="font-semibold">Sp. Def:</span> {unit.base_stats?.sp_defense ?? "?"}</div>
                <div><span className="font-semibold">Attack:</span> {unit.base_stats?.attack ?? "?"}</div>
                <div><span className="font-semibold">Speed:</span> {unit.base_stats?.speed ?? "?"}</div>
                <div><span className="font-semibold">Defense:</span> {unit.base_stats?.defense ?? "?"}</div>
                <div><span className="font-semibold">Range:</span> {unit.base_stats?.range ?? "?"}</div>
                <div><span className="font-semibold">Sp. Atk:</span> {unit.base_stats?.sp_attack ?? "?"}</div>
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
              <button
                className="mt-4 w-full bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
                onClick={async () => {
                  if (!placedUnitAtTile?.id || !gameData?.link) return;

                  const res = await secureFetch(`/api/games/${gameData.link}/units/remove/${placedUnitAtTile.id}`, {
                    method: "DELETE"
                  });

                  if (!res.ok) {
                    setToastMessage("Failed to remove unit.");
                    return;
                  }

                  // Refund the cost and remove the unit from placedUnits
                  setCash(prev => prev + (placedUnitAtTile.unit?.cost ?? 0));
                  setPlacedUnits(prev => prev.filter(u => u.id !== placedUnitAtTile.id));
                  setSelectedTile(null);
                }}
              >
                Remove Unit
              </button>
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
                          tile: [placedUnit.current_x, placedUnit.current_y],
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
          const unit = activeUnit.unit;
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
                <div><span className="font-semibold">Sp. Def:</span> {unit.base_stats?.sp_defense ?? "?"}</div>
                <div><span className="font-semibold">Attack:</span> {unit.base_stats?.attack ?? "?"}</div>
                <div><span className="font-semibold">Speed:</span> {unit.base_stats?.speed ?? "?"}</div>
                <div><span className="font-semibold">Defense:</span> {unit.base_stats?.defense ?? "?"}</div>
                <div><span className="font-semibold">Range:</span> {unit.base_stats?.range ?? "?"}</div>
                <div><span className="font-semibold">Sp. Atk:</span> {unit.base_stats?.sp_attack ?? "?"}</div>
              </div>

              {unit.move_ids?.length > 0 && (
                <div className="mt-3">
                  <h3 className="text-md font-semibold mb-1">Moves:</h3>
                  <ul className="space-y-2 text-sm">
                    {unit.move_ids.map((id: number) => {
                      const move = moveMap[id];
                      if (!move) return null;
                      return (
                        <li key={id}>
                          <MoveButton move={move} TYPE_COLORS={TYPE_COLORS} />
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
