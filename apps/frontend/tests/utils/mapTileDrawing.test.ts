import { describe, expect, it } from "vitest";
import { buildOverlay2TileSet, isTileRefPresent } from "@/utils/mapTileDrawing";

describe("isTileRefPresent", () => {
  it("returns true for valid tile refs", () => {
    expect(isTileRefPresent([3, 1])).toBe(true);
  });

  it("returns false for empty or invalid refs", () => {
    expect(isTileRefPresent(null)).toBe(false);
    expect(isTileRefPresent([-1, 0])).toBe(false);
  });
});

describe("buildOverlay2TileSet", () => {
  it("collects coordinates for populated overlay2 tiles", () => {
    const set = buildOverlay2TileSet([
      [[1, 0], null],
      [null, [2, 1]],
    ]);

    expect(set.has("0,0")).toBe(true);
    expect(set.has("1,1")).toBe(true);
    expect(set.size).toBe(2);
  });
});
