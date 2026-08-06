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

  it("skips missing moves, colors low PP, and blocks locked/unusable TM selection", async () => {
    const user = userEvent.setup();
    const onMoveSelect = vi.fn();
    const onMoveHoverStart = vi.fn();

    render(
      <UnitMoveList
        unitState={{
          equipped_move_ids: [1, 99, 3],
          held_tm_move_id: 4,
          move_pp: [1, 0, 3, 2],
          can_move: false,
          unit: { tm_moves: [] },
        }}
        moveMap={{
          1: { id: 1, name: "Scratch", type: "Normal", power: 40, pp: 35 },
          3: { id: 3, name: "Growl", type: "Normal", power: null, pp: 40 },
          4: { id: 4, name: "Hyper Beam", type: "Normal", power: 150, pp: 5 },
        }}
        typeColors={{}}
        moveTargeting
        selectEnabled
        onMoveHoverStart={onMoveHoverStart}
        onMoveHoverEnd={() => {}}
        onMoveSelect={onMoveSelect}
      />,
    );

    expect(screen.getByText("Scratch")).toBeInTheDocument();
    expect(screen.getByText("Growl")).toBeInTheDocument();
    expect(screen.getByText(/Hyper Beam \(TM\)/)).toBeInTheDocument();
    expect(screen.queryByText("99")).not.toBeInTheDocument();

    const scratch = screen.getByRole("button", { name: /Scratch/i });
    expect(scratch).toBeDisabled();
    await user.hover(scratch);
    expect(onMoveHoverStart).not.toHaveBeenCalled();
    await user.click(scratch);
    expect(onMoveSelect).not.toHaveBeenCalled();

    const tm = screen.getByRole("button", { name: /Hyper Beam/i });
    expect(tm).toBeDisabled();
    expect(tm).toHaveAttribute("title", expect.stringMatching(/cannot learn/i));
  });

  it("renders header without types/status and non-removable item label", () => {
    render(
      <UnitInfoHeader
        unit={{ name: "Ditto", asset_folder: "132_ditto", types: [] }}
        currentHp={10}
        maxHp={10}
        statusIconSrc={null}
        typeColors={{}}
        ability={null}
        item={null}
      />,
    );
    expect(screen.getByText("Ditto")).toBeInTheDocument();
    expect(screen.getByText(/Ability:/)).toBeInTheDocument();
    expect(screen.getByText(/Item:/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("shows equipped item text when removal is unavailable", () => {
    render(
      <UnitInfoHeader
        unit={{ name: "Eevee", asset_folder: "133_eevee", types: ["Normal", "Fairy"] }}
        currentHp={12}
        maxHp={20}
        statusIconSrc={null}
        typeColors={{ Normal: "#aaa", Fairy: "#faf" }}
        ability="Run Away"
        item="Oran Berry"
      />,
    );
    expect(screen.getByText(/Oran Berry/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Oran Berry" })).not.toBeInTheDocument();
    expect(screen.getByText("Normal")).toBeInTheDocument();
    expect(screen.getByText("Fairy")).toBeInTheDocument();
  });

  it("renders stats with missing current_stats as question marks", () => {
    render(<UnitInfoStats unitState={{ level: 1 }} getStatColor={() => "#fff"} />);
    expect(screen.getAllByText("?").length).toBeGreaterThanOrEqual(6);
  });

  it("colors mid-range PP yellow and allows selecting a usable move", async () => {
    const user = userEvent.setup();
    const onMoveSelect = vi.fn();
    render(
      <UnitMoveList
        unitState={{
          equipped_move_ids: [1],
          move_pp: [8],
          can_move: true,
        }}
        moveMap={{
          1: { id: 1, name: "Tackle", type: "Normal", power: 40, pp: 20 },
        }}
        typeColors={{}}
        moveTargeting={false}
        selectEnabled
        onMoveHoverStart={() => {}}
        onMoveHoverEnd={() => {}}
        onMoveSelect={onMoveSelect}
      />,
    );
    const pp = screen.getByText("PP: 8/20");
    expect(pp).toHaveStyle({ color: "#eab308" });
    await user.click(screen.getByRole("button", { name: /Tackle/i }));
    expect(onMoveSelect).toHaveBeenCalled();
  });
});
