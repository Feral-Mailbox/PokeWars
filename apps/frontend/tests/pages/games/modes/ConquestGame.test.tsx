import { render } from "@testing-library/react";
import ConquestGame from "@/pages/games/modes/ConquestGame";

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
});
