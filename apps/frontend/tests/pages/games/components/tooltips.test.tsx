import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MapItemTooltip from "@/pages/games/components/MapItemTooltip";
import UnitStateTooltip from "@/pages/games/components/unit-menus/UnitStateTooltip";
import UnitStateIndicator from "@/pages/games/components/unit-menus/UnitStateIndicator";

describe("game tooltips and state indicator", () => {
  it("renders MapItemTooltip only when visible with a label", () => {
    const { rerender } = render(
      <MapItemTooltip label="Potion" x={10} y={20} visible={false} />
    );
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    rerender(<MapItemTooltip label="Potion" x={10} y={20} visible />);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Potion");

    rerender(<MapItemTooltip label="" x={10} y={20} visible />);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("renders UnitStateTooltip content", () => {
    render(
      <UnitStateTooltip
        content={{
          name: "Confusion",
          description: "May hurt itself",
          roundsLine: "2 rounds left",
        }}
        x={5}
        y={8}
        visible
      />
    );
    expect(screen.getByRole("tooltip")).toHaveTextContent("Confusion");
    expect(screen.getByText("May hurt itself")).toBeInTheDocument();
    expect(screen.getByText("2 rounds left")).toBeInTheDocument();
  });

  it("shows UnitStateIndicator and opens tooltip on hover", async () => {
    const user = userEvent.setup();
    render(<UnitStateIndicator states={["confusion", 3]} />);

    const button = screen.getByRole("button", { name: /Active state: Confusion/i });
    await user.hover(button);
    expect(screen.getByRole("tooltip")).toHaveTextContent("Confusion");

    await user.unhover(button);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });

  it("returns null when there is no active state", () => {
    const { container } = render(<UnitStateIndicator states={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});
