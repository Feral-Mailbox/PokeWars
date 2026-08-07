import { useCallback, useEffect } from "react";
import { useMapRenderer } from "@/hooks/useMapRenderer";
import { pointerToTileCoords } from "@/utils/mapPointer";

const TILE_SIZE = 16;
const TILE_SCALE = 2;

const DEFAULT_SPAWN_COLORS = [
  "#0000FF80",
  "#FF000080",
  "#FFFF0080",
  "#00FF0080",
  "#88888880",
  "#80008080",
  "#FF00FF80",
  "#00FFFF80",
];

const FLAG_OWNER_COLORS = [
  "rgba(180, 180, 180, 0.55)", // neutral
  "rgba(239, 68, 68, 0.55)",
  "rgba(59, 130, 246, 0.55)",
  "rgba(34, 197, 94, 0.55)",
  "rgba(234, 179, 8, 0.55)",
  "rgba(168, 85, 247, 0.55)",
  "rgba(249, 115, 22, 0.55)",
  "rgba(6, 182, 212, 0.55)",
  "rgba(244, 63, 94, 0.55)",
];

export function getCtfPlayerNumber(gameData: any, userId: number): number {
  const playerOrder: number[] = Array.isArray(gameData?.player_order) ? gameData.player_order : [];
  const playerIndex = playerOrder.indexOf(userId);
  return playerIndex >= 0 ? playerIndex + 1 : 0;
}

export function patchFlagTile(gameData: any, x: number, y: number, patch: { owner: number }) {
  if (!gameData?.map_state?.flag_tiles?.[y]?.[x]) return gameData;

  const nextTiles = gameData.map_state.flag_tiles.map((row: any[], rowY: number) =>
    Array.isArray(row)
      ? row.map((cell, colX) =>
          rowY === y && colX === x && cell ? { ...cell, owner: patch.owner } : cell
        )
      : row
  );

  return {
    ...gameData,
    map_state: {
      ...gameData.map_state,
      flag_tiles: nextTiles,
    },
  };
}

export function patchUnlockTile(
  gameData: any,
  x: number,
  y: number,
  patch: { hp: number; max_hp: number }
) {
  if (!gameData?.map_state?.unlock_tiles?.[y]?.[x]) return gameData;

  const nextTiles = gameData.map_state.unlock_tiles.map((row: any[], rowY: number) =>
    Array.isArray(row)
      ? row.map((cell, colX) =>
          rowY === y && colX === x && cell
            ? { ...cell, hp: patch.hp, max_hp: patch.max_hp }
            : cell
        )
      : row
  );

  return {
    ...gameData,
    map_state: {
      ...gameData.map_state,
      unlock_tiles: nextTiles,
    },
  };
}

export type CtfActionTarget =
  | { kind: "flag"; x: number; y: number }
  | { kind: "unlock"; x: number; y: number; hp: number; max_hp: number };

export function getCtfActionTarget(
  activeUnit: any,
  gameData: any,
  userId: number
): CtfActionTarget | null {
  if (
    !activeUnit ||
    gameData?.gamemode !== "Capture The Flag" ||
    gameData?.status !== "in_progress"
  ) {
    return null;
  }
  if (activeUnit.user_id !== userId || activeUnit.can_move === false) return null;
  if (activeUnit.flags?.jailed) return null;

  const playerNumber = getCtfPlayerNumber(gameData, userId);
  if (playerNumber <= 0) return null;

  const [x, y] = activeUnit.tile ?? [activeUnit.current_x, activeUnit.current_y];
  const flagCell = gameData.map_state?.flag_tiles?.[y]?.[x];
  if (flagCell && Number(flagCell.owner ?? 0) !== playerNumber) {
    return { kind: "flag", x, y };
  }

  const unlockCell = gameData.map_state?.unlock_tiles?.[y]?.[x];
  if (unlockCell) {
    return {
      kind: "unlock",
      x,
      y,
      hp: Number(unlockCell.hp ?? unlockCell.max_hp ?? 20),
      max_hp: Number(unlockCell.max_hp ?? 20),
    };
  }

  return null;
}

