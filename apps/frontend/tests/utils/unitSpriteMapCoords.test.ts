import { describe, expect, it } from "vitest";
import {
  getUnitSpriteBoundsOnMap,
  getUnitSpriteCanvasStyle,
  spriteCanvasPixelToMapCoords,
  UNIT_SPRITE_SCALE,
} from "@/utils/unitSpriteMapCoords";

describe("unitSpriteMapCoords", () => {
  const tile: [number, number] = [2, 3];
  const tileDrawSize = 32;
  const frameWidth = 24;
  const frameHeight = 48;

  it("converts sprite canvas pixels into map coordinates", () => {
    const [mapX, mapY] = spriteCanvasPixelToMapCoords(
      0,
      0,
      tile,
      tileDrawSize,
      frameHeight,
      frameWidth
    );
    const bounds = getUnitSpriteBoundsOnMap(tile, tileDrawSize, frameWidth, frameHeight);
    expect(mapX).toBeCloseTo(bounds.minX);
    expect(mapY).toBeCloseTo(bounds.maxY - frameHeight * UNIT_SPRITE_SCALE);
  });

  it("computes sprite bounds on the map", () => {
    const bounds = getUnitSpriteBoundsOnMap(tile, tileDrawSize, frameWidth, frameHeight);
    expect(bounds.maxX - bounds.minX).toBeCloseTo(frameWidth * UNIT_SPRITE_SCALE);
    expect(bounds.maxY - bounds.minY).toBeCloseTo(frameHeight * UNIT_SPRITE_SCALE);
    expect(bounds.maxY).toBe(tile[1] * tileDrawSize + tileDrawSize);
  });

  it("builds absolute canvas style with bottom-center scale", () => {
    const style = getUnitSpriteCanvasStyle(tile, tileDrawSize, frameWidth, frameHeight);
    expect(style.position).toBe("absolute");
    expect(style.width).toBe(frameWidth);
    expect(style.height).toBe(frameHeight);
    expect(style.transform).toBe(`scale(${UNIT_SPRITE_SCALE})`);
    expect(style.transformOrigin).toBe("bottom center");
    expect(style.pointerEvents).toBe("none");
  });
});
