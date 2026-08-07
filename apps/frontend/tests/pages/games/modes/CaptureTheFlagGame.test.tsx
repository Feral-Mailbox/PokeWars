import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import CaptureTheFlagGame, {
  getCtfActionTarget,
  patchFlagTile,
  patchUnlockTile,
} from "@/pages/games/modes/CaptureTheFlagGame";

const { useMapRenderer } = vi.hoisted(() => ({ useMapRenderer: vi.fn() }));
vi.mock("@/hooks/useMapRenderer", () => ({ useMapRenderer }));

describe("CaptureTheFlagGame", () => {
  beforeEach(() => useMapRenderer.mockClear());

  it("renders the CTF mode description", () => {
    render(
      <CaptureTheFlagGame
        gameData={{ status: "in_progress", player_order: [1], map: {}, map_state: { flag_tiles: [] } }}
        userId={1}
        onTileSelect={() => {}}
        isReady={false}
      />
    );
    expect(screen.getByText(/Capture The Flag: Claim every banner/i)).toBeInTheDocument();
  });

  it("draws flag overlays from map_state.flag_tiles", () => {
    render(
      <CaptureTheFlagGame
        userId={1}
        onTileSelect={() => {}}
        isReady={false}
        gameData={{
          status: "in_progress",
          player_order: [1],
          map: { tile_data: { special_tiles: [] } },
          map_state: {
            flag_tiles: [[{ owner: 0 }, { owner: 1 }], [null, { owner: 2 }]],
            unlock_tiles: [],
          },
        }}
      />
    );

    const drawOverlay = useMapRenderer.mock.calls[0][2];
    const ctx = {
      fillRect: vi.fn(),
      fillText: vi.fn(),
      fillStyle: "",
      font: "",
    } as unknown as CanvasRenderingContext2D;
    drawOverlay(ctx);

    expect(ctx.fillRect).toHaveBeenCalled();
    expect(ctx.fillText).toHaveBeenCalled();
  });

  it("getCtfActionTarget returns flag when standing on enemy flag", () => {
    const target = getCtfActionTarget(
      { user_id: 1, can_move: true, tile: [0, 0] },
      {
        gamemode: "Capture The Flag",
        status: "in_progress",
        player_order: [1, 2],
        map_state: { flag_tiles: [[{ owner: 2 }]], unlock_tiles: [] },
      },
      1
    );
    expect(target).toEqual({ kind: "flag", x: 0, y: 0 });
  });

  it("getCtfActionTarget returns unlock when standing on unlock tile", () => {
    const target = getCtfActionTarget(
      { user_id: 1, can_move: true, tile: [1, 0] },
      {
        gamemode: "Capture The Flag",
        status: "in_progress",
        player_order: [1, 2],
        map_state: {
          flag_tiles: [[null, null]],
          unlock_tiles: [[null, { hp: 12, max_hp: 20 }]],
        },
      },
      1
    );
    expect(target).toEqual({ kind: "unlock", x: 1, y: 0, hp: 12, max_hp: 20 });
  });

  it("patch helpers update map_state cells", () => {
    const base = {
      map_state: {
        flag_tiles: [[{ owner: 0 }]],
        unlock_tiles: [[{ hp: 20, max_hp: 20 }]],
      },
    };
    expect(patchFlagTile(base, 0, 0, { owner: 2 }).map_state.flag_tiles[0][0].owner).toBe(2);
    expect(patchUnlockTile(base, 0, 0, { hp: 10, max_hp: 20 }).map_state.unlock_tiles[0][0].hp).toBe(10);
  });
});
