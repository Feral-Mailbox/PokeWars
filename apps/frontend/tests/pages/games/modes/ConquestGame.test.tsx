import { fireEvent, render } from "@testing-library/react";
import { vi } from "vitest";
import ConquestGame from "@/pages/games/modes/ConquestGame";

const { useMapRenderer, pointerToTileCoords } = vi.hoisted(() => ({
  useMapRenderer: vi.fn(),
  pointerToTileCoords: vi.fn(),
}));
vi.mock("@/hooks/useMapRenderer", () => ({ useMapRenderer }));
vi.mock("@/utils/mapPointer", () => ({ pointerToTileCoords }));

describe("ConquestGame", () => {
  const gameData = {
    status: "preparation",
    players: [{ player_id: 1, id: 1 }],
    map: {
      tile_data: {
        spawn_points: [
          [1, 0],
          [0, 1],
        ],
      },
    },
  };

  it("renders without crashing during preparation", () => {
    const mockSelect = vi.fn();
    render(
      <ConquestGame
        gameData={gameData}
        userId={1}
        onTileSelect={mockSelect}
        selectedTile={null}
        selectedUnit={null}
        occupiedTile={null}
        isReady={false}
      />
    );
  });

  it("does not render anything visibly", () => {
    const { container } = render(
      <ConquestGame
        gameData={gameData}
        userId={1}
        onTileSelect={() => {}}
        selectedTile={null}
        selectedUnit={null}
        occupiedTile={null}
        isReady={false}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("selects only the current player's spawn tile", () => {
    pointerToTileCoords.mockReturnValueOnce([0, 0]).mockReturnValueOnce([1, 0]);
    const onTileSelect = vi.fn();
    const canvas = document.createElement("canvas");
    canvas.id = "mapCanvas";
    document.body.append(canvas);

    const { unmount } = render(
      <ConquestGame
        gameData={{ ...gameData, map: { ...gameData.map, width: 2, height: 2 }, player_order: [1, 2] }}
        userId={1}
        onTileSelect={onTileSelect}
        selectedTile={null}
        selectedUnit={null}
        occupiedTile={null}
        isReady={false}
      />,
    );
    fireEvent.click(canvas, { clientX: 10, clientY: 10 });
    fireEvent.click(canvas, { clientX: 40, clientY: 10 });

    expect(onTileSelect).toHaveBeenNthCalledWith(1, [0, 0]);
    expect(onTileSelect).toHaveBeenNthCalledWith(2, null);
    unmount();
    canvas.remove();
  });

  it("draws own, occupied, configured, and fallback spawn overlays", () => {
    render(
      <ConquestGame
        gameData={{
          status: "preparation",
          player_order: [1, 2, 3],
          map: { width: 3, height: 1, tile_data: { spawn_points: [[1, 2, 3]] } },
        }}
        userId={1}
        onTileSelect={() => {}}
        selectedTile={null}
        selectedUnit={null}
        occupiedTile={[0, 0]}
        isReady={false}
        getPlayerColor={(id) => (id === 2 ? "#12345680" : "#00000000")}
      />,
    );
    const drawOverlay = useMapRenderer.mock.calls.at(-1)[2];
    const ctx = { fillRect: vi.fn(), fillStyle: "" } as unknown as CanvasRenderingContext2D;
    drawOverlay(ctx);

    expect(ctx.fillRect).toHaveBeenCalledTimes(3);
    expect(ctx.fillRect).toHaveBeenNthCalledWith(1, 0, 0, 32, 32);
    expect(ctx.fillRect).toHaveBeenNthCalledWith(3, 64, 0, 32, 32);
    expect(ctx.fillStyle).toBe("#FFFF0080");
  });

  it("does not activate selection or overlays outside preparation", () => {
    render(
      <ConquestGame
        gameData={{ status: "in_progress", map: { width: 1, height: 1, tile_data: {} } }}
        userId={1}
        onTileSelect={() => {}}
        selectedTile={null}
        selectedUnit={null}
        occupiedTile={null}
        isReady
      />,
    );
    const ctx = { fillRect: vi.fn() } as unknown as CanvasRenderingContext2D;
    useMapRenderer.mock.calls.at(-1)[2](ctx);
    expect(ctx.fillRect).not.toHaveBeenCalled();
  });
});
