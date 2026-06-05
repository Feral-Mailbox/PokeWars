export const WATER_TILE = "water";
export const ROCK_TILE = "rock";
export const GRASS_TILE = "grass";
export const SAND_TILE = "sand";
export const SAND_MOVEMENT_COST = 2;
export const ICE_TILE = "ice";
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

export function isSandTile(
  specialTiles: unknown[][] | null | undefined,
  x: number,
  y: number
): boolean {
  return getSpecialTile(specialTiles, x, y) === SAND_TILE;
}

export function isIceTile(
  specialTiles: unknown[][] | null | undefined,
  x: number,
  y: number
): boolean {
  return getSpecialTile(specialTiles, x, y) === ICE_TILE;
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

export function unitCanPassThroughUnits(
  types: string[] | null | undefined
): boolean {
  return normalizedTypes(types).has("ghost");
}

export function unitIgnoresSandSlow(
  types: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  const normalized = normalizedTypes(types);
  if (normalized.has("ground") || normalized.has("flying")) return true;
  return unitHasLevitate(types, abilityNames);
}

export function unitIgnoresIceSlide(
  types: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  const normalized = normalizedTypes(types);
  if (normalized.has("ice") || normalized.has("flying")) return true;
  return unitHasLevitate(types, abilityNames);
}

function normalizeStepDirection(dx: number, dy: number): [number, number] {
  const ndx = dx === 0 ? 0 : dx > 0 ? 1 : -1;
  const ndy = dy === 0 ? 0 : dy > 0 ? 1 : -1;
  return [ndx, ndy];
}

export function findShortestPath(
  start: [number, number],
  end: [number, number],
  movementCosts: number[][],
  specialTiles: unknown[][] | null | undefined,
  width: number,
  height: number,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null,
  blockedTiles?: Set<string>
): [number, number][] | null {
  const [sx, sy] = start;
  const [ex, ey] = end;
  if (sx === ex && sy === ey) return [start];

  const blocked = blockedTiles ?? new Set<string>();
  const parent = new Map<string, [number, number]>();
  const queue: [number, number][] = [[sx, sy]];
  const seen = new Set<string>([`${sx},${sy}`]);
  const directions: [number, number][] = [
    [1, 0],
    [-1, 0],
    [0, 1],
    [0, -1],
  ];

  while (queue.length > 0) {
    const [x, y] = queue.shift()!;
    if (x === ex && y === ey) {
      const path: [number, number][] = [[ex, ey]];
      let cur: [number, number] = [ex, ey];
      while (parent.has(`${cur[0]},${cur[1]}`)) {
        cur = parent.get(`${cur[0]},${cur[1]}`)!;
        path.push(cur);
      }
      path.reverse();
      return path;
    }

    for (const [dx, dy] of directions) {
      const nx = x + dx;
      const ny = y + dy;
      if (nx < 0 || ny < 0 || nx >= width || ny >= height) continue;
      const key = `${nx},${ny}`;
      if (blocked.has(key) || seen.has(key)) continue;
      if (!canEnterTile(specialTiles, x, y, nx, ny, unitTypes, abilityNames)) continue;
      const stepCost = movementCosts[ny][nx];
      if (stepCost >= IMPOSSIBLE_MOVEMENT_COST) continue;
      seen.add(key);
      parent.set(key, [x, y]);
      queue.push([nx, ny]);
    }
  }

  return null;
}

export function slideOnIceFrom(
  iceX: number,
  iceY: number,
  dx: number,
  dy: number,
  specialTiles: unknown[][] | null | undefined,
  width: number,
  height: number,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null,
  occupiedTiles?: Set<string>
): [number, number] {
  const occupied = occupiedTiles ?? new Set<string>();
  let x = iceX;
  let y = iceY;

  while (true) {
    const nx = x + dx;
    const ny = y + dy;
    if (nx < 0 || ny < 0 || nx >= width || ny >= height) return [x, y];
    const key = `${nx},${ny}`;
    if (occupied.has(key)) return [x, y];
    if (!unitCanOccupyTile(specialTiles, nx, ny, unitTypes, abilityNames)) return [x, y];
    if (!isIceTile(specialTiles, nx, ny)) return [nx, ny];
    x = nx;
    y = ny;
  }
}

export function resolveMovementDestination(
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  movementCosts: number[][],
  specialTiles: unknown[][] | null | undefined,
  width: number,
  height: number,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null,
  blockedTiles?: Set<string>,
  occupiedTiles?: Set<string>
): { x: number; y: number; slid: boolean } {
  if (unitIgnoresIceSlide(unitTypes, abilityNames)) {
    return { x: toX, y: toY, slid: false };
  }

  const path = findShortestPath(
    [fromX, fromY],
    [toX, toY],
    movementCosts,
    specialTiles,
    width,
    height,
    unitTypes,
    abilityNames,
    blockedTiles
  );
  if (!path) return { x: toX, y: toY, slid: false };

  for (let idx = 1; idx < path.length; idx++) {
    const [px, py] = path[idx];
    const [prevX, prevY] = path[idx - 1];
    if (!isIceTile(specialTiles, px, py)) continue;
    if (isIceTile(specialTiles, prevX, prevY)) continue;
    const [dx, dy] = normalizeStepDirection(px - prevX, py - prevY);
    if (dx === 0 && dy === 0) continue;
    const [fx, fy] = slideOnIceFrom(
      px,
      py,
      dx,
      dy,
      specialTiles,
      width,
      height,
      unitTypes,
      abilityNames,
      occupiedTiles
    );
    return { x: fx, y: fy, slid: true };
  }

  return { x: toX, y: toY, slid: false };
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
  const ignoresSandSlow = unitIgnoresSandSlow(unitTypes, abilityNames);

  return baseCosts.map((row, y) =>
    row.map((cost, x) => {
      const tile = getSpecialTile(specialTiles, x, y);
      if (tile === WATER_TILE && !canWater) return IMPOSSIBLE_MOVEMENT_COST;
      if (tile === ROCK_TILE && !canRock) return IMPOSSIBLE_MOVEMENT_COST;
      if (tile != null && LEDGE_TILES.has(tile) && !canStandOnLedge) return 0;
      if (tile === SAND_TILE && !ignoresSandSlow) return SAND_MOVEMENT_COST;
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
