import { describe, expect, it } from "vitest";
import {
  computeMapDisplayScale,
  pointerToTileCoords,
} from "@/utils/mapPointer";

describe("computeMapDisplayScale", () => {
  it("returns 1 when the map fits within limits", () => {
    expect(computeMapDisplayScale(640, 480, 960, 640)).toBe(1);
  });

  it("scales down maps that exceed width", () => {
    expect(computeMapDisplayScale(1280, 480, 960, 640)).toBe(0.75);
  });

  it("scales down maps that exceed height", () => {
    expect(computeMapDisplayScale(640, 960, 960, 640)).toBeCloseTo(0.666666, 5);
  });

  it("uses the tighter axis when both dimensions exceed limits", () => {
    expect(computeMapDisplayScale(1280, 960, 960, 640)).toBe(0.6666666666666666);
  });

  it("returns 1 for empty dimensions", () => {
    expect(computeMapDisplayScale(0, 960, 960, 640)).toBe(1);
  });
});

describe("pointerToTileCoords", () => {
  it("maps pointer position proportionally to tile coordinates", () => {
    const canvas = {
      getBoundingClientRect: () => ({
        left: 100,
        top: 50,
        width: 640,
        height: 480,
        right: 740,
        bottom: 530,
        x: 100,
        y: 50,
        toJSON: () => ({}),
      }),
    } as HTMLCanvasElement;

    expect(pointerToTileCoords(canvas, 20, 15, 420, 290)).toEqual([10, 7]);
  });

  it("handles scaled-down canvas display sizes", () => {
    const canvas = {
      getBoundingClientRect: () => ({
        left: 0,
        top: 0,
        width: 320,
        height: 240,
        right: 320,
        bottom: 240,
        x: 0,
        y: 0,
        toJSON: () => ({}),
      }),
    } as HTMLCanvasElement;

    expect(pointerToTileCoords(canvas, 40, 30, 160, 120)).toEqual([20, 15]);
  });
});
