import { describe, expect, it } from "vitest";
import {
  buildTitanicOcclusionMap,
  DEFAULT_TITANIC_FOOTPRINT,
  resolveTitanicFootprint,
} from "@/utils/titanicOcclusion";

describe("titanicOcclusion", () => {
  it("returns null footprint for non-titanic units", () => {
    expect(resolveTitanicFootprint({ is_titanic: false })).toBeNull();
    expect(resolveTitanicFootprint({})).toBeNull();
    expect(resolveTitanicFootprint(null)).toBeNull();
  });

  it("applies default footprint when titanic without explicit sizes", () => {
    expect(resolveTitanicFootprint({ is_titanic: true })).toEqual(
      DEFAULT_TITANIC_FOOTPRINT
    );
  });

  it("uses explicit footprint values when provided", () => {
    expect(
      resolveTitanicFootprint({
        is_titanic: true,
        titanic_footprint: { north: 2, west: 0, east: 1 },
      })
    ).toEqual({ north: 2, west: 0, east: 1 });
  });

  it("marks northern tiles behind a titanic unit", () => {
    const map = buildTitanicOcclusionMap([
      {
        tile: [5, 5],
        unit: {
          is_titanic: true,
          titanic_footprint: { north: 2, west: 1, east: 1 },
        },
      },
    ]);

    expect(map.get("5,4")).toBe(5);
    expect(map.get("4,4")).toBe(5);
    expect(map.get("6,4")).toBe(5);
    expect(map.get("5,3")).toBe(5);
    expect(map.has("5,5")).toBe(false);
    expect(map.has("5,2")).toBe(false);
  });

  it("keeps the southernmost occluder when footprints overlap", () => {
    const map = buildTitanicOcclusionMap([
      {
        tile: [2, 4],
        unit: {
          is_titanic: true,
          titanic_footprint: { north: 3, west: 0, east: 0 },
        },
      },
      {
        tile: [2, 6],
        unit: {
          is_titanic: true,
          titanic_footprint: { north: 3, west: 0, east: 0 },
        },
      },
    ]);

    expect(map.get("2,3")).toBe(6);
  });
});
