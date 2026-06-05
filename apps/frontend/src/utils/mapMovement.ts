export const WATER_TILE = "water";
export const ROCK_TILE = "rock";
export const GRASS_TILE = "grass";
export const LEDGE_UP = "ledge_up";
export const LEDGE_DOWN = "ledge_down";
export const LEDGE_LEFT = "ledge_left";
export const LEDGE_RIGHT = "ledge_right";
const LEDGE_TILES = new Set([
  LEDGE_UP,
  LEDGE_DOWN,
  LEDGE_LEFT,
  LEDGE_RIGHT,
]);
export const IMPOSSIBLE_MOVEMENT_COST = 1_000_000_000;

export function normalizeSpecialTile(cell: unknown): string | null {
  if (cell == null) return null;
  if (typeof cell === "string") {
    const value = cell.trim().toLowerCase();
    return value || null;
  }
  return null;
}

export function getSpecialTile(
  specialTiles: unknown[][] | null | undefined,
  x: number,
  y: number
): string | null {
  if (!specialTiles || y < 0 || x < 0 || y >= specialTiles.length) return null;
  const row = specialTiles[y];
  if (!Array.isArray(row) || x >= row.length) return null;
  return normalizeSpecialTile(row[x]);
}

export function isWaterTile(
  specialTiles: unknown[][] | null | undefined,
  x: number,
  y: number
): boolean {
  return getSpecialTile(specialTiles, x, y) === WATER_TILE;
}

export function isRockTile(
  specialTiles: unknown[][] | null | undefined,
  x: number,
  y: number
): boolean {
  return getSpecialTile(specialTiles, x, y) === ROCK_TILE;
}

export function isLedgeTile(
  specialTiles: unknown[][] | null | undefined,
  x: number,
  y: number
): boolean {
  const tile = getSpecialTile(specialTiles, x, y);
  return tile != null && LEDGE_TILES.has(tile);
}

function normalizedTypes(types: string[] | null | undefined): Set<string> {
  return new Set(
    (types ?? []).map((t) => String(t).trim().toLowerCase()).filter(Boolean)
  );
}

function normalizedAbilities(abilityNames?: string[] | null): Set<string> {
  return new Set(
    (abilityNames ?? []).map((a) => String(a).trim().toLowerCase()).filter(Boolean)
  );
}

export function unitHasLevitate(
  types: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  return normalizedAbilities(abilityNames).has("levitate");
}

export function unitCanCrossWater(
  types: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  const normalized = normalizedTypes(types);
  if (normalized.has("water") || normalized.has("flying")) return true;
  return unitHasLevitate(types, abilityNames);
}

export function unitCanCrossRock(
  types: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  const normalized = normalizedTypes(types);
  if (normalized.has("flying") || normalized.has("rock")) return true;
  return unitHasLevitate(types, abilityNames);
}

export function unitCanStandOnLedge(
  types: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  const normalized = normalizedTypes(types);
  if (normalized.has("flying")) return true;
  return unitHasLevitate(types, abilityNames);
}

export function ledgeAllowsEntry(
  tile: string,
  fromX: number,
  fromY: number,
  toX: number,
  toY: number
): boolean {
  const dx = toX - fromX;
  const dy = toY - fromY;
  if (tile === LEDGE_UP) return dy === -1;
  if (tile === LEDGE_DOWN) return dy === 1;
  if (tile === LEDGE_LEFT) return dx === -1;
  if (tile === LEDGE_RIGHT) return dx === 1;
  return false;
}

export function canEnterTile(
  specialTiles: unknown[][] | null | undefined,
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  const tile = getSpecialTile(specialTiles, toX, toY);
  if (tile == null) return true;
  if (LEDGE_TILES.has(tile)) {
    if (unitCanStandOnLedge(unitTypes, abilityNames)) return true;
    return ledgeAllowsEntry(tile, fromX, fromY, toX, toY);
  }
  return true;
}

