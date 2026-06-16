import { useMemo, useState } from "react";
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
import PreparationAbilitySelectPanel, {
  HIDDEN_ABILITY_COST,
  type PreparationAbilityOption,
} from "./PreparationAbilitySelectPanel";

type PreparationPlacedUnitMenuProps = {
  placedUnitAtTile: any;
  moveMap: Record<number, any>;
  typeColors: Record<string, string>;
  statusIconSrc: string | null;
  getStatColor: (unitState: any, statName: string) => string;
  items: PreparationItemOption[];
  abilities: Array<{ id: number; name: string }>;
  cash: number;
  disabled?: boolean;
  onRemoveUnit: () => void;
  onChangeAbility: (abilityId: number) => void | Promise<void>;
  onChangeItem: (itemId: number) => void | Promise<void>;
  onRemoveItem: () => void | Promise<void>;
  onMoveHoverStart: (move?: any) => void;
  onMoveHoverEnd: () => void;
  onAbilityError?: (message: string) => void;
};

export default function PreparationPlacedUnitMenu({
  placedUnitAtTile,
  moveMap,
  typeColors,
  statusIconSrc,
  getStatColor,
  items,
  abilities,
  cash,
  disabled = false,
  onRemoveUnit,
  onChangeAbility,
  onChangeItem,
  onRemoveItem,
  onMoveHoverStart,
  onMoveHoverEnd,
  onAbilityError,
}: PreparationPlacedUnitMenuProps) {
  const unit = placedUnitAtTile.unit;
  const [abilityPickerOpen, setAbilityPickerOpen] = useState(false);
  const [itemPickerOpen, setItemPickerOpen] = useState(false);

  const abilityNameById = useMemo(
    () => Object.fromEntries(abilities.map((ability) => [ability.id, ability.name])),
    [abilities]
  );

  const abilityOptions: PreparationAbilityOption[] = useMemo(() => {
    const regularIds = Array.isArray(unit?.ability_ids) ? unit.ability_ids : [];
    const options = regularIds.map((abilityId: number) => ({
      id: abilityId,
      name: abilityNameById[abilityId] ?? `Ability ${abilityId}`,
      isHidden: false,
      cost: 0,
    }));

    const hiddenAbilityId = unit?.hidden_ability;
    if (hiddenAbilityId != null) {
      options.push({
        id: hiddenAbilityId,
        name: abilityNameById[hiddenAbilityId] ?? `Ability ${hiddenAbilityId}`,
        isHidden: true,
        cost: HIDDEN_ABILITY_COST,
      });
    }

    return options;
  }, [abilityNameById, unit?.ability_ids, unit?.hidden_ability]);

  const handleSelectAbility = async (abilityId: number) => {
    const hiddenAbilityId = unit?.hidden_ability ?? null;
    const currentAbilityId = placedUnitAtTile?.ability_id ?? null;
    const selectingHidden = hiddenAbilityId != null && abilityId === hiddenAbilityId;
    const currentlyHidden =
      hiddenAbilityId != null && currentAbilityId === hiddenAbilityId;

    if (selectingHidden && !currentlyHidden && cash < HIDDEN_ABILITY_COST) {
      onAbilityError?.("You don't have enough cash for this hidden ability!");
      return;
    }

    await onChangeAbility(abilityId);
    setAbilityPickerOpen(false);
  };

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
          onClick={() => {
            setItemPickerOpen(false);
            setAbilityPickerOpen((open) => !open);
          }}
          className={`flex-1 font-bold py-2 px-4 rounded text-white disabled:cursor-not-allowed disabled:opacity-50 ${
            abilityPickerOpen ? "bg-yellow-600 hover:bg-yellow-700" : "bg-gray-600 hover:bg-gray-700"
          }`}
        >
          Change Ability
        </button>
        <button
          type="button"
          disabled={disabled}
          onClick={() => {
            setAbilityPickerOpen(false);
            setItemPickerOpen((open) => !open);
          }}
          className={`flex-1 font-bold py-2 px-4 rounded text-white disabled:cursor-not-allowed disabled:opacity-50 ${
            itemPickerOpen ? "bg-yellow-600 hover:bg-yellow-700" : "bg-gray-600 hover:bg-gray-700"
          }`}
        >
          Change Item
        </button>
      </div>

      {abilityPickerOpen && !disabled && (
        <PreparationAbilitySelectPanel
          abilities={abilityOptions}
          cash={cash}
          currentAbilityId={placedUnitAtTile?.ability_id ?? null}
          onSelectAbility={handleSelectAbility}
        />
      )}

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
