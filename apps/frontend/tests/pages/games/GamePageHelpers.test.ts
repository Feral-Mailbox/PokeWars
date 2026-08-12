import { describe, expect, it } from "vitest";
import {
  buildPlayerColorMap,
  getBlockedTilesByEnemy,
  isActivePlacedUnit,
  PLAYER_COLORS,
} from "@/pages/games/GamePage";

describe("GamePage helpers", () => {
  it("detects active placed units", () => {
    expect(isActivePlacedUnit({ current_hp: 10, is_fainted: false })).toBe(true);
    expect(isActivePlacedUnit({ current_hp: 0 })).toBe(false);
    expect(isActivePlacedUnit({ current_hp: 10, is_fainted: true })).toBe(false);
  });

  it("blocks living enemy tiles unless the unit is ghost-type", () => {
    const units = [
      { user_id: 1, tile: [0, 0], current_hp: 10 },
      { user_id: 2, tile: [1, 1], current_hp: 5 },
      { user_id: 2, tile: [2, 2], current_hp: 0 },
      { user_id: 2, tile: [3, 3], is_fainted: true, current_hp: 10 },
      { user_id: 2, tile: [4, 4], current_hp: 10, jailed: true },
    ];
    expect([...getBlockedTilesByEnemy(units, 1)]).toEqual(["1,1"]);
    expect(getBlockedTilesByEnemy(units, 1, ["Ghost"]).size).toBe(0);
  });

  it("maps players to palette colors by id order", () => {
    expect(buildPlayerColorMap(null)).toEqual({});
    expect(buildPlayerColorMap([10, 20])).toEqual({});
    expect(
      buildPlayerColorMap([
        { id: 2, player_id: 20 },
        { id: 1, player_id: 10 },
      ])
    ).toEqual({
      10: PLAYER_COLORS[0],
      20: PLAYER_COLORS[1],
    });
  });
});
