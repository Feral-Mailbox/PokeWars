import { render, screen } from "@testing-library/react";
import WarGame from "@/pages/games/modes/WARGame";

describe("WarGame", () => {
  it("renders the War mode description", () => {
    render(<WarGame gameData={{}} userId={1} />);
    expect(
      screen.getByText(/War Mode: Eliminate all enemies to win/i)
    ).toBeInTheDocument();
  });
});
