import {
  UNIT_MENU_WIDTH_CLASS,
  UnitCredits,
  UnitInfoHeader,
  UnitInfoStats,
  UnitMoveList,
} from "./UnitMenuShared";

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
  onWait: () => void;
  showWaitButton?: boolean;
  onCapture?: () => void;
  showCaptureButton?: boolean;
  captureHpLabel?: string | null;
  onPickUpItem?: () => void;
  showPickUpButton?: boolean;
  pickUpItemLabel?: string | null;
  pickUpButtonText?: string;
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
  onWait,
  showWaitButton = false,
  onCapture,
  showCaptureButton = false,
  captureHpLabel = null,
  onPickUpItem,
  showPickUpButton = false,
  pickUpItemLabel = null,
  pickUpButtonText = "Pick Up",
  getPlayerColor,
}: InProgressUnitMenuProps) {
  const unit = activeUnit.unit;
  const currentHp = Number(activeUnit?.current_hp ?? 0);
  const maxHp = Number(activeUnit?.current_stats?.hp ?? 0);
  const isDizzyPortrait = maxHp > 0 && currentHp <= maxHp / 5;
  const isPainPortrait = !isDizzyPortrait && maxHp > 0 && currentHp <= maxHp / 2;

  const portraitFrameX = isDizzyPortrait ? 120 : isPainPortrait ? 80 : 0;
  const portraitFrameY = isDizzyPortrait ? 80 : 0;

  return (
    <div
      data-unit-info
      className={`${UNIT_MENU_WIDTH_CLASS} bg-gray-800 text-white p-4 rounded-lg shadow-lg max-h-[calc(100vh-8rem)] overflow-y-auto`}
      style={{ border: `2px solid ${getPlayerColor(activeUnit.user_id)}` }}
    >
      <UnitInfoHeader
        unit={unit}
        currentHp={currentHp}
        maxHp={maxHp}
        statusIconSrc={statusIconSrc}
        states={activeUnit?.states}
        typeColors={typeColors}
        ability={activeUnit?.ability}
        item={activeUnit?.held_item}
        portraitFrameX={portraitFrameX}
        portraitFrameY={portraitFrameY}
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

      {showPickUpButton && onPickUpItem && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onPickUpItem();
          }}
          className="mt-3 w-full bg-amber-600 hover:bg-amber-700 text-white font-bold py-2 px-4 rounded"
        >
          {pickUpButtonText}
          {pickUpItemLabel ? `: ${pickUpItemLabel}` : ""}
        </button>
      )}

      {showCaptureButton && onCapture && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onCapture();
          }}
          className="mt-3 w-full bg-orange-600 hover:bg-orange-700 text-white font-bold py-2 px-4 rounded"
        >
          Capture Objective{captureHpLabel ? ` (${captureHpLabel})` : ""}
        </button>
      )}

      {showWaitButton && (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onWait();
          }}
          className="mt-3 w-full bg-gray-500 hover:bg-gray-600 text-white font-bold py-2 px-4 rounded"
        >
          Wait
        </button>
      )}

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
