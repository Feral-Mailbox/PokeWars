import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PreparationUnitSelectMenu from "@/pages/games/components/unit-menus/PreparationUnitSelectMenu";

vi.mock("@/components/units/UnitPortrait", () => ({
  default: ({ assetFolder }: { assetFolder: string }) => (
    <span data-testid={`portrait-${assetFolder}`} />
  ),
}));

const units = [
  { id: 2, name: "Zubat", cost: 50, asset_folder: "zubat", types: ["Poison", "Flying"] },
  { id: 1, name: "Abra", cost: 200, asset_folder: "abra", types: ["Psychic"] },
  { id: 3, name: "", cost: 10, asset_folder: "missing" },
];

const baseProps = {
  availableUnits: units,
  cash: 100,
  unitSearchQuery: "",
  unitTypeFilterPrimary: "",
  unitTypeFilterSecondary: "",
  unitSortBy: "id" as const,
  unitSortDirection: "asc" as const,
  unitTypeOptions: ["Poison", "Flying", "Psychic"],
  typeColors: { Poison: "purple", Flying: "blue" },
  onSearchChange: vi.fn(),
  onPrimaryTypeChange: vi.fn(),
  onSecondaryTypeChange: vi.fn(),
  onSortByChange: vi.fn(),
  onSortDirectionChange: vi.fn(),
  onSelectUnit: vi.fn(),
};

describe("PreparationUnitSelectMenu", () => {
  it("filters, sorts, and reports control changes", async () => {
    const user = userEvent.setup();
    render(<PreparationUnitSelectMenu {...baseProps} />);

    const rows = document.querySelectorAll("[data-unit]");
    expect(rows[0]).toHaveTextContent("Abra");
    expect(rows[1]).toHaveTextContent("Zubat");
    expect(screen.getByTestId("portrait-zubat")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("Search units..."), {
      target: { value: "zu" },
    });
    const selects = screen.getAllByRole("combobox");
    await user.selectOptions(selects[0], "Poison");
    await user.selectOptions(selects[1], "Flying");
    await user.selectOptions(selects[2], "name");
    await user.selectOptions(selects[3], "desc");

    expect(baseProps.onSearchChange).toHaveBeenCalledWith("zu");
    expect(baseProps.onPrimaryTypeChange).toHaveBeenCalledWith("Poison");
    expect(baseProps.onSecondaryTypeChange).toHaveBeenCalledWith("Flying");
    expect(baseProps.onSortByChange).toHaveBeenCalledWith("name");
    expect(baseProps.onSortDirectionChange).toHaveBeenCalledWith("desc");
  });

  it("selects affordable units, excludes unavailable units, and shows empty filters", async () => {
    const user = userEvent.setup();
    const onSelectUnit = vi.fn();
    const { rerender } = render(
      <PreparationUnitSelectMenu {...baseProps} onSelectUnit={onSelectUnit} />
    );

    await user.click(document.querySelectorAll("[data-unit]")[1]);
    expect(onSelectUnit).toHaveBeenCalledWith(expect.objectContaining({ name: "Zubat" }));
    await user.click(screen.getByText("Abra"));
    expect(onSelectUnit).toHaveBeenCalledTimes(1);

    rerender(
      <PreparationUnitSelectMenu
        {...baseProps}
        unitSortBy="name"
        unitSortDirection="desc"
      />
    );
    expect(document.querySelectorAll("[data-unit]")[0]).toHaveTextContent("Zubat");

    rerender(
      <PreparationUnitSelectMenu
        {...baseProps}
        unitTypeFilterPrimary="Poison"
        unitTypeFilterSecondary="Flying"
        unitSortBy="cost"
      />
    );
    expect(document.querySelectorAll("[data-unit]")).toHaveLength(1);
    expect(screen.getByText("Zubat")).toBeInTheDocument();
    expect(screen.getAllByRole("option", { name: "Poison" }).some((option) => option.disabled)).toBe(
      true
    );

    rerender(
      <PreparationUnitSelectMenu
        {...baseProps}
        unitSearchQuery="missing"
        unitTypeFilterPrimary="Psychic"
        unitTypeFilterSecondary="Flying"
        unitSortBy="cost"
        unitSortDirection="desc"
      />
    );
    expect(screen.getByText("No units match the current filters.")).toBeInTheDocument();
  });
});
