import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useMapDisplayScale } from "@/hooks/useMapDisplayScale";

vi.mock("@/utils/mapPointer", () => ({
  getMapDisplayMaxSize: vi.fn(() => ({ maxWidth: 640, maxHeight: 480 })),
  computeMapDisplayScale: vi.fn((w: number, h: number, maxW: number, maxH: number) =>
    Math.min(maxW / w, maxH / h)
  ),
}));

import { computeMapDisplayScale, getMapDisplayMaxSize } from "@/utils/mapPointer";

describe("useMapDisplayScale", () => {
  it("computes scale on mount and resize", () => {
    const { result } = renderHook(() => useMapDisplayScale(320, 240));
    expect(getMapDisplayMaxSize).toHaveBeenCalled();
    expect(computeMapDisplayScale).toHaveBeenCalledWith(320, 240, 640, 480);
    expect(result.current).toBe(2);

    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(getMapDisplayMaxSize).toHaveBeenCalledTimes(2);
  });
});
