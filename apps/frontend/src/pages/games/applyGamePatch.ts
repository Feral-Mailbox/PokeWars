import { mapPlacedUnitFromBackend, isVisibleOnMapUnit, type PlacedUnitState } from "./mapPlacedUnit";

export type GamePatchOp =
  | { op: "unit_upsert"; unit: Record<string, unknown> }
  | { op: "unit_moved"; unit_id: number; user_id?: number; x: number; y: number }
  | { op: "unit_removed"; unit_id: number }
  | {
      op: "turn";
      current_turn?: number | null;
      turn_deadline?: string | null;
      status?: string | null;
      winner_id?: number | null;
      players?: number[];
    }
  | { op: "turnlock"; player_id?: number; locks: Record<string, { origin: [number, number]; tiles: [number, number][] }> }
  | { op: "sync_start_tiles" }
  | {
      op: "players";
      players: Array<{
        player_id: number;
        cash_remaining?: number | null;
        is_ready?: boolean;
        game_units?: number[];
      }>;
    }
  | { op: "objective_updated"; x: number; y: number; hp: number; owner: number; kind?: string }
  | { op: "flag_updated"; x: number; y: number; owner: number; hp?: number; max_hp?: number }
  | { op: "unlock_updated"; x: number; y: number; hp: number; max_hp: number }
  | { op: "map_item_picked"; x: number; y: number }
  | { op: "map_item_swapped"; x: number; y: number; item_id: number }
  | { op: "game_completed"; winner_id?: number | null; status?: string };

export type GamePatchMessage = {
  event: "game_patch";
  event_seq: number;
  cause?: string;
  ops?: GamePatchOp[];
  refetch?: string[];
};

export type ApplyGamePatchResult = {
  gameData: any;
  placedUnits: PlacedUnitState[];
  cash: number | null;
  turnlock: Record<string, { origin: [number, number]; tiles: [number, number][] }> | null;
  clearUiForTurn: boolean;
  removedUnitIds: number[];
  refetch: string[];
};

function mergeUnitPatch(existing: PlacedUnitState | undefined, raw: Record<string, unknown>): PlacedUnitState {
  const mapped = mapPlacedUnitFromBackend({
    ...(existing
      ? {
          id: existing.id,
          game_id: existing.game_id,
          unit_id: existing.unit_id,
          user_id: existing.user_id,
          unit: existing.unit,
          current_x: existing.tile[0],
          current_y: existing.tile[1],
          starting_x: existing.start_tile[0],
          starting_y: existing.start_tile[1],
          level: existing.level,
          current_hp: existing.current_hp,
          current_stats: existing.current_stats,
          stat_boosts: existing.stat_boosts,
          status_effects: existing.status_effects,
          states: existing.states,
          is_fainted: existing.is_fainted,
          jailed: existing.jailed,
          jailed_by: existing.jailed_by,
          can_move: existing.can_move,
          move_pp: existing.move_pp,
          held_item: existing.held_item,
          held_item_slug: existing.held_item_slug,
          held_tm_move_id: existing.held_tm_move_id,
          equipped_move_ids: existing.equipped_move_ids,
          ability: existing.ability,
          ability_id: existing.ability_id,
        }
      : {}),
    ...raw,
  });
  // Preserve nested unit catalog fields when patches send a sparse summary.
  if (existing?.unit) {
    if (raw.unit == null) {
      mapped.unit = existing.unit;
    } else if (typeof raw.unit === "object") {
      mapped.unit = { ...existing.unit, ...(raw.unit as Record<string, unknown>) };
    }
  }
  return mapped;
}

