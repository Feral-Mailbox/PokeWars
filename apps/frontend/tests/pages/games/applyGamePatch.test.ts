import { describe, expect, it } from "vitest";
import { applyGamePatch } from "@/pages/games/applyGamePatch";
import type { PlacedUnitState } from "@/pages/games/mapPlacedUnit";

function unit(partial: Partial<PlacedUnitState> & { id: number }): PlacedUnitState {
  return {
    game_id: 1,
    unit_id: 1,
    user_id: 1,
    unit: { name: "A" },
    tile: [0, 0],
    start_tile: [0, 0],
    level: 50,
    current_hp: 20,
    current_stats: {},
    stat_boosts: {},
    status_effects: [],
    states: [],
    is_fainted: false,
    jailed: false,
    jailed_by: null,
    can_move: true,
    move_pp: [],
    held_item: null,
    held_item_slug: null,
    held_tm_move_id: null,
    equipped_move_ids: [],
    ability: null,
    ability_id: null,
    ...partial,
  };
}

describe("applyGamePatch", () => {
  it("moves, upserts, and removes units without refetch", () => {
    const placed = [unit({ id: 1, tile: [1, 1], start_tile: [1, 1], current_hp: 20 })];
    const result = applyGamePatch({
      patch: {
        event: "game_patch",
        event_seq: 2,
        ops: [
          { op: "unit_moved", unit_id: 1, x: 3, y: 4 },
          {
            op: "unit_upsert",
            unit: { id: 1, current_hp: 5, current_x: 3, current_y: 4, can_move: false },
          },
          { op: "unit_removed", unit_id: 99 },
        ],
      },
      gameData: { link: "g", status: "in_progress" },
      placedUnits: placed,
      cash: 100,
      viewerUserId: 1,
    });
    expect(result.placedUnits[0].tile).toEqual([3, 4]);
    expect(result.placedUnits[0].current_hp).toBe(5);
    expect(result.placedUnits[0].can_move).toBe(false);
    expect(result.refetch).toEqual([]);
  });

  it("applies turn + sync_start_tiles + turnlock", () => {
    const placed = [unit({ id: 1, tile: [2, 2], start_tile: [0, 0] })];
    const roster = [
      { id: 1, player_id: 1, username: "alpha", cash_remaining: 100 },
      { id: 2, player_id: 2, username: "beta", cash_remaining: 100 },
    ];
    const result = applyGamePatch({
      patch: {
        event: "game_patch",
        event_seq: 3,
        cause: "turn_advanced",
        ops: [
          { op: "sync_start_tiles" },
          {
            op: "turn",
            current_turn: 4,
            status: "in_progress",
            turn_deadline: "t",
            players: [1, 2],
          },
          { op: "turnlock", player_id: 1, locks: { "1": { origin: [2, 2], tiles: [[2, 2]] } } },
          {
            op: "players",
            players: [{ player_id: 1, cash_remaining: 250 }],
          },
        ],
      },
      gameData: {
        link: "g",
        status: "in_progress",
        current_turn: 3,
        players: roster,
        player_order: [1, 2],
        players_info: [{ player_id: 1, cash_remaining: 100 }],
      },
      placedUnits: placed,
      cash: 100,
      viewerUserId: 1,
    });
    expect(result.clearUiForTurn).toBe(true);
    expect(result.gameData.current_turn).toBe(4);
    expect(result.gameData.player_order).toEqual([1, 2]);
    // Turn-order ids must not wipe the PlayerInfo roster used for colors/sidebar.
    expect(result.gameData.players).toEqual([
      { id: 1, player_id: 1, username: "alpha", cash_remaining: 250 },
      { id: 2, player_id: 2, username: "beta", cash_remaining: 100 },
    ]);
    expect(result.placedUnits[0].start_tile).toEqual([2, 2]);
    expect(result.turnlock?.["1"].origin).toEqual([2, 2]);
    expect(result.cash).toBe(250);
  });

  it("patches map item and objective cells", () => {
    const gameData = {
      map_state: {
        item_id_tiles: [[5, null], [null, 7]],
        objective_tiles: [[{ hp: 20, owner: 0, kind: "pokeball" }, null], [null, null]],
      },
    };
    const result = applyGamePatch({
      patch: {
        event: "game_patch",
        event_seq: 1,
        ops: [
          { op: "map_item_picked", x: 0, y: 0 },
          { op: "map_item_swapped", x: 1, y: 1, item_id: 9 },
          { op: "objective_updated", x: 0, y: 0, hp: 8, owner: 2, kind: "pokeball" },
        ],
      },
      gameData,
      placedUnits: [],
      cash: 0,
    });
    expect(result.gameData.map_state.item_id_tiles[0][0]).toBeNull();
    expect(result.gameData.map_state.item_id_tiles[1][1]).toBe(9);
    expect(result.gameData.map_state.objective_tiles[0][0].hp).toBe(8);
    expect(result.gameData.map_state.objective_tiles[0][0].owner).toBe(2);
  });

  it("applies flag_updated and unlock_updated patches", () => {
    const gameData = {
      map_state: {
        flag_tiles: [[{ owner: 0 }, null]],
        unlock_tiles: [[{ hp: 20, max_hp: 20 }, null]],
      },
    };
    const result = applyGamePatch({
      patch: {
        event: "game_patch",
        event_seq: 1,
        ops: [
          { op: "flag_updated", x: 0, y: 0, owner: 2, hp: 4, max_hp: 10 },
          { op: "unlock_updated", x: 0, y: 0, hp: 7, max_hp: 20 },
        ],
      },
      gameData,
      placedUnits: [],
      cash: 0,
    });
    expect(result.gameData.map_state.flag_tiles[0][0].owner).toBe(2);
    expect(result.gameData.map_state.flag_tiles[0][0].hp).toBe(4);
    expect(result.gameData.map_state.flag_tiles[0][0].max_hp).toBe(10);
    expect(result.gameData.map_state.unlock_tiles[0][0].hp).toBe(7);
  });

  it("ignores opponent unit_upsert during preparation", () => {
    const result = applyGamePatch({
      patch: {
        event: "game_patch",
        event_seq: 4,
        cause: "unit_placed",
        ops: [
          {
            op: "unit_upsert",
            unit: {
              id: 50,
              user_id: 2,
              current_x: 1,
              current_y: 1,
              current_hp: 155,
              is_fainted: false,
              unit: { name: "Enemy" },
            },
          },
          {
            op: "unit_upsert",
            unit: {
              id: 51,
              user_id: 1,
              current_x: 2,
              current_y: 2,
              current_hp: 155,
              is_fainted: false,
              unit: { name: "Mine" },
            },
          },
        ],
      },
      gameData: { link: "g", status: "preparation" },
      placedUnits: [],
      cash: 2000,
      viewerUserId: 1,
    });
    expect(result.placedUnits).toHaveLength(1);
    expect(result.placedUnits[0].id).toBe(51);
    expect(result.placedUnits[0].user_id).toBe(1);
  });

  it("upserts an existing unit id instead of duplicating", () => {
    const placed = [unit({ id: 7, user_id: 1, current_hp: 100 })];
    const result = applyGamePatch({
      patch: {
        event: "game_patch",
        event_seq: 5,
        ops: [
          {
            op: "unit_upsert",
            unit: { id: 7, user_id: 1, current_hp: 155, current_x: 0, current_y: 0 },
          },
        ],
      },
      gameData: { link: "g", status: "preparation" },
      placedUnits: placed,
      cash: 1800,
      viewerUserId: 1,
    });
    expect(result.placedUnits).toHaveLength(1);
    expect(result.placedUnits[0].current_hp).toBe(155);
  });

  it("preserves asset_folder when a sparse unit summary is patched in", () => {
    const placed = [
      unit({
        id: 7,
        user_id: 1,
        unit: { name: "Torterra", asset_folder: "003_torterra", cost: 1000, types: ["Grass", "Ground"] },
      }),
    ];
    const result = applyGamePatch({
      patch: {
        event: "game_patch",
        event_seq: 6,
        ops: [
          {
            op: "unit_upsert",
            unit: {
              id: 7,
              user_id: 1,
              current_hp: 155,
              unit: { id: 3, name: "Torterra", types: ["Grass", "Ground"], base_stats: {}, sprite_url: null },
            },
          },
        ],
      },
      gameData: { link: "g", status: "preparation" },
      placedUnits: placed,
      cash: 2000,
      viewerUserId: 1,
    });
    expect(result.placedUnits[0].unit.asset_folder).toBe("003_torterra");
    expect(result.placedUnits[0].unit.cost).toBe(1000);
    expect(result.placedUnits[0].current_hp).toBe(155);
  });

  it("preserves jail fields across sparse unit upserts", () => {
    const placed = [unit({ id: 9, user_id: 2, jailed: true, jailed_by: 1, tile: [5, 5], current_hp: 100 })];
    const result = applyGamePatch({
      patch: {
        event: "game_patch",
        event_seq: 7,
        ops: [
          {
            op: "unit_upsert",
            unit: { id: 9, user_id: 2, current_hp: 100, can_move: false, current_x: 5, current_y: 5 },
          },
        ],
      },
      gameData: { link: "g", status: "in_progress" },
      placedUnits: placed,
      cash: 0,
      viewerUserId: 1,
    });
    expect(result.placedUnits[0].jailed).toBe(true);
    expect(result.placedUnits[0].jailed_by).toBe(1);
    expect(result.placedUnits[0].tile).toEqual([5, 5]);
  });
});
