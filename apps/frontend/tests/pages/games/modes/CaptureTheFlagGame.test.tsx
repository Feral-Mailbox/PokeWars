import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import CaptureTheFlagGame from "@/pages/games/modes/CaptureTheFlagGame";

const { useMapRenderer } = vi.hoisted(() => ({ useMapRenderer: vi.fn() }));
vi.mock("@/hooks/useMapRenderer", () => ({ useMapRenderer }));

describe("CaptureTheFlagGame", () => {
  beforeEach(() => useMapRenderer.mockClear());

  it("renders the CTF mode description", () => {
    render(<CaptureTheFlagGame gameData={{}} userId={1} />);
    expect(
      screen.getByText(/Capture the Flag: Seize your opponent/i)
    ).toBeInTheDocument();
  });

  it("draws a flag overlay only for occupied flag cells", () => {
    render(
      <CaptureTheFlagGame
        userId={1}
        gameData={{ map: { tile_data: { flag_data: [[0, 1], [2, 0]] } } }}
      />,
    );

    const drawOverlay = useMapRenderer.mock.calls[0][2];
    const ctx = { fillRect: vi.fn(), fillStyle: "" } as unknown as CanvasRenderingContext2D;
    drawOverlay(ctx);

    expect(ctx.fillStyle).toBe("rgba(0, 200, 255, 0.4)");
    expect(ctx.fillRect).toHaveBeenNthCalledWith(1, 32, 0, 32, 32);
    expect(ctx.fillRect).toHaveBeenNthCalledWith(2, 0, 32, 32, 32);
  });

  it("skips drawing when the map has no flag data", () => {
    render(<CaptureTheFlagGame userId={1} gameData={{ map: { tile_data: {} } }} />);
    const ctx = { fillRect: vi.fn() } as unknown as CanvasRenderingContext2D;

    useMapRenderer.mock.calls[0][2](ctx);

    expect(ctx.fillRect).not.toHaveBeenCalled();
  });
});
