export type Tile = [number, number];

export const DISPLACEMENT_MOVE_KINDS = new Set(["dash_attack", "jump_attack"]);

export function isDisplacementMoveKind(kind: string): boolean {
  return DISPLACEMENT_MOVE_KINDS.has(kind);
}

export function getDisplacementAttackTiles([x, y]: Tile): { step: Tile[]; attack: Tile[] } {
  const step: Tile[] = [
    [x, y - 1],
    [x, y + 1],
    [x - 1, y],
    [x + 1, y],
  ];

  const attack: Tile[] = [
    [x, y - 2],
    [x, y + 2],
    [x - 2, y],
    [x + 2, y],
  ];

  return { step, attack };
}

export function filterInBoundsTiles(
  tiles: Tile[],
  width: number,
  height: number
): Tile[] {
  return tiles.filter(([cx, cy]) => cx >= 0 && cy >= 0 && cx < width && cy < height);
}

/** Landing tile for dash/jump attacks from origin toward the selected effect tile. */
export function getDisplacementLandingTile(
  origin: Tile | null,
  target: Tile | null,
  kind: string
): Tile | null {
  if (!origin || !target || !isDisplacementMoveKind(kind)) return null;

  const [ax, ay] = origin;
  const [tx, ty] = target;
  const dx = tx - ax;
  const dy = ty - ay;
  if (dx === 0 && dy === 0) return null;

  const dist = Math.abs(dx) + Math.abs(dy);
  if (dist !== 1 && dist !== 2) return null;
  if (dx !== 0 && dy !== 0) return null;

  if (dist === 1) return [tx, ty];

  return [ax + dx / 2, ay + dy / 2];
}

export function getDisplacementLandingTilesFromEffectTiles(
  origin: Tile,
  effectTiles: Tile[],
  kind: string
): Tile | null {
  if (!isDisplacementMoveKind(kind) || effectTiles.length === 0) return null;

  const [ax, ay] = origin;
  let best: Tile | null = null;
  let bestDist = 0;

  for (const [tx, ty] of effectTiles) {
    const dx = tx - ax;
    const dy = ty - ay;
    if (dx !== 0 && dy !== 0) continue;
    const dist = Math.abs(dx) + Math.abs(dy);
    if (dist !== 1 && dist !== 2) continue;
    if (dist > bestDist) {
      bestDist = dist;
      best = [tx, ty];
    }
  }

  if (!best) return null;
  return getDisplacementLandingTile(origin, best, kind);
}
