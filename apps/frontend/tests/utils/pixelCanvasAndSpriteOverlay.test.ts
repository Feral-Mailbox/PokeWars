import { describe, expect, it, vi } from "vitest";
import {
  getDevicePixelRatio,
  MAP_TILE_DRAW_SIZE,
  MAP_TILE_SCALE,
  MAP_TILE_SIZE,
  setupPixelCanvas,
} from "@/utils/pixelCanvas";
import {
  applyOpaquePixelOverlay,
  drawImageWithPlayerOverlay,
  SPRITE_OVERLAY_ALPHA,
} from "@/utils/spriteOverlay";

describe("pixelCanvas", () => {
  it("exposes tile size constants", () => {
    expect(MAP_TILE_SIZE).toBe(16);
    expect(MAP_TILE_SCALE).toBe(2);
    expect(MAP_TILE_DRAW_SIZE).toBe(32);
  });

  it("reads device pixel ratio with a floor of 1", () => {
    const original = window.devicePixelRatio;
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: 0 });
    expect(getDevicePixelRatio()).toBe(1);
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: 2 });
    expect(getDevicePixelRatio()).toBe(2);
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: original });
  });

  it("sizes canvas buffers for DPR", () => {
    Object.defineProperty(window, "devicePixelRatio", { configurable: true, value: 2 });
    const canvas = document.createElement("canvas");
    const dpr = setupPixelCanvas(canvas, 100, 50);
    expect(dpr).toBe(2);
    expect(canvas.width).toBe(200);
    expect(canvas.height).toBe(100);
    expect(canvas.style.width).toBe("100px");
    expect(canvas.style.height).toBe("50px");
  });
});

describe("spriteOverlay", () => {
  it("tints only opaque pixels", () => {
    const fillRect = vi.fn();
    const ctx = {
      fillStyle: "",
      globalAlpha: 1,
      fillRect,
    } as unknown as CanvasRenderingContext2D;
    const data = new Uint8ClampedArray(8);
    data[3] = 255;
    data[7] = 0;
    applyOpaquePixelOverlay(ctx, { data, width: 2, height: 1 } as ImageData, 10, 20, "#ff0000");
    expect(ctx.fillStyle).toBe("#ff0000");
    expect(ctx.globalAlpha).toBe(1);
    expect(fillRect).toHaveBeenCalledWith(10, 20, 1, 1);
    expect(fillRect).toHaveBeenCalledTimes(1);
    expect(SPRITE_OVERLAY_ALPHA).toBe(0.7);
  });

  it("draws without overlay when color is empty or transparent", () => {
    const drawImage = vi.fn();
    const ctx = { drawImage } as unknown as CanvasRenderingContext2D;
    const image = {} as HTMLImageElement;
    drawImageWithPlayerOverlay(ctx, image, 0, 0, 8, 8, 1, 2, 8, 8, null);
    drawImageWithPlayerOverlay(ctx, image, 0, 0, 8, 8, 1, 2, 8, 8, "#00000000");
    expect(drawImage).toHaveBeenCalledTimes(2);
  });

  it("applies player overlay when a color is provided", () => {
    const fillRect = vi.fn();
    const drawImage = vi.fn();
    const ctx = {
      drawImage,
      fillStyle: "",
      globalAlpha: 1,
      fillRect,
    } as unknown as CanvasRenderingContext2D;

    const frameCtx = {
      drawImage: vi.fn(),
      getImageData: vi.fn(() => {
        const data = new Uint8ClampedArray(4);
        data[3] = 255;
        return { data, width: 1, height: 1 } as ImageData;
      }),
    };
    const createElement = vi.spyOn(document, "createElement").mockImplementation((tag) => {
      if (tag === "canvas") {
        return {
          width: 0,
          height: 0,
          getContext: () => frameCtx,
        } as unknown as HTMLCanvasElement;
      }
      return document.createElementNS("http://www.w3.org/1999/xhtml", tag);
    });

    drawImageWithPlayerOverlay(
      ctx,
      {} as HTMLImageElement,
      0,
      0,
      8,
      8,
      3,
      4,
      1,
      1,
      "#00ff00"
    );

    expect(drawImage).toHaveBeenCalled();
    expect(fillRect).toHaveBeenCalledWith(3, 4, 1, 1);
    createElement.mockRestore();
  });

  it("keeps the base image when the overlay canvas has no context", () => {
    const drawImage = vi.fn();
    const ctx = { drawImage } as unknown as CanvasRenderingContext2D;
    const createElement = vi.spyOn(document, "createElement").mockImplementation((tag) => {
      if (tag === "canvas") {
        return { width: 0, height: 0, getContext: () => null } as unknown as HTMLCanvasElement;
      }
      return document.createElementNS("http://www.w3.org/1999/xhtml", tag);
    });

    drawImageWithPlayerOverlay(ctx, {} as HTMLImageElement, 0, 0, 8, 8, 1, 2, 8, 8, "#00ff00");

    expect(drawImage).toHaveBeenCalledTimes(1);
    createElement.mockRestore();
  });
});
