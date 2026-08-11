export type TileRef = [number, number];

export type MapTileData = {
  base: (TileRef | null)[][];
  overlay: (TileRef | null)[][];
  overlay2: (TileRef | null)[][];
  overlay3: (TileRef | null)[][];
  spawn_points: (number | null)[][];
  special_tiles: (string | null)[][];
  flags: (number | null)[][];
  movement_cost: number[][];
  item_id_tiles: (number | null)[][];
  /** Solid fill used for cells whose base is null or does not map to a tileset tile. */
  background_color?: string;
};

export const DEFAULT_MAP_BACKGROUND_COLOR = "#000000";

export function isValidTileRef(tile: TileRef | null | undefined): tile is TileRef {
  if (tile == null || !Array.isArray(tile) || tile.length < 2) return false;
  const [rawIndex, rawTileset] = tile;
  if (rawIndex == null || rawTileset == null) return false;
  const tileIndex = Number(rawIndex);
  const tilesetIndex = Number(rawTileset);
  return Number.isFinite(tileIndex) && Number.isFinite(tilesetIndex) && tileIndex >= 0 && tilesetIndex >= 0;
}

/** True when the cell has no tile id to draw (null / invalid). */
export function isVoidTileRef(tile: TileRef | null | undefined): boolean {
  return !isValidTileRef(tile);
}

export function normalizeBackgroundColor(value: unknown): string {
  if (typeof value !== "string") return DEFAULT_MAP_BACKGROUND_COLOR;
  const trimmed = value.trim();
  if (/^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/.test(trimmed)) {
    return trimmed;
  }
  return DEFAULT_MAP_BACKGROUND_COLOR;
}

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

/** Conquest is always playable. War is selected by default; CTF is opt-in. */
export const DEFAULT_MAP_ALLOWED_MODES = ["Conquest", "War"] as const;

export const GAME_MODES = ["Conquest", "War", "Capture The Flag"] as const;

export type GameModeName = (typeof GAME_MODES)[number];

export function normalizeAllowedModes(modes: unknown): GameModeName[] {
  const selected = new Set<GameModeName>(["Conquest"]);
  if (Array.isArray(modes)) {
    for (const mode of modes) {
      if (mode === "War" || mode === "Capture The Flag") {
        selected.add(mode);
      }
    }
  }
  return GAME_MODES.filter((mode) => selected.has(mode));
}

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
  "sky",
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

export const CTF_JAIL_TILE = "ctf_jail";
export const CTF_UNLOCK_TILE = "ctf_unlock";

export type CtfBrushKind = "flag" | "jail";

const CTF_JAIL_PATTERN = /^ctf_jail(?:_p([1-8]))?$/i;

export function encodeCtfJail(owner: number): string {
  return `${CTF_JAIL_TILE}_p${owner}`;
}

export function parseCtfJailTile(value: string | null | undefined): { owner: number } | null {
  if (!value) return null;
  const match = value.trim().match(CTF_JAIL_PATTERN);
  if (!match) return null;
  if (match[1] == null) return null;
  return { owner: Number(match[1]) };
}

export function isCtfJailTile(value: string | null | undefined): boolean {
  if (!value) return false;
  return CTF_JAIL_PATTERN.test(value.trim());
}

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

export function isCtfSpecialTile(value: string | null | undefined): boolean {
  if (!value) return false;
  const key = value.trim().toLowerCase();
  return isCtfJailTile(key) || key === CTF_UNLOCK_TILE;
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
