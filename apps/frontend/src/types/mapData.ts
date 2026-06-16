export type TileRef = [number, number];

export type MapTileData = {
  base: TileRef[][];
  overlay: (TileRef | null)[][];
  overlay2: (TileRef | null)[][];
  overlay3: (TileRef | null)[][];
  spawn_points: (number | null)[][];
  special_tiles: (string | null)[][];
  flags: (number | null)[][];
  movement_cost: number[][];
};

export type MapExport = {
  name: string;
  is_official: boolean;
  tileset_names: string[];
  allowed_modes: string[];
  allowed_player_counts: number[];
  width: number;
  height: number;
  tile_data: MapTileData;
  preview_image: string;
};

export type MapLayer =
  | "base"
  | "overlay"
  | "overlay2"
  | "overlay3"
  | "spawn_points"
  | "special_tiles"
  | "flags"
  | "movement_cost";

export const GAME_MODES = ["Conquest", "War", "Capture The Flag"] as const;

export const MAX_PLAYERS = 8;

export const PLAYER_COUNTS = [2, 3, 4, 5, 6, 7, 8] as const;

export const PLAYER_IDS = [1, 2, 3, 4, 5, 6, 7, 8] as const;

/** Default movement cost for passable tiles. */
export const DEFAULT_MOVEMENT_COST = 1;

/** Paintable movement cost values in the map builder. */
export const MOVEMENT_COST_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9] as const;

export const SPECIAL_TILE_TYPES = [
  "impassable",
  "water",
  "grass",
  "stump",
  "rock",
  "sand",
  "ice",
  "ledge_up",
  "ledge_down",
  "ledge_left",
  "ledge_right",
] as const;

export type SpecialTileType = (typeof SPECIAL_TILE_TYPES)[number];
