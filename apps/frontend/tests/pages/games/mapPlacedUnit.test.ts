import { describe, expect, it } from "vitest";
import {
  getUnitMoveIds,
  isVisibleOnMapUnit,
  mapPlacedUnitFromBackend,
  mapVisiblePlacedUnitsFromBackend,
  resolveMovePpIndex,
  toActiveUnitView,
} from "@/pages/games/mapPlacedUnit";

describe("mapPlacedUnit", () => {
  const backendUnit = {
    id: "10",
    game_id: "2",
    unit_id: "3",
    user_id: "4",
    unit: { name: "Pikachu" },
    current_x: 5,
    current_y: 6,
    starting_x: 1,
    starting_y: 2,
    level: 42,
    current_hp: 30,
    current_stats: { attack: 10 },
    is_fainted: false,
    can_move: true,
    move_pp: ["5", "10"],
    held_item: "Oran Berry",
    held_item_slug: "oran-berry",
    held_tm_move_id: "99",
    equipped_move_ids: ["1", "2"],
    ability: "Static",
    ability_id: "7",
  };

  it("maps backend units and visibility", () => {
    const placed = mapPlacedUnitFromBackend(backendUnit);
    expect(placed).toMatchObject({
      id: 10,
      game_id: 2,
      unit_id: 3,
      user_id: 4,
      tile: [5, 6],
      start_tile: [1, 2],
      level: 42,
      current_hp: 30,
      held_tm_move_id: 99,
      equipped_move_ids: [1, 2],
      move_pp: [5, 10],
      ability_id: 7,
    });
    expect(isVisibleOnMapUnit(placed)).toBe(true);
    expect(isVisibleOnMapUnit({ ...placed, is_fainted: true })).toBe(false);
    expect(isVisibleOnMapUnit({ ...placed, current_hp: 0 })).toBe(false);
    expect(isVisibleOnMapUnit({ ...placed, tile: [-1, 0] })).toBe(false);

    const visible = mapVisiblePlacedUnitsFromBackend([
      backendUnit,
      { ...backendUnit, id: 11, is_fainted: true },
    ]);
    expect(visible).toHaveLength(1);
    expect(toActiveUnitView(placed).instanceId).toBe(10);
  });

  it("resolves move ids and PP indexes including held TMs", () => {
    const placed = mapPlacedUnitFromBackend(backendUnit);
    expect(getUnitMoveIds(placed)).toEqual([1, 2, 99]);
    expect(getUnitMoveIds({ ...placed, held_tm_move_id: 1 })).toEqual([1, 2]);
    expect(getUnitMoveIds({ ...placed, held_tm_move_id: null })).toEqual([1, 2]);
    expect(resolveMovePpIndex(placed, 2)).toBe(1);
    expect(resolveMovePpIndex(placed, 99)).toBe(2);
    expect(resolveMovePpIndex(placed, 55)).toBe(-1);
  });

  it("covers backend defaults and sparse payloads", () => {
    const sparse = mapPlacedUnitFromBackend({
      id: 1,
      game_id: 2,
      unit_id: 3,
      user_id: 4,
      unit: { name: "X" },
      starting_x: 9,
      starting_y: 8,
      can_move: false,
      held_tm_move_id: null,
      ability_id: null,
    });
    expect(sparse).toMatchObject({
      tile: [9, 8],
      start_tile: [9, 8],
      level: 50,
      current_hp: 0,
      can_move: false,
      move_pp: [],
      equipped_move_ids: [],
      held_item: null,
      held_tm_move_id: null,
      ability_id: null,
      status_effects: [],
      states: [],
    });
    expect(isVisibleOnMapUnit(sparse)).toBe(false);
    expect(isVisibleOnMapUnit({ ...sparse, current_hp: 1, tile: [0, -1] })).toBe(false);
  });
});
