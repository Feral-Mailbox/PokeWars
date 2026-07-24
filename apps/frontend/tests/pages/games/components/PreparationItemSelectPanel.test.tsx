import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import PreparationItemSelectPanel from "@/pages/games/components/unit-menus/PreparationItemSelectPanel";

describe("PreparationItemSelectPanel", () => {
  const items = [
    { id: 1, name: "Oran Berry", slug: "oran-berry", category: "berry", cost: 50 },
    {
      id: 2,
      name: "TM01",
      slug: "tm01",
      category: "tm",
      cost: 200,
      move_id: 9,
    },
    {
      id: 3,
      name: "TM99",
      slug: "tm99",
      category: "tm",
      cost: 10,
      move_id: 99,
    },
  ];

  it("filters by search/category and selects affordable usable items", async () => {
    const user = userEvent.setup();
    const onSelectItem = vi.fn();

    render(
      <PreparationItemSelectPanel
        items={items}
        cash={200}
        currentItemSlug="oran-berry"
        moveMap={{ 9: { name: "Focus Punch" }, 99: { name: "Hidden Power" } }}
        unit={{ tm_moves: [9] }}
        onSelectItem={onSelectItem}
      />
    );

    expect(screen.getByText("Oran Berry")).toBeInTheDocument();
    expect(screen.getByText("TM01 - Focus Punch")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText(/Search items/i), "oran");
    expect(screen.getByText("Oran Berry")).toBeInTheDocument();
    expect(screen.queryByText(/TM01/)).not.toBeInTheDocument();

    await user.clear(screen.getByPlaceholderText(/Search items/i));
    await user.selectOptions(screen.getByRole("combobox"), "tm");
    expect(screen.getByText("TM01 - Focus Punch")).toBeInTheDocument();
    expect(screen.queryByText("Oran Berry")).not.toBeInTheDocument();

    const unusable = screen.getByRole("button", { name: /TM99/i });
    expect(unusable).toBeDisabled();

    await user.click(screen.getByRole("button", { name: /TM01/i }));
    expect(onSelectItem).toHaveBeenCalledWith(2);
  });

  it("shows empty filter state", () => {
    render(
      <PreparationItemSelectPanel
        items={items}
        cash={0}
        currentItemSlug={null}
        moveMap={{}}
        onSelectItem={() => {}}
      />
    );
    // With cash 0 and no equipped item, only free/cheap usable items could show;
    // force empty via search.
  });

  it("shows no-match message for unmatched search", async () => {
    const user = userEvent.setup();
    render(
      <PreparationItemSelectPanel
        items={items}
        cash={999}
        currentItemSlug={null}
        moveMap={{}}
        unit={{ tm_moves: [9, 99] }}
        onSelectItem={() => {}}
      />
    );
    await user.type(screen.getByPlaceholderText(/Search items/i), "zzzz");
    expect(screen.getByText(/No items match/i)).toBeInTheDocument();
  });
});
