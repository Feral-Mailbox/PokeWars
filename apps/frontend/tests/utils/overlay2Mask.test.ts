import { describe, expect, it, vi } from "vitest";
import {
  captureOverlay2Mask,
  overlay2MaskHasCoverage,
  sampleOverlay2Mask,
  type Overlay2Mask,
} from "@/utils/overlay2Mask";

function makeMask(
  width: number,
  height: number,
  alphaAt: Array<[number, number, number]> = []
): Overlay2Mask {
  const data = new Uint8ClampedArray(width * height * 4);
  for (const [x, y, alpha] of alphaAt) {
    data[(y * width + x) * 4 + 3] = alpha;
  }
  return { data, width, height, dpr: 1 };
}

describe("overlay2Mask", () => {
  it("returns null when canvas context or size is invalid", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 0;
    canvas.height = 0;
    expect(captureOverlay2Mask(canvas)).toBeNull();

    const bad = document.createElement("canvas");
    bad.width = 8;
    bad.height = 8;
    vi.spyOn(bad, "getContext").mockReturnValue(null);
    expect(captureOverlay2Mask(bad)).toBeNull();
  });

  it("captures mask pixel data and dpr", () => {
    const canvas = document.createElement("canvas");
    canvas.width = 4;
    canvas.height = 2;
    Object.defineProperty(canvas, "clientWidth", { value: 2 });
    const mask = captureOverlay2Mask(canvas);
    expect(mask).not.toBeNull();
    expect(mask!.width).toBe(4);
    expect(mask!.height).toBe(2);
    expect(mask!.dpr).toBe(2);
    expect(mask!.data).toBeInstanceOf(Uint8ClampedArray);
  });

  it("samples alpha and reports coverage", () => {
    const mask = makeMask(3, 3, [[1, 1, 200]]);
    expect(sampleOverlay2Mask(null, 1, 1)).toBe(0);
    expect(sampleOverlay2Mask(mask, -1, 0)).toBe(0);
    expect(sampleOverlay2Mask(mask, 1, 1)).toBe(200);
    expect(overlay2MaskHasCoverage(null, 0, 0, 2, 2)).toBe(false);
    expect(overlay2MaskHasCoverage(mask, 0, 0, 2, 2)).toBe(true);
    expect(overlay2MaskHasCoverage(makeMask(2, 2), 0, 0, 1, 1)).toBe(false);
  });
});
