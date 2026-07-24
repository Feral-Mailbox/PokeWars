import { describe, expect, it } from "vitest";
import {
  canSelectWarObjectiveTile,
  canSummonOnObjective,
  getCurrentRound,
  getWarCaptureTarget,
  getWarPlayerNumber,
  isWarObjectiveTileOccupied,
  patchObjectiveTile,
} from "@/pages/games/modes/WarGame";

describe("WarGame helpers", () => {
  const cell = {
    kind: "pokeball" as const,
    owner: 1,
    hp: 20,
    max_hp: 20,
    last_summon_round: null as number | null,
  };

  it("computes player number and round", () => {
    expect(getWarPlayerNumber({ player_order: [10, 20] }, 20)).toBe(2);
    expect(getWarPlayerNumber({ player_order: [10, 20] }, 99)).toBe(0);
    expect(getCurrentRound({ player_order: [1, 2], current_turn: 0 })).toBe(1);
    expect(getCurrentRound({ player_order: [1, 2], current_turn: 2 })).toBe(2);
    expect(getCurrentRound({ player_order: [], current_turn: 5 })).toBe(1);
  });

  it("checks summon eligibility and occupancy", () => {
    expect(canSummonOnObjective(cell, 1, 1)).toBe(true);
    expect(canSummonOnObjective(cell, 2, 1)).toBe(false);
    expect(canSummonOnObjective({ ...cell, last_summon_round: 1 }, 1, 1)).toBe(false);
    expect(canSummonOnObjective({ ...cell, last_summon_round: 1 }, 1, 2)).toBe(true);
    expect(
      isWarObjectiveTileOccupied(
        [
          { tile: [1, 1], current_hp: 5 },
          { tile: [2, 2], current_hp: 0 },
        ],
        1,
        1
      )
    ).toBe(true);
    expect(isWarObjectiveTileOccupied([{ tile: [1, 1], current_hp: 0 }], 1, 1)).toBe(false);
  });

  it("gates objective selection by phase ownership and summons", () => {
    const gameData = {
      status: "in_progress",
      current_turn: 0,
      player_order: [10, 20],
      map_state: {
        objective_tiles: [[cell]],
      },
    };
    expect(canSelectWarObjectiveTile(gameData, 10, 0, 0, [])).toBe(true);
    expect(canSelectWarObjectiveTile({ ...gameData, status: "open" }, 10, 0, 0)).toBe(false);
    expect(
      canSelectWarObjectiveTile(gameData, 10, 0, 0, [{ tile: [0, 0], current_hp: 10 }])
    ).toBe(false);
    expect(
      canSelectWarObjectiveTile(
        {
          ...gameData,
          status: "preparation",
        },
        10,
        0,
        0,
        []
      )
    ).toBe(true);
  });

  it("patches objective tiles and finds capture targets", () => {
    const gameData = {
      gamemode: "War",
      status: "in_progress",
      player_order: [10, 20],
      map_state: {
        objective_tiles: [[{ ...cell, owner: 2 }]],
      },
    };
    const patched = patchObjectiveTile(gameData, 0, 0, { hp: 5, owner: 1, kind: "master_ball" });
    expect(patched.map_state.objective_tiles[0][0]).toMatchObject({
      hp: 5,
      owner: 1,
      kind: "master_ball",
    });
    expect(patchObjectiveTile(gameData, 9, 9, { hp: 1, owner: 1 })).toBe(gameData);

    expect(
      getWarCaptureTarget(
        { user_id: 10, can_move: true, tile: [0, 0] },
        gameData,
        10
      )
    ).toEqual({ x: 0, y: 0, hp: 20, max_hp: 20 });
    expect(getWarCaptureTarget(null, gameData, 10)).toBeNull();
    expect(
      getWarCaptureTarget({ user_id: 10, can_move: false, tile: [0, 0] }, gameData, 10)
    ).toBeNull();
  });
});
