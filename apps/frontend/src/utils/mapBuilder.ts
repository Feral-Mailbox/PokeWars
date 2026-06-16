import type { MapExport, MapTileData, TileRef } from "@/types/mapData";
import { DEFAULT_MOVEMENT_COST } from "@/types/mapData";

export function createEmptyTileData(width: number, height: number): MapTileData {
  const base: TileRef[][] = [];
  const overlay: (TileRef | null)[][] = [];
  const overlay2: (TileRef | null)[][] = [];
  const overlay3: (TileRef | null)[][] = [];
  const spawn_points: (number | null)[][] = [];
  const special_tiles: (string | null)[][] = [];
  const flags: (number | null)[][] = [];
  const movement_cost: number[][] = [];

  for (let y = 0; y < height; y++) {
    base.push(Array.from({ length: width }, () => [0, 0] as TileRef));
    overlay.push(Array.from({ length: width }, () => null));
    overlay2.push(Array.from({ length: width }, () => null));
    overlay3.push(Array.from({ length: width }, () => null));
    spawn_points.push(Array.from({ length: width }, () => null));
    special_tiles.push(Array.from({ length: width }, () => null));
    flags.push(Array.from({ length: width }, () => null));
    movement_cost.push(Array.from({ length: width }, () => DEFAULT_MOVEMENT_COST));
  }

  return { base, overlay, overlay2, overlay3, spawn_points, special_tiles, flags, movement_cost };
}

export function normalizeTileData(raw: Partial<MapTileData>, width: number, height: number): MapTileData {
  const empty = createEmptyTileData(width, height);
  if (!raw.base?.length) return empty;

  const mapHeight = Math.min(height, raw.base.length);
  const mapWidth = Math.min(width, raw.base[0]?.length ?? 0);

  for (let y = 0; y < mapHeight; y++) {
    for (let x = 0; x < mapWidth; x++) {
      if (raw.base[y]?.[x]) {
        empty.base[y][x] = [...raw.base[y][x]] as TileRef;
      }
      if (raw.overlay?.[y]?.[x]) {
        empty.overlay[y][x] = [...raw.overlay[y][x]!] as TileRef;
      }
      if (raw.overlay2?.[y]?.[x]) {
        empty.overlay2[y][x] = [...raw.overlay2[y][x]!] as TileRef;
      }
      if (raw.overlay3?.[y]?.[x]) {
        empty.overlay3[y][x] = [...raw.overlay3[y][x]!] as TileRef;
      }
      if (raw.spawn_points?.[y]?.[x] != null) {
        empty.spawn_points[y][x] = raw.spawn_points[y][x];
      }
      if (raw.special_tiles?.[y]?.[x] != null) {
        empty.special_tiles[y][x] = raw.special_tiles[y][x];
      }
      if (raw.flags?.[y]?.[x] != null) {
        empty.flags[y][x] = raw.flags[y][x];
      }
      const cost = raw.movement_cost?.[y]?.[x];
      if (typeof cost === "number" && cost >= 1) {
        empty.movement_cost[y][x] = cost;
      }
    }
  }

  return empty;
}

export function resizeTileData(
  tileData: MapTileData,
  oldWidth: number,
  oldHeight: number,
  newWidth: number,
  newHeight: number
): MapTileData {
  const next = createEmptyTileData(newWidth, newHeight);

  for (let y = 0; y < Math.min(oldHeight, newHeight); y++) {
    for (let x = 0; x < Math.min(oldWidth, newWidth); x++) {
      next.base[y][x] = [...tileData.base[y][x]] as TileRef;
      next.overlay[y][x] = tileData.overlay[y][x]
        ? ([...tileData.overlay[y][x]!] as TileRef)
        : null;
      next.overlay2[y][x] = tileData.overlay2?.[y]?.[x]
        ? ([...tileData.overlay2[y][x]!] as TileRef)
        : null;
      next.overlay3[y][x] = tileData.overlay3?.[y]?.[x]
        ? ([...tileData.overlay3[y][x]!] as TileRef)
        : null;
      next.spawn_points[y][x] = tileData.spawn_points[y][x];
      next.special_tiles[y][x] = tileData.special_tiles[y][x];
      next.flags[y][x] = tileData.flags[y][x];
      next.movement_cost[y][x] = tileData.movement_cost[y][x];
    }
  }

  return next;
}

export function slugifyMapName(name: string): string {
  return name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "")
    .slice(0, 64);
}

export function buildMapExport(input: {
  name: string;
  tilesetNames: string[];
  allowedModes: string[];
  allowedPlayerCounts: number[];
  width: number;
  height: number;
  tileData: MapTileData;
}): MapExport {
  const slug = slugifyMapName(input.name) || "custom_map";
  return {
    name: input.name.trim() || "Untitled Map",
    is_official: false,
    tileset_names: input.tilesetNames,
    allowed_modes: input.allowedModes,
    allowed_player_counts: input.allowedPlayerCounts,
    width: input.width,
    height: input.height,
    tile_data: input.tileData,
    preview_image: `previews/${slug}.png`,
  };
}

export function downloadMapJson(map: MapExport): void {
  const blob = new Blob([JSON.stringify(map, null, 4)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `${slugifyMapName(map.name) || "map"}.json`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function parseMapImport(raw: unknown): MapExport {
  if (!raw || typeof raw !== "object") {
    throw new Error("Invalid map file");
  }
  const map = raw as Partial<MapExport>;
  if (
    typeof map.name !== "string" ||
    !Array.isArray(map.tileset_names) ||
    !Array.isArray(map.allowed_modes) ||
    !Array.isArray(map.allowed_player_counts) ||
    typeof map.width !== "number" ||
    typeof map.height !== "number" ||
    !map.tile_data
  ) {
    throw new Error("Map file is missing required fields");
  }
  return {
    ...(map as MapExport),
    tile_data: normalizeTileData(map.tile_data as Partial<MapTileData>, map.width!, map.height!),
  };
}
