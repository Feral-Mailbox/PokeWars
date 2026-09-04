export type TitanicFootprint = {
  north: number;
  west: number;
  east: number;
};

export const DEFAULT_TITANIC_FOOTPRINT: TitanicFootprint = {
  north: 3,
  west: 1,
  east: 1,
};

type TitanicUnitLike = {
  is_titanic?: boolean;
  titanic_footprint?: Partial<TitanicFootprint> | null;
};

type PlacedLike = {
  tile: [number, number];
  unit?: TitanicUnitLike | null;
};

function positiveInt(value: unknown, fallback: number): number {
  const n = Number(value);
  if (!Number.isFinite(n) || n < 0) return fallback;
  return Math.floor(n);
}

/** Resolve footprint for a catalog unit marked titanic; null if not titanic. */
export function resolveTitanicFootprint(
  unit: TitanicUnitLike | null | undefined
): TitanicFootprint | null {
  if (!unit?.is_titanic) return null;
  const fp = unit.titanic_footprint;
  return {
    north: positiveInt(fp?.north, DEFAULT_TITANIC_FOOTPRINT.north),
    west: positiveInt(fp?.west, DEFAULT_TITANIC_FOOTPRINT.west),
    east: positiveInt(fp?.east, DEFAULT_TITANIC_FOOTPRINT.east),
  };
}

/**
 * Map of "x,y" → southernmost titanic tile Y that visually covers that cell.
 * Used so units "behind" a titanic sprite can outline above it.
 */
export function buildTitanicOcclusionMap(
  units: PlacedLike[]
): Map<string, number> {
  const occlusion = new Map<string, number>();

  for (const placed of units) {
    const footprint = resolveTitanicFootprint(placed.unit);
    if (!footprint || footprint.north <= 0) continue;

    const [tx, ty] = placed.tile;
    for (let dy = 1; dy <= footprint.north; dy++) {
      const y = ty - dy;
      for (let dx = -footprint.west; dx <= footprint.east; dx++) {
        const x = tx + dx;
        const key = `${x},${y}`;
        const prev = occlusion.get(key);
        if (prev === undefined || ty > prev) {
          occlusion.set(key, ty);
        }
      }
    }
  }

  return occlusion;
}
