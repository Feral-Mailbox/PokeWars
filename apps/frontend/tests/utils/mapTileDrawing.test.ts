import { afterEach, describe, expect, it, vi } from "vitest";
import {
  buildOverlay2TileSet,
  installMapTileRenderer,
  isTileRefPresent,
} from "@/utils/mapTileDrawing";

describe("isTileRefPresent", () => {
  it("returns true for valid tile refs, including tile 0", () => {
    expect(isTileRefPresent([3, 1])).toBe(true);
    expect(isTileRefPresent([0, 1])).toBe(true);
    expect(isTileRefPresent([0, 0])).toBe(true);
    expect(isTileRefPresent([1, 0])).toBe(true);
  });

  it("returns false for empty or invalid refs", () => {
    expect(isTileRefPresent(null)).toBe(false);
    expect(isTileRefPresent([-1, 0])).toBe(false);
    expect(isTileRefPresent([1, null] as unknown as [number, number])).toBe(false);
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

  it("returns an empty set when overlay2 is absent", () => {
    expect(buildOverlay2TileSet(undefined)).toEqual(new Set());
  });
});

describe("installMapTileRenderer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("draws requested layers after every tileset loads", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      width = 32;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    const callback = vi.fn();
    const stop = installMapTileRenderer(
      canvas,
      {
        width: 1,
        height: 1,
        tileset_names: ["one.png", "two.png"],
        tile_data: {
          base: [[ [4, 0] ]],
          overlay: [[ [1, 1] ]],
          overlay2: [[ [2, 0] ]],
          overlay3: [[ [3, 1] ]],
        },
      },
      ["base", "overlay", "overlay2", "overlay3"],
      callback
    );

    images[0].complete = true;
    images[0].onload?.();
    expect(ctx.drawImage).not.toHaveBeenCalled();
    images[1].complete = true;
    images[1].onload?.();

    expect(ctx.drawImage).toHaveBeenCalledTimes(4);
    expect(callback).toHaveBeenCalledWith(ctx);
    stop();
  });

  it("logs failed image loads and does not draw after cleanup", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      width = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const error = vi.spyOn(console, "error").mockImplementation(() => {});
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    const stop = installMapTileRenderer(
      canvas,
      { width: 1, height: 1, tileset_names: ["bad.png"], tile_data: { base: [[[0, 0]]], overlay: [[null]] } },
      ["base"]
    );

    images[0].onerror?.();
    expect(error).toHaveBeenCalledWith(expect.stringContaining("bad.png"));
    stop();
    images[0].onload?.();
    expect(ctx.drawImage).not.toHaveBeenCalled();
  });

  it("draws only the requested base layer", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      width = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    installMapTileRenderer(
      canvas,
      {
        width: 1,
        height: 1,
        tileset_names: ["one.png"],
        tile_data: {
          base: [[[1, 0]]],
          overlay: [[[2, 0]]],
          overlay2: [[[3, 0]]],
          overlay3: [[[4, 0]]],
          background_color: "#abcdef",
        },
      },
      ["base"]
    );

    images[0].complete = true;
    images[0].onload?.();
    expect(ctx.drawImage).toHaveBeenCalledTimes(1);
    expect(ctx.fillRect).not.toHaveBeenCalled();
  });

  it("draws tile 0 from a non-void tileset", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      width = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    installMapTileRenderer(
      canvas,
      {
        width: 1,
        height: 1,
        tileset_names: ["one.png", "snow.png"],
        tile_data: { base: [[[0, 1]]], overlay: [[null]] },
      },
      ["base"]
    );

    images[0].complete = true;
    images[0].onload?.();
    images[1].complete = true;
    images[1].width = 16;
    images[1].onload?.();
    expect(ctx.drawImage).toHaveBeenCalledTimes(1);
  });

  it("draws tileset tile 0 when the base layer uses null for empty cells", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      width = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    installMapTileRenderer(
      canvas,
      {
        width: 2,
        height: 1,
        tileset_names: ["snow.png"],
        tile_data: { base: [[[0, 0], null]], overlay: [[null, null]] },
      },
      ["base"]
    );

    images[0].complete = true;
    images[0].onload?.();
    expect(ctx.drawImage).toHaveBeenCalledTimes(1);
  });

  it("fills background only when the base cell is null or unmapped", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      width = 16;
      naturalHeight = 16;
      height = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    installMapTileRenderer(
      canvas,
      {
        width: 2,
        height: 1,
        tileset_names: ["one.png"],
        tile_data: { base: [[null, [99, 0]]], overlay: [[null, null]] },
      },
      ["base"]
    );

    images[0].complete = true;
    images[0].onload?.();
    expect(ctx.drawImage).not.toHaveBeenCalled();
    expect(ctx.fillRect).toHaveBeenCalled();
  });

  it("draws tile id 0 when the base cell maps to a tileset tile", () => {
    const images: MockImage[] = [];
    class MockImage {
      complete = false;
      width = 16;
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      set src(_value: string) {}
      constructor() {
        images.push(this);
      }
    }
    vi.stubGlobal("Image", MockImage);
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d")!;
    canvas.getContext = vi.fn(() => ctx);
    installMapTileRenderer(
      canvas,
      {
        width: 1,
        height: 1,
        tileset_names: ["clouds.png"],
        tile_data: { base: [[[0, 0]]], overlay: [[null]] },
      },
      ["base"]
    );

    images[0].complete = true;
    images[0].onload?.();
    expect(ctx.drawImage).toHaveBeenCalledTimes(1);
  });
});
