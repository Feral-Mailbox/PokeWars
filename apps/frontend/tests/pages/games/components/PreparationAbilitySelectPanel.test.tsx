import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PreparationAbilitySelectPanel, {
  HIDDEN_ABILITY_COST,
} from "@/pages/games/components/unit-menus/PreparationAbilitySelectPanel";

describe("PreparationAbilitySelectPanel", () => {
  const abilities = [
    { id: 1, name: "Static", isHidden: false, cost: 0 },
    { id: 2, name: "Lightning Rod", isHidden: true, cost: HIDDEN_ABILITY_COST },
  ];

  it("renders empty state and selects affordable abilities", async () => {
    const user = userEvent.setup();
    const onSelectAbility = vi.fn();
    const { rerender } = render(
      <PreparationAbilitySelectPanel
        abilities={[]}
        cash={0}
        currentAbilityId={null}
        onSelectAbility={onSelectAbility}
      />
    );
    expect(screen.getByText(/no abilities/i)).toBeInTheDocument();

    rerender(
      <PreparationAbilitySelectPanel
        abilities={abilities}
        cash={100}
        currentAbilityId={1}
        onSelectAbility={onSelectAbility}
      />
    );

    expect(screen.getByRole("button", { name: /Static/i })).toBeEnabled();
    const hidden = screen.getByRole("button", { name: /Lightning Rod/i });
    expect(hidden).toBeDisabled();
    expect(screen.getByText(`$${HIDDEN_ABILITY_COST}`)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Static/i }));
    expect(onSelectAbility).toHaveBeenCalledWith(1);
  });

  it("allows selecting hidden abilities when already owned or affordable", async () => {
    const user = userEvent.setup();
    const onSelectAbility = vi.fn();
    render(
      <PreparationAbilitySelectPanel
        abilities={abilities}
        cash={HIDDEN_ABILITY_COST}
        currentAbilityId={null}
        onSelectAbility={onSelectAbility}
      />
    );
    await user.click(screen.getByRole("button", { name: /Lightning Rod/i }));
    expect(onSelectAbility).toHaveBeenCalledWith(2);
  });
});