export function applyGamePatch(args: {
  patch: GamePatchMessage;
  gameData: any;
  placedUnits: PlacedUnitState[];
  cash: number;
  viewerUserId?: number | null;
}): ApplyGamePatchResult {
  const { patch, viewerUserId } = args;
  let gameData = args.gameData;
  let placedUnits = [...args.placedUnits];
  let cash: number | null = args.cash;
  let turnlock: ApplyGamePatchResult["turnlock"] = null;
  let clearUiForTurn = false;
  const removedUnitIds: number[] = [];
  const refetch = [...(patch.refetch || [])];

  for (const op of patch.ops || []) {
    switch (op.op) {
      case "unit_upsert": {
        const raw = op.unit || {};
        const id = Number(raw.id);
        if (!Number.isFinite(id)) break;
        const idx = placedUnits.findIndex((u) => u.id === id);
        const existing = idx >= 0 ? placedUnits[idx] : undefined;
        const merged = mergeUnitPatch(existing, raw);
        // Prep fog-of-war: never add opponents' placements into local state.
        if (
          gameData?.status === "preparation" &&
          viewerUserId != null &&
          Number(merged.user_id) !== Number(viewerUserId)
        ) {
          break;
        }
        if (!isVisibleOnMapUnit(merged)) {
          if (idx >= 0) {
            placedUnits = placedUnits.filter((u) => u.id !== id);
            removedUnitIds.push(id);
          }
          break;
        }
        if (idx >= 0) {
          placedUnits = placedUnits.map((u, i) => (i === idx ? merged : u));
        } else {
          placedUnits = [...placedUnits, merged];
        }
        break;
      }
      case "unit_moved": {
        const unitId = Number(op.unit_id);
        const x = Number(op.x);
        const y = Number(op.y);
        if (!Number.isFinite(unitId) || !Number.isFinite(x) || !Number.isFinite(y)) break;
        placedUnits = placedUnits.map((u) =>
          u.id === unitId ? { ...u, tile: [x, y] as [number, number] } : u,
        );
        break;
      }
      case "unit_removed": {
        const unitId = Number(op.unit_id);
        if (!Number.isFinite(unitId)) break;
        placedUnits = placedUnits.filter((u) => u.id !== unitId);
        removedUnitIds.push(unitId);
        break;
      }
      case "sync_start_tiles": {
        placedUnits = placedUnits.map((u) => ({
          ...u,
          start_tile: [...u.tile] as [number, number],
        }));
        clearUiForTurn = true;
        break;
      }
      case "turn": {
        if (!gameData) break;
        // Backend turn.players is the playable turn-order id list (same as player_order),
        // not the PlayerInfo roster on gameData.players.
        const nextOrder = Array.isArray(op.players) ? op.players.map(Number) : null;
        gameData = {
          ...gameData,
          current_turn: op.current_turn ?? gameData.current_turn,
          turn_deadline: op.turn_deadline ?? gameData.turn_deadline,
          status: op.status ?? gameData.status,
          winner_id: op.winner_id !== undefined ? op.winner_id : gameData.winner_id,
          ...(nextOrder ? { player_order: nextOrder } : {}),
        };
        clearUiForTurn = true;
        break;
      }
      case "turnlock": {
        turnlock = op.locks || {};
        break;
      }
      case "players": {
        if (!gameData) break;
        const rosterKey = Array.isArray(gameData.players)
          ? "players"
          : Array.isArray(gameData.players_info)
            ? "players_info"
            : null;
        if (rosterKey) {
          const prevRoster = gameData[rosterKey];
          const nextPlayers = prevRoster.map((p: any) => {
            const row = op.players.find((r) => Number(r.player_id) === Number(p.player_id ?? p.id));
            if (!row) return p;
            return {
              ...p,
              cash_remaining: row.cash_remaining ?? p.cash_remaining,
              is_ready: row.is_ready ?? p.is_ready,
              game_units: row.game_units ?? p.game_units,
            };
          });
          gameData = { ...gameData, [rosterKey]: nextPlayers };
        }
        if (viewerUserId != null) {
          const mine = op.players.find((r) => Number(r.player_id) === Number(viewerUserId));
          if (mine && mine.cash_remaining != null) {
            cash = Number(mine.cash_remaining);
          }
        }
        break;
      }
      case "objective_updated": {
        if (!gameData?.map_state?.objective_tiles) break;
        const tiles = gameData.map_state.objective_tiles.map((row: any[]) =>
          Array.isArray(row) ? [...row] : row,
        );
        if (Array.isArray(tiles[op.y])) {
          tiles[op.y] = [...tiles[op.y]];
          const prev = tiles[op.y][op.x] || {};
          tiles[op.y][op.x] = {
            ...prev,
            hp: op.hp,
            owner: op.owner,
            kind: op.kind || prev.kind,
          };
        }
        gameData = {
          ...gameData,
          map_state: { ...gameData.map_state, objective_tiles: tiles },
        };
        break;
      }
      case "flag_updated": {
        if (!gameData?.map_state?.flag_tiles) break;
        const tiles = gameData.map_state.flag_tiles.map((row: any[]) =>
          Array.isArray(row) ? [...row] : row,
        );
        if (Array.isArray(tiles[op.y])) {
          tiles[op.y] = [...tiles[op.y]];
          const prev = tiles[op.y][op.x] || {};
          tiles[op.y][op.x] = {
            ...prev,
            owner: op.owner,
            ...(op.hp != null ? { hp: op.hp } : {}),
            ...(op.max_hp != null ? { max_hp: op.max_hp } : {}),
          };
        }
        gameData = {
          ...gameData,
          map_state: { ...gameData.map_state, flag_tiles: tiles },
        };
        break;
      }
      case "unlock_updated": {
        if (!gameData?.map_state) break;
        const prevGrid = Array.isArray(gameData.map_state.unlock_tiles)
          ? gameData.map_state.unlock_tiles
          : [];
        const height = Math.max(prevGrid.length, op.y + 1);
        const width = Math.max(
          ...prevGrid.map((row: any) => (Array.isArray(row) ? row.length : 0)),
          op.x + 1,
        );
        const tiles = Array.from({ length: height }, (_, rowY) => {
          const src = Array.isArray(prevGrid[rowY]) ? prevGrid[rowY] : [];
          const row = Array.from({ length: width }, (_, colX) => src[colX] ?? null);
          if (rowY === op.y) {
            row[op.x] = {
              ...(row[op.x] || {}),
              hp: op.hp,
              max_hp: op.max_hp,
            };
          }
          return row;
        });
        gameData = {
          ...gameData,
          map_state: { ...gameData.map_state, unlock_tiles: tiles },
        };
        break;
      }
      case "map_item_picked": {
        if (!gameData?.map_state?.item_id_tiles) break;
        const nextTiles = gameData.map_state.item_id_tiles.map((row: (number | null)[]) =>
          Array.isArray(row) ? [...row] : row,
        );
        if (Array.isArray(nextTiles[op.y])) {
          nextTiles[op.y] = [...nextTiles[op.y]];
          nextTiles[op.y][op.x] = null;
        }
        gameData = {
          ...gameData,
          map_state: { ...gameData.map_state, item_id_tiles: nextTiles },
        };
        break;
      }
      case "map_item_swapped": {
        if (!gameData?.map_state?.item_id_tiles) break;
        const nextTiles = gameData.map_state.item_id_tiles.map((row: (number | null)[]) =>
          Array.isArray(row) ? [...row] : row,
        );
        if (Array.isArray(nextTiles[op.y])) {
          nextTiles[op.y] = [...nextTiles[op.y]];
          nextTiles[op.y][op.x] = Number(op.item_id);
        }
        gameData = {
          ...gameData,
          map_state: { ...gameData.map_state, item_id_tiles: nextTiles },
        };
        break;
      }
      case "game_completed": {
        if (!gameData) break;
        gameData = {
          ...gameData,
          status: op.status || "completed",
          winner_id: op.winner_id !== undefined ? op.winner_id : gameData.winner_id,
        };
        clearUiForTurn = true;
        break;
      }
      default:
        break;
    }
  }

  return {
    gameData,
    placedUnits,
    cash,
    turnlock,
    clearUiForTurn,
    removedUnitIds,
    refetch,
  };
}
