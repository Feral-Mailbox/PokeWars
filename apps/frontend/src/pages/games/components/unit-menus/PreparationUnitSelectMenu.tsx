import UnitPortrait from "@/components/units/UnitPortrait";

type PreparationUnitSelectMenuProps = {
  availableUnits: any[];
  unitSearchQuery: string;
  unitTypeFilterPrimary: string;
  unitTypeFilterSecondary: string;
  unitSortBy: "id" | "name" | "cost";
  unitSortDirection: "asc" | "desc";
  unitTypeOptions: string[];
  typeColors: Record<string, string>;
  onSearchChange: (value: string) => void;
  onPrimaryTypeChange: (value: string) => void;
  onSecondaryTypeChange: (value: string) => void;
  onSortByChange: (value: "id" | "name" | "cost") => void;
  onSortDirectionChange: (value: "asc" | "desc") => void;
  onSelectUnit: (unit: any) => void;
};

export default function PreparationUnitSelectMenu({
  availableUnits,
  unitSearchQuery,
  unitTypeFilterPrimary,
  unitTypeFilterSecondary,
  unitSortBy,
  unitSortDirection,
  unitTypeOptions,
  typeColors,
  onSearchChange,
  onPrimaryTypeChange,
  onSecondaryTypeChange,
  onSortByChange,
  onSortDirectionChange,
  onSelectUnit,
}: PreparationUnitSelectMenuProps) {
  const query = unitSearchQuery.toLowerCase().trim();
  const typeFilters = [unitTypeFilterPrimary, unitTypeFilterSecondary].filter(Boolean);

  const filteredUnits = availableUnits
    .filter((unit) => {
      const unitName = String(unit.name || "").toLowerCase();
      if (!unitName.includes(query)) return false;

      const unitTypes = Array.isArray(unit.types) ? unit.types : [];
      return typeFilters.every((type) => unitTypes.includes(type));
    })
    .sort((a, b) => {
      let comparison = 0;
      if (unitSortBy === "name") {
        comparison = String(a.name || "").localeCompare(String(b.name || ""));
      } else if (unitSortBy === "cost") {
        comparison = Number(a.cost ?? 0) - Number(b.cost ?? 0);
      } else {
        comparison = Number(a.id ?? 0) - Number(b.id ?? 0);
      }
      return unitSortDirection === "asc" ? comparison : -comparison;
    });

  return (
    <div className="w-72 bg-gray-800 text-white border border-yellow-500 rounded-lg shadow-lg flex flex-col max-h-[calc(100vh-8rem)] overflow-hidden">
      <div className="p-4 border-b border-yellow-500 bg-gray-800 sticky top-0 z-10 rounded-t-lg">
        <h2 className="text-lg font-bold mb-2">Select a Unit</h2>
        <input
          type="text"
          value={unitSearchQuery}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search units..."
          className="w-full mb-3 px-2 py-1 rounded bg-gray-900 border border-gray-600 text-white placeholder-gray-400 focus:outline-none focus:border-yellow-500"
        />
        <div className="grid grid-cols-2 gap-2 mb-3">
          <select
            value={unitTypeFilterPrimary}
            onChange={(e) => onPrimaryTypeChange(e.target.value)}
            className="w-full px-2 py-1 rounded bg-gray-900 border border-gray-600 text-white focus:outline-none focus:border-yellow-500"
          >
            <option value="">Type 1: Any</option>
            {unitTypeOptions.map((type) => (
              <option key={`primary-${type}`} value={type}>{type}</option>
            ))}
          </select>
          <select
            value={unitTypeFilterSecondary}
            onChange={(e) => onSecondaryTypeChange(e.target.value)}
            className="w-full px-2 py-1 rounded bg-gray-900 border border-gray-600 text-white focus:outline-none focus:border-yellow-500"
          >
            <option value="">Type 2: Any</option>
            {unitTypeOptions.map((type) => (
              <option
                key={`secondary-${type}`}
                value={type}
                disabled={type === unitTypeFilterPrimary}
              >
                {type}
              </option>
            ))}
          </select>
        </div>
        <div className="grid grid-cols-2 gap-2">
          <select
            value={unitSortBy}
            onChange={(e) => onSortByChange(e.target.value as "id" | "name" | "cost")}
            className="w-full px-2 py-1 rounded bg-gray-900 border border-gray-600 text-white focus:outline-none focus:border-yellow-500"
          >
            <option value="id">Sort: ID</option>
            <option value="name">Sort: Name</option>
            <option value="cost">Sort: Price</option>
          </select>
          <select
            value={unitSortDirection}
            onChange={(e) => onSortDirectionChange(e.target.value as "asc" | "desc")}
            className="w-full px-2 py-1 rounded bg-gray-900 border border-gray-600 text-white focus:outline-none focus:border-yellow-500"
          >
            <option value="asc">Ascending</option>
            <option value="desc">Descending</option>
          </select>
        </div>
      </div>
      <ul className="space-y-2 text-sm overflow-y-auto p-4 flex-1 -mt-px">
        {filteredUnits.length === 0 && (
          <li className="px-2 py-2 text-gray-400 border border-dashed border-gray-600 rounded">
            No units match the current filters.
          </li>
        )}
        {filteredUnits.map((unit) => (
          <li
            key={unit.id}
            data-unit
            className="flex items-center justify-between px-2 py-1 hover:bg-gray-700 rounded cursor-pointer"
            onClick={() => onSelectUnit(unit)}
          >
            <div className="flex items-center gap-2">
              <UnitPortrait assetFolder={unit.asset_folder} />
              <div className="leading-tight">
                <div className="font-semibold">{unit.name}</div>
                {unit.types?.length > 0 && (
                  <div className="text-sm text-gray-300">
                    (
                    {unit.types.map((type: string, idx: number) => (
                      <span key={idx}>
                        <span className="font-medium" style={{ color: typeColors[type] || "#fff" }}>
                          {type}
                        </span>
                        {idx < unit.types.length - 1 && <span className="text-white">/</span>}
                      </span>
                    ))}
                    )
                  </div>
                )}
              </div>
            </div>
            <span>${unit.cost}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
