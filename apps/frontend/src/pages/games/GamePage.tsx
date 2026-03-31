import { useEffect, useMemo, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";
import GameMapStage from "./components/GameMapStage";
import InProgressUnitMenu from "./components/unit-menus/InProgressUnitMenu";
import PreparationPlacedUnitMenu from "./components/unit-menus/PreparationPlacedUnitMenu";
import PreparationUnitSelectMenu from "./components/unit-menus/PreparationUnitSelectMenu";
import ConquestGame from "./modes/ConquestGame";
import WarGame from "./modes/WarGame";
import CaptureTheFlagGame from "./modes/CaptureTheFlagGame";
import ChatPanel from "./components/ChatPanel";

const TILE_SIZE = 16;
const TILE_SCALE = 2;
const TILE_DRAW_SIZE = TILE_SIZE * TILE_SCALE;

function getMovementRange(
  start: [number, number],
  range: number,
  movementCosts: number[][],
  width: number,
  height: number,
  blockedTiles?: Set<string>
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
        const nextKey = `${nx},${ny}`;
        // Don't pathfind through tiles blocked by enemy units
        if (blockedTiles?.has(nextKey)) continue;
        
        const nextCost = cost + movementCosts[ny][nx];
        if (!visited.has(nextKey) && nextCost <= range) {
          queue.push({ x: nx, y: ny, cost: nextCost });
        }
      }
    }
  }

  return result;
}

function getBlockedTilesByEnemy(placedUnits: any[], unitUserId: number): Set<string> {
  const blocked = new Set<string>();
  for (const u of placedUnits) {
    // Only enemy units block pathfinding; allied units do not
    if (u.user_id !== unitUserId) {
      blocked.add(`${u.tile[0]},${u.tile[1]}`);
    }
  }
  return blocked;
}

export type ChatEntry = {
  id: string;
  kind: "chat" | "system";
  text: string;
  username?: string;
  playerId?: number;
};

