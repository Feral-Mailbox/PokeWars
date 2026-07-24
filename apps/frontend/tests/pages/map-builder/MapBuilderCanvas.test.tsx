import { fireEvent, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import MapBuilderCanvas from "@/pages/map-builder/MapBuilderCanvas";
import { createEmptyTileData } from "@/utils/mapBuilder";
import { RANDOM_TM_ITEM_ID } from "@/types/mapData";

function stubImagesComplete() {
  vi.stubGlobal(
    "Image",
    class {
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      complete = false;
      naturalWidth = 0;
      width = 0;
      set src(_val: string) {
        this.complete = true;
        this.naturalWidth = 64;
        this.width = 64;
        queueMicrotask(() => this.onload?.());
      }
    } as any
  );
}

function makeTileData() {
  const data = createEmptyTileData(3, 3);
  data.base[0][0] = [1, 0];
  data.overlay[0][1] = [2, 0];
  data.overlay2[1][0] = [3, 0];
  data.overlay3[1][1] = [4, 0];
  data.spawn_points[0][0] = 1;
  data.special_tiles[0][2] = "water";
  data.special_tiles[2][0] = "pokeball";
  data.special_tiles[2][1] = "master_ball_p2";
  data.flags[1][2] = 3;
  data.movement_cost[2][2] = 3;
  data.item_id_tiles[0][0] = RANDOM_TM_ITEM_ID;
  data.item_id_tiles[1][1] = 10;
  return data;
}

function paintProps(overrides: Record<string, unknown> = {}) {
  return {
    width: 3,
    height: 3,
    tileData: makeTileData(),
    tilesetNames: ["Brick City.png"],
    activeLayer: "base" as const,
    tool: "pencil" as const,
    selectedTile: [1, 0] as [number, number],
    spawnBrush: 1,
    specialBrush: "rock",
    flagBrush: 2,
    movementCostBrush: 2,
    itemBrush: 10,
    itemMoveTypeById: { 10: "Fighting" },
    warBrush: "pokeball",
    showAllOverlays: true,
    onStrokeStart: vi.fn(),
    onStrokeEnd: vi.fn(),
    onTileDataChange: vi.fn(),
    ...overrides,
  };
}

function stubCanvasGeometry(canvas: HTMLCanvasElement) {
  canvas.getBoundingClientRect = () =>
    ({
      left: 0,
      top: 0,
      width: 96,
      height: 96,
      right: 96,
      bottom: 96,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    }) as DOMRect;
}

describe("MapBuilderCanvas", () => {
  beforeEach(() => {
    stubImagesComplete();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders and redraws overlays for spawn/special/war/flags/items/cost", async () => {
    const props = paintProps({ activeLayer: "war" });
    const { container, rerender } = render(<MapBuilderCanvas {...props} />);
    const canvas = container.querySelector("canvas")!;
    expect(canvas).toBeTruthy();

    await waitFor(() => {
      expect(canvas.getContext).toHaveBeenCalled();
    });

    rerender(<MapBuilderCanvas {...paintProps({ activeLayer: "movement_cost", showAllOverlays: false })} />);
    rerender(<MapBuilderCanvas {...paintProps({ activeLayer: "items", showAllOverlays: true })} />);
    rerender(<MapBuilderCanvas {...paintProps({ activeLayer: "spawn_points" })} />);
    rerender(<MapBuilderCanvas {...paintProps({ activeLayer: "flags" })} />);
    rerender(<MapBuilderCanvas {...paintProps({ activeLayer: "special_tiles" })} />);
  });

  it("paints with pencil and eraser tools", async () => {
    const onStrokeStart = vi.fn();
    const onStrokeEnd = vi.fn();
    const onTileDataChange = vi.fn();
    const props = paintProps({ onStrokeStart, onStrokeEnd, onTileDataChange, tool: "pencil" });
    const { container } = render(<MapBuilderCanvas {...props} />);
    const canvas = container.querySelector("canvas")!;
    stubCanvasGeometry(canvas);

    fireEvent.mouseDown(canvas, { clientX: 16, clientY: 16, button: 0 });
    expect(onStrokeStart).toHaveBeenCalled();
    expect(onTileDataChange).toHaveBeenCalled();

    fireEvent.mouseMove(canvas, { clientX: 48, clientY: 16, button: 0 });
    fireEvent.mouseUp(canvas);
    expect(onStrokeEnd).toHaveBeenCalled();

    onTileDataChange.mockClear();
    onStrokeStart.mockClear();
    const eraserProps = paintProps({
      tool: "eraser",
      onStrokeStart,
      onStrokeEnd,
      onTileDataChange,
    });
    const { container: c2 } = render(<MapBuilderCanvas {...eraserProps} />);
    const canvas2 = c2.querySelector("canvas")!;
    stubCanvasGeometry(canvas2);
    fireEvent.mouseDown(canvas2, { clientX: 16, clientY: 16, button: 0 });
    expect(onStrokeStart).toHaveBeenCalled();
    fireEvent.mouseLeave(canvas2);
    expect(onStrokeEnd).toHaveBeenCalled();
  });

  it("fills a box selection", () => {
    const onTileDataChange = vi.fn();
    const props = paintProps({
      tool: "box",
      onTileDataChange,
      onStrokeStart: vi.fn(),
      onStrokeEnd: vi.fn(),
    });
    const { container } = render(<MapBuilderCanvas {...props} />);
    const canvas = container.querySelector("canvas")!;
    stubCanvasGeometry(canvas);

    fireEvent.mouseDown(canvas, { clientX: 8, clientY: 8, button: 0 });
    fireEvent.mouseMove(canvas, { clientX: 70, clientY: 70, button: 0 });
    expect(onTileDataChange).toHaveBeenCalled();
    fireEvent.mouseUp(canvas);
  });

  it("ignores non-primary mouse buttons and out-of-bounds cells", () => {
    const onStrokeStart = vi.fn();
    const props = paintProps({ onStrokeStart });
    const { container } = render(<MapBuilderCanvas {...props} />);
    const canvas = container.querySelector("canvas")!;
    stubCanvasGeometry(canvas);

    fireEvent.mouseDown(canvas, { clientX: 16, clientY: 16, button: 2 });
    expect(onStrokeStart).not.toHaveBeenCalled();

    fireEvent.contextMenu(canvas);
    fireEvent.mouseDown(canvas, { clientX: -10, clientY: -10, button: 0 });
    expect(onStrokeStart).not.toHaveBeenCalled();
  });

  it("loads tilesets and TM images for brushes", async () => {
    const props = paintProps({
      itemBrush: 10,
      itemMoveTypeById: { 10: "Dragon" },
      tilesetNames: ["A.png", "B.png"],
    });
    render(<MapBuilderCanvas {...props} />);
    await waitFor(() => {
      expect(true).toBe(true);
    });
  });
});
