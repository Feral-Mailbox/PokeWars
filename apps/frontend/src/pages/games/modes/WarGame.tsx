import { useEffect } from "react";
import { useMapRenderer } from "@/hooks/useMapRenderer";
import { pointerToTileCoords } from "@/utils/mapPointer";

export type { ObjectiveTileState } from "@/hooks/useMapObjectiveRenderer";

type ObjectiveTileState = {
  kind: "pokeball" | "master_ball";
  owner: number;
  hp: number;
  max_hp: number;
  last_summon_round?: number | null;
  original_owner?: number;
};

export function getWarPlayerNumber(gameData: any, userId: number): number {
  const playerOrder: number[] = Array.isArray(gameData?.player_order) ? gameData.player_order : [];
  const playerIndex = playerOrder.indexOf(userId);
  return playerIndex >= 0 ? playerIndex + 1 : 0;
}

export function getCurrentRound(gameData: any): number {
  const players = gameData?.player_order?.length ?? 0;
  const turn = gameData?.current_turn ?? 0;
  if (!players) return 1;
  return Math.floor(turn / players) + 1;
}

export function canSummonOnObjective(
  cell: ObjectiveTileState,
  playerNumber: number,
  currentRound: number
) {
  if (cell.owner !== playerNumber) return false;
  const lastRound = cell.last_summon_round;
  return lastRound == null || lastRound < currentRound;
}

export function isWarObjectiveTileOccupied(
  placedUnits: Array<{ tile: [number, number]; current_hp?: number }>,
  x: number,
  y: number
) {
  return placedUnits.some(
    (unit) =>
      unit.tile[0] === x &&
      unit.tile[1] === y &&
      (unit.current_hp == null || unit.current_hp > 0)
  );
}

export function canSelectWarObjectiveTile(
  gameData: any,
  userId: number,
  x: number,
  y: number,
  placedUnits: Array<{ tile: [number, number]; current_hp?: number }> = []
): boolean {
  const status = gameData?.status;
  if (status !== "preparation" && status !== "in_progress") return false;

  const playerNumber = getWarPlayerNumber(gameData, userId);
  if (playerNumber <= 0) return false;

  const cell = gameData?.map_state?.objective_tiles?.[y]?.[x] as ObjectiveTileState | undefined;
  if (!cell || cell.owner !== playerNumber) return false;
  if (isWarObjectiveTileOccupied(placedUnits, x, y)) return false;

  if (status === "preparation") return true;

  return canSummonOnObjective(cell, playerNumber, getCurrentRound(gameData));
}

export default function WarGame({
  gameData,
  userId,
  onObjectiveSelect,
  isMyTurn,
  isReady = false,
  placedUnits = [],
}: {
  gameData: any;
  userId: number;
  onObjectiveSelect: (tile: [number, number] | null) => void;
  isMyTurn: boolean;
  isReady?: boolean;
  placedUnits?: Array<{ tile: [number, number]; current_hp?: number }>;
}) {
  const isPreparationPhase = gameData.status === "preparation";
  const isInProgress = gameData.status === "in_progress";
  const playerNumber = getWarPlayerNumber(gameData, userId);
  const objectiveGrid: (ObjectiveTileState | null)[][] =
    gameData.map_state?.objective_tiles ?? [];
  const cashPerTurn = gameData?.cash_per_turn ?? 0;

  const canSelectObjectives =
    (isPreparationPhase && !isReady) || (isInProgress && isMyTurn);

  useEffect(() => {
    if (!canSelectObjectives) return;
    const canvas = document.getElementById("mapCanvas") as HTMLCanvasElement;
    if (!canvas) return;

    const mapTilesW = gameData.map.width ?? 0;
    const mapTilesH = gameData.map.height ?? 0;

    const handleClick = (e: MouseEvent) => {
      const [x, y] = pointerToTileCoords(canvas, mapTilesW, mapTilesH, e.clientX, e.clientY);
      if (!canSelectWarObjectiveTile(gameData, userId, x, y, placedUnits)) {
        onObjectiveSelect(null);
        return;
      }

      onObjectiveSelect([x, y]);
    };

    canvas.addEventListener("click", handleClick);
    return () => canvas.removeEventListener("click", handleClick);
  }, [
    gameData,
    userId,
    canSelectObjectives,
    gameData.map.width,
    gameData.map.height,
    onObjectiveSelect,
    placedUnits,
  ]);

  useMapRenderer("mapCanvas", gameData);

  const ownedObjectives =
    objectiveGrid.flat().filter((cell) => cell && cell.owner === playerNumber).length ?? 0;
  const roundIncome = cashPerTurn * ownedObjectives;

  return (
    <div className="mt-2 text-white text-sm space-y-1">
      <p className="italic text-blue-300">
        War Mode: Capture objectives, summon units, and eliminate opponents.
      </p>
      {isPreparationPhase && !isReady && (
        <p className="text-yellow-300 text-xs">
          Click one of your objectives to place a unit from your starting cash.
        </p>
      )}
      {isInProgress && (
        <p className="text-gray-300">
          Income next round: <span className="text-green-400">${roundIncome}</span>
          {ownedObjectives > 0 && (
            <span className="text-gray-500">
              {" "}
              ({ownedObjectives} objective{ownedObjectives === 1 ? "" : "s"} × ${cashPerTurn})
            </span>
          )}
        </p>
      )}
      {isInProgress && isMyTurn && (
        <p className="text-yellow-300 text-xs">
          Click one of your objectives to summon a unit.
        </p>
      )}
    </div>
  );
}

export function patchObjectiveTile(
  gameData: any,
  x: number,
  y: number,
  patch: { hp: number; owner: number; kind?: string }
) {
  if (!gameData?.map_state?.objective_tiles?.[y]?.[x]) return gameData;

  const nextTiles = gameData.map_state.objective_tiles.map((row: any[], rowY: number) =>
    Array.isArray(row)
      ? row.map((cell, colX) =>
          rowY === y && colX === x && cell
            ? {
                ...cell,
                hp: patch.hp,
                owner: patch.owner,
                ...(patch.kind ? { kind: patch.kind } : {}),
              }
            : cell
        )
      : row
  );

  return {
    ...gameData,
    map_state: {
      ...gameData.map_state,
      objective_tiles: nextTiles,
    },
  };
}

export function getWarCaptureTarget(
  activeUnit: any,
  gameData: any,
  userId: number
): { x: number; y: number; hp: number; max_hp: number } | null {
  if (!activeUnit || gameData?.gamemode !== "War" || gameData?.status !== "in_progress") {
    return null;
  }
  if (activeUnit.user_id !== userId || activeUnit.can_move === false) return null;

  const playerOrder: number[] = Array.isArray(gameData.player_order) ? gameData.player_order : [];
  const playerNumber = playerOrder.indexOf(userId) + 1;
  if (playerNumber <= 0) return null;

  const [x, y] = activeUnit.tile ?? [activeUnit.current_x, activeUnit.current_y];
  const cell = gameData.map_state?.objective_tiles?.[y]?.[x];
  if (!cell || cell.owner === playerNumber) return null;

  return {
    x,
    y,
    hp: cell.hp ?? cell.max_hp ?? 20,
    max_hp: cell.max_hp ?? 20,
  };
}
