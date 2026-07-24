import { describe, expect, it } from "vitest";
import {
  filterInBoundsTiles,
  getDisplacementAttackTiles,
  getDisplacementLandingTile,
  getDisplacementLandingTilesFromEffectTiles,
  isDisplacementMoveKind,
} from "@/utils/displacementMoves";

describe("displacementMoves", () => {
  it("recognizes displacement move kinds", () => {
    expect(isDisplacementMoveKind("dash_attack")).toBe(true);
    expect(isDisplacementMoveKind("jump_attack")).toBe(true);
    expect(isDisplacementMoveKind("tackle")).toBe(false);
  });

  it("returns orthogonal step and attack tiles", () => {
    expect(getDisplacementAttackTiles([5, 5])).toEqual({
      step: [
        [5, 4],
        [5, 6],
        [4, 5],
        [6, 5],
      ],
      attack: [
        [5, 3],
        [5, 7],
        [3, 5],
        [7, 5],
      ],
    });
  });

  it("filters tiles to map bounds", () => {
    expect(
      filterInBoundsTiles(
        [
          [-1, 0],
          [0, 0],
          [2, 1],
          [1, 5],
        ],
        2,
        2
      )
    ).toEqual([[0, 0]]);
  });

  it("computes landing tiles for dash/jump attacks", () => {
    expect(getDisplacementLandingTile(null, [1, 0], "dash_attack")).toBeNull();
    expect(getDisplacementLandingTile([0, 0], [0, 0], "dash_attack")).toBeNull();
    expect(getDisplacementLandingTile([0, 0], [1, 1], "dash_attack")).toBeNull();
    expect(getDisplacementLandingTile([0, 0], [3, 0], "dash_attack")).toBeNull();
    expect(getDisplacementLandingTile([0, 0], [1, 0], "tackle")).toBeNull();

    expect(getDisplacementLandingTile([2, 2], [3, 2], "dash_attack")).toEqual([3, 2]);
    expect(getDisplacementLandingTile([2, 2], [4, 2], "jump_attack")).toEqual([3, 2]);
  });

  it("picks the farthest orthogonal effect tile for landing", () => {
    expect(
      getDisplacementLandingTilesFromEffectTiles([2, 2], [], "dash_attack")
    ).toBeNull();
    expect(
      getDisplacementLandingTilesFromEffectTiles([2, 2], [[3, 3]], "dash_attack")
    ).toBeNull();
    expect(
      getDisplacementLandingTilesFromEffectTiles(
        [2, 2],
        [
          [3, 2],
          [4, 2],
        ],
        "dash_attack"
      )
    ).toEqual([3, 2]);
  });
});
