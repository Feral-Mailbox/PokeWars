import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import CaptureTheFlagGame, {
  getCtfActionTarget,
  getCtfJailAt,
  patchFlagTile,
} from "@/pages/games/modes/CaptureTheFlagGame";

const { useMapRenderer, drawCtfMapIcon } = vi.hoisted(() => ({
  useMapRenderer: vi.fn(),
  drawCtfMapIcon: vi.fn(() => true),
}));
vi.mock("@/hooks/useMapRenderer", () => ({ useMapRenderer }));
vi.mock("@/utils/ctfIcons", () => ({ drawCtfMapIcon }));

describe("CaptureTheFlagGame", () => {
  beforeEach(() => {
    useMapRenderer.mockClear();
    drawCtfMapIcon.mockClear();
  });

  it("renders the CTF mode description", () => {
    render(
      <CaptureTheFlagGame
        gameData={{ status: "in_progress", player_order: [1], map: {}, map_state: { flag_tiles: [] } }}
        userId={1}
        onTileSelect={() => {}}
        isReady={false}
      />
    );
    expect(screen.getByText(/stand on a jail to free its prisoners/i)).toBeInTheDocument();
  });

  it("draws flag and jail overlays with war-style player colors", () => {
    const getPlayerColor = vi.fn((id: number) => (id === 10 ? "#abcdef80" : "#00000000"));
    render(
      <CaptureTheFlagGame
        userId={1}
        onTileSelect={() => {}}
        isReady={false}
        getPlayerColor={getPlayerColor}
        gameData={{
          status: "in_progress",
          player_order: [10, 20],
          map: { tile_data: { special_tiles: [[null, "ctf_jail_p2"]] } },
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

    expect(drawCtfMapIcon).toHaveBeenCalledWith(ctx, expect.anything(), 0, 0, null, 32);
    expect(drawCtfMapIcon).toHaveBeenCalledWith(ctx, expect.anything(), 1, 0, "#abcdef80", 32);
    expect(drawCtfMapIcon).toHaveBeenCalledWith(ctx, expect.anything(), 1, 1, "#FF000080", 32);
    expect(drawCtfMapIcon).toHaveBeenCalledWith(ctx, expect.anything(), 1, 0, "#FF000080", 32);
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

  it("getCtfActionTarget returns unlock when standing on a jail", () => {
    const target = getCtfActionTarget(
      { user_id: 1, can_move: true, tile: [1, 0] },
      {
        gamemode: "Capture The Flag",
        status: "in_progress",
        player_order: [1, 2],
        map: { tile_data: { special_tiles: [[null, "ctf_jail_p2"]] } },
        map_state: {
          flag_tiles: [[null, null]],
        },
      },
      1
    );
    expect(target).toEqual({ kind: "unlock", x: 1, y: 0, owner: 2 });
    expect(
      getCtfJailAt(
        { map: { tile_data: { special_tiles: [[null, "ctf_jail_p2"]] } } },
        1,
        0
      )
    ).toEqual({ x: 1, y: 0, owner: 2 });
  });

  it("patch helpers update map_state cells", () => {
    const base = {
      map_state: {
        flag_tiles: [[{ owner: 0 }]],
      },
    };
    expect(patchFlagTile(base, 0, 0, { owner: 2 }).map_state.flag_tiles[0][0].owner).toBe(2);
  });
});
