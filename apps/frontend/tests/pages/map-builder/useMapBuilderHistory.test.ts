import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useMapBuilderHistory } from "@/pages/map-builder/useMapBuilderHistory";
import { createEmptyTileData } from "@/utils/mapBuilder";

describe("useMapBuilderHistory", () => {
  it("tracks undo/redo and reset", () => {
    const initial = createEmptyTileData(2, 2);
    const { result } = renderHook(() => useMapBuilderHistory(initial));

    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);

    const next = createEmptyTileData(2, 2);
    next.base[0][0] = [4, 5];

    act(() => {
      result.current.pushHistory(result.current.tileData);
      result.current.setTileData(next);
    });

    expect(result.current.canUndo).toBe(true);
    expect(result.current.tileData.base[0][0]).toEqual([4, 5]);

    act(() => {
      result.current.undo();
    });
    expect(result.current.tileData.base[0][0]).toEqual([0, 0]);
    expect(result.current.canRedo).toBe(true);

    act(() => {
      result.current.redo();
    });
    expect(result.current.tileData.base[0][0]).toEqual([4, 5]);

    const reset = createEmptyTileData(1, 1);
    act(() => {
      result.current.resetHistory(reset);
    });
    expect(result.current.tileData.base).toHaveLength(1);
    expect(result.current.canUndo).toBe(false);
    expect(result.current.canRedo).toBe(false);

    act(() => {
      result.current.undo();
      result.current.redo();
    });
    expect(result.current.canUndo).toBe(false);
  });
});