export function isValidMovementDestination(
  specialTiles: unknown[][] | null | undefined,
  x: number,
  y: number,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  const tile = getSpecialTile(specialTiles, x, y);
  if (tile != null && LEDGE_TILES.has(tile) && !unitCanStandOnLedge(unitTypes, abilityNames)) {
    return false;
  }
  return true;
}

export function buildMovementCostGrid(
  baseCosts: number[][],
  specialTiles: unknown[][] | null | undefined,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null
): number[][] {
  if (!specialTiles?.length) return baseCosts;

  const canWater = unitCanCrossWater(unitTypes, abilityNames);
  const canRock = unitCanCrossRock(unitTypes, abilityNames);
  const canStandOnLedge = unitCanStandOnLedge(unitTypes, abilityNames);

  return baseCosts.map((row, y) =>
    row.map((cost, x) => {
      const tile = getSpecialTile(specialTiles, x, y);
      if (tile === WATER_TILE && !canWater) return IMPOSSIBLE_MOVEMENT_COST;
      if (tile === ROCK_TILE && !canRock) return IMPOSSIBLE_MOVEMENT_COST;
      if (tile != null && LEDGE_TILES.has(tile) && !canStandOnLedge) return 0;
      return cost;
    })
  );
}

export function getMovementRangeWithTerrain(
  start: [number, number],
  range: number,
  movementCosts: number[][],
  specialTiles: unknown[][] | null | undefined,
  width: number,
  height: number,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null,
  blockedTiles?: Set<string>
): [number, number][] {
  const visited = new Set<string>();
  const result: [number, number][] = [];
  const queue: Array<{ x: number; y: number; cost: number }> = [
    { x: start[0], y: start[1], cost: 0 },
  ];

  const directions = [
    [0, 1],
    [0, -1],
    [1, 0],
    [-1, 0],
  ];

  while (queue.length > 0) {
    const { x, y, cost } = queue.shift()!;
    const key = `${x},${y}`;
    if (visited.has(key) || x < 0 || y < 0 || x >= width || y >= height) continue;
    visited.add(key);

    if (isValidMovementDestination(specialTiles, x, y, unitTypes, abilityNames)) {
      result.push([x, y]);
    }

    for (const [dx, dy] of directions) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;

      const nextKey = `${nx},${ny}`;
      if (blockedTiles?.has(nextKey)) continue;
      if (visited.has(nextKey)) continue;
      if (!canEnterTile(specialTiles, x, y, nx, ny, unitTypes, abilityNames)) continue;

      const stepCost = movementCosts[ny][nx];
      if (stepCost >= IMPOSSIBLE_MOVEMENT_COST) continue;

      const nextCost = cost + stepCost;
      if (nextCost <= range) {
        queue.push({ x: nx, y: ny, cost: nextCost });
      }
    }
  }

  return result;
}

export function unitCanOccupyTile(
  specialTiles: unknown[][] | null | undefined,
  x: number,
  y: number,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  const tile = getSpecialTile(specialTiles, x, y);
  if (tile === WATER_TILE) return unitCanCrossWater(unitTypes, abilityNames);
  if (tile === ROCK_TILE) return unitCanCrossRock(unitTypes, abilityNames);
  if (tile != null && LEDGE_TILES.has(tile)) {
    return unitCanStandOnLedge(unitTypes, abilityNames);
  }
  return true;
}

/** Remove tiles the unit cannot stop on from a movement list. */
export function filterMovementTilesForUnit(
  tiles: [number, number][],
  specialTiles: unknown[][] | null | undefined,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null
): [number, number][] {
  if (!specialTiles?.length) return tiles;
  return tiles.filter(([x, y]) =>
    isValidMovementDestination(specialTiles, x, y, unitTypes, abilityNames) &&
    unitCanOccupyTile(specialTiles, x, y, unitTypes, abilityNames)
  );
}
