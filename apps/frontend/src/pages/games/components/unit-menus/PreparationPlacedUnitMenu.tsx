import { useState } from "react";
import {
  UNIT_MENU_WIDTH_CLASS,
  UnitCredits,
  UnitInfoHeader,
  UnitInfoStats,
  UnitMoveList,
} from "./UnitMenuShared";
import PreparationItemSelectPanel, {
  type PreparationItemOption,
} from "./PreparationItemSelectPanel";

type PreparationPlacedUnitMenuProps = {
  placedUnitAtTile: any;
  moveMap: Record<number, any>;
  typeColors: Record<string, string>;
  statusIconSrc: string | null;
  getStatColor: (unitState: any, statName: string) => string;
  items: PreparationItemOption[];
  cash: number;
  disabled?: boolean;
  onRemoveUnit: () => void;
  onChangeItem: (itemId: number) => void | Promise<void>;
  onRemoveItem: () => void | Promise<void>;
  onMoveHoverStart: (move?: any) => void;
  onMoveHoverEnd: () => void;
};

export default function PreparationPlacedUnitMenu({
  placedUnitAtTile,
  moveMap,
  typeColors,
  statusIconSrc,
  getStatColor,
  items,
  cash,
  disabled = false,
  onRemoveUnit,
  onChangeItem,
  onRemoveItem,
  onMoveHoverStart,
  onMoveHoverEnd,
}: PreparationPlacedUnitMenuProps) {
  const unit = placedUnitAtTile.unit;
  const [itemPickerOpen, setItemPickerOpen] = useState(false);

  const handleSelectItem = async (itemId: number) => {
    await onChangeItem(itemId);
    setItemPickerOpen(false);
  };

  return (
    <div className={`${UNIT_MENU_WIDTH_CLASS} bg-gray-800 text-white p-4 border border-yellow-500 rounded-lg shadow-lg max-h-[calc(100vh-8rem)] overflow-y-auto`}>
      <UnitInfoHeader
        unit={unit}
        currentHp={placedUnitAtTile?.current_hp ?? 0}
        maxHp={placedUnitAtTile?.current_stats?.hp ?? 0}
        statusIconSrc={statusIconSrc}
        states={placedUnitAtTile?.states}
        typeColors={typeColors}
        ability={placedUnitAtTile?.ability}
        item={placedUnitAtTile?.held_item}
        onRemoveItem={!disabled && placedUnitAtTile?.held_item_slug ? onRemoveItem : undefined}
      />

      <UnitInfoStats unitState={placedUnitAtTile} getStatColor={getStatColor} />

      <UnitMoveList
        unitState={placedUnitAtTile}
        moveMap={moveMap}
        typeColors={typeColors}
        moveTargeting={false}
        selectEnabled={false}
        onMoveHoverStart={onMoveHoverStart}
        onMoveHoverEnd={onMoveHoverEnd}
      />

      <div className="mt-4 flex gap-2">
        <button
          type="button"
          disabled={disabled}
          className="flex-1 bg-gray-600 hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-50 text-white font-bold py-2 px-4 rounded"
        >
          Change Ability
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => setItemPickerOpen((open) => !open)}
          className={`flex-1 font-bold py-2 px-4 rounded text-white disabled:cursor-not-allowed disabled:opacity-50 ${
            itemPickerOpen ? "bg-yellow-600 hover:bg-yellow-700" : "bg-gray-600 hover:bg-gray-700"
          }`}
        >
          Change Item
        </button>
      </div>

      {itemPickerOpen && !disabled && (
        <PreparationItemSelectPanel
          items={items}
          cash={cash}
          currentItemSlug={placedUnitAtTile?.held_item_slug ?? null}
          onSelectItem={handleSelectItem}
        />
      )}

      <button
        className="mt-2 w-full bg-red-600 hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50 text-white font-bold py-2 px-4 rounded"
        onClick={onRemoveUnit}
        disabled={disabled}
      >
        Remove Unit
      </button>

      <UnitCredits unit={unit} />
    </div>
  );
}
