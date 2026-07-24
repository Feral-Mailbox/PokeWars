import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useOverlay2Renderer } from "@/hooks/useOverlay2Renderer";
import { useOverlay3Renderer } from "@/hooks/useOverlay3Renderer";
import { useMapItemRenderer } from "@/hooks/useMapItemRenderer";
import { useMapObjectiveRenderer } from "@/hooks/useMapObjectiveRenderer";
import { createRef } from "react";

vi.mock("@/utils/mapTileDrawing", () => ({
  installMapTileRenderer: vi.fn(() => () => {}),
}));

import { installMapTileRenderer } from "@/utils/mapTileDrawing";

describe("map overlay hooks early exits", () => {
  it("skips overlay2/3 install when map data is incomplete", () => {
    const canvasRef = createRef<HTMLCanvasElement | null>();
    canvasRef.current = document.createElement("canvas");

    renderHook(() => useOverlay2Renderer(canvasRef, null));
    renderHook(() =>
      useOverlay2Renderer(canvasRef, {
        width: 1,
        height: 1,
        tileset_names: [],
        tile_data: { base: [], overlay: [] },
      })
    );
    renderHook(() => useOverlay3Renderer(canvasRef, null));
    expect(installMapTileRenderer).not.toHaveBeenCalled();

    renderHook(() =>
      useOverlay2Renderer(canvasRef, {
        width: 1,
        height: 1,
        tileset_names: ["a.png"],
        tile_data: {
          base: [[[0, 0]]],
          overlay: [[null]],
          overlay2: [[[1, 0]]],
        },
      })
    );
    expect(installMapTileRenderer).toHaveBeenCalled();
  });

  it("returns early for item/objective renderers without canvas size", () => {
    const canvasRef = createRef<HTMLCanvasElement | null>();
    canvasRef.current = null;

    renderHook(() => useMapItemRenderer(null, 0, 0, null, {}));
    renderHook(() => useMapItemRenderer(canvasRef, 32, 32, [[1]], { 1: "Fire" }));
    renderHook(() => useMapObjectiveRenderer(null, 0, 0, null));
    renderHook(() =>
      useMapObjectiveRenderer(canvasRef, 32, 32, [[{ kind: "pokeball", owner: 1, hp: 20, max_hp: 20 }]])
    );
    // Smoke: hooks should not throw when canvas is missing.
    expect(true).toBe(true);
  });
});
