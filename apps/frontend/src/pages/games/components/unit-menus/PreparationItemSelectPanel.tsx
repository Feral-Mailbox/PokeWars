import { useState } from "react";

export type PreparationItemOption = {
  id: number;
  name: string;
  slug: string;
  category: string;
  cost: number;
};

const ITEM_CATEGORY_OPTIONS = [
  { value: "", label: "All items" },
  { value: "berry", label: "Berries" },
  { value: "gem", label: "Gems" },
  { value: "type_boost", label: "Type Boost" },
] as const;

type PreparationItemSelectPanelProps = {
  items: PreparationItemOption[];
  cash: number;
  currentItemSlug: string | null;
  onSelectItem: (itemId: number) => void;
};

export default function PreparationItemSelectPanel({
  items,
  cash,
  currentItemSlug,
  onSelectItem,
}: PreparationItemSelectPanelProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");

  const currentItem = items.find((item) => item.slug === currentItemSlug) ?? null;
  const currentItemCost = currentItem?.cost ?? 0;
  const query = searchQuery.toLowerCase().trim();

  const filteredItems = items
    .filter((item) => {
      if (categoryFilter && item.category !== categoryFilter) return false;
      return String(item.name || "").toLowerCase().includes(query);
    })
    .sort((a, b) => String(a.name || "").localeCompare(String(b.name || "")));

  const canAffordItem = (item: PreparationItemOption) =>
    cash + currentItemCost >= item.cost;

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
        {ITEM_CATEGORY_OPTIONS.map((option) => (
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
          const isEquipped = item.slug === currentItemSlug;

          return (
            <li key={item.id}>
              <button
                type="button"
                disabled={!affordable}
                onClick={() => onSelectItem(item.id)}
                className={`flex w-full items-center justify-between rounded px-2 py-1 text-left ${
                  isEquipped
                    ? "bg-yellow-700/40 hover:bg-yellow-700/60"
                    : affordable
                      ? "hover:bg-gray-700"
                      : "cursor-not-allowed opacity-50"
                }`}
              >
                <span className="font-medium">{item.name}</span>
                <span className="text-green-400">${item.cost}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
