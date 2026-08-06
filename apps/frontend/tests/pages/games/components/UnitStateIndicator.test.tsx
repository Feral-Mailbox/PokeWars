import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import UnitStateIndicator from "@/pages/games/components/unit-menus/UnitStateIndicator";

describe("UnitStateIndicator", () => {
  it("returns nothing when no active state exists", () => {
    const { container } = render(<UnitStateIndicator states={["confusion", 0]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("opens, positions, and closes its tooltip for pointer and focus interactions", () => {
    render(<UnitStateIndicator states={["reflect", 2]} />);
    const indicator = screen.getByRole("button", { name: "Active state: Reflect" });
    Object.defineProperty(indicator, "getBoundingClientRect", {
      value: () => ({ left: 10, width: 20, bottom: 30 }),
    });

    fireEvent.mouseEnter(indicator, { clientX: 5, clientY: 6 });
    expect(screen.getByRole("tooltip")).toHaveTextContent("Reflect");
    fireEvent.mouseMove(indicator, { clientX: 7, clientY: 8 });
    fireEvent.mouseLeave(indicator);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();

    fireEvent.focus(indicator);
    expect(screen.getByRole("tooltip")).toHaveTextContent("2 rounds left");
    fireEvent.blur(indicator);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});
