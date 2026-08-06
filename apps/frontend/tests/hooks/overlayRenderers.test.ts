import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useOverlay2Renderer } from "@/hooks/useOverlay2Renderer";
import { useOverlay3Renderer } from "@/hooks/useOverlay3Renderer";
import { useMapItemRenderer } from "@/hooks/useMapItemRenderer";
import { useMapObjectiveRenderer } from "@/hooks/useMapObjectiveRenderer";
import { createRef } from "react";

vi.mock("@/utils/mapTileDrawing", () => ({
  installMapTileRenderer: vi.fn(() => () => {}),
}));

vi.mock("@/utils/spriteOverlay", () => ({
  drawImageWithPlayerOverlay: vi.fn(),
}));

import { installMapTileRenderer } from "@/utils/mapTileDrawing";
import { drawImageWithPlayerOverlay } from "@/utils/spriteOverlay";

describe("map overlay hooks early exits", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

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

  it("installs overlay3 only when its layer and tilesets exist", () => {
    const canvasRef = createRef<HTMLCanvasElement | null>();
    canvasRef.current = document.createElement("canvas");
    const map = {
      width: 1,
      height: 1,
      tileset_names: ["a.png"],
      tile_data: {
        base: [[[0, 0]]],
        overlay: [[null]],
        overlay3: [[[1, 0]]],
      },
    };

    renderHook(() => useOverlay3Renderer(canvasRef, map));

    expect(installMapTileRenderer).toHaveBeenCalledWith(canvasRef.current, map, ["overlay3"]);
  });

  it("draws loaded item machines and redraws after image failure", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      naturalWidth = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvasRef = createRef<HTMLCanvasElement | null>();
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    canvasRef.current = canvas;

    renderHook(() => useMapItemRenderer(canvasRef, 32, 32, [[1, null], [2, 999]], { 1: "Fire", 2: "Water" }));
    expect(images).toHaveLength(2);
    images[0].complete = true;
    images[0].onload?.();
    images[1].onerror?.();

    expect(ctx.drawImage).toHaveBeenCalledTimes(1);
  });

  it("clears item canvases without loading unused or invalid item types", () => {
    const canvasRef = createRef<HTMLCanvasElement | null>();
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    canvasRef.current = canvas;
    const ImageMock = vi.fn();
    vi.stubGlobal("Image", ImageMock);

    renderHook(() => useMapItemRenderer(canvasRef, 32, 32, [[null, 999], null as unknown as number[]], {}));

    expect(ImageMock).not.toHaveBeenCalled();
    expect(ctx.clearRect).toHaveBeenCalled();
    expect(ctx.drawImage).not.toHaveBeenCalled();
  });

  it("renders objectives with player colors, selection, and health", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      naturalWidth = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvasRef = createRef<HTMLCanvasElement | null>();
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    canvasRef.current = canvas;
    const getPlayerColor = vi.fn((id: number) => id === 10 ? "#abcdef" : "#00000000");

    renderHook(() =>
      useMapObjectiveRenderer(
        canvasRef,
        64,
        32,
        [[
          { kind: "pokeball", owner: 1, hp: 10, max_hp: 20 },
          { kind: "master_ball", owner: 2, hp: 20, max_hp: 20 },
        ]],
        { selectedTile: [0, 0], playerOrder: [10, 20], getPlayerColor }
      )
    );
    expect(images).toHaveLength(2);
    images[0].complete = true;
    images[0].onload?.();
    images[1].complete = true;
    images[1].onload?.();

    expect(drawImageWithPlayerOverlay).toHaveBeenCalledWith(
      ctx,
      images[0],
      0, 0, 48, 48, 0, 0, 32, 32,
      "#abcdef"
    );
    expect(drawImageWithPlayerOverlay).toHaveBeenCalledWith(
      ctx,
      images[1],
      0, 0, 48, 48, 32, 0, 32, 32,
      "#FF000080"
    );
    expect(ctx.strokeRect).toHaveBeenCalled();
    expect(ctx.fillRect).toHaveBeenCalledTimes(4);
  });

  it("draws an empty objective layer and uses defaults for an ownerless objective", () => {
    const canvasRef = createRef<HTMLCanvasElement | null>();
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    canvasRef.current = canvas;

    const empty = renderHook(() => useMapObjectiveRenderer(canvasRef, 32, 32, []));
    expect(ctx.clearRect).toHaveBeenCalled();
    empty.unmount();

    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      naturalWidth = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    renderHook(() =>
      useMapObjectiveRenderer(canvasRef, 32, 32, [[{ kind: "pokeball", owner: 0, hp: 20, max_hp: 0 }]])
    );
    images[0].complete = true;
    images[0].onload?.();

    expect(drawImageWithPlayerOverlay).toHaveBeenLastCalledWith(
      ctx, images[0], 0, 0, 48, 48, 0, 0, 32, 32, null
    );
  });

  it("skips bad objective rows and falls back to palette when player color is transparent", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      naturalWidth = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvasRef = createRef<HTMLCanvasElement | null>();
    const canvas = document.createElement("canvas");
    const ctx = {
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      strokeRect: vi.fn(),
      fillRect: vi.fn(),
      drawImage: vi.fn(),
      imageSmoothingEnabled: true,
      strokeStyle: "",
      lineWidth: 1,
      fillStyle: "",
    };
    canvas.getContext = vi.fn(() => ctx) as any;
    canvasRef.current = canvas;

    const getPlayerColor = vi.fn(() => "#00000000");
    renderHook(() =>
      useMapObjectiveRenderer(
        canvasRef,
        64,
        32,
        [null as any, [{ kind: "pokeball", owner: 1, hp: 5, max_hp: 10 }, null]],
        { selectedTile: null, playerOrder: [42], getPlayerColor },
      ),
    );

    images[0].complete = true;
    images[0].naturalWidth = 16;
    images[0].onload?.();

    expect(getPlayerColor).toHaveBeenCalledWith(42);
    expect(drawImageWithPlayerOverlay).toHaveBeenCalledWith(
      ctx,
      images[0],
      0,
      0,
      48,
      48,
      0,
      32,
      32,
      32,
      "#0000FF80",
    );
  });

  it("loads item images that are incomplete until onload", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      naturalWidth = 0;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvasRef = createRef<HTMLCanvasElement | null>();
    const canvas = document.createElement("canvas");
    const ctx = {
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      drawImage: vi.fn(),
      imageSmoothingEnabled: true,
    };
    canvas.getContext = vi.fn(() => ctx) as any;
    canvasRef.current = canvas;

    renderHook(() => useMapItemRenderer(canvasRef, 32, 32, [[5]], { 5: "Grass" }));
    expect(images).toHaveLength(1);
    images[0].complete = true;
    images[0].naturalWidth = 16;
    images[0].onload?.();
    expect(ctx.drawImage).toHaveBeenCalled();
  });
});