export default function CaptureTheFlagGame({
  gameData,
  userId,
  onTileSelect,
  occupiedTile,
  isReady,
  getPlayerColor,
}: {
  gameData: any;
  userId: number;
  onTileSelect: (tile: [number, number] | null) => void;
  occupiedTile?: [number, number] | null;
  isReady: boolean;
  getPlayerColor?: (playerId: number) => string;
}) {
  const isPreparationPhase = gameData.status === "preparation";
  const isInProgress = gameData.status === "in_progress";
  const playerOrder: number[] = Array.isArray(gameData.player_order) ? gameData.player_order : [];
  const playerNumber = getCtfPlayerNumber(gameData, userId);
  const spawnGrid = gameData.map?.tile_data?.spawn_points;
  const flagTiles = gameData.map_state?.flag_tiles ?? [];
  const unlockTiles = gameData.map_state?.unlock_tiles ?? [];
  const specialTiles = gameData.map?.tile_data?.special_tiles ?? [];

  useEffect(() => {
    if (!isPreparationPhase || isReady) return;
    const canvas = document.getElementById("mapCanvas") as HTMLCanvasElement;
    if (!canvas || !spawnGrid) return;

    const mapTilesW = gameData.map.width ?? 0;
    const mapTilesH = gameData.map.height ?? 0;

    const handleClick = (e: MouseEvent) => {
      const [x, y] = pointerToTileCoords(canvas, mapTilesW, mapTilesH, e.clientX, e.clientY);
      if (spawnGrid[y]?.[x] === playerNumber) {
        onTileSelect([x, y]);
      } else {
        onTileSelect(null);
      }
    };

    canvas.addEventListener("click", handleClick);
    return () => canvas.removeEventListener("click", handleClick);
  }, [
    spawnGrid,
    playerNumber,
    isPreparationPhase,
    isReady,
    gameData.map?.width,
    gameData.map?.height,
    onTileSelect,
  ]);

  const drawOverlay = useCallback(
    (ctx: CanvasRenderingContext2D) => {
      if (isPreparationPhase && !isReady && spawnGrid) {
        for (let y = 0; y < spawnGrid.length; y++) {
          for (let x = 0; x < spawnGrid[y].length; x++) {
            const spawnPlayer = spawnGrid[y][x];
            if (spawnPlayer == null) continue;

            const isOwnTile = spawnPlayer === playerNumber;
            const isOccupied = isOwnTile && occupiedTile?.[0] === x && occupiedTile?.[1] === y;

            let fillStyle: string;
            if (isOccupied) {
              fillStyle = "rgba(255, 165, 0, 0.5)";
            } else {
              const ownerId = playerOrder[spawnPlayer - 1];
              const playerColor =
                ownerId != null && getPlayerColor ? getPlayerColor(ownerId) : null;
              fillStyle =
                playerColor && playerColor !== "#00000000"
                  ? playerColor
                  : DEFAULT_SPAWN_COLORS[(spawnPlayer - 1) % DEFAULT_SPAWN_COLORS.length];
            }

            ctx.fillStyle = fillStyle;
            ctx.fillRect(
              x * TILE_SIZE * TILE_SCALE,
              y * TILE_SIZE * TILE_SCALE,
              TILE_SIZE * TILE_SCALE,
              TILE_SIZE * TILE_SCALE
            );
          }
        }
      }

      for (let y = 0; y < flagTiles.length; y++) {
        const row = flagTiles[y];
        if (!Array.isArray(row)) continue;
        for (let x = 0; x < row.length; x++) {
          const cell = row[x];
          if (!cell) continue;
          const owner = Number(cell.owner ?? 0);
          ctx.fillStyle = FLAG_OWNER_COLORS[Math.min(owner, FLAG_OWNER_COLORS.length - 1)];
          ctx.fillRect(
            x * TILE_SIZE * TILE_SCALE,
            y * TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE
          );
          ctx.fillStyle = "#ffffff";
          ctx.font = "bold 12px sans-serif";
          ctx.fillText(
            owner > 0 ? `F${owner}` : "F",
            x * TILE_SIZE * TILE_SCALE + 4,
            y * TILE_SIZE * TILE_SCALE + 14
          );
        }
      }

      for (let y = 0; y < specialTiles.length; y++) {
        const row = specialTiles[y];
        if (!Array.isArray(row)) continue;
        for (let x = 0; x < row.length; x++) {
          const special = row[x];
          if (typeof special !== "string") continue;
          const key = special.trim().toLowerCase();
          if (key === "ctf_jail") {
            ctx.fillStyle = "rgba(88, 28, 135, 0.45)";
            ctx.fillRect(
              x * TILE_SIZE * TILE_SCALE,
              y * TILE_SIZE * TILE_SCALE,
              TILE_SIZE * TILE_SCALE,
              TILE_SIZE * TILE_SCALE
            );
            ctx.fillStyle = "#e9d5ff";
            ctx.font = "bold 10px sans-serif";
            ctx.fillText("J", x * TILE_SIZE * TILE_SCALE + 8, y * TILE_SIZE * TILE_SCALE + 14);
          }
        }
      }

      for (let y = 0; y < unlockTiles.length; y++) {
        const row = unlockTiles[y];
        if (!Array.isArray(row)) continue;
        for (let x = 0; x < row.length; x++) {
          const cell = row[x];
          if (!cell) continue;
          ctx.fillStyle = "rgba(251, 146, 60, 0.5)";
          ctx.fillRect(
            x * TILE_SIZE * TILE_SCALE,
            y * TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE
          );
          const hp = Number(cell.hp ?? 0);
          const maxHp = Number(cell.max_hp ?? 20);
          ctx.fillStyle = "#fff7ed";
          ctx.font = "bold 9px sans-serif";
          ctx.fillText(
            `U${hp}/${maxHp}`,
            x * TILE_SIZE * TILE_SCALE + 2,
            y * TILE_SIZE * TILE_SCALE + 14
          );
        }
      }
    },
    [
      isPreparationPhase,
      isReady,
      spawnGrid,
      playerNumber,
      occupiedTile,
      playerOrder,
      getPlayerColor,
      flagTiles,
      unlockTiles,
      specialTiles,
    ]
  );

  useMapRenderer("mapCanvas", gameData, drawOverlay);

  const ownedFlags = flagTiles.flat().filter((cell: any) => cell && Number(cell.owner) === playerNumber)
    .length;
  const totalFlags = flagTiles.flat().filter((cell: any) => cell).length;

  return (
    <div className="mt-2 text-white text-sm space-y-1">
      <p className="italic text-cyan-300">
        Capture The Flag: Claim every banner, free allies from jail, and outlast the turn limit.
      </p>
      {isPreparationPhase && !isReady && (
        <p className="text-yellow-300 text-xs">
          Click one of your spawn tiles to place a unit from your starting cash.
        </p>
      )}
      {isInProgress && (
        <p className="text-gray-300">
          Flags controlled:{" "}
          <span className="text-cyan-300">
            {ownedFlags}/{totalFlags}
          </span>
        </p>
      )}
    </div>
  );
}
