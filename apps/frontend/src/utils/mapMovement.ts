export const WATER_TILE = "water";
export const IMPOSSIBLE_MOVEMENT_COST = 1_000_000_000;

export function normalizeSpecialTile(cell: unknown): string | null {
  if (cell == null) return null;
  if (typeof cell === "string") {
    const value = cell.trim().toLowerCase();
    return value || null;
  }
  return null;
}

export function isWaterTile(
  specialTiles: unknown[][] | null | undefined,
  x: number,
  y: number
): boolean {
  if (!specialTiles || y < 0 || x < 0 || y >= specialTiles.length) return false;
  const row = specialTiles[y];
  if (!Array.isArray(row) || x >= row.length) return false;
  return normalizeSpecialTile(row[x]) === WATER_TILE;
}

export function unitCanCrossWater(
  types: string[] | null | undefined,
  abilityNames?: string[] | null
): boolean {
  const normalized = new Set(
    (types ?? []).map((t) => String(t).trim().toLowerCase()).filter(Boolean)
  );
  if (normalized.has("water") || normalized.has("flying")) return true;
  if (abilityNames?.some((a) => String(a).trim().toLowerCase() === "levitate")) {
    return true;
  }
  return false;
}

export function buildMovementCostGrid(
  baseCosts: number[][],
  specialTiles: unknown[][] | null | undefined,
  canCrossWater: boolean
): number[][] {
  if (canCrossWater || !specialTiles?.length) return baseCosts;

  return baseCosts.map((row, y) =>
    row.map((cost, x) =>
      isWaterTile(specialTiles, x, y) ? IMPOSSIBLE_MOVEMENT_COST : cost
    )
  );
}

/** Remove water tiles from a movement list when the unit cannot walk on water. */
export function filterMovementTilesForUnit(
  tiles: [number, number][],
  specialTiles: unknown[][] | null | undefined,
  unitTypes: string[] | null | undefined,
  abilityNames?: string[] | null
): [number, number][] {
  if (unitCanCrossWater(unitTypes, abilityNames)) return tiles;
  if (!specialTiles?.length) return tiles;
  return tiles.filter(([x, y]) => !isWaterTile(specialTiles, x, y));
}