export default function GamePage() {

  const { gameId } = useParams();
  const [userId, setUserId] = useState<number | null>(null);
  const [remainingTime, setRemainingTime] = useState<number | null>(null);
  const [gameData, setGameData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedTile, setSelectedTile] = useState<[number, number] | null>(null);
  const [availableUnits, setAvailableUnits] = useState<any[]>([]);
  const [placedUnits, setPlacedUnits] = useState<{ id?: number; unit: any; tile: [number, number]; current_hp: number; user_id: number; status_effects?: any[]; level?: number; current_stats?: any; stat_boosts?: any; can_move?: boolean; move_pp?: number[] }[]>([]);
  const [playerColorMap, setPlayerColorMap] = useState<Record<number, string>>({});
  const [moveMap, setMoveMap] = useState<Record<number, any>>({});
  const [cash, setCash] = useState<number>(0);
  const [isReady, setIsReady] = useState<boolean>(false);
  const [hoveredUnit, setHoveredUnit] = useState<any | null>(null);
  const [hoveredMove, setHoveredMove] = useState<any | null>(null);
  const [selectedMove, setSelectedMove] = useState<any | null>(null);
  const [moveTargeting, setMoveTargeting] = useState(false);
  const [hoveredOverlayTile, setHoveredOverlayTile] = useState<[number, number] | null>(null);
  const [selectedMoveTarget, setSelectedMoveTarget] = useState<[number, number] | null>(null);
  const [lockedUnit, setLockedUnit] = useState<any | null>(null);
  const [unitOriginalTile, setUnitOriginalTile] = useState<[number, number] | null>(null);
  const [highlightedTiles, setHighlightedTiles] = useState<[number, number][]>([]);
  const [unitSearchQuery, setUnitSearchQuery] = useState<string>("");
  const [unitTypeFilterPrimary, setUnitTypeFilterPrimary] = useState<string>("");
  const [unitTypeFilterSecondary, setUnitTypeFilterSecondary] = useState<string>("");
  const [unitSortBy, setUnitSortBy] = useState<"id" | "name" | "cost">("id");
  const [unitSortDirection, setUnitSortDirection] = useState<"asc" | "desc">("asc");
  const [spriteHeight, setSpriteHeight] = useState<number>(48);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [weatherIconRefresh, setWeatherIconRefresh] = useState<number>(0);
  const [hazardIconRefresh, setHazardIconRefresh] = useState<number>(0);
  const [menuScreenPosition, setMenuScreenPosition] = useState<{ left: number; top: number }>({ left: 24, top: 96 });
  const [chatEntries, setChatEntries] = useState<ChatEntry[]>([]);
  const [chatInput, setChatInput] = useState<string>("");
  const gameLinkRef = useRef<string | undefined>(undefined);
  const myTurnRef = useRef(false);

  const canvasRef = useRef<HTMLCanvasElement>(null);
  const overlayRef = useRef<HTMLCanvasElement>(null);
  const mapStageRef = useRef<HTMLDivElement>(null);
  const gameHeaderRef = useRef<HTMLHeadingElement>(null);
  const weatherIconCacheRef = useRef<Record<number, HTMLImageElement>>({});
  const weatherIconLoadFailedRef = useRef<Record<number, boolean>>({});
  const hazardIconRef = useRef<HTMLImageElement | null>(null);
  const hazardIconLoadFailedRef = useRef<boolean>(false);

  const placedUnitsRef = useRef(placedUnits);
  const activeUnit = lockedUnit ?? hoveredUnit;
  const frozenMovesRef = useRef<Record<number, { origin: [number, number]; tiles: [number, number][] }>>({});
  const preMoveStateRef = useRef<{
    lockedUnit: any | null;
    hoveredUnit: any | null;
    highlightedTiles: [number, number][];
    unitOriginalTile: [number, number] | null;
  } | null>(null);
  const isPreparationPhase = gameData?.status === "preparation";
  const unitLimit = gameData?.unit_limit ?? 6;
  const isUnitSelectMenuVisible =
    isPreparationPhase &&
    selectedTile &&
    !placedUnits.some(
      (u) => u.tile[0] === selectedTile[0] && u.tile[1] === selectedTile[1]
    ) &&
    placedUnits.length < unitLimit;
  
  // Derive current player from turn counter
  const currentPlayerId = 
    gameData?.player_order && gameData.current_turn !== null && gameData.current_turn !== undefined
      ? gameData.player_order[gameData.current_turn % gameData.player_order.length]
      : null;
  const isMyTurn = userId != null && currentPlayerId === userId;

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

  const unitTypeOptions = useMemo(() => {
    const seen = new Set<string>();
    for (const unit of availableUnits) {
      const types = Array.isArray(unit?.types) ? unit.types : [];
      for (const t of types) {
        if (typeof t === "string" && t.trim().length > 0) {
          seen.add(t);
        }
      }
    }
    return Array.from(seen).sort((a, b) => a.localeCompare(b));
  }, [availableUnits]);

  function getBaseBattleStatValue(unitState: any, statName: string): number | null {
    const baseStats = unitState?.unit?.base_stats;
    if (!baseStats || typeof baseStats !== 'object') return null;

    const level = typeof unitState?.level === 'number' ? unitState.level : 50;
    if (statName === 'range') {
      const baseSpeed = baseStats?.speed;
      if (typeof baseSpeed !== 'number') return null;
      const baseBattleSpeed = Math.floor((2 * baseSpeed * level) / 100 + 5);
      return Math.max(0, Math.floor(2 + (baseBattleSpeed / 50)));
    }

    const baseValue = baseStats?.[statName];
    if (typeof baseValue !== 'number') return null;

    if (statName === 'hp') {
      return Math.floor((2 * baseValue * level) / 100) + level + 10;
    }
    return Math.floor((2 * baseValue * level) / 100 + 5);
  }

  function getCurrentMovementRange(unitState: any): number {
    const explicitRange = unitState?.current_stats?.range;
    if (typeof explicitRange === 'number') return Math.max(0, Math.floor(explicitRange));

    const currentSpeed = unitState?.current_stats?.speed;
    if (typeof currentSpeed === 'number') return Math.max(0, Math.floor(2 + (currentSpeed / 50)));

    const baseRange = getBaseBattleStatValue(unitState, 'range');
    if (typeof baseRange === 'number') return Math.max(0, Math.floor(baseRange));

    return 0;
  }

  function getStatColor(unitState: any, statName: string): string {
    const currentValue = unitState?.current_stats?.[statName];
    if (typeof currentValue !== 'number') return '#ffffff';

    const baseValue = getBaseBattleStatValue(unitState, statName);
    if (typeof baseValue !== 'number') return '#ffffff';

    if (currentValue > baseValue) return '#22c55e';
    if (currentValue < baseValue) return '#ef4444';
    return '#ffffff';
  }

  function getPlayerColor(playerId: number): string {
    return playerColorMap[playerId] ?? "#00000000";
  }



  function addSystemChat(text: string) {
    setChatEntries((prev) => [
      ...prev,
      {
        id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        kind: "system",
        text,
      },
    ]);
  }

  function mapReplayLogToChatEntries(replayLog: any): ChatEntry[] {
    if (!Array.isArray(replayLog)) return [];

    const out: ChatEntry[] = [];
    for (let i = 0; i < replayLog.length; i++) {
      const row = replayLog[i];
      if (!row || typeof row !== "object") continue;

      if (row.event === "chat_message") {
        out.push({
          id: `replay-${i}-${String(row.created_at ?? "")}`,
          kind: "chat",
          text: String(row.message ?? ""),
          username: String(row.username ?? "Unknown"),
          playerId: Number(row.player_id),
        });
      } else if (row.event === "system_log") {
        out.push({
          id: `replay-${i}-${String(row.created_at ?? "")}`,
          kind: "system",
          text: String(row.message ?? ""),
        });
      }
    }

    return out;
  }

  function getOverlayColor(unit: any | null): string {
    if (!unit) return "#00000000";
    if (unit.can_move === false) return "#77777780";
    return getPlayerColor(unit.user_id ?? 0);
  }

  function getAssetBaseUrl(): string {
    const assetBase = (import.meta as any).env?.VITE_ASSET_BASE ?? "/game-assets";
    const normalizedBase = assetBase.startsWith("http")
      ? assetBase
      : `${window.location.origin}${assetBase.startsWith("/") ? "" : "/"}${assetBase}`;
    return normalizedBase.replace(/\/$/, "");
  }

  function normalizeStatusName(status: string): string {
    const normalized = String(status || "").toLowerCase();
    if (normalized === "badly_poison") return "badly_poisoned";
    return normalized;
  }

  function getActiveStatusName(statusEffects: any): string | null {
    if (!statusEffects) return null;

    if (Array.isArray(statusEffects) && statusEffects.length === 2 && typeof statusEffects[0] === "string") {
      return normalizeStatusName(statusEffects[0]);
    }

    if (Array.isArray(statusEffects) && Array.isArray(statusEffects[0]) && typeof statusEffects[0][0] === "string") {
      return normalizeStatusName(statusEffects[0][0]);
    }

    if (Array.isArray(statusEffects) && typeof statusEffects[0] === "string") {
      return normalizeStatusName(statusEffects[0]);
    }

    if (typeof statusEffects === "object" && typeof statusEffects.status === "string") {
      return normalizeStatusName(statusEffects.status);
    }

    return null;
  }

  function getStatusIconSrc(statusEffects: any): string | null {
    const status = getActiveStatusName(statusEffects);
    if (!status) return null;

    const iconByStatus: Record<string, string> = {
      burn: "status_burn.png",
      sleep: "status_sleep.png",
      poison: "status_poisoned.png",
      badly_poisoned: "status_poisoned.png",
      frozen: "status_frozen.png",
      paralysis: "status_paralysis.png",
    };

    const iconFile = iconByStatus[status];
    if (!iconFile) return null;

    return `${getAssetBaseUrl()}/misc/status_icons/${iconFile}`;
  }

  function build2DGrid<T>(height: number, width: number, fill: T): T[][] {
    return Array.from({ length: Math.max(0, height) }, () =>
      Array.from({ length: Math.max(0, width) }, () => fill)
    );
  }

  function buildHazardGrid(height: number, width: number): [number, number][][][] {
    return Array.from({ length: Math.max(0, height) }, () =>
      Array.from({ length: Math.max(0, width) }, () => [] as [number, number][])
    );
  }

  function normalizeGameMapState(game: any) {
    const mapWidth = Number(game?.map?.width ?? 0);
    const mapHeight = Number(game?.map?.height ?? 0);
    const raw = game?.map_state ?? {};

    const parseTimedEffectCell = (cell: any): [number, number] => {
      if (Array.isArray(cell) && cell.length >= 2) {
        const effectId = Number(cell[0]);
        const turns = Number(cell[1]);
        if (!Number.isFinite(effectId) || !Number.isFinite(turns)) return [0, 0];
        if (effectId <= 0 || turns <= 0) return [0, 0];
        return [Math.trunc(effectId), Math.trunc(turns)];
      }

      const legacyId = Number(cell ?? 0);
      if (!Number.isFinite(legacyId) || legacyId <= 0) return [0, 0];
      // Legacy backend payloads may send a plain weather/terrain id.
      return [Math.trunc(legacyId), 0];
    };

    const normalizeNumberGrid = (value: any) => {
      if (!Array.isArray(value)) return build2DGrid(mapHeight, mapWidth, 0);
      return Array.from({ length: mapHeight }, (_, y) => {
        const row = value[y];
        return Array.from({ length: mapWidth }, (_, x) => {
          const n = Number(Array.isArray(row) ? row[x] : 0);
          return Number.isFinite(n) ? n : 0;
        });
      });
    };

    const normalizeTimedEffectGrid = (value: any) => {
      if (!Array.isArray(value)) return build2DGrid<[number, number]>(mapHeight, mapWidth, [0, 0]);
      return Array.from({ length: mapHeight }, (_, y) => {
        const row = value[y];
        return Array.from({ length: mapWidth }, (_, x) => {
          const cell = Array.isArray(row) ? row[x] : 0;
          return parseTimedEffectCell(cell);
        });
      });
    };

    const normalizeHazardGrid = (value: any) => {
      if (!Array.isArray(value)) return buildHazardGrid(mapHeight, mapWidth);
      return Array.from({ length: mapHeight }, (_, y) => {
        const row = value[y];
        return Array.from({ length: mapWidth }, (_, x) => {
          const cell = Array.isArray(row) ? row[x] : [];
          if (!Array.isArray(cell)) return [] as [number, number][];
          return cell
            .filter((entry: any) => Array.isArray(entry) && entry.length >= 2)
            .map((entry: any) => [Number(entry[0]) || 0, Number(entry[1]) || 0] as [number, number])
            .filter(([hazardId, turns]) => Number.isFinite(hazardId) && Number.isFinite(turns) && hazardId > 0 && turns > 0);
        });
      });
    };

    const normalizeItemIdGrid = (value: any) => {
      if (!Array.isArray(value)) return build2DGrid<number | null>(mapHeight, mapWidth, null);
      return Array.from({ length: mapHeight }, (_, y) => {
        const row = value[y];
        return Array.from({ length: mapWidth }, (_, x) => {
          const v = Array.isArray(row) ? row[x] : null;
          return v == null ? null : (Number(v) || null);
        });
      });
    };

    return {
      ...raw,
      weather_tiles: normalizeTimedEffectGrid(raw.weather_tiles),
      hazard_tiles: normalizeHazardGrid(raw.hazard_tiles),
      room_effect_tiles: normalizeTimedEffectGrid(raw.room_effect_tiles),
      terrain_effect_tiles: normalizeTimedEffectGrid(raw.terrain_effect_tiles),
      field_effect_tiles: normalizeNumberGrid(raw.field_effect_tiles),
      item_id_tiles: normalizeItemIdGrid(raw.item_id_tiles),
    };
  }

  function normalizeGameData(game: any) {
    if (!game || !game.map) return game;
    return {
      ...game,
      map_state: normalizeGameMapState(game),
    };
  }

  function getWeatherIconSrc(weatherId: number): string | null {
    const iconByWeatherId: Record<number, string> = {
      1: "weather_sun.png",
      2: "weather_rain.png",
      3: "weather_sandstorm.png",
      4: "weather_hail.png",
    };
    const iconFile = iconByWeatherId[weatherId];
    if (!iconFile) return null;
    return `${getAssetBaseUrl()}/misc/weather_icons/${iconFile}`;
  }

  function getWeatherIconImage(weatherId: number): HTMLImageElement | null {
    if (weatherIconLoadFailedRef.current[weatherId]) return null;

    const src = getWeatherIconSrc(weatherId);
    if (!src) return null;

    const cached = weatherIconCacheRef.current[weatherId];
    if (cached) return cached;

    const img = new Image();
    img.src = src;
    img.onload = () => setWeatherIconRefresh((prev) => prev + 1);
    img.onerror = () => {
      weatherIconLoadFailedRef.current[weatherId] = true;
      setWeatherIconRefresh((prev) => prev + 1);
    };
    weatherIconCacheRef.current[weatherId] = img;
    return img;
  }

  function getHazardIconSrc(): string {
    return `${getAssetBaseUrl()}/misc/hazard_icon.png`;
  }

  function getHazardIconImage(): HTMLImageElement | null {
    if (hazardIconLoadFailedRef.current) return null;

    const cached = hazardIconRef.current;
    if (cached) return cached;

    const img = new Image();
    img.src = getHazardIconSrc();
    img.onload = () => setHazardIconRefresh((prev) => prev + 1);
    img.onerror = () => {
      hazardIconLoadFailedRef.current = true;
      setHazardIconRefresh((prev) => prev + 1);
    };
    hazardIconRef.current = img;
    return img;
  }

  function drawWeatherFallback(ctx: CanvasRenderingContext2D, weatherId: number, tileX: number, tileY: number) {
    const labelByWeatherId: Record<number, string> = {
      1: "SUN",
      2: "RAIN",
      3: "SAND",
      4: "HAIL",
    };
    const colorByWeatherId: Record<number, string> = {
      1: "rgba(255, 181, 60, 0.9)",
      2: "rgba(80, 150, 255, 0.9)",
      3: "rgba(194, 154, 92, 0.9)",
      4: "rgba(180, 220, 255, 0.9)",
    };

    const label = labelByWeatherId[weatherId];
    if (!label) return;

    const chipW = Math.max(16, Math.floor(TILE_DRAW_SIZE * 0.9));
    const chipH = Math.max(8, Math.floor(TILE_DRAW_SIZE * 0.28));
    const drawX = tileX * TILE_DRAW_SIZE + 1;
    const drawY = tileY * TILE_DRAW_SIZE + 1;

    ctx.save();
    ctx.fillStyle = colorByWeatherId[weatherId] ?? "rgba(255,255,255,0.9)";
    ctx.fillRect(drawX, drawY, chipW, chipH);
    ctx.font = "bold 7px sans-serif";
    ctx.fillStyle = "#111";
    ctx.textBaseline = "middle";
    ctx.fillText(label, drawX + 2, drawY + Math.floor(chipH / 2));
    ctx.restore();
  }

  function isTileOccupied(x: number, y: number, ignoreUnitId?: number) {
    return placedUnitsRef.current.some(u => {
      if (ignoreUnitId != null && u.id === ignoreUnitId) return false;
      return u.tile[0] === x && u.tile[1] === y;
    });
  }

  function getOccupiedTileSet(ignoreUnitId?: number): Set<string> {
    const occupied = new Set<string>();
    for (const u of placedUnitsRef.current) {
      if (ignoreUnitId != null && u.id === ignoreUnitId) continue;
      occupied.add(`${u.tile[0]},${u.tile[1]}`);
    }
    return occupied;
  }

  function filterOccupiedTiles(tiles: [number, number][], ignoreUnitId?: number): [number, number][] {
    const occupied = getOccupiedTileSet(ignoreUnitId);
    return tiles.filter(([x, y]) => !occupied.has(`${x},${y}`));
  }

  function getMovementOverlayTiles(
    start: [number, number],
    range: number,
    movementCosts: number[][],
    width: number,
    height: number,
    unitUserId: number,
    ignoreUnitId?: number
  ): [number, number][] {
    const blockedTiles = getBlockedTilesByEnemy(placedUnitsRef.current, unitUserId);
    const tiles = getMovementRange(start, range, movementCosts, width, height, blockedTiles);
    return filterOccupiedTiles(tiles, ignoreUnitId);
  }

  function getActiveOrigin(): [number, number] | null {
    const u = lockedUnit ?? hoveredUnit;
    if (u) {
      const unitId = u.instanceId ?? u.id;
      const live = placedUnitsRef.current.find(p => p.id === unitId);
      return (live?.tile as [number, number]) ?? (u.tile as [number, number]) ?? null;
    }

    // Preparation mode does not lock/select a unit for move execution, but move hover
    // should still preview range from the currently selected placed unit.
    if (gameData?.status === "preparation" && selectedTile) {
      const selected = placedUnitsRef.current.find(
        (p) => p.tile[0] === selectedTile[0] && p.tile[1] === selectedTile[1]
      );
      if (selected) {
        return selected.tile as [number, number];
      }
    }

    return null;
  }

  /* ----- ATTACK RANGE FUNCTIONS ------ */

  const prevTilesRef = useRef<[number, number][]>([]);
  const mapTilesW = gameData?.map?.width ?? 0;
  const mapTilesH = gameData?.map?.height ?? 0;

  const [attackOverlay, setAttackOverlay] = useState<{
    normal: [number, number][];
    invert: [number, number][];
  }>({ normal: [], invert: [] });

  function dedupeTiles(tiles: [number, number][]): [number, number][] {
    const seen = new Set<string>();
    const unique: [number, number][] = [];
    for (const [x, y] of tiles) {
      const key = `${x},${y}`;
      if (seen.has(key)) continue;
      seen.add(key);
      unique.push([x, y]);
    }
    return unique;
  }

  function normalizeAttackOverlay(overlay: {
    normal: [number, number][];
    invert: [number, number][];
  }) {
    const normal = dedupeTiles(overlay.normal);
    const normalSet = new Set(normal.map(([x, y]) => `${x},${y}`));
    const invert = dedupeTiles(overlay.invert).filter(([x, y]) => !normalSet.has(`${x},${y}`));
    return { normal, invert };
  }

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
      if (kind === "self") {
        next.normal = [origin];
      } else if (kind === "adjacent") {
        next.normal = getAdjacentTiles(origin);
      } else if (kind === "dash_attack") {
        const { step, attack } = getDashAttackTiles(origin);
        next.invert = step;  // dash step
        next.normal = attack; // attack tiles
      } else if (kind === "blast") {
        next.normal = getBlastTiles(origin, offset || 1);
      } else if (kind === "sweep") {
        next.normal = getSweepTiles(origin, offset || 1);
      } else if (kind === "ranged") {
        next.normal = getRangedTiles(origin, offset || 1);
      } else if (kind === "line") {
        next.normal = getLineTiles(origin, offset || 1);
      } else if (kind === "pulse") {
        next.normal = getPulseTiles(origin, offset || 1);
      } else if (kind === "bomb") {
        next.normal = getBombTiles(origin, offset || 1);
      } else if (kind === "cone") {
        next.normal = getConeTiles(origin, offset || 1);
      } else if (kind === "inverted_cone") {
        next.normal = getInvertedConeTiles(origin, offset || 1);
      } else if (kind === "x_attack") {
        next.normal = getXAttackTiles(origin, offset || 1);
      }
    }
    setAttackOverlay(normalizeAttackOverlay(next));
  }

  function parseRangeSpec(move: any): { kind: string; offset: number } {
    // Prefer range_type if provided; fall back to range, then targeting
    const raw = String(move?.range_type ?? move?.range ?? move?.targeting ?? "").toLowerCase().trim();
    // Supports "blast", "blast:1", "dash_attack", "adjacent", "self", etc.
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

  function getInvertedConeTiles([x, y]: [number, number], range: number) {
    // Inverted cone flips the original cone distances
    // inverted_cone:1/2 = 2 tiles deep, inverted_cone:3/4 = 3 tiles deep
    // Even values include middle tiles, odd values exclude middles
    const tiles: [number, number][] = [];

    const pushIfIn = (tx: number, ty: number) => {
      if (inBounds(tx, ty)) tiles.push([tx, ty]);
    };

    const includeMiddles = range % 2 === 0;
    const depth = range <= 2 ? 2 : 3;
    const sweeps = depth === 2
      ? [{ dist: 2, half: 1 }]
      : [{ dist: 2, half: 1 }, { dist: 3, half: 2 }];

    const allowOffset = (offset: number, half: number) =>
      includeMiddles || Math.abs(offset) > (half - 1);

    // UP direction - adjacent tile at distance 1
    pushIfIn(x, y - 1);
    for (const { dist, half } of sweeps) {
      for (let dx = -half; dx <= half; dx++) {
        if (allowOffset(dx, half)) pushIfIn(x + dx, y - dist);
      }
    }

    // DOWN direction - adjacent tile at distance 1
    pushIfIn(x, y + 1);
    for (const { dist, half } of sweeps) {
      for (let dx = -half; dx <= half; dx++) {
        if (allowOffset(dx, half)) pushIfIn(x + dx, y + dist);
      }
    }

    // LEFT direction - adjacent tile at distance 1
    pushIfIn(x - 1, y);
    for (const { dist, half } of sweeps) {
      for (let dy = -half; dy <= half; dy++) {
        if (allowOffset(dy, half)) pushIfIn(x - dist, y + dy);
      }
    }

    // RIGHT direction - adjacent tile at distance 1
    pushIfIn(x + 1, y);
    for (const { dist, half } of sweeps) {
      for (let dy = -half; dy <= half; dy++) {
        if (allowOffset(dy, half)) pushIfIn(x + dist, y + dy);
      }
    }

    return tiles;
  }

  function getXAttackTiles([x, y]: [number, number], range: number) {
    // X attack hits one tile in each direction at distance `range`,
    // plus the diagonals from that attacked tile.
    const tiles: [number, number][] = [];

    const pushIfIn = (tx: number, ty: number) => {
      if (inBounds(tx, ty)) tiles.push([tx, ty]);
    };

    const attackPoints: [number, number][] = [
      [x, y - range], // up
      [x, y + range], // down
      [x - range, y], // left
      [x + range, y], // right
    ];

    for (const [ax, ay] of attackPoints) {
      if (!inBounds(ax, ay)) continue;
      pushIfIn(ax, ay);
      pushIfIn(ax - 1, ay - 1);
      pushIfIn(ax + 1, ay - 1);
      pushIfIn(ax - 1, ay + 1);
      pushIfIn(ax + 1, ay + 1);
    }

    return tiles;
  }

  function getSweepTiles([x, y]: [number, number], offset: number) {
    // Sweep hits 3 tiles perpendicular to each direction at 'offset' distance
    const tiles: [number, number][] = [];

    const pushIfIn = (tx: number, ty: number) => {
      if (inBounds(tx, ty)) tiles.push([tx, ty]);
    };

    // Up (sweep left-to-right at offset distance up)
    const upY = y - offset;
    for (let dx = -1; dx <= 1; dx++) {
      pushIfIn(x + dx, upY);
    }

    // Down (sweep left-to-right at offset distance down)
    const downY = y + offset;
    for (let dx = -1; dx <= 1; dx++) {
      pushIfIn(x + dx, downY);
    }

    // Left (sweep up-down at offset distance left)
    const leftX = x - offset;
    for (let dy = -1; dy <= 1; dy++) {
      pushIfIn(leftX, y + dy);
    }

    // Right (sweep up-down at offset distance right)
    const rightX = x + offset;
    for (let dy = -1; dy <= 1; dy++) {
      pushIfIn(rightX, y + dy);
    }

    return tiles;
  }

  function getRangedTiles([x, y]: [number, number], range: number) {
    // Ranged hits a SINGLE tile at the specified distance in each cardinal direction
    // ranged:1 hits 2 tiles away (4 tiles total), ranged:2 hits 3 tiles away, etc.
    const tiles: [number, number][] = [];

    const pushIfIn = (tx: number, ty: number) => {
      if (inBounds(tx, ty)) tiles.push([tx, ty]);
    };

    const distance = range + 1;

    // Up (negative y direction) - only at exact distance
    pushIfIn(x, y - distance);

    // Down (positive y direction) - only at exact distance
    pushIfIn(x, y + distance);

    // Left (negative x direction) - only at exact distance
    pushIfIn(x - distance, y);

    // Right (positive x direction) - only at exact distance
    pushIfIn(x + distance, y);

    return tiles;
  }

  function getLineTiles([x, y]: [number, number], range: number) {
    // Line extends straight from the user, hitting MULTIPLE tiles in each direction
    // line:1 hits 1 tile per direction, line:2 hits 2 tiles, etc.
    const tiles: [number, number][] = [];

    const pushIfIn = (tx: number, ty: number) => {
      if (inBounds(tx, ty)) tiles.push([tx, ty]);
    };

    // Up (negative y direction)
    for (let i = 1; i <= range; i++) {
      pushIfIn(x, y - i);
    }

    // Down (positive y direction)
    for (let i = 1; i <= range; i++) {
      pushIfIn(x, y + i);
    }

    // Left (negative x direction)
    for (let i = 1; i <= range; i++) {
      pushIfIn(x - i, y);
    }

    // Right (positive x direction)
    for (let i = 1; i <= range; i++) {
      pushIfIn(x + i, y);
    }

    return tiles;
  }

  function getPulseTiles([x, y]: [number, number], pulse: number) {
    // pulse:1 -> cardinal neighbors at radius 1 (no diagonals)
    // pulse:2 -> radius 1 including diagonals, excluding self
    // pulse:3 -> radius 1 including diagonals and self
    // pulse:4/5/6 are the above, extended to radius 2
    const tiles: [number, number][] = [];

    const pushIfIn = (tx: number, ty: number) => {
      if (inBounds(tx, ty)) tiles.push([tx, ty]);
    };

    const isExtended = pulse >= 4;
    const radius = isExtended ? 2 : 1;
    const baseMode = ((pulse - 1) % 3) + 1; // maps 1..6 to 1..3

    for (let dy = -radius; dy <= radius; dy++) {
      for (let dx = -radius; dx <= radius; dx++) {
        const tx = x + dx;
        const ty = y + dy;
        const manhattan = Math.abs(dx) + Math.abs(dy);
        const chebyshev = Math.max(Math.abs(dx), Math.abs(dy));

        if (baseMode === 1) {
          // Cardinal-only pulse (no diagonals), exclude self.
          if (manhattan >= 1 && manhattan <= radius && (dx === 0 || dy === 0)) {
            pushIfIn(tx, ty);
          }
        } else if (baseMode === 2) {
          // Full square pulse up to radius, exclude self.
          if (chebyshev >= 1 && chebyshev <= radius) {
            pushIfIn(tx, ty);
          }
        } else {
          // Full square pulse up to radius, include self.
          if (chebyshev <= radius) {
            pushIfIn(tx, ty);
          }
        }
      }
    }

    return tiles;
  }

  function getBombTiles([x, y]: [number, number], range: number) {
    // Bomb attacks 2 tiles away in each cardinal direction,
    // and each attack point creates a plus pattern around it
    // bomb:2 includes the center of each explosion, bomb:1 does not
    const tiles: [number, number][] = [];

    const pushIfIn = (tx: number, ty: number) => {
      if (inBounds(tx, ty)) tiles.push([tx, ty]);
    };

    const includeCenter = range >= 2;
    const distance = 2;

    // Attack points at distance 2 in each cardinal direction
    const attackPoints: [number, number][] = [
      [x, y - distance],     // up
      [x, y + distance],     // down
      [x - distance, y],     // left
      [x + distance, y],     // right
    ];

    // For each attack point, create a plus pattern
    for (const [ax, ay] of attackPoints) {
      if (!inBounds(ax, ay)) continue;

      // Center of explosion (only if range >= 2)
      if (includeCenter) {
        pushIfIn(ax, ay);
      }

      // Plus pattern around the attack point
      pushIfIn(ax, ay - 1);  // up
      pushIfIn(ax, ay + 1);  // down
      pushIfIn(ax - 1, ay);  // left
      pushIfIn(ax + 1, ay);  // right
    }

    return tiles;
  }

  function getConeTiles([x, y]: [number, number], range: number) {
    // Cone is the flipped profile of inverted_cone.
    // cone:1/2 extends 2 tiles, cone:3/4 extends 3 tiles.
    const tiles: [number, number][] = [];

    const pushIfIn = (tx: number, ty: number) => {
      if (inBounds(tx, ty)) tiles.push([tx, ty]);
    };

    const includeMiddles = range % 2 === 0;
    const depth = range <= 2 ? 2 : 3;
    const layers = depth === 2
      ? [{ half: 1 }, { half: 0 }]
      : [{ half: 2 }, { half: 1 }, { half: 0 }];

    const allowOffset = (offset: number, half: number, layerIndex: number) => {
      if (layerIndex === 0) return true;
      return includeMiddles || Math.abs(offset) > (half - 1);
    };

    // UP direction
    for (let i = 0; i < layers.length; i++) {
      const dist = i + 1;
      const { half } = layers[i];
      if (half === 0) {
        pushIfIn(x, y - dist);
        continue;
      }
      for (let dx = -half; dx <= half; dx++) {
        if (allowOffset(dx, half, i)) {
          pushIfIn(x + dx, y - dist);
        }
      }
    }

    // DOWN direction
    for (let i = 0; i < layers.length; i++) {
      const dist = i + 1;
      const { half } = layers[i];
      if (half === 0) {
        pushIfIn(x, y + dist);
        continue;
      }
      for (let dx = -half; dx <= half; dx++) {
        if (allowOffset(dx, half, i)) {
          pushIfIn(x + dx, y + dist);
        }
      }
    }

    // LEFT direction
    for (let i = 0; i < layers.length; i++) {
      const dist = i + 1;
      const { half } = layers[i];
      if (half === 0) {
        pushIfIn(x - dist, y);
        continue;
      }
      for (let dy = -half; dy <= half; dy++) {
        if (allowOffset(dy, half, i)) {
          pushIfIn(x - dist, y + dy);
        }
      }
    }

    // RIGHT direction
    for (let i = 0; i < layers.length; i++) {
      const dist = i + 1;
      const { half } = layers[i];
      if (half === 0) {
        pushIfIn(x + dist, y);
        continue;
      }
      for (let dy = -half; dy <= half; dy++) {
        if (allowOffset(dy, half, i)) {
          pushIfIn(x + dist, y + dy);
        }
      }
    }

    return tiles;
  }

  function getDirectionalOverlayTiles(target: [number, number] | null) {
    if (!target) return [] as [number, number][];
    const origin = getActiveOrigin();
    if (!origin) return [] as [number, number][];

    const [ox, oy] = origin;
    const [tx, ty] = target;
    const dx = tx - ox;
    const dy = ty - oy;
    
    // For self-targeting (origin === target), return the target as-is
    if (dx === 0 && dy === 0) return [target];

    const { kind, offset } = parseRangeSpec(activeMove);
    const useHorizontal = Math.abs(dx) >= Math.abs(dy);
    const dir = useHorizontal ? (dx >= 0 ? 1 : -1) : (dy >= 0 ? 1 : -1);
    const overlayTiles = [...attackOverlay.normal, ...attackOverlay.invert];

    // pulse affects all tiles in its pulse area; do not directional-slice it.
    if (kind === "pulse") {
      return overlayTiles;
    }

    // x_attack should resolve to the selected direction's X cluster, not a cone-style slice.
    if (kind === "x_attack") {
      const attackRange = offset > 0 ? offset : 1;
      const cx = useHorizontal ? ox + dir * attackRange : ox;
      const cy = useHorizontal ? oy : oy + dir * attackRange;
      const xTiles: [number, number][] = [
        [cx, cy],
        [cx - 1, cy - 1],
        [cx + 1, cy - 1],
        [cx - 1, cy + 1],
        [cx + 1, cy + 1],
      ];
      return xTiles.filter(([x, y]) => inBounds(x, y));
    }

    // bomb should resolve to a single directional diamond cluster.
    if (kind === "bomb") {
      const bombRange = offset > 0 ? offset : 1;
      const distance = 2;
      const cx = useHorizontal ? ox + dir * distance : ox;
      const cy = useHorizontal ? oy : oy + dir * distance;
      const includeCenter = bombRange >= 2;

      return overlayTiles.filter(([x, y]) => {
        const manhattan = Math.abs(x - cx) + Math.abs(y - cy);
        if (includeCenter) {
          return manhattan <= 1;
        }
        return manhattan === 1;
      });
    }

    // blast should resolve to one directional 3x2 rectangle.
    if (kind === "blast") {
      const blastOffset = offset > 0 ? offset : 1;
      return overlayTiles.filter(([x, y]) => {
        const rx = x - ox;
        const ry = y - oy;
        if (useHorizontal) {
          const onDepth = rx === dir * blastOffset || rx === dir * (blastOffset + 1);
          return onDepth && Math.abs(ry) <= 1;
        }
        const onDepth = ry === dir * blastOffset || ry === dir * (blastOffset + 1);
        return onDepth && Math.abs(rx) <= 1;
      });
    }

    // Sweep should only include the exact 3-tile band, not any extra diagonal spillover.
    if (kind === "sweep") {
      const sweepOffset = offset > 0 ? offset : 1;
      return overlayTiles.filter(([x, y]) => {
        const rx = x - ox;
        const ry = y - oy;
        if (useHorizontal) {
          return rx === dir * sweepOffset && Math.abs(ry) <= 1;
        }
        return ry === dir * sweepOffset && Math.abs(rx) <= 1;
      });
    }

    return overlayTiles.filter(([x, y]) => {
      const rx = x - ox;
      const ry = y - oy;
      if (rx === 0 && ry === 0) return false;
      if (useHorizontal) {
        return rx * dir > 0 && Math.abs(rx) + 1 >= Math.abs(ry);
      }
      return ry * dir > 0 && Math.abs(ry) + 1 >= Math.abs(rx);
    });
  }

  function drawTileOutline(ctx: CanvasRenderingContext2D, tiles: [number, number][], lineWidth: number) {
    if (!tiles.length) return;
    const tileSet = new Set(tiles.map(([x, y]) => `${x},${y}`));
    const hasTile = (x: number, y: number) => tileSet.has(`${x},${y}`);

    ctx.save();
    ctx.strokeStyle = "#FFFFFF";
    ctx.lineWidth = lineWidth;
    ctx.beginPath();

    tiles.forEach(([x, y]) => {
      const left = x * TILE_DRAW_SIZE + 1;
      const top = y * TILE_DRAW_SIZE + 1;
      const right = left + TILE_DRAW_SIZE - 2;
      const bottom = top + TILE_DRAW_SIZE - 2;

      if (!hasTile(x - 1, y)) {
        ctx.moveTo(left, top);
        ctx.lineTo(left, bottom);
      }
      if (!hasTile(x + 1, y)) {
        ctx.moveTo(right, top);
        ctx.lineTo(right, bottom);
      }
      if (!hasTile(x, y - 1)) {
        ctx.moveTo(left, top);
        ctx.lineTo(right, top);
      }
      if (!hasTile(x, y + 1)) {
        ctx.moveTo(left, bottom);
        ctx.lineTo(right, bottom);
      }
    });

    ctx.stroke();
    ctx.restore();
  }

  function handleMoveHoverStart(move?: any) {
    if (moveTargeting) return;
    if (prevTilesRef.current.length === 0 && highlightedTiles.length > 0) {
      prevTilesRef.current = highlightedTiles;
    }
    setHighlightedTiles([]);
    setHoveredMove(move || null);
    rebuildAttackOverlay(move);
  }

  function handleMoveHoverEnd() {
    if (moveTargeting) return;
    setHoveredMove(null);
    setAttackOverlay({ normal: [], invert: [] });
    if (prevTilesRef.current.length > 0) {
      setHighlightedTiles(prevTilesRef.current);
      prevTilesRef.current = [];
    }
  }

  function isMoveOverlayTile(x: number, y: number) {
    return (
      attackOverlay.normal.some(([tx, ty]) => tx === x && ty === y) ||
      attackOverlay.invert.some(([tx, ty]) => tx === x && ty === y)
    );
  }

  function handleMoveSelect(move: any) {
    if (!activeUnit) return;
    if (!isMyTurn) {
      setToastMessage("You can only use moves on your turn.");
      return;
    }
    if (activeUnit.user_id !== userId) {
      setToastMessage("You can only use your own unit's moves.");
      return;
    }
    if (activeUnit.can_move === false) {
      setToastMessage("This unit is locked and cannot act.");
      return;
    }

    if (!moveTargeting) {
      preMoveStateRef.current = {
        lockedUnit,
        hoveredUnit,
        highlightedTiles,
        unitOriginalTile,
      };
    }

    if (!lockedUnit || lockedUnit.instanceId !== activeUnit.instanceId) {
      const unitId = activeUnit.instanceId;
      const cached = frozenMovesRef.current[unitId];
      if (cached) {
        setHighlightedTiles(filterOccupiedTiles(cached.tiles, unitId));
        setUnitOriginalTile(cached.origin);
      } else if (gameData?.map) {
        const movement = getCurrentMovementRange(activeUnit);
        const costMap = gameData.map.tile_data.movement_cost;
        const width = gameData.map.width;
        const height = gameData.map.height;
        const newOrigin: [number, number] = activeUnit.tile as [number, number];
        const newTiles = getMovementOverlayTiles(newOrigin, movement, costMap, width, height, activeUnit.user_id, unitId);
        frozenMovesRef.current[unitId] = { origin: newOrigin, tiles: newTiles };
        setHighlightedTiles(newTiles);
        setUnitOriginalTile(newOrigin);
      }
      setLockedUnit(activeUnit);
    }

    setSelectedMove(move);
    setMoveTargeting(true);
    setHoveredOverlayTile(null);
    setHoveredMove(null);
    rebuildAttackOverlay(move);
    
    // Auto-select target for self-targeting moves
    const { kind } = parseRangeSpec(move);
    if (kind === "self") {
      setSelectedMoveTarget(activeUnit.tile as [number, number]);
    } else {
      setSelectedMoveTarget(null);
    }
  }

  function handleMoveCancel() {
    setMoveTargeting(false);
    setSelectedMove(null);
    setSelectedMoveTarget(null);
    setHoveredOverlayTile(null);
    setAttackOverlay({ normal: [], invert: [] });

    const snapshot = preMoveStateRef.current;
    if (snapshot) {
      const fallbackLocked = lockedUnit ?? snapshot.lockedUnit;
      setLockedUnit(fallbackLocked);
      setHoveredUnit(snapshot.lockedUnit ? snapshot.hoveredUnit : null);
      const locked = fallbackLocked;
      if (locked) {
        const unitId = locked.instanceId ?? locked.id;
        const cached = frozenMovesRef.current[unitId];
        if (cached) {
          setHighlightedTiles(filterOccupiedTiles(cached.tiles, unitId));
          setUnitOriginalTile(cached.origin);
        } else if (gameData?.map) {
          const movement = getCurrentMovementRange(locked);
          const costMap = gameData.map.tile_data.movement_cost;
          const width = gameData.map.width;
          const height = gameData.map.height;
          const origin: [number, number] = (locked.tile as [number, number]) ?? snapshot.unitOriginalTile ?? [0, 0];
          const tiles = getMovementOverlayTiles(origin, movement, costMap, width, height, locked.user_id, unitId);
          frozenMovesRef.current[unitId] = { origin, tiles };
          setHighlightedTiles(tiles);
          setUnitOriginalTile(origin);
        } else {
          setHighlightedTiles(snapshot.highlightedTiles);
          setUnitOriginalTile(snapshot.unitOriginalTile);
        }
      } else {
        setHighlightedTiles(snapshot.highlightedTiles);
        setUnitOriginalTile(snapshot.unitOriginalTile);
      }
    }
    preMoveStateRef.current = null;
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
      if (r.ok) setGameData(normalizeGameData(await r.json()));
    }
  }


  const handleStartGame = async () => {
    const res = await secureFetch(`/api/games/start/${gameData.id}`, { method: "POST" });
    if (res.ok) {
      const updated = await secureFetch(`/api/games/${gameData.link}`);
      setGameData(normalizeGameData(await updated.json()));
    } else {
      alert("Unable to start game.");
    }
  };

  const handleEndTurn = async () => {
    if (!gameData?.link) return;
    const res = await secureFetch(`/api/games/${gameData.link}/end_turn`, { method: "POST" });
    if (!res.ok) {
      setToastMessage("Unable to end turn.");
      return;
    }
  };

  const handleExecuteMove = async () => {
    if (!gameData?.link || !activeUnit?.instanceId || !selectedMove) return;
    
    // Find the moveIndex and check PP (only if move_pp is initialized)
    const moveIndex = activeUnit.unit?.move_ids?.indexOf(selectedMove.id) ?? -1;
    if (moveIndex === -1) return;
    
    // Only check PP on frontend if move_pp array is properly initialized
    if (activeUnit.move_pp && Array.isArray(activeUnit.move_pp) && activeUnit.move_pp.length > moveIndex) {
      const currentMovePP = activeUnit.move_pp[moveIndex];
      if (currentMovePP <= 0) {
        setToastMessage("This move has no PP left!");
        return;
      }
    }
    
    const activeId = activeUnit.instanceId;
    const attackTiles = selectedDirectionalTiles.length > 0 ? selectedDirectionalTiles : attackOverlay.normal;
    const attackTileSet = new Set(attackTiles.map(([x, y]) => `${x},${y}`));
    const currentUnits = placedUnitsRef.current;
    const receivingTargets = currentUnits.filter(u => {
      if (u.id === activeId) return false;
      const key = `${u.tile[0]},${u.tile[1]}`;
      return attackTileSet.has(key);
    });

    const res = await secureFetch(`/api/games/${gameData.link}/execute_move`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        unit_id: activeId,
        move_id: selectedMove.id,
        target_ids: receivingTargets.map(t => t.id),
        effect_tiles: attackTiles
      })
    });
    if (!res.ok) {
      setToastMessage("Unable to execute move.");
      return;
    }

    const data = await res.json();
    if (Array.isArray(data?.targets) && data.targets.length > 0) {
      const nextHpById = new Map<number, number>();
      for (const t of data.targets) {
        if (typeof t?.id === "number" && typeof t?.current_hp === "number") {
          nextHpById.set(t.id, t.current_hp);
        }
      }
      if (nextHpById.size > 0) {
        setPlacedUnits(prev =>
          prev.map(u => {
            const nextHp = nextHpById.get(u.id);
            return nextHp == null ? u : { ...u, current_hp: nextHp };
          })
        );
        setLockedUnit(prev => {
          if (!prev) return prev;
          const nextHp = nextHpById.get(prev.instanceId ?? prev.id);
          return nextHp == null ? prev : { ...prev, current_hp: nextHp };
        });
        setHoveredUnit(prev => {
          if (!prev) return prev;
          const nextHp = nextHpById.get(prev.instanceId ?? prev.id);
          return nextHp == null ? prev : { ...prev, current_hp: nextHp };
        });
      }
    }

    if (Array.isArray(data?.removed_ids) && data.removed_ids.length > 0) {
      const removedSet = new Set<number>(data.removed_ids);
      setPlacedUnits(prev => prev.filter(u => !removedSet.has(u.id)));
      setLockedUnit(prev => {
        if (!prev) return prev;
        const id = prev.instanceId ?? prev.id;
        return removedSet.has(id) ? null : prev;
      });
      setHoveredUnit(prev => {
        if (!prev) return prev;
        const id = prev.instanceId ?? prev.id;
        return removedSet.has(id) ? null : prev;
      });
    }

    // Update PP from backend response
    const updatedMovePP = data?.move_pp ?? [];
    
    setPlacedUnits(prev =>
      prev.map(u => {
        if (u.id === activeId) {
          return { ...u, can_move: false, move_pp: updatedMovePP };
        }
        return u;
      })
    );
    
    // Update lockedUnit with PP from backend
    setLockedUnit(prev => {
      if (!prev) return prev;
      if (prev.instanceId === activeId || prev.id === activeId) {
        return { ...prev, can_move: false, move_pp: updatedMovePP };
      }
      return { ...prev, can_move: false };
    });
    
    // Update hoveredUnit with PP from backend
    setHoveredUnit(prev => {
      if (!prev) return prev;
      if (prev.instanceId === activeId || prev.id === activeId) {
        return { ...prev, can_move: false, move_pp: updatedMovePP };
      }
      return { ...prev, can_move: false };
    });
    setMoveTargeting(false);
    setSelectedMove(null);
    setSelectedMoveTarget(null);
    setHoveredOverlayTile(null);
    setAttackOverlay({ normal: [], invert: [] });
  };

  useEffect(() => {
    const fetchGame = async () => {
      try {
        const res = await secureFetch(`/api/games/${gameId}`);
        if (!res.ok) throw new Error("Game not found");
        const data = normalizeGameData(await res.json());
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


          const mapped = visibleUnits.map((u: any) => {
            // Preserve move_pp from backend - it should contain the current PP for each move
            let movePP = Array.isArray(u.move_pp) && u.move_pp.length > 0 ? u.move_pp : [];
            
            return {
              id: u.id,
              unit: {
                id: u.unit_id,
                asset_folder: u.unit.asset_folder,
                name: u.unit.name,
                types: u.unit.types,
                cost: u.unit.cost,
                base_stats: u.unit.base_stats,
                move_ids: u.unit.move_ids,
                portrait_credits: u.unit.portrait_credits,
                sprite_credits: u.unit.sprite_credits,
              },
              tile: [u.current_x, u.current_y],
              current_hp: u.current_hp,
              user_id: u.user_id,
              status_effects: u.status_effects ?? [],
              level: u.level,
              current_stats: u.current_stats,
              stat_boosts: u.stat_boosts || {},
              can_move: u.can_move ?? true,
              move_pp: movePP,
            };
          });

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
    if (!gameData?.turn_deadline) return;
    const deadlineMs = new Date(gameData.turn_deadline).getTime();

    const tick = () => {
      const now = Date.now();
      const secs = Math.max(0, Math.ceil((deadlineMs - now) / 1000));
      setRemainingTime(secs);
    };

    tick();
    const id = setInterval(tick, 1000);
    
    // Handle page visibility changes - recalculate timer when page becomes active
    const handleVisibilityChange = () => {
      if (!document.hidden) {
        tick();
      }
    };
    
    document.addEventListener('visibilitychange', handleVisibilityChange);
    
    return () => {
      clearInterval(id);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [gameData?.turn_deadline]);

  const lastOriginRef = useRef<string>("");

  const activeMove = selectedMove ?? hoveredMove;
  const hoveredDirectionalTiles = getDirectionalOverlayTiles(hoveredOverlayTile);
  const selectedDirectionalTiles = getDirectionalOverlayTiles(selectedMoveTarget);

  useEffect(() => {
    if (!activeMove) return;
    let raf = 0;

    const tick = () => {
      const o = getActiveOrigin();
      const key = o ? `${o[0]},${o[1]}` : "";
      if (key !== lastOriginRef.current) {
        lastOriginRef.current = key;
        rebuildAttackOverlay(activeMove);
      }
      raf = requestAnimationFrame(tick);
    };

    tick();
    return () => cancelAnimationFrame(raf);
  }, [activeMove, lockedUnit, hoveredUnit, placedUnits]);

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

  // Initialize move_pp with full PP values from moveMap if not provided by backend
  useEffect(() => {
    if (Object.keys(moveMap).length === 0) return;
    
    setPlacedUnits(prev =>
      prev.map(unit => {
        // Only initialize move_pp if it's completely missing or empty
        // Don't overwrite existing values from the backend
        if (!Array.isArray(unit.move_pp) || unit.move_pp.length === 0) {
          const ppArray = unit.unit.move_ids?.map((moveId: number) => {
            const move = moveMap[moveId];
            return move?.pp ?? 0;
          }) ?? [];
          return { ...unit, move_pp: ppArray };
        }
        return unit;
      })
    );
  }, [moveMap]);

  useEffect(() => {
    if (activeMove) rebuildAttackOverlay(activeMove);
  }, [placedUnits, activeMove]);

  useEffect(() => {
    if (isReady) {
      setSelectedTile(null);
    }
  }, [isReady]);

  useEffect(() => {
    if (!isUnitSelectMenuVisible) {
      setUnitSearchQuery("");
      setUnitTypeFilterPrimary("");
      setUnitTypeFilterSecondary("");
      setUnitSortBy("id");
      setUnitSortDirection("asc");
    }
  }, [isUnitSelectMenuVisible]);

  useEffect(() => {
    if (unitTypeFilterPrimary && unitTypeFilterPrimary === unitTypeFilterSecondary) {
      setUnitTypeFilterSecondary("");
    }
  }, [unitTypeFilterPrimary, unitTypeFilterSecondary]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (moveTargeting) return;
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
  }, [moveTargeting]);

  useEffect(() => {
    if (gameData?.status !== "in_progress") return;
    const canvas = overlayRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const overlayUnit = lockedUnit ?? hoveredUnit;
    const overlayColor = getOverlayColor(overlayUnit);

    if (!moveTargeting) {
      // movement tiles
      highlightedTiles.forEach(([x, y]) => {
        ctx.fillStyle = overlayColor;
        ctx.fillRect(x * TILE_DRAW_SIZE, y * TILE_DRAW_SIZE, TILE_DRAW_SIZE, TILE_DRAW_SIZE);
      });
    }

    // attack tiles
    attackOverlay.normal.forEach(([x, y]) => {
      ctx.fillStyle = overlayColor;
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

    if (moveTargeting && hoveredDirectionalTiles.length) {
      drawTileOutline(ctx, hoveredDirectionalTiles, 2);
    }

    if (moveTargeting && selectedDirectionalTiles.length) {
      drawTileOutline(ctx, selectedDirectionalTiles, 3);
    }

    const weatherTiles = gameData?.map_state?.weather_tiles;
    if (Array.isArray(weatherTiles)) {
      const iconSize = Math.max(10, Math.floor(TILE_DRAW_SIZE * 0.42));
      const iconPadding = 2;
      for (let y = 0; y < weatherTiles.length; y++) {
        const row = weatherTiles[y];
        if (!Array.isArray(row)) continue;
        for (let x = 0; x < row.length; x++) {
          const cell = row[x];
          const weatherId = Number(Array.isArray(cell) ? cell[0] : cell ?? 0);
          if (!Number.isFinite(weatherId) || weatherId <= 0) continue;

          const icon = getWeatherIconImage(weatherId);
          const drawX = x * TILE_DRAW_SIZE + iconPadding;
          const drawY = y * TILE_DRAW_SIZE + iconPadding;
          if (icon && icon.complete && icon.naturalWidth > 0) {
            ctx.drawImage(icon, drawX, drawY, iconSize, iconSize);
          } else {
            drawWeatherFallback(ctx, weatherId, x, y);
          }
        }
      }
    }

    const hazardTiles = gameData?.map_state?.hazard_tiles;
    if (Array.isArray(hazardTiles)) {
      const iconSize = Math.max(10, Math.floor(TILE_DRAW_SIZE * 0.42));
      const iconPadding = 2;
      const hazardIcon = getHazardIconImage();
      for (let y = 0; y < hazardTiles.length; y++) {
        const row = hazardTiles[y];
        if (!Array.isArray(row)) continue;
        for (let x = 0; x < row.length; x++) {
          const cell = row[x];
          if (!Array.isArray(cell) || cell.length === 0) continue;

          const drawX = (x + 1) * TILE_DRAW_SIZE - iconSize - iconPadding;
          const drawY = y * TILE_DRAW_SIZE + iconPadding;
          if (hazardIcon && hazardIcon.complete && hazardIcon.naturalWidth > 0) {
            ctx.drawImage(hazardIcon, drawX, drawY, iconSize, iconSize);
          } else {
            ctx.save();
            ctx.fillStyle = "rgba(220, 80, 80, 0.9)";
            ctx.beginPath();
            ctx.arc(drawX + iconSize / 2, drawY + iconSize / 2, iconSize / 2, 0, Math.PI * 2);
            ctx.fill();
            ctx.restore();
          }
        }
      }
    }
  }, [
    highlightedTiles,
    lockedUnit,
    unitOriginalTile,
    isMyTurn,
    userId,
    gameData?.link,
    gameData?.status,
    attackOverlay,
    moveTargeting,
    hoveredOverlayTile,
    selectedMoveTarget,
    activeMove,
    gameData?.map_state,
    weatherIconRefresh,
    hazardIconRefresh
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

      if (moveTargeting && selectedMove) {
        if (isMoveOverlayTile(x, y)) {
          setSelectedMoveTarget(clickedTile);
        }
        return;
      }
      
      if (!lockedUnit || !unitOriginalTile || !myTurnRef.current) return;
      if (lockedUnit.can_move === false) {
        setToastMessage("This unit is locked and cannot act.");
        return;
      }

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
  }, [highlightedTiles, lockedUnit, unitOriginalTile, moveTargeting, selectedMove, attackOverlay]);

  useEffect(() => {
    if (gameData?.status !== "in_progress") return;
    const canvas = overlayRef.current;
    if (!canvas) return;

    const handleMove = (e: MouseEvent) => {
      if (!moveTargeting || !selectedMove) return;
      const rect = canvas.getBoundingClientRect();
      const x = Math.floor((e.clientX - rect.left) / TILE_DRAW_SIZE);
      const y = Math.floor((e.clientY - rect.top) / TILE_DRAW_SIZE);
      if (isMoveOverlayTile(x, y)) {
        setHoveredOverlayTile([x, y]);
      } else {
        setHoveredOverlayTile(null);
      }
    };

    const handleLeave = () => setHoveredOverlayTile(null);

    canvas.addEventListener("mousemove", handleMove);
    canvas.addEventListener("mouseleave", handleLeave);
    return () => {
      canvas.removeEventListener("mousemove", handleMove);
      canvas.removeEventListener("mouseleave", handleLeave);
    };
  }, [gameData?.status, moveTargeting, selectedMove, attackOverlay]);

  useEffect(() => {
    setLockedUnit(null);
    setHighlightedTiles([]);
    setUnitOriginalTile(null);
    frozenMovesRef.current = {};
    setMoveTargeting(false);
    setSelectedMove(null);
    setSelectedMoveTarget(null);
    setHoveredOverlayTile(null);
    setAttackOverlay({ normal: [], invert: [] });
  }, [gameData?.current_turn]);

  useEffect(() => {
    if (lockedUnit) return;
    setMoveTargeting(false);
    setSelectedMove(null);
    setSelectedMoveTarget(null);
    setHoveredOverlayTile(null);
    setAttackOverlay({ normal: [], invert: [] });
    preMoveStateRef.current = null;
  }, [lockedUnit]);

  useEffect(() => {
    if (!gameData?.link || !gameData?.current_turn) return;
    (async () => {
      const res = await secureFetch(`/api/games/${gameData.link}/turnlock`);
      if (!res.ok) return;
      const locks = await res.json() as Record<string, {origin:[number,number], tiles:[number,number][]}>;
      const next: Record<number, {origin:[number,number], tiles:[number,number][]}> = {};
      for (const [k, v] of Object.entries(locks)) {
        const unitId = Number(k);
        next[unitId] = {
          origin: v.origin,
          tiles: filterOccupiedTiles(v.tiles, unitId),
        };
      }
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
      if (typeof event.data === "string" && event.data.startsWith("{")) {
        try {
          const payload = JSON.parse(event.data);
          if (payload?.event === "chat_message") {
            setChatEntries((prev) => [
              ...prev,
              {
                id: `${Date.now()}-${Math.random().toString(36).slice(2)}`,
                kind: "chat",
                text: String(payload.message ?? ""),
                username: String(payload.username ?? "Unknown"),
                playerId: Number(payload.player_id),
              },
            ]);
            return;
          }
          if (payload?.event === "system_log") {
            const message = String(payload.message ?? "").trim();
            if (message) {
              addSystemChat(message);
            }
            return;
          }
        } catch {
          // Ignore malformed payloads and continue with legacy string handlers.
        }
      }

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

      if (typeof event.data === "string" && event.data.startsWith("unit_removed:")) {
        const [, unitIdStr] = event.data.split(":");
        const unitId = Number(unitIdStr);
        setPlacedUnits(prev => prev.filter(u => u.id !== unitId));
        setLockedUnit(prev => {
          if (!prev) return prev;
          const id = prev.instanceId ?? prev.id;
          return id === unitId ? null : prev;
        });
        setHoveredUnit(prev => {
          if (!prev) return prev;
          const id = prev.instanceId ?? prev.id;
          return id === unitId ? null : prev;
        });
        setMoveTargeting(false);
        setSelectedMove(null);
        setSelectedMoveTarget(null);
        setHoveredOverlayTile(null);
        setAttackOverlay({ normal: [], invert: [] });
        setHighlightedTiles([]);
        setUnitOriginalTile(null);
        return;
      }
      
      if (typeof event.data === "string" && event.data.startsWith("unit_pp_updated:")) {
        const [, unitIdStr] = event.data.split(":");
        const unitId = Number(unitIdStr);
        // Fetch updated unit data to get the latest move_pp
        secureFetch(`/api/games/${gameId}/units`)
          .then(res => res.json())
          .then(backendUnits => {
            const updatedUnit = backendUnits.find((u: any) => u.id === unitId);
            if (updatedUnit && updatedUnit.move_pp) {
              setPlacedUnits(prev =>
                prev.map(u => u.id === unitId ? { ...u, move_pp: updatedUnit.move_pp } : u)
              );
              setLockedUnit(prev => {
                if (!prev) return prev;
                const id = prev.instanceId ?? prev.id;
                return id === unitId ? { ...prev, move_pp: updatedUnit.move_pp } : prev;
              });
              setHoveredUnit(prev => {
                if (!prev) return prev;
                const id = prev.instanceId ?? prev.id;
                return id === unitId ? { ...prev, move_pp: updatedUnit.move_pp } : prev;
              });
            }
          })
          .catch(err => console.error("Failed to fetch unit PP update:", err));
        return;
      }
      
      if (typeof event.data === "string" && event.data.startsWith("unit_stats_updated:")) {
        const [, unitIdStr] = event.data.split(":");
        const unitId = Number(unitIdStr);
        // Fetch updated unit data to get the latest current_stats and stat_boosts
        secureFetch(`/api/games/${gameId}/units`)
          .then(res => res.json())
          .then(backendUnits => {
            const updatedUnit = backendUnits.find((u: any) => u.id === unitId);
            if (updatedUnit) {
              setPlacedUnits(prev =>
                prev.map(u => u.id === unitId ? { 
                  ...u, 
                  current_stats: updatedUnit.current_stats,
                  stat_boosts: updatedUnit.stat_boosts || {},
                  status_effects: updatedUnit.status_effects ?? u.status_effects ?? [],
                  move_pp: updatedUnit.move_pp || u.move_pp 
                } : u)
              );
              setLockedUnit(prev => {
                if (!prev) return prev;
                const id = prev.instanceId ?? prev.id;
                return id === unitId ? { 
                  ...prev, 
                  current_stats: updatedUnit.current_stats,
                  stat_boosts: updatedUnit.stat_boosts || {},
                  status_effects: updatedUnit.status_effects ?? prev.status_effects ?? [],
                  move_pp: updatedUnit.move_pp || prev.move_pp 
                } : prev;
              });
              setHoveredUnit(prev => {
                if (!prev) return prev;
                const id = prev.instanceId ?? prev.id;
                return id === unitId ? { 
                  ...prev, 
                  current_stats: updatedUnit.current_stats,
                  stat_boosts: updatedUnit.stat_boosts || {},
                  status_effects: updatedUnit.status_effects ?? prev.status_effects ?? [],
                  move_pp: updatedUnit.move_pp || prev.move_pp 
                } : prev;
              });
            }
          })
          .catch(err => console.error("Failed to fetch unit stats update:", err));
        return;
      }
      
      if (["player_joined", "game_started", "player_ready", "game_preparation", "turn_started", "turn_advanced", "unit_locked", "game_completed"].includes(event.data)) {
        if (event.data === "turn_started" || event.data === "turn_advanced" || event.data === "game_completed") {
          setLockedUnit(null);
          setHoveredUnit(null);
          setHighlightedTiles([]);
          setUnitOriginalTile(null);
          setMoveTargeting(false);
          setSelectedMove(null);
          setSelectedMoveTarget(null);
          setHoveredOverlayTile(null);
          setAttackOverlay({ normal: [], invert: [] });
          preMoveStateRef.current = null;
        }
        (async () => {
          const res = await secureFetch(`/api/games/${gameData.link}`);
          if (!res.ok) return;
          const updatedGame = normalizeGameData(await res.json());
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
              portrait_credits: u.unit.portrait_credits,
              sprite_credits: u.unit.sprite_credits,
            },
            tile: [u.current_x, u.current_y],
            current_hp: u.current_hp,
            user_id: u.user_id,
            status_effects: u.status_effects ?? [],
            level: u.level,
            current_stats: u.current_stats,
            stat_boosts: u.stat_boosts || {},
            can_move: u.can_move ?? true,
            move_pp: Array.isArray(u.move_pp) && u.move_pp.length > 0 ? u.move_pp : [],
          }));

          setPlacedUnits(mapped);

          // Update lockedUnit and hoveredUnit if they're affected by the update
          setLockedUnit(prev => {
            if (!prev) return prev;
            const updated = mapped.find((u: any) => u.id === prev.instanceId);
            return updated
              ? { ...prev, can_move: updated.can_move, move_pp: updated.move_pp, status_effects: updated.status_effects ?? prev.status_effects ?? [] }
              : prev;
          });
          setHoveredUnit(prev => {
            if (!prev) return prev;
            const updated = mapped.find((u: any) => u.id === prev.instanceId);
            return updated
              ? { ...prev, can_move: updated.can_move, move_pp: updated.move_pp, status_effects: updated.status_effects ?? prev.status_effects ?? [] }
              : prev;
          });

          try {
            const lockRes = await secureFetch(`/api/games/${updatedGame.link}/turnlock`);
            if (lockRes.ok) {
              const locks = await lockRes.json() as Record<string, {origin:[number,number], tiles:[number,number][]}>;
              const next: Record<number, {origin:[number,number], tiles:[number,number][]}> = {};
              for (const [k, v] of Object.entries(locks)) {
                const unitId = Number(k);
                next[unitId] = {
                  origin: v.origin,
                  tiles: filterOccupiedTiles(v.tiles, unitId),
                };
              }
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

  useEffect(() => {
    setChatEntries(mapReplayLogToChatEntries(gameData?.replay_log));
    setChatInput("");
  }, [gameData?.link, gameData?.replay_log]);

  useEffect(() => {
    const updateMenuPosition = () => {
      const stage = mapStageRef.current;
      if (!stage) return;
      const header = gameHeaderRef.current;

      const rect = stage.getBoundingClientRect();
      const headerRect = header?.getBoundingClientRect();
      const panelWidth = 288; // Tailwind w-72
      const chatPanelWidth = 360;
      const gap = 24;
      const viewportPadding = 12;

      const desiredLeft = rect.right + gap;
      const maxLeft = window.innerWidth - panelWidth - chatPanelWidth - gap;
      const clampedLeft = Math.max(viewportPadding, Math.min(desiredLeft, maxLeft));
      const anchorTop = typeof headerRect?.top === "number" ? headerRect.top : rect.top;
      const clampedTop = Math.max(viewportPadding, anchorTop);

      setMenuScreenPosition({ left: clampedLeft, top: clampedTop });
    };

    updateMenuPosition();
    window.addEventListener("resize", updateMenuPosition);
    window.addEventListener("scroll", updateMenuPosition, true);

    return () => {
      window.removeEventListener("resize", updateMenuPosition);
      window.removeEventListener("scroll", updateMenuPosition, true);
    };
  }, [mapWidth, mapHeight, gameData?.status, selectedTile, activeUnit]);

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
  const winnerPlayer = gameData?.players?.find((p: any) => p.player_id === gameData.winner_id);
  const allPlayersReady = gameData?.players?.every((p: any) => p.is_ready === true);
  const drawPlayers = (gameData?.draw_player_ids ?? [])
    .map((id: number) => gameData?.players?.find((p: any) => p.player_id === id)?.username)
    .filter((name: string | undefined) => Boolean(name));
  const usernameColorMap = useMemo(() => {
    const out: Record<string, string> = {};
    const players = Array.isArray(gameData?.players) ? gameData.players : [];
    for (const player of players) {
      const username = String(player?.username ?? "").trim();
      const playerId = Number(player?.player_id);
      const color = playerColorMap[playerId];
      if (!username || !Number.isFinite(playerId) || !color) continue;
      out[username] = color;
    }
    return out;
  }, [gameData?.players, playerColorMap]);

  const placedUnitAtTile = selectedTile
  ? placedUnits.find(
      (u) => u.tile[0] === selectedTile[0] && u.tile[1] === selectedTile[1]
    )
  : null;

  const handleRemovePlacedUnit = async () => {
    if (!placedUnitAtTile?.id || !gameData?.link) return;

    const res = await secureFetch(`/api/games/${gameData.link}/units/remove/${placedUnitAtTile.id}`, {
      method: "DELETE"
    });

    if (!res.ok) {
      setToastMessage("Failed to remove unit.");
      return;
    }

    setCash((prev) => prev + (placedUnitAtTile.unit?.cost ?? 0));
    setPlacedUnits((prev) => prev.filter((u) => u.id !== placedUnitAtTile.id));
    setSelectedTile(null);
  };

  const handlePlacePreparationUnit = async (unit: any) => {
    if (!selectedTile || !gameData?.link) return;
    if (unit.cost > cash) {
      setToastMessage("You don't have enough cash to buy this unit!");
      return;
    }

    const payload = {
      unit_id: unit.id,
      x: selectedTile[0],
      y: selectedTile[1],
      current_hp: 100,
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
    const movePP = placedUnit.move_pp ?? [];

    setPlacedUnits((prev) => [
      ...prev,
      {
        id: placedUnit.id,
        unit: placedUnit.unit,
        tile: [placedUnit.current_x, placedUnit.current_y],
        current_hp: placedUnit.current_hp,
        user_id: placedUnit.user_id,
        status_effects: placedUnit.status_effects ?? [],
        level: placedUnit.level,
        current_stats: placedUnit.current_stats,
        can_move: placedUnit.can_move ?? true,
        move_pp: movePP,
      }
    ]);
    setCash((prev) => prev - unit.cost);
    setSelectedTile(null);
  };

  const handleMapUnitMouseEnter = (unitState: any) => {
    if (gameData?.status === "in_progress" && !lockedUnit && !moveTargeting) {
      const live = placedUnits.find((p) => p.id === unitState.id);
      setHoveredUnit({
        unit: unitState.unit,
        user_id: unitState.user_id,
        current_hp: unitState.current_hp,
        instanceId: unitState.id,
        tile: unitState.tile,
        current_stats: live?.current_stats,
        stat_boosts: live?.stat_boosts,
        status_effects: live?.status_effects ?? [],
        can_move: live?.can_move ?? true,
        move_pp: live?.move_pp ?? [],
      });
    }
  };

  const handleMapUnitMouseLeave = () => {
    if (gameData?.status === "in_progress" && !lockedUnit && !moveTargeting) {
      setHoveredUnit(null);
    }
  };

  const handleMapUnitClick = (unitState: any) => {
    if (moveTargeting) return;

    if (gameData?.status === "preparation") {
      if (isReady) return;
      setSelectedTile(unitState.tile);
      return;
    }

    if (gameData?.status !== "in_progress") return;

    const live = placedUnits.find((p) => p.id === unitState.id);
    setLockedUnit((prev) => {
      const isSameInstance = prev?.instanceId === unitState.id;
      if (isSameInstance) {
        setHighlightedTiles([]);
        setUnitOriginalTile(null);
        return null;
      }

      const cached = frozenMovesRef.current[unitState.id];
      if (cached) {
        setHighlightedTiles(filterOccupiedTiles(cached.tiles, unitState.id));
        setUnitOriginalTile(cached.origin);
        return {
          unit: unitState.unit,
          user_id: unitState.user_id,
          current_hp: unitState.current_hp,
          instanceId: unitState.id,
          tile: unitState.tile,
          current_stats: live?.current_stats,
          stat_boosts: live?.stat_boosts,
          status_effects: live?.status_effects ?? [],
          can_move: live?.can_move ?? true,
          move_pp: live?.move_pp ?? [],
        };
      }

      const movement = getCurrentMovementRange({
        unit: unitState.unit,
        current_stats: live?.current_stats,
        level: live?.level,
      });
      const costMap = gameData.map.tile_data.movement_cost;
      const width = gameData.map.width;
      const height = gameData.map.height;

      const newOrigin: [number, number] = unitState.tile;
      const newTiles = getMovementOverlayTiles(newOrigin, movement, costMap, width, height, unitState.user_id, unitState.id);

      frozenMovesRef.current[unitState.id] = { origin: newOrigin, tiles: newTiles };
      setHighlightedTiles(newTiles);
      setUnitOriginalTile(newOrigin);

      return {
        unit: unitState.unit,
        user_id: unitState.user_id,
        current_hp: unitState.current_hp,
        instanceId: unitState.id,
        tile: unitState.tile,
        current_stats: live?.current_stats,
        stat_boosts: live?.stat_boosts,
        status_effects: live?.status_effects ?? [],
        can_move: live?.can_move ?? true,
        move_pp: live?.move_pp ?? [],
      };
    });
  };

  const handleSendChat = async () => {
    if (!gameData?.link) return;
    const message = chatInput.trim();
    if (!message) return;

    const res = await secureFetch(`/api/games/${gameData.link}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message }),
    });

    if (!res.ok) {
      setToastMessage("Unable to send chat message.");
      return;
    }

    setChatInput("");
  };

  return (
    <div className="relative p-8 text-white flex flex-row items-start gap-6">
      {toastMessage && (
        <div className="fixed top-4 left-1/2 transform -translate-x-1/2 bg-red-600 text-white px-4 py-2 rounded shadow-lg z-50">
          {toastMessage}
        </div>
      )}

      <div className="flex-1">
        <h1 ref={gameHeaderRef} className="text-3xl font-bold mb-2">
          {gameData?.game_name || "Untitled Game"} <span className="text-sm text-gray-400">({gameData?.gamemode})</span>
        </h1>
        
        {gameData?.max_turns && gameData.current_turn !== null && gameData.current_turn !== undefined && gameData.player_order && gameData.host_id && gameData?.status === "in_progress" && (
          (() => {
            // Calculate display turn based on host's turn only
            const hostIndex = gameData.player_order.indexOf(gameData.host_id);
            const displayTurn = Math.floor((gameData.current_turn + gameData.player_order.length - hostIndex) / gameData.player_order.length);
            return (
              <p className="text-md text-gray-300 mb-2">
                Turn {displayTurn} / {gameData.max_turns}
              </p>
            );
          })()
        )}

        <p className="text-lg font-semibold mb-2 text-yellow-400">
          {gameData?.status === "in_progress" ? (
            (() => {
              const current = gameData.players.find(
                (p: any) => p.player_id === currentPlayerId
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
          ) : gameData?.status === "completed" ? (
            winnerPlayer
              ? `${winnerPlayer.username} wins the match!`
              : drawPlayers.length > 0
                ? `Draw between ${drawPlayers.join(", ")}.`
                : "Match completed."
          ) : gameData?.status === "closed" && isHost ? (
            "Players have been found!"
          ) : !isFull ? (
            "Waiting for players..."
          ) : (
            "Waiting for host to start the match..."
          )}
        </p>

        {gameData?.status === "in_progress" && isMyTurn && (
          <button
            className="mt-2 mb-4 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded"
            onClick={handleEndTurn}
          >
            End Turn
          </button>
        )}

        {isHost && gameData?.status !== "in_progress" && gameData?.status !== "preparation" && gameData?.status !== "completed" && (
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

        <GameMapStage
          mapWidth={mapWidth}
          mapHeight={mapHeight}
          canvasRef={canvasRef}
          overlayRef={overlayRef}
          mapStageRef={mapStageRef}
          overlayPointerEventsEnabled={(lockedUnit && lockedUnit.can_move !== false && isMyTurn) || moveTargeting}
          placedUnits={placedUnits}
          tileDrawSize={TILE_DRAW_SIZE}
          moveTargeting={moveTargeting}
          getPlayerColor={getPlayerColor}
          onSpriteFrameSize={([, h]) => setSpriteHeight(h)}
          onUnitMouseEnter={handleMapUnitMouseEnter}
          onUnitMouseLeave={handleMapUnitMouseLeave}
          onUnitClick={handleMapUnitClick}
        />

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

      <ChatPanel
        chatEntries={chatEntries}
        chatInput={chatInput}
        onChatInputChange={setChatInput}
        onSendChat={handleSendChat}
        playerColorMap={playerColorMap}
        usernameColorMap={usernameColorMap}
      />

      {(() => {
        let panel: any = null;

        if (isPreparationPhase && selectedTile && placedUnitAtTile !== undefined) {
          panel = (
            <PreparationPlacedUnitMenu
              placedUnitAtTile={placedUnitAtTile}
              moveMap={moveMap}
              typeColors={TYPE_COLORS}
              statusIconSrc={getStatusIconSrc(placedUnitAtTile?.status_effects ?? [])}
              getStatColor={getStatColor}
              onRemoveUnit={handleRemovePlacedUnit}
              onMoveHoverStart={handleMoveHoverStart}
              onMoveHoverEnd={handleMoveHoverEnd}
            />
          );
        }
        else if (isPreparationPhase && selectedTile && placedUnitAtTile === undefined && placedUnits.length < unitLimit) {
          panel = (
            <PreparationUnitSelectMenu
              availableUnits={availableUnits}
              unitSearchQuery={unitSearchQuery}
              unitTypeFilterPrimary={unitTypeFilterPrimary}
              unitTypeFilterSecondary={unitTypeFilterSecondary}
              unitSortBy={unitSortBy}
              unitSortDirection={unitSortDirection}
              unitTypeOptions={unitTypeOptions}
              typeColors={TYPE_COLORS}
              onSearchChange={setUnitSearchQuery}
              onPrimaryTypeChange={setUnitTypeFilterPrimary}
              onSecondaryTypeChange={setUnitTypeFilterSecondary}
              onSortByChange={setUnitSortBy}
              onSortDirectionChange={setUnitSortDirection}
              onSelectUnit={handlePlacePreparationUnit}
            />
          );
        }
        else if (gameData?.status === "in_progress" && activeUnit) {
          panel = (
            <InProgressUnitMenu
              activeUnit={activeUnit}
              typeColors={TYPE_COLORS}
              statusIconSrc={getStatusIconSrc(activeUnit?.status_effects ?? [])}
              getStatColor={getStatColor}
              moveMap={moveMap}
              moveTargeting={moveTargeting}
              selectedMove={selectedMove}
              onMoveHoverStart={handleMoveHoverStart}
              onMoveHoverEnd={handleMoveHoverEnd}
              onMoveSelect={handleMoveSelect}
              onExecuteMove={handleExecuteMove}
              onCancelMove={handleMoveCancel}
              getPlayerColor={getPlayerColor}
            />
          );
        }

        if (!panel) return null;

        return (
          <div
            className="fixed z-40 pointer-events-auto"
            style={{ left: `${menuScreenPosition.left}px`, top: `${menuScreenPosition.top}px` }}
          >
            {panel}
          </div>
        );
      })()}

    </div>
  );
}