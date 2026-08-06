import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PreparationPlacedUnitMenu from "@/pages/games/components/unit-menus/PreparationPlacedUnitMenu";

const { headerSpy } = vi.hoisted(() => ({ headerSpy: vi.fn() }));

vi.mock("@/pages/games/components/unit-menus/UnitMenuShared", () => ({
  UNIT_MENU_WIDTH_CLASS: "unit-menu",
  formatTmDisplayName: (item: string, move?: string) => `${item} - ${move}`,
  UnitInfoHeader: (props: any) => {
    headerSpy(props);
    return (
      <div>
        <span data-testid="equipped-item">{props.item}</span>
        {props.onRemoveItem && <button onClick={props.onRemoveItem}>Remove item</button>}
      </div>
    );
  },
  UnitInfoStats: () => <div data-testid="stats" />,
  UnitMoveList: () => <div data-testid="moves" />,
  UnitCredits: () => <div data-testid="credits" />,
}));

vi.mock("@/pages/games/components/unit-menus/PreparationAbilitySelectPanel", () => ({
  HIDDEN_ABILITY_COST: 250,
  default: ({ abilities, onSelectAbility }: any) => (
    <div data-testid="ability-picker">
      {abilities.map((ability: any) => (
        <button key={ability.id} onClick={() => onSelectAbility(ability.id)}>
          {ability.name}
        </button>
      ))}
    </div>
  ),
}));

vi.mock("@/pages/games/components/unit-menus/PreparationItemSelectPanel", () => ({
  default: ({ onSelectItem }: any) => (
    <button data-testid="item-picker" onClick={() => onSelectItem(2)}>
      Select item
    </button>
  ),
}));

const baseProps = {
  placedUnitAtTile: {
    unit: { name: "Pikachu", ability_ids: [1], hidden_ability: 2 },
    current_hp: 30,
    current_stats: { hp: 35 },
    ability_id: 1,
    held_item_slug: "tm01",
    held_item: "TM01",
  },
  moveMap: { 9: { name: "Focus Punch" } },
  typeColors: {},
  statusIconSrc: null,
  getStatColor: vi.fn(() => "white"),
  items: [{ id: 2, name: "TM01", slug: "tm01", category: "tm", cost: 100, move_id: 9 }],
  abilities: [
    { id: 1, name: "Static" },
    { id: 2, name: "Lightning Rod" },
  ],
  cash: 300,
  onRemoveUnit: vi.fn(),
  onChangeAbility: vi.fn(),
  onChangeItem: vi.fn(),
  onRemoveItem: vi.fn(),
  onMoveHoverStart: vi.fn(),
  onMoveHoverEnd: vi.fn(),
};

describe("PreparationPlacedUnitMenu", () => {
  it("switches pickers and applies ability and item choices", async () => {
    const user = userEvent.setup();
    const onChangeAbility = vi.fn();
    const onChangeItem = vi.fn();
    const onRemoveUnit = vi.fn();
    const onRemoveItem = vi.fn();
    render(
      <PreparationPlacedUnitMenu
        {...baseProps}
        onChangeAbility={onChangeAbility}
        onChangeItem={onChangeItem}
        onRemoveUnit={onRemoveUnit}
        onRemoveItem={onRemoveItem}
      />
    );

    expect(screen.getByTestId("equipped-item")).toHaveTextContent("TM01 - Focus Punch");
    await user.click(screen.getByRole("button", { name: "Change Ability" }));
    expect(screen.getByTestId("ability-picker")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Static" }));
    expect(onChangeAbility).toHaveBeenCalledWith(1);
    expect(screen.queryByTestId("ability-picker")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Change Item" }));
    expect(screen.getByTestId("item-picker")).toBeInTheDocument();
    await user.click(screen.getByTestId("item-picker"));
    expect(onChangeItem).toHaveBeenCalledWith(2);
    expect(screen.queryByTestId("item-picker")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Remove item" }));
    await user.click(screen.getByRole("button", { name: "Remove Unit" }));
    expect(onRemoveItem).toHaveBeenCalledOnce();
    expect(onRemoveUnit).toHaveBeenCalledOnce();
  });

  it("reports unaffordable hidden abilities and disables all controls", async () => {
    const user = userEvent.setup();
    const onAbilityError = vi.fn();
    render(
      <PreparationPlacedUnitMenu
        {...baseProps}
        cash={100}
        onAbilityError={onAbilityError}
      />
    );

    await user.click(screen.getByRole("button", { name: "Change Ability" }));
    await user.click(screen.getByRole("button", { name: "Lightning Rod" }));
    expect(onAbilityError).toHaveBeenCalledWith(
      "You don't have enough cash for this hidden ability!"
    );

    const { rerender } = render(<PreparationPlacedUnitMenu {...baseProps} disabled />);
    expect(screen.getAllByRole("button", { name: "Change Ability" }).at(-1)).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Change Item" }).at(-1)).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Remove Unit" }).at(-1)).toBeDisabled();
    rerender(
      <PreparationPlacedUnitMenu
        {...baseProps}
        placedUnitAtTile={{
          ...baseProps.placedUnitAtTile,
          held_item_slug: null,
          held_item: "Oran Berry",
        }}
      />
    );
    expect(headerSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ item: "Oran Berry", onRemoveItem: undefined })
    );
  });

  it("handles missing ability names, non-tm items, and already-hidden selection", async () => {
    const user = userEvent.setup();
    const onChangeAbility = vi.fn();
    render(
      <PreparationPlacedUnitMenu
        {...baseProps}
        abilities={[{ id: 2, name: "Lightning Rod" }]}
        items={[
          { id: 3, name: "Leftovers", slug: "leftovers", category: "held", cost: 50 },
          { id: 4, name: "TM99", slug: "tm99", category: "tm", cost: 50, move_id: 404 },
        ]}
        placedUnitAtTile={{
          ...baseProps.placedUnitAtTile,
          ability_id: 2,
          unit: { name: "Pikachu", ability_ids: [99], hidden_ability: 2 },
          held_item_slug: "leftovers",
          held_item: "Leftovers",
        }}
        onChangeAbility={onChangeAbility}
      />,
    );

    expect(headerSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ item: "Leftovers" }),
    );

    await user.click(screen.getByRole("button", { name: "Change Ability" }));
    expect(screen.getByRole("button", { name: "Ability 99" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Lightning Rod" }));
    expect(onChangeAbility).toHaveBeenCalledWith(2);

    const { rerender } = render(
      <PreparationPlacedUnitMenu
        {...baseProps}
        placedUnitAtTile={{
          ...baseProps.placedUnitAtTile,
          held_item_slug: "missing-slug",
          held_item: "Fallback Item",
          unit: { name: "Pikachu", ability_ids: null, hidden_ability: null },
        }}
      />,
    );
    expect(headerSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ item: "Fallback Item" }),
    );

    rerender(
      <PreparationPlacedUnitMenu
        {...baseProps}
        items={[{ id: 4, name: "TM99", slug: "tm99", category: "tm", cost: 50, move_id: 404 }]}
        moveMap={{}}
        placedUnitAtTile={{
          ...baseProps.placedUnitAtTile,
          held_item_slug: "tm99",
          held_item: "TM99",
        }}
      />,
    );
    expect(headerSpy).toHaveBeenLastCalledWith(
      expect.objectContaining({ item: "TM99 - undefined" }),
    );
  });
});
