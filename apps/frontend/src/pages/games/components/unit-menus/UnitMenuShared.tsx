import UnitPortrait from "@/components/units/UnitPortrait";

export function normalizeCredits(credits: any): string[] {
  if (!Array.isArray(credits)) return [];
  return credits
    .map((entry) => String(entry ?? "").trim())
    .filter((entry) => entry.length > 0);
}

export function UnitCredits({ unit }: { unit: any }) {
  const portraitCredits = normalizeCredits(unit?.portrait_credits);
  const spriteCredits = normalizeCredits(unit?.sprite_credits);

  if (portraitCredits.length === 0 && spriteCredits.length === 0) return null;

  return (
    <div className="mt-4 pt-3 border-t border-gray-600 text-xs text-gray-300 space-y-1">
      {portraitCredits.length > 0 && (
        <p>
          <span className="font-semibold text-gray-200">Portrait:</span> {portraitCredits.join(", ")}
        </p>
      )}
      {spriteCredits.length > 0 && (
        <p>
          <span className="font-semibold text-gray-200">Sprite:</span> {spriteCredits.join(", ")}
        </p>
      )}
    </div>
  );
}

export function UnitInfoHeader({
  unit,
  currentHp,
  maxHp,
  statusIconSrc,
  typeColors,
}: {
  unit: any;
  currentHp: number;
  maxHp: number;
  statusIconSrc: string | null;
  typeColors: Record<string, string>;
}) {
  return (
    <>
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <UnitPortrait assetFolder={unit.asset_folder} />
          <div className="font-semibold text-lg flex items-center gap-2">
            <span>{unit.name}</span>
            {statusIconSrc && (
              <img
                src={statusIconSrc}
                alt="Status"
                className="w-12 h-12 object-contain"
              />
            )}
          </div>
        </div>
        <div className="text-sm text-gray-300 font-medium">
          {currentHp ?? "?"}/{maxHp ?? "?"}
        </div>
      </div>

      {unit.types?.length > 0 && (
        <div className="text-sm mb-2">
          {unit.types.map((type: string, idx: number) => (
            <span key={idx} className="font-medium" style={{ color: typeColors[type] || "#fff" }}>
              {type}
              {idx < unit.types.length - 1 && <span className="text-white">/</span>}
            </span>
          ))}
        </div>
      )}
    </>
  );
}

export function UnitInfoStats({
  unitState,
  getStatColor,
}: {
  unitState: any;
  getStatColor: (unitState: any, statName: string) => string;
}) {
  return (
    <>
      <div className="text-sm mb-2 font-medium">Level: {unitState?.level}</div>

      <div className="grid grid-cols-2 gap-y-1 text-sm mb-2">
        <div>
          <span className="font-semibold">Attack:</span>{" "}
          <span style={{ color: getStatColor(unitState, "attack") }}>
            {unitState?.current_stats?.attack ?? "?"}
          </span>
        </div>
        <div>
          <span className="font-semibold">Sp. Def:</span>{" "}
          <span style={{ color: getStatColor(unitState, "sp_defense") }}>
            {unitState?.current_stats?.sp_defense ?? "?"}
          </span>
        </div>
        <div>
          <span className="font-semibold">Defense:</span>{" "}
          <span style={{ color: getStatColor(unitState, "defense") }}>
            {unitState?.current_stats?.defense ?? "?"}
          </span>
        </div>
        <div>
          <span className="font-semibold">Speed:</span>{" "}
          <span style={{ color: getStatColor(unitState, "speed") }}>
            {unitState?.current_stats?.speed ?? "?"}
          </span>
        </div>
        <div>
          <span className="font-semibold">Sp. Atk:</span>{" "}
          <span style={{ color: getStatColor(unitState, "sp_attack") }}>
            {unitState?.current_stats?.sp_attack ?? "?"}
          </span>
        </div>
        <div>
          <span className="font-semibold">Range:</span>{" "}
          <span style={{ color: getStatColor(unitState, "range") }}>
            {unitState?.current_stats?.range ?? "?"}
          </span>
        </div>
      </div>
    </>
  );
}

export function UnitMoveList({
  unitState,
  moveMap,
  typeColors,
  moveTargeting,
  selectEnabled,
  onMoveHoverStart,
  onMoveHoverEnd,
  onMoveSelect,
}: {
  unitState: any;
  moveMap: Record<number, any>;
  typeColors: Record<string, string>;
  moveTargeting: boolean;
  selectEnabled: boolean;
  onMoveHoverStart: (move?: any) => void;
  onMoveHoverEnd: () => void;
  onMoveSelect?: (move: any) => void;
}) {
  const unit = unitState?.unit;
  if (!unit?.move_ids?.length) return null;

  const isLocked = unitState?.can_move === false;

  return (
    <div className="mt-3">
      <h3 className="text-md font-semibold mb-1">Moves:</h3>
      <ul className="space-y-2 text-sm">
        {unit.move_ids.map((id: number, moveIndex: number) => {
          const move = moveMap[id];
          if (!move) return null;

          const movePP = unitState?.move_pp?.[moveIndex] ?? move.pp ?? 0;
          const maxPP = move.pp ?? 0;
          const ppPercentage = maxPP > 0 ? (movePP / maxPP) * 100 : 0;

          let ppColor = "#ffffff";
          if (ppPercentage <= 10) {
            ppColor = "#ef4444";
          } else if (ppPercentage <= 50) {
            ppColor = "#eab308";
          }

          const disabled = (selectEnabled && moveTargeting) || (selectEnabled && isLocked);

          return (
            <li key={id}>
              <button
                type="button"
                onMouseEnter={() => !isLocked && onMoveHoverStart(move)}
                onMouseLeave={onMoveHoverEnd}
                onClick={() => {
                  if (!selectEnabled || !onMoveSelect || isLocked) return;
                  onMoveSelect(move);
                }}
                disabled={disabled}
                className={`w-full text-left border border-gray-600 p-2 rounded hover:bg-gray-700 focus:outline-none ${disabled ? "opacity-50 cursor-not-allowed" : ""}`}
              >
                <div className="flex justify-between font-bold">
                  <span>{move.name}</span>
                  <span
                    className="text-xs font-medium px-2 py-0.5 rounded"
                    style={{ backgroundColor: typeColors[move.type] ?? "#444" }}
                  >
                    {move.type}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span>Power: {move.power ?? "-"}</span>
                  <span style={{ color: ppColor }}>PP: {movePP}/{maxPP}</span>
                </div>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
