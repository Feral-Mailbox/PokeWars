import { UnitCredits, UnitInfoHeader, UnitInfoStats, UnitMoveList } from "./UnitMenuShared";

type InProgressUnitMenuProps = {
  activeUnit: any;
  typeColors: Record<string, string>;
  statusIconSrc: string | null;
  getStatColor: (unitState: any, statName: string) => string;
  moveMap: Record<number, any>;
  moveTargeting: boolean;
  selectedMove: any;
  onMoveHoverStart: (move?: any) => void;
  onMoveHoverEnd: () => void;
  onMoveSelect: (move: any) => void;
  onExecuteMove: () => void;
  onCancelMove: () => void;
  getPlayerColor: (playerId: number) => string;
};

export default function InProgressUnitMenu({
  activeUnit,
  typeColors,
  statusIconSrc,
  getStatColor,
  moveMap,
  moveTargeting,
  selectedMove,
  onMoveHoverStart,
  onMoveHoverEnd,
  onMoveSelect,
  onExecuteMove,
  onCancelMove,
  getPlayerColor,
}: InProgressUnitMenuProps) {
  const unit = activeUnit.unit;

  return (
    <div
      data-unit-info
      className="w-72 bg-gray-800 text-white p-4 rounded-lg shadow-lg max-h-[calc(100vh-8rem)] overflow-y-auto"
      style={{ border: `2px solid ${getPlayerColor(activeUnit.user_id)}` }}
    >
      <UnitInfoHeader
        unit={unit}
        currentHp={activeUnit?.current_hp ?? 0}
        maxHp={activeUnit?.current_stats?.hp ?? 0}
        statusIconSrc={statusIconSrc}
        typeColors={typeColors}
      />

      <UnitInfoStats unitState={activeUnit} getStatColor={getStatColor} />

      <UnitMoveList
        unitState={activeUnit}
        moveMap={moveMap}
        typeColors={typeColors}
        moveTargeting={moveTargeting}
        selectEnabled={true}
        onMoveHoverStart={onMoveHoverStart}
        onMoveHoverEnd={onMoveHoverEnd}
        onMoveSelect={onMoveSelect}
      />

      {moveTargeting && selectedMove && (
        <>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onExecuteMove();
            }}
            className="mt-3 w-full bg-green-600 hover:bg-green-700 text-white font-bold py-2 px-4 rounded"
          >
            Execute Move
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onCancelMove();
            }}
            className="mt-3 w-full bg-red-600 hover:bg-red-700 text-white font-bold py-2 px-4 rounded"
          >
            Cancel Move
          </button>
        </>
      )}

      <UnitCredits unit={unit} />
    </div>
  );
}
