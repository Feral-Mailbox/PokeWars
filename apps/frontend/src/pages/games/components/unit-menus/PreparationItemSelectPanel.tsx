import { useEffect, useMemo, useState } from "react";
import { formatTmDisplayName, unitCanLearnTmMove } from "./UnitMenuShared";

export type PreparationItemOption = {
  id: number;
  name: string;
  slug: string;
  category: string;
  cost: number;
  move_id?: number | null;
};

const ITEM_CATEGORY_OPTIONS = [
  { value: "", label: "All items", sortId: 0 },
  { value: "berry", label: "Berries", sortId: 1 },
  { value: "gem", label: "Gems", sortId: 68 },
  { value: "type_boost", label: "Type Boost", sortId: 86 },
  { value: "plate", label: "Plates", sortId: 104 },
  { value: "memory", label: "Memories", sortId: 121 },
  { value: "unit_specific", label: "Unit Specific", sortId: 139 },
  { value: "incense", label: "Incense", sortId: 166 },
  { value: "power", label: "Power", sortId: 175 },
  { value: "misc", label: "Misc", sortId: 181 },
  { value: "tm", label: "TMs", sortId: 257 },
] as const;

type PreparationItemSelectPanelProps = {
  items: PreparationItemOption[];
  cash: number;
  currentItemSlug: string | null;
  moveMap: Record<number, { name?: string }>;
  unit?: any;
  onSelectItem: (itemId: number) => void;
};

export default function PreparationItemSelectPanel({
  items,
  cash,
  currentItemSlug,
  moveMap,
  unit,
  onSelectItem,
}: PreparationItemSelectPanelProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");

  const categoryOptions = useMemo(() => {
    const availableCategories = new Set(items.map((item) => item.category));
    return ITEM_CATEGORY_OPTIONS.filter(
      (option) => option.value === "" || availableCategories.has(option.value)
    ).sort((a, b) => a.sortId - b.sortId);
  }, [items]);

  useEffect(() => {
    if (categoryFilter && !categoryOptions.some((option) => option.value === categoryFilter)) {
      setCategoryFilter("");
    }
  }, [categoryFilter, categoryOptions]);

  const currentItem = items.find((item) => item.slug === currentItemSlug) ?? null;
  const currentItemCost = currentItem?.cost ?? 0;
  const query = searchQuery.toLowerCase().trim();

  const getItemDisplayName = (item: PreparationItemOption) => {
    if (item.category !== "tm" || item.move_id == null) {
      return item.name;
    }
    return formatTmDisplayName(item.name, moveMap[item.move_id]?.name);
  };

  const filteredItems = items
    .filter((item) => {
      if (categoryFilter && item.category !== categoryFilter) return false;
      if (!query) return true;
      const displayName = getItemDisplayName(item).toLowerCase();
      return displayName.includes(query) || String(item.name || "").toLowerCase().includes(query);
    })
    .sort((a, b) => a.id - b.id);

  const canAffordItem = (item: PreparationItemOption) =>
    cash + currentItemCost >= item.cost;

  const canUseTmItem = (item: PreparationItemOption) => {
    if (item.category !== "tm" || item.move_id == null) return true;
    return unitCanLearnTmMove(unit, item.move_id);
  };

  return (
    <div className="mt-2 rounded border border-gray-600 bg-gray-900/80 p-3">
      <input
        type="text"
        value={searchQuery}
        onChange={(e) => setSearchQuery(e.target.value)}
        placeholder="Search items..."
        className="mb-2 w-full rounded border border-gray-600 bg-gray-950 px-2 py-1 text-sm text-white placeholder-gray-400 focus:border-yellow-500 focus:outline-none"
      />
      <select
        value={categoryFilter}
        onChange={(e) => setCategoryFilter(e.target.value)}
        className="mb-3 w-full rounded border border-gray-600 bg-gray-950 px-2 py-1 text-sm text-white focus:border-yellow-500 focus:outline-none"
      >
        {categoryOptions.map((option) => (
          <option key={option.value || "all"} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>

      <ul className="max-h-48 space-y-1 overflow-y-auto text-sm">
        {filteredItems.length === 0 && (
          <li className="rounded border border-dashed border-gray-600 px-2 py-2 text-gray-400">
            No items match the current filters.
          </li>
        )}
        {filteredItems.map((item) => {
          const affordable = canAffordItem(item);
          const usable = canUseTmItem(item);
          const isEquipped = item.slug === currentItemSlug;
          const enabled = affordable && usable;

          return (
            <li key={item.id}>
              <button
                type="button"
                disabled={!enabled}
                onClick={() => onSelectItem(item.id)}
                title={!usable ? "This unit cannot learn this TM move." : undefined}
                className={`flex w-full items-center justify-between rounded px-2 py-1 text-left ${
                  isEquipped
                    ? "bg-yellow-700/40 hover:bg-yellow-700/60"
                    : enabled
                      ? "hover:bg-gray-700"
                      : "cursor-not-allowed opacity-50"
                }`}
              >
                <span className="font-medium">{getItemDisplayName(item)}</span>
                <span className="text-green-400">${item.cost}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
