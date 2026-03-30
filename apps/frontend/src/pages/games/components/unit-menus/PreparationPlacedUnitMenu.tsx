import { UnitCredits, UnitInfoHeader, UnitInfoStats, UnitMoveList } from "./UnitMenuShared";

type PreparationPlacedUnitMenuProps = {
  placedUnitAtTile: any;
  moveMap: Record<number, any>;
  typeColors: Record<string, string>;
  statusIconSrc: string | null;
  getStatColor: (unitState: any, statName: string) => string;
  onRemoveUnit: () => void;
  onMoveHoverStart: (move?: any) => void;
  onMoveHoverEnd: () => void;
};

export default function PreparationPlacedUnitMenu({
  placedUnitAtTile,
  moveMap,
  typeColors,
  statusIconSrc,
  getStatColor,
  onRemoveUnit,
  onMoveHoverStart,
  onMoveHoverEnd,
}: PreparationPlacedUnitMenuProps) {
  const unit = placedUnitAtTile.unit;

  return (
    <div className="w-72 bg-gray-800 text-white p-4 border border-yellow-500 rounded-lg shadow-lg max-h-[calc(100vh-8rem)] overflow-y-auto">
      <UnitInfoHeader
        unit={unit}
        currentHp={placedUnitAtTile?.current_hp ?? 0}
        maxHp={placedUnitAtTile?.current_stats?.hp ?? 0}
        statusIconSrc={statusIconSrc}
        typeColors={typeColors}
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

      <button
        className="mt-4 w-full bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
        onClick={onRemoveUnit}
      >
        Remove Unit
      </button>

      <UnitCredits unit={unit} />
    </div>
  );
}
