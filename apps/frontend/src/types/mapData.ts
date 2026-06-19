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
  item_id_tiles: (number | null)[][];
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
  | "war"
  | "flags"
  | "movement_cost"
  | "items";

/** Maps are playable in Conquest; War objectives are placed via the War layer. */
export const DEFAULT_MAP_ALLOWED_MODES = ["Conquest", "War"] as const;

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

export type WarObjectiveKind = "pokeball" | "master_ball";

const WAR_OBJECTIVE_PATTERN =
  /^(pokeball(?:_p([1-8]))?|master_ball_p([1-8]))$/;

/** Encodes a War objective for storage in special_tiles. */
export function encodeWarObjective(kind: WarObjectiveKind, owner: number | null): string {
  if (kind === "master_ball") {
    if (owner == null || owner < 1 || owner > 8) {
      throw new Error("Master balls must belong to a player (P1–P8).");
    }
    return `master_ball_p${owner}`;
  }
  if (owner == null || owner < 1) {
    return "pokeball";
  }
  return `pokeball_p${owner}`;
}

export function isWarObjectiveTile(value: string | null | undefined): boolean {
  if (!value) return false;
  return WAR_OBJECTIVE_PATTERN.test(value);
}

export function parseWarObjectiveTile(value: string): {
  kind: WarObjectiveKind;
  owner: number | null;
} | null {
  if (value === "pokeball") {
    return { kind: "pokeball", owner: null };
  }
  const pokeMatch = value.match(/^pokeball_p([1-8])$/);
  if (pokeMatch) {
    return { kind: "pokeball", owner: Number(pokeMatch[1]) };
  }
  const masterMatch = value.match(/^master_ball_p([1-8])$/);
  if (masterMatch) {
    return { kind: "master_ball", owner: Number(masterMatch[1]) };
  }
  return null;
}

/** Placeholder item id for map tiles that resolve to a random TM at game start. */
export const RANDOM_TM_ITEM_ID = 0;
