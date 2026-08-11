import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import JailTooltip from "@/pages/games/components/JailTooltip";

describe("JailTooltip", () => {
  it("lists imprisoned units in their owner colors", () => {
    render(
      <JailTooltip
        ownerLabel="rival's jail"
        occupants={[
          { name: "Pikachu", color: "#0000FF" },
          { name: "Eevee", color: "#FF0000" },
        ]}
        x={10}
        y={20}
        visible
      />
    );

    expect(screen.getByText("rival's jail")).toBeInTheDocument();
    expect(screen.getByText("Pikachu")).toHaveStyle({ color: "#0000FF" });
    expect(screen.getByText("Eevee")).toHaveStyle({ color: "#FF0000" });
  });

  it("shows empty copy when the jail has no prisoners", () => {
    render(
      <JailTooltip ownerLabel="testuser's jail" occupants={[]} x={0} y={0} visible />
    );
    expect(screen.getByText("Empty")).toBeInTheDocument();
  });

  it("renders nothing when hidden", () => {
    const { container } = render(
      <JailTooltip ownerLabel="hidden" occupants={[]} x={0} y={0} visible={false} />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
