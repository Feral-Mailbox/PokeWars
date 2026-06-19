import { render, screen } from "@testing-library/react";
import WarGame, {
  canSelectWarObjectiveTile,
  getWarPlayerNumber,
} from "@/pages/games/modes/WarGame";

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
});
