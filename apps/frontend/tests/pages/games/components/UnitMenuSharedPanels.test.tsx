import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  UnitInfoHeader,
  UnitInfoStats,
  UnitMoveList,
} from "@/pages/games/components/unit-menus/UnitMenuShared";

vi.mock("@/components/units/UnitPortrait", () => ({
  default: () => <div data-testid="portrait" />,
}));

vi.mock("@/pages/games/components/unit-menus/UnitStateIndicator", () => ({
  default: () => null,
}));

describe("UnitMenuShared panels", () => {
  it("renders header with types, ability, and removable item", async () => {
    const user = userEvent.setup();
    const onRemoveItem = vi.fn();
    render(
      <UnitInfoHeader
        unit={{
          name: "Pikachu",
          asset_folder: "025_pikachu",
          types: ["Electric"],
        }}
        currentHp={20}
        maxHp={35}
        statusIconSrc="/status.png"
        typeColors={{ Electric: "#ff0" }}
        ability="Static"
        item="Oran Berry"
        onRemoveItem={onRemoveItem}
      />
    );

    expect(screen.getByText("Pikachu")).toBeInTheDocument();
    expect(screen.getByText("20/35")).toBeInTheDocument();
    expect(screen.getByText("Electric")).toBeInTheDocument();
    expect(screen.getByText(/Ability: Static/)).toBeInTheDocument();
    expect(screen.getByAltText("Status")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Oran Berry" }));
    expect(onRemoveItem).toHaveBeenCalled();
  });

  it("renders stats with colored values", () => {
    render(
      <UnitInfoStats
        unitState={{
          level: 50,
          current_stats: {
            attack: 10,
            defense: 11,
            sp_attack: 12,
            sp_defense: 13,
            speed: 14,
            range: 2,
          },
        }}
        getStatColor={() => "red"}
      />
    );
    expect(screen.getByText(/Level: 50/)).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
  });

  it("lists moves including TM move and handles selection", async () => {
    const user = userEvent.setup();
    const onMoveSelect = vi.fn();
    const onMoveHoverStart = vi.fn();
    const onMoveHoverEnd = vi.fn();

    render(
      <UnitMoveList
        unitState={{
          equipped_move_ids: [1],
          held_tm_move_id: 2,
          move_pp: [5, 1],
          can_move: true,
          unit: { tm_moves: [2] },
        }}
        moveMap={{
          1: { id: 1, name: "Thunderbolt", type: "Electric", power: 90, pp: 15 },
          2: { id: 2, name: "Focus Punch", type: "Fighting", power: 150, pp: 5 },
        }}
        typeColors={{ Electric: "#ff0", Fighting: "#a00" }}
        moveTargeting={false}
        selectEnabled
        onMoveHoverStart={onMoveHoverStart}
        onMoveHoverEnd={onMoveHoverEnd}
        onMoveSelect={onMoveSelect}
      />
    );

    expect(screen.getByText("Thunderbolt")).toBeInTheDocument();
    expect(screen.getByText(/Focus Punch \(TM\)/)).toBeInTheDocument();
    await user.hover(screen.getByRole("button", { name: /Thunderbolt/i }));
    expect(onMoveHoverStart).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: /Thunderbolt/i }));
    expect(onMoveSelect).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Thunderbolt" })
    );
  });

  it("returns null when there are no moves", () => {
    const { container } = render(
      <UnitMoveList
        unitState={{ equipped_move_ids: [] }}
        moveMap={{}}
        typeColors={{}}
        moveTargeting={false}
        selectEnabled={false}
        onMoveHoverStart={() => {}}
        onMoveHoverEnd={() => {}}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
