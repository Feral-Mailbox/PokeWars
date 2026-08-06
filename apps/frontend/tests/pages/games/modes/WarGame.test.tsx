import { fireEvent, render, screen } from "@testing-library/react";
import { vi } from "vitest";
import WarGame, {
  canSelectWarObjectiveTile,
  canSummonOnObjective,
  getCurrentRound,
  getWarCaptureTarget,
  getWarPlayerNumber,
  isWarObjectiveTileOccupied,
  patchObjectiveTile,
} from "@/pages/games/modes/WarGame";

const { pointerToTileCoords } = vi.hoisted(() => ({ pointerToTileCoords: vi.fn() }));
vi.mock("@/hooks/useMapRenderer", () => ({ useMapRenderer: vi.fn() }));
vi.mock("@/utils/mapPointer", () => ({ pointerToTileCoords }));

describe("WarGame", () => {
  it("renders the War mode description", () => {
    render(
      <WarGame
        gameData={{ status: "open", map: { width: 1, height: 1, tile_data: {}, tileset_names: [] } }}
        userId={1}
        onObjectiveSelect={() => {}}
        isMyTurn={false}
        isReady={false}
        placedUnits={[]}
      />
    );
    expect(
      screen.getByText(/War Mode: Capture objectives, summon units/i)
    ).toBeInTheDocument();
  });

  it("allows selecting owned objectives during the player's turn", () => {
    const gameData = {
      status: "in_progress",
      current_turn: 1,
      player_order: [10, 20],
      map_state: {
        objective_tiles: [[{ kind: "pokeball", owner: 1, hp: 20, max_hp: 20 }]],
      },
    };

    expect(getWarPlayerNumber(gameData, 10)).toBe(1);
    expect(canSelectWarObjectiveTile(gameData, 10, 0, 0, [])).toBe(true);
    expect(canSelectWarObjectiveTile(gameData, 20, 0, 0, [])).toBe(false);
  });

  it("selects an eligible objective and clears invalid objective clicks", () => {
    pointerToTileCoords.mockReturnValueOnce([0, 0]).mockReturnValueOnce([1, 0]);
    const onObjectiveSelect = vi.fn();
    const canvas = document.createElement("canvas");
    canvas.id = "mapCanvas";
    document.body.append(canvas);
    const gameData = {
      status: "preparation",
      player_order: [10, 20],
      map: { width: 2, height: 1 },
      map_state: {
        objective_tiles: [
          [
            { kind: "pokeball", owner: 1, hp: 20, max_hp: 20 },
            { kind: "pokeball", owner: 2, hp: 20, max_hp: 20 },
          ],
        ],
      },
    };

    const { unmount } = render(
      <WarGame
        gameData={gameData}
        userId={10}
        onObjectiveSelect={onObjectiveSelect}
        isMyTurn={false}
      />,
    );
    fireEvent.click(canvas);
    fireEvent.click(canvas);

    expect(onObjectiveSelect).toHaveBeenNthCalledWith(1, [0, 0]);
    expect(onObjectiveSelect).toHaveBeenNthCalledWith(2, null);
    unmount();
    canvas.remove();
  });

  it("renders in-progress income and does not bind clicks when not selectable", () => {
    const { rerender } = render(
      <WarGame
        gameData={{
          status: "in_progress",
          cash_per_turn: 25,
          player_order: [10, 20],
          map: { width: 1, height: 1 },
          map_state: {
            objective_tiles: [[{ kind: "pokeball", owner: 1, hp: 20, max_hp: 20 }]],
          },
        }}
        userId={10}
        onObjectiveSelect={() => {}}
        isMyTurn
      />,
    );
    expect(screen.getByText(/Income next round:/)).toHaveTextContent("$25");
    expect(screen.getByText(/\(1 objective/)).toBeInTheDocument();

    rerender(
      <WarGame
        gameData={{ status: "preparation", map: { width: 1, height: 1 }, map_state: {} }}
        userId={10}
        onObjectiveSelect={() => {}}
        isMyTurn={false}
        isReady
      />,
    );
    expect(screen.queryByText(/Click one of your objectives/)).not.toBeInTheDocument();
  });

  it("covers objective helper edge cases and capture state patches", () => {
    const objective = { kind: "pokeball" as const, owner: 1, hp: 10, max_hp: 20 };
    const gameData = {
      gamemode: "War",
      status: "in_progress",
      current_turn: 3,
      player_order: [10, 20],
      map_state: { objective_tiles: [[objective]] },
    };
    expect(getWarPlayerNumber({}, 10)).toBe(0);
    expect(getCurrentRound({})).toBe(1);
    expect(getCurrentRound(gameData)).toBe(2);
    expect(canSummonOnObjective(objective, 2, 2)).toBe(false);
    expect(canSummonOnObjective({ ...objective, last_summon_round: 2 }, 1, 2)).toBe(false);
    expect(canSummonOnObjective({ ...objective, last_summon_round: 1 }, 1, 2)).toBe(true);
    expect(isWarObjectiveTileOccupied([{ tile: [0, 0], current_hp: 0 }], 0, 0)).toBe(false);
    expect(isWarObjectiveTileOccupied([{ tile: [0, 0] }], 0, 0)).toBe(true);
    expect(canSelectWarObjectiveTile({ status: "open" }, 10, 0, 0)).toBe(false);
    expect(canSelectWarObjectiveTile(gameData, 99, 0, 0)).toBe(false);
    expect(canSelectWarObjectiveTile(gameData, 10, 0, 0, [{ tile: [0, 0] }])).toBe(false);

    expect(patchObjectiveTile(gameData, 3, 3, { hp: 1, owner: 2 })).toBe(gameData);
    const patched = patchObjectiveTile(gameData, 0, 0, { hp: 5, owner: 2, kind: "master_ball" });
    expect(patched.map_state.objective_tiles[0][0]).toMatchObject({
      hp: 5,
      owner: 2,
      kind: "master_ball",
    });
    const captureGame = {
      ...gameData,
      map_state: { objective_tiles: [[{ ...objective, owner: 2 }]] },
    };
    expect(
      getWarCaptureTarget(
        { user_id: 10, can_move: true, tile: [0, 0] },
        captureGame,
        10,
      ),
    ).toEqual({ x: 0, y: 0, hp: 10, max_hp: 20 });
    expect(getWarCaptureTarget({ user_id: 20, tile: [0, 0] }, gameData, 10)).toBeNull();
    expect(getWarCaptureTarget({ user_id: 10, can_move: false, tile: [0, 0] }, gameData, 10)).toBeNull();
    expect(getWarCaptureTarget({ user_id: 10, tile: [0, 0] }, { ...gameData, gamemode: "Conquest" }, 10)).toBeNull();
  });
});
