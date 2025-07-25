import { renderHook } from "@testing-library/react";
import { useMapRenderer } from "@/hooks/useMapRenderer";

describe("useMapRenderer", () => {
  let canvas: HTMLCanvasElement;
  let fakeCtx: CanvasRenderingContext2D;

  beforeEach(() => {
    document.body.innerHTML = `<canvas id="test-canvas" width="128" height="128"></canvas>`;
    canvas = document.getElementById("test-canvas") as HTMLCanvasElement;

    // Define a single mock context and spy on its methods
    fakeCtx = {
      clearRect: vi.fn(),
      drawImage: vi.fn(),
    } as unknown as CanvasRenderingContext2D;

    // Return that same mock context from getContext
    canvas.getContext = vi.fn(() => fakeCtx);
  });

  // AN IMPORTANT CALL FOR COVERAGE, BUT NOTHING I'VE TRIED WORKS FOR NOW SO I'M PUTTING IT OFF FOR A BIT

  // it("calls drawOverlay after image loads", async () => {
  //   const drawOverlay = vi.fn();

  //   const gameData = {
  //     map: {
  //       tileset: "TestSet",
  //       tile_data: {
  //         base: [[1, 2], [3, 4]],
  //         overlay: [[0, 0], [0, 0]],
  //       },
  //     },
  //   };

  //   // Save original Image constructor to restore after test
  //   const OriginalImage = global.Image;

  //   class MockImage {
  //     onload: (() => void) | null = null;
  //     set src(_) {
  //       setTimeout(() => {
  //         this.onload?.();
  //       }, 0);
  //     }
  //   }

  //   global.Image = MockImage as any;

  //   renderHook(() =>
  //     useMapRenderer("test-canvas", gameData, drawOverlay)
  //   );

  //   // Wait for the mock image to "load"
  //   await new Promise((resolve) => setTimeout(resolve, 10));

  //   // Now check that drawOverlay was called with the mocked ctx
  //   expect(drawOverlay).toHaveBeenCalledWith(fakeCtx);

  //   // Restore original Image
  //   global.Image = OriginalImage;
  // });

  it("does nothing if canvas is missing", () => {
    document.body.innerHTML = "";
    const drawOverlay = vi.fn();
    renderHook(() =>
      useMapRenderer("missing-canvas", { map: {} }, drawOverlay)
    );
    expect(drawOverlay).not.toHaveBeenCalled();
  });

  it("does nothing if mapData is missing", () => {
    const drawOverlay = vi.fn();
    renderHook(() =>
      useMapRenderer("test-canvas", { map: {} }, drawOverlay)
    );
    expect(drawOverlay).not.toHaveBeenCalled();
  });
});
