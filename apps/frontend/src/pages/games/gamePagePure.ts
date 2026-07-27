import { RANDOM_TM_ITEM_ID } from "@/types/mapData";

export type ChatEntry = {
  id: string;
  kind: "chat" | "system";
  text: string;
  username?: string;
  playerId?: number;
  isSpectator?: boolean;
};
export function formatTurnCountdown(seconds: number): string {
  const hrs = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);
  const secs = seconds % 60;

  if (hrs > 0) {
    return `${hrs}:${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  }
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function getBaseBattleStatValue(unitState: any, statName: string): number | null {
  const baseStats = unitState?.unit?.base_stats;
  if (!baseStats || typeof baseStats !== "object") return null;

  const level = typeof unitState?.level === "number" ? unitState.level : 50;
  if (statName === "range") {
    const baseSpeed = baseStats?.speed;
    if (typeof baseSpeed !== "number") return null;
    const baseBattleSpeed = Math.floor((2 * baseSpeed * level) / 100 + 5);
    return Math.max(0, Math.floor(2 + baseBattleSpeed / 50));
  }

  const baseValue = baseStats?.[statName];
  if (typeof baseValue !== "number") return null;

  if (statName === "hp") {
    return Math.floor((2 * baseValue * level) / 100) + level + 10;
  }
  return Math.floor((2 * baseValue * level) / 100 + 5);
}

export function getCurrentMovementRange(unitState: any): number {
  const explicitRange = unitState?.current_stats?.range;
  if (typeof explicitRange === "number") return Math.max(0, Math.floor(explicitRange));

  const currentSpeed = unitState?.current_stats?.speed;
  if (typeof currentSpeed === "number") return Math.max(0, Math.floor(2 + currentSpeed / 50));

  const baseRange = getBaseBattleStatValue(unitState, "range");
  if (typeof baseRange === "number") return Math.max(0, Math.floor(baseRange));

  return 0;
}

export function getStatColor(unitState: any, statName: string): string {
  const currentValue = unitState?.current_stats?.[statName];
  if (typeof currentValue !== "number") return "#ffffff";

  const baseValue = getBaseBattleStatValue(unitState, statName);
  if (typeof baseValue !== "number") return "#ffffff";

  if (currentValue > baseValue) return "#22c55e";
  if (currentValue < baseValue) return "#ef4444";
  return "#ffffff";
}

export function mapReplayLogToChatEntries(replayLog: any): ChatEntry[] {
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
        isSpectator: Boolean(row.is_spectator),
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

export function normalizeStatusName(status: string): string {
  const normalized = String(status || "").toLowerCase();
  if (normalized === "badly_poison") return "badly_poisoned";
  return normalized;
}

export function getActiveStatusName(statusEffects: any): string | null {
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

export function getStatusIconSrc(statusEffects: any, assetBaseUrl: string): string | null {
  const status = getActiveStatusName(statusEffects);
  if (!status) return null;

  const iconByStatus: Record<string, string> = {
    burn: "status_burn.png",
    sleep: "status_sleep.png",
    poison: "status_poisoned.png",
    badly_poisoned: "status_badly_poisoned.png",
    frozen: "status_frozen.png",
    paralysis: "status_paralysis.png",
  };

  const iconFile = iconByStatus[status];
  if (!iconFile) return null;

  return `${assetBaseUrl.replace(/\/$/, "")}/misc/status_icons/${iconFile}`;
}

export function getWeatherIconSrc(weatherId: number, assetBaseUrl: string): string | null {
  const iconByWeatherId: Record<number, string> = {
    1: "weather_sun.png",
    2: "weather_rain.png",
    3: "weather_sandstorm.png",
    4: "weather_hail.png",
  };
  const iconFile = iconByWeatherId[weatherId];
  if (!iconFile) return null;
  return `${assetBaseUrl.replace(/\/$/, "")}/misc/weather_icons/${iconFile}`;
}

export function build2DGrid<T>(height: number, width: number, fill: T): T[][] {
  return Array.from({ length: Math.max(0, height) }, () =>
    Array.from({ length: Math.max(0, width) }, () => fill)
  );
}

export function buildHazardGrid(height: number, width: number): [number, number][][][] {
  return Array.from({ length: Math.max(0, height) }, () =>
    Array.from({ length: Math.max(0, width) }, () => [] as [number, number][])
  );
}

export function normalizeGameMapState(game: any) {
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
          .filter(
            ([hazardId, turns]) =>
              Number.isFinite(hazardId) && Number.isFinite(turns) && hazardId > 0 && turns > 0
          );
      });
    });
  };

  const normalizeItemIdGrid = (value: any) => {
    if (!Array.isArray(value)) return build2DGrid<number | null>(mapHeight, mapWidth, null);
    return Array.from({ length: mapHeight }, (_, y) => {
      const row = value[y];
      return Array.from({ length: mapWidth }, (_, x) => {
        const v = Array.isArray(row) ? row[x] : null;
        if (v == null) return null;
        const id = Number(v);
        if (!Number.isFinite(id)) return null;
        if (id === RANDOM_TM_ITEM_ID) return RANDOM_TM_ITEM_ID;
        return id > 0 ? id : null;
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
    objective_tiles: Array.isArray(raw.objective_tiles) ? raw.objective_tiles : [],
  };
}

export function normalizeGameData(game: any) {
  if (!game || !game.map) return game;
  return {
    ...game,
    map_state: normalizeGameMapState(game),
  };
}

export function dedupeTiles(tiles: [number, number][]): [number, number][] {
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

export function normalizeAttackOverlay(overlay: {
  normal: [number, number][];
  invert: [number, number][];
}) {
  const normal = dedupeTiles(overlay.normal);
  const normalSet = new Set(normal.map(([x, y]) => `${x},${y}`));
  const invert = dedupeTiles(overlay.invert).filter(([x, y]) => !normalSet.has(`${x},${y}`));
  return { normal, invert };
}

export function parseRangeSpec(move: any): { kind: string; offset: number } {
  const raw = String(move?.range_type ?? move?.range ?? move?.targeting ?? "")
    .toLowerCase()
    .trim();
  const m = raw.match(/^([a-z_]+)(?::(\d+))?$/);
  const kind = m?.[1] ?? "";
  const offset = m?.[2] ? parseInt(m[2], 10) : 0;
  return { kind, offset };
}

function makeInBounds(mapWidth: number, mapHeight: number) {
  return (x: number, y: number) => x >= 0 && y >= 0 && x < mapWidth && y < mapHeight;
}

export function getAdjacentTiles(
  [x, y]: [number, number],
  mapWidth: number,
  mapHeight: number
): [number, number][] {
  const cand: [number, number][] = [
    [x, y - 1],
    [x, y + 1],
    [x - 1, y],
    [x + 1, y],
  ];
  return cand.filter(([cx, cy]) => cx >= 0 && cy >= 0 && cx < mapWidth && cy < mapHeight);
}

export function getBlastTiles(
  [x, y]: [number, number],
  offset: number,
  mapWidth: number,
  mapHeight: number
) {
  const tiles: [number, number][] = [];
  const inBounds = makeInBounds(mapWidth, mapHeight);
  const pushIfIn = (tx: number, ty: number) => {
    if (inBounds(tx, ty)) tiles.push([tx, ty]);
  };

  const uy1 = y - offset;
  const uy2 = y - (offset + 1);
  for (let dx = -1; dx <= 1; dx++) {
    pushIfIn(x + dx, uy1);
    pushIfIn(x + dx, uy2);
  }

  const dy1 = y + offset;
  const dy2 = y + (offset + 1);
  for (let dx = -1; dx <= 1; dx++) {
    pushIfIn(x + dx, dy1);
    pushIfIn(x + dx, dy2);
  }

  const lx1 = x - offset;
  const lx2 = x - (offset + 1);
  for (let dy = -1; dy <= 1; dy++) {
    pushIfIn(lx1, y + dy);
    pushIfIn(lx2, y + dy);
  }

  const rx1 = x + offset;
  const rx2 = x + (offset + 1);
  for (let dy = -1; dy <= 1; dy++) {
    pushIfIn(rx1, y + dy);
    pushIfIn(rx2, y + dy);
  }

  return tiles;
}

export function getInvertedConeTiles(
  [x, y]: [number, number],
  range: number,
  mapWidth: number,
  mapHeight: number
) {
  const tiles: [number, number][] = [];
  const inBounds = makeInBounds(mapWidth, mapHeight);
  const pushIfIn = (tx: number, ty: number) => {
    if (inBounds(tx, ty)) tiles.push([tx, ty]);
  };

  const includeMiddles = range % 2 === 0;
  const depth = range <= 2 ? 2 : 3;
  const sweeps =
    depth === 2 ? [{ dist: 2, half: 1 }] : [{ dist: 2, half: 1 }, { dist: 3, half: 2 }];

  const allowOffset = (offset: number, half: number) =>
    includeMiddles || Math.abs(offset) > half - 1;

  pushIfIn(x, y - 1);
  for (const { dist, half } of sweeps) {
    for (let dx = -half; dx <= half; dx++) {
      if (allowOffset(dx, half)) pushIfIn(x + dx, y - dist);
    }
  }

  pushIfIn(x, y + 1);
  for (const { dist, half } of sweeps) {
    for (let dx = -half; dx <= half; dx++) {
      if (allowOffset(dx, half)) pushIfIn(x + dx, y + dist);
    }
  }

  pushIfIn(x - 1, y);
  for (const { dist, half } of sweeps) {
    for (let dy = -half; dy <= half; dy++) {
      if (allowOffset(dy, half)) pushIfIn(x - dist, y + dy);
    }
  }

  pushIfIn(x + 1, y);
  for (const { dist, half } of sweeps) {
    for (let dy = -half; dy <= half; dy++) {
      if (allowOffset(dy, half)) pushIfIn(x + dist, y + dy);
    }
  }

  return tiles;
}

export function getXAttackTiles(
  [x, y]: [number, number],
  range: number,
  mapWidth: number,
  mapHeight: number
) {
  const tiles: [number, number][] = [];
  const inBounds = makeInBounds(mapWidth, mapHeight);
  const pushIfIn = (tx: number, ty: number) => {
    if (inBounds(tx, ty)) tiles.push([tx, ty]);
  };

  const attackPoints: [number, number][] = [
    [x, y - range],
    [x, y + range],
    [x - range, y],
    [x + range, y],
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

export function getSweepTiles(
  [x, y]: [number, number],
  offset: number,
  mapWidth: number,
  mapHeight: number
) {
  const tiles: [number, number][] = [];
  const inBounds = makeInBounds(mapWidth, mapHeight);
  const pushIfIn = (tx: number, ty: number) => {
    if (inBounds(tx, ty)) tiles.push([tx, ty]);
  };

  const upY = y - offset;
  for (let dx = -1; dx <= 1; dx++) pushIfIn(x + dx, upY);
  const downY = y + offset;
  for (let dx = -1; dx <= 1; dx++) pushIfIn(x + dx, downY);
  const leftX = x - offset;
  for (let dy = -1; dy <= 1; dy++) pushIfIn(leftX, y + dy);
  const rightX = x + offset;
  for (let dy = -1; dy <= 1; dy++) pushIfIn(rightX, y + dy);

  return tiles;
}

export function getRangedTiles(
  [x, y]: [number, number],
  range: number,
  mapWidth: number,
  mapHeight: number
) {
  const tiles: [number, number][] = [];
  const inBounds = makeInBounds(mapWidth, mapHeight);
  const pushIfIn = (tx: number, ty: number) => {
    if (inBounds(tx, ty)) tiles.push([tx, ty]);
  };
  const distance = range + 1;
  pushIfIn(x, y - distance);
  pushIfIn(x, y + distance);
  pushIfIn(x - distance, y);
  pushIfIn(x + distance, y);
  return tiles;
}

export function getLineTiles(
  [x, y]: [number, number],
  range: number,
  mapWidth: number,
  mapHeight: number
) {
  const tiles: [number, number][] = [];
  const inBounds = makeInBounds(mapWidth, mapHeight);
  const pushIfIn = (tx: number, ty: number) => {
    if (inBounds(tx, ty)) tiles.push([tx, ty]);
  };
  for (let i = 1; i <= range; i++) {
    pushIfIn(x, y - i);
    pushIfIn(x, y + i);
    pushIfIn(x - i, y);
    pushIfIn(x + i, y);
  }
  return tiles;
}

export function getPulseTiles(
  [x, y]: [number, number],
  pulse: number,
  mapWidth: number,
  mapHeight: number
) {
  const tiles: [number, number][] = [];
  const inBounds = makeInBounds(mapWidth, mapHeight);
  const pushIfIn = (tx: number, ty: number) => {
    if (inBounds(tx, ty)) tiles.push([tx, ty]);
  };

  const isExtended = pulse >= 4;
  const radius = isExtended ? 2 : 1;
  const baseMode = ((pulse - 1) % 3) + 1;

  for (let dy = -radius; dy <= radius; dy++) {
    for (let dx = -radius; dx <= radius; dx++) {
      const tx = x + dx;
      const ty = y + dy;
      const manhattan = Math.abs(dx) + Math.abs(dy);
      const chebyshev = Math.max(Math.abs(dx), Math.abs(dy));

      if (baseMode === 1) {
        if (manhattan >= 1 && manhattan <= radius && (dx === 0 || dy === 0)) {
          pushIfIn(tx, ty);
        }
      } else if (baseMode === 2) {
        if (chebyshev >= 1 && chebyshev <= radius) {
          pushIfIn(tx, ty);
        }
      } else if (chebyshev <= radius) {
        pushIfIn(tx, ty);
      }
    }
  }

  return tiles;
}

export function getBombTiles(
  [x, y]: [number, number],
  range: number,
  mapWidth: number,
  mapHeight: number
) {
  const tiles: [number, number][] = [];
  const inBounds = makeInBounds(mapWidth, mapHeight);
  const pushIfIn = (tx: number, ty: number) => {
    if (inBounds(tx, ty)) tiles.push([tx, ty]);
  };

  const includeCenter = range >= 2;
  const distance = 2;
  const attackPoints: [number, number][] = [
    [x, y - distance],
    [x, y + distance],
    [x - distance, y],
    [x + distance, y],
  ];

  for (const [ax, ay] of attackPoints) {
    if (!inBounds(ax, ay)) continue;
    if (includeCenter) pushIfIn(ax, ay);
    pushIfIn(ax, ay - 1);
    pushIfIn(ax, ay + 1);
    pushIfIn(ax - 1, ay);
    pushIfIn(ax + 1, ay);
  }

  return tiles;
}

export function getConeTiles(
  [x, y]: [number, number],
  range: number,
  mapWidth: number,
  mapHeight: number
) {
  const tiles: [number, number][] = [];
  const inBounds = makeInBounds(mapWidth, mapHeight);
  const pushIfIn = (tx: number, ty: number) => {
    if (inBounds(tx, ty)) tiles.push([tx, ty]);
  };

  const includeMiddles = range % 2 === 0;
  const depth = range <= 2 ? 2 : 3;
  const layers =
    depth === 2 ? [{ half: 1 }, { half: 0 }] : [{ half: 2 }, { half: 1 }, { half: 0 }];

  const allowOffset = (offset: number, half: number, layerIndex: number) => {
    if (layerIndex === 0) return true;
    return includeMiddles || Math.abs(offset) > half - 1;
  };

  for (const [sx, sy, horizontal] of [
    [0, -1, false],
    [0, 1, false],
    [-1, 0, true],
    [1, 0, true],
  ] as const) {
    for (let i = 0; i < layers.length; i++) {
      const dist = i + 1;
      const { half } = layers[i];
      const cx = horizontal ? x + sx * dist : x;
      const cy = horizontal ? y : y + sy * dist;
      if (half === 0) {
        pushIfIn(cx, cy);
        continue;
      }
      for (let o = -half; o <= half; o++) {
        if (!allowOffset(o, half, i)) continue;
        if (horizontal) pushIfIn(cx, y + o);
        else pushIfIn(x + o, cy);
      }
    }
  }

  return tiles;
}

export function computeAttackOverlayForMove(
  move: any,
  origin: [number, number] | null,
  mapWidth: number,
  mapHeight: number,
  getDisplacementAttackTilesFn: (tile: [number, number]) => {
    step: [number, number][];
    attack: [number, number][];
  },
  filterInBoundsTilesFn: (
    tiles: [number, number][],
    width: number,
    height: number
  ) => [number, number][]
) {
  let next = { normal: [] as [number, number][], invert: [] as [number, number][] };
  if (!origin || !move) return normalizeAttackOverlay(next);

  const { kind, offset } = parseRangeSpec(move);
  if (kind === "self") {
    next.normal = [origin];
  } else if (kind === "adjacent") {
    next.normal = getAdjacentTiles(origin, mapWidth, mapHeight);
  } else if (kind === "dash_attack" || kind === "jump_attack") {
    const { step, attack } = getDisplacementAttackTilesFn(origin);
    next.invert = filterInBoundsTilesFn(step, mapWidth, mapHeight);
    next.normal = filterInBoundsTilesFn(attack, mapWidth, mapHeight);
  } else if (kind === "blast") {
    next.normal = getBlastTiles(origin, offset || 1, mapWidth, mapHeight);
  } else if (kind === "sweep") {
    next.normal = getSweepTiles(origin, offset || 1, mapWidth, mapHeight);
  } else if (kind === "ranged") {
    next.normal = getRangedTiles(origin, offset || 1, mapWidth, mapHeight);
  } else if (kind === "line") {
    next.normal = getLineTiles(origin, offset || 1, mapWidth, mapHeight);
  } else if (kind === "pulse") {
    next.normal = getPulseTiles(origin, offset || 1, mapWidth, mapHeight);
  } else if (kind === "bomb") {
    next.normal = getBombTiles(origin, offset || 1, mapWidth, mapHeight);
  } else if (kind === "cone") {
    next.normal = getConeTiles(origin, offset || 1, mapWidth, mapHeight);
  } else if (kind === "inverted_cone") {
    next.normal = getInvertedConeTiles(origin, offset || 1, mapWidth, mapHeight);
  } else if (kind === "x_attack") {
    next.normal = getXAttackTiles(origin, offset || 1, mapWidth, mapHeight);
  }

  return normalizeAttackOverlay(next);
}

export function getDirectionalOverlayTiles(args: {
  target: [number, number] | null;
  origin: [number, number] | null;
  activeMove: any;
  attackOverlay: { normal: [number, number][]; invert: [number, number][] };
  mapWidth: number;
  mapHeight: number;
}): [number, number][] {
  const { target, origin, activeMove, attackOverlay, mapWidth, mapHeight } = args;
  if (!target) return [];
  if (!origin) return [];

  const [ox, oy] = origin;
  const [tx, ty] = target;
  const dx = tx - ox;
  const dy = ty - oy;
  const inBounds = makeInBounds(mapWidth, mapHeight);

  if (dx === 0 && dy === 0) return [target];

  const { kind, offset } = parseRangeSpec(activeMove);
  const useHorizontal = Math.abs(dx) >= Math.abs(dy);
  const dir = useHorizontal ? (dx >= 0 ? 1 : -1) : dy >= 0 ? 1 : -1;
  const overlayTiles = [...attackOverlay.normal, ...attackOverlay.invert];

  if (kind === "pulse") {
    return overlayTiles;
  }

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

  if (kind === "bomb") {
    const bombRange = offset > 0 ? offset : 1;
    const distance = 2;
    const cx = useHorizontal ? ox + dir * distance : ox;
    const cy = useHorizontal ? oy : oy + dir * distance;
    const includeCenter = bombRange >= 2;

    return overlayTiles.filter(([x, y]) => {
      const manhattan = Math.abs(x - cx) + Math.abs(y - cy);
      if (includeCenter) return manhattan <= 1;
      return manhattan === 1;
    });
  }

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
