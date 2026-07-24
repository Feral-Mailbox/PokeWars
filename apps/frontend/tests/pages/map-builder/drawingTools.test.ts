import { describe, expect, it } from "vitest";
import {
  DRAWING_TOOL_LABELS,
  fillRectOnMap,
  normalizeRect,
  paintCellOnMap,
} from "@/pages/map-builder/drawingTools";
import { createEmptyTileData } from "@/utils/mapBuilder";
import { DEFAULT_MOVEMENT_COST } from "@/types/mapData";

describe("drawingTools", () => {
  const paintOptions = {
    layer: "base" as const,
    erase: false,
    selectedTile: [2, 3] as [number, number],
    spawnBrush: 1,
    specialBrush: "water",
    flagBrush: 2,
    movementCostBrush: 3,
    itemBrush: 9,
    warBrush: "pokeball",
  };

  it("exposes tool labels and normalizes rectangles", () => {
    expect(DRAWING_TOOL_LABELS.pencil).toBe("Pencil");
    expect(normalizeRect(3, 1, 1, 4)).toEqual({
      minX: 1,
      minY: 1,
      maxX: 3,
      maxY: 4,
    });
  });

  it("paints and erases cells across layers", () => {
    const data = createEmptyTileData(3, 3);

    const paintedBase = paintCellOnMap(data, 1, 1, paintOptions);
    expect(paintedBase.base[1][1]).toEqual([2, 3]);

    const paintedOverlay = paintCellOnMap(data, 0, 0, {
      ...paintOptions,
      layer: "overlay",
    });
    expect(paintedOverlay.overlay[0][0]).toEqual([2, 3]);

    const paintedSpawn = paintCellOnMap(data, 0, 1, {
      ...paintOptions,
      layer: "spawn_points",
    });
    expect(paintedSpawn.spawn_points[1][0]).toBe(1);

    const paintedSpecial = paintCellOnMap(data, 1, 0, {
      ...paintOptions,
      layer: "special_tiles",
    });
    expect(paintedSpecial.special_tiles[0][1]).toBe("water");

    const paintedFlags = paintCellOnMap(data, 2, 2, {
      ...paintOptions,
      layer: "flags",
    });
    expect(paintedFlags.flags[2][2]).toBe(2);

    const paintedCost = paintCellOnMap(data, 2, 0, {
      ...paintOptions,
      layer: "movement_cost",
    });
    expect(paintedCost.movement_cost[0][2]).toBe(3);

    const paintedItems = paintCellOnMap(data, 0, 2, {
      ...paintOptions,
      layer: "items",
    });
    expect(paintedItems.item_id_tiles[2][0]).toBe(9);

    const paintedWar = paintCellOnMap(data, 1, 2, {
      ...paintOptions,
      layer: "war",
    });
    expect(paintedWar.special_tiles[2][1]).toBe("pokeball");

    const withWar = createEmptyTileData(2, 2);
    withWar.special_tiles[0][0] = "pokeball";
    withWar.special_tiles[0][1] = "water";
    const erasedWar = paintCellOnMap(withWar, 0, 0, {
      ...paintOptions,
      layer: "war",
      erase: true,
    });
    expect(erasedWar.special_tiles[0][0]).toBeNull();
    const erasedNonWar = paintCellOnMap(withWar, 1, 0, {
      ...paintOptions,
      layer: "war",
      erase: true,
    });
    expect(erasedNonWar.special_tiles[0][1]).toBe("water");

    const erasedBase = paintCellOnMap(paintedBase, 1, 1, {
      ...paintOptions,
      erase: true,
    });
    expect(erasedBase.base[1][1]).toEqual([0, 0]);

    const erasedOverlay = paintCellOnMap(paintedOverlay, 0, 0, {
      ...paintOptions,
      layer: "overlay",
      erase: true,
    });
    expect(erasedOverlay.overlay[0][0]).toBeNull();

    const erasedCost = paintCellOnMap(paintedCost, 2, 0, {
      ...paintOptions,
      layer: "movement_cost",
      erase: true,
    });
    expect(erasedCost.movement_cost[0][2]).toBe(DEFAULT_MOVEMENT_COST);
  });

  it("fills a rectangle without mutating the original snapshot", () => {
    const data = createEmptyTileData(4, 4);
    const filled = fillRectOnMap(data, 1, 1, 2, 2, {
      ...paintOptions,
      layer: "overlay2",
    });
    expect(data.overlay2[1][1]).toBeNull();
    expect(filled.overlay2[1][1]).toEqual([2, 3]);
    expect(filled.overlay2[2][2]).toEqual([2, 3]);
    expect(filled.overlay2[0][0]).toBeNull();

    const erased = fillRectOnMap(filled, 1, 1, 2, 2, {
      ...paintOptions,
      layer: "overlay2",
      erase: true,
    });
    expect(erased.overlay2[1][1]).toBeNull();
  });
});
