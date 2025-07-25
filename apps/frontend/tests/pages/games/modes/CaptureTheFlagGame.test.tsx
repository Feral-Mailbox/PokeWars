import { render, screen } from "@testing-library/react";
import CaptureTheFlagGame from "@/pages/games/modes/CaptureTheFlagGame";

describe("CaptureTheFlagGame", () => {
  it("renders the CTF mode description", () => {
    render(<CaptureTheFlagGame gameData={{}} userId={1} />);
    expect(
      screen.getByText(/Capture the Flag: Seize your opponent/i)
    ).toBeInTheDocument();
  });
});
