import { DEFAULT_MOVEMENT_COST, type MapLayer, type MapTileData, type TileRef } from "@/types/mapData";

export type DrawingTool = "pencil" | "box" | "eraser";

export const DRAWING_TOOL_LABELS: Record<DrawingTool, string> = {
  pencil: "Pencil",
  box: "Box",
  eraser: "Eraser",
};

export function normalizeRect(
  x0: number,
  y0: number,
  x1: number,
  y1: number
): { minX: number; minY: number; maxX: number; maxY: number } {
  return {
    minX: Math.min(x0, x1),
    minY: Math.min(y0, y1),
    maxX: Math.max(x0, x1),
    maxY: Math.max(y0, y1),
  };
}

type FillRectOptions = {
  layer: MapLayer;
  erase: boolean;
  selectedTile: TileRef;
  spawnBrush: number | null;
  specialBrush: string;
  flagBrush: number | null;
  movementCostBrush: number;
};

function applyPaintCell(data: MapTileData, x: number, y: number, options: FillRectOptions) {
  switch (options.layer) {
    case "base":
      data.base[y][x] = [...options.selectedTile] as TileRef;
      break;
    case "overlay":
      data.overlay[y][x] = [...options.selectedTile] as TileRef;
      break;
    case "overlay2":
      data.overlay2[y][x] = [...options.selectedTile] as TileRef;
      break;
    case "overlay3":
      data.overlay3[y][x] = [...options.selectedTile] as TileRef;
      break;
    case "spawn_points":
      data.spawn_points[y][x] = options.spawnBrush;
      break;
    case "special_tiles":
      data.special_tiles[y][x] = options.specialBrush;
      break;
    case "flags":
      data.flags[y][x] = options.flagBrush;
      break;
    case "movement_cost":
      data.movement_cost[y][x] = options.movementCostBrush;
      break;
  }
}

function applyEraseCell(data: MapTileData, x: number, y: number, layer: MapLayer) {
  switch (layer) {
    case "base":
      data.base[y][x] = [0, 0];
      break;
    case "overlay":
      data.overlay[y][x] = null;
      break;
    case "overlay2":
      data.overlay2[y][x] = null;
      break;
    case "overlay3":
      data.overlay3[y][x] = null;
      break;
    case "spawn_points":
      data.spawn_points[y][x] = null;
      break;
    case "special_tiles":
      data.special_tiles[y][x] = null;
      break;
    case "flags":
      data.flags[y][x] = null;
      break;
    case "movement_cost":
      data.movement_cost[y][x] = DEFAULT_MOVEMENT_COST;
      break;
  }
}

export function fillRectOnMap(
  snapshot: MapTileData,
  x0: number,
  y0: number,
  x1: number,
  y1: number,
  options: FillRectOptions
): MapTileData {
  const next = structuredClone(snapshot);
  const { minX, minY, maxX, maxY } = normalizeRect(x0, y0, x1, y1);
  const mapHeight = next.base.length;
  const mapWidth = next.base[0]?.length ?? 0;

  for (let y = minY; y <= maxY; y++) {
    if (y < 0 || y >= mapHeight) continue;
    for (let x = minX; x <= maxX; x++) {
      if (x < 0 || x >= mapWidth) continue;
      if (options.erase) {
        applyEraseCell(next, x, y, options.layer);
      } else {
        applyPaintCell(next, x, y, options);
      }
    }
  }

  return next;
}

export function paintCellOnMap(
  snapshot: MapTileData,
  x: number,
  y: number,
  options: FillRectOptions
): MapTileData {
  const next = structuredClone(snapshot);
  if (options.erase) {
    applyEraseCell(next, x, y, options.layer);
  } else {
    applyPaintCell(next, x, y, options);
  }
  return next;
}
