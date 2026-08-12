import { useCallback, useEffect, useRef, useState } from "react";
import { useMapRenderer } from "@/hooks/useMapRenderer";
import { pointerToTileCoords } from "@/utils/mapPointer";
import { parseCtfJailTile } from "@/types/mapData";
import { getCtfFlagUrl, getCtfJailUrl } from "@/utils/gameAssets";
import { drawCtfMapIcon } from "@/utils/ctfIcons";
import { drawTileHealthBar } from "@/utils/mapHealthBar";
import { resolvePlayerSlotOverlayColor } from "@/utils/playerOverlayColor";

export const CTF_FLAG_MAX_HP = 10;
export const CTF_JAIL_MAX_HP = 20;

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

export function getCtfPlayerNumber(gameData: any, userId: number): number {
  const playerOrder: number[] = Array.isArray(gameData?.player_order) ? gameData.player_order : [];
  const playerIndex = playerOrder.indexOf(userId);
  return playerIndex >= 0 ? playerIndex + 1 : 0;
}

export function patchFlagTile(
  gameData: any,
  x: number,
  y: number,
  patch: { owner: number; hp?: number; max_hp?: number }
) {
  if (!gameData?.map_state?.flag_tiles?.[y]?.[x]) return gameData;

  const nextTiles = gameData.map_state.flag_tiles.map((row: any[], rowY: number) =>
    Array.isArray(row)
      ? row.map((cell, colX) =>
          rowY === y && colX === x && cell ? { ...cell, ...patch } : cell
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
  const prevGrid = Array.isArray(gameData?.map_state?.unlock_tiles)
    ? gameData.map_state.unlock_tiles
    : [];
  const height = Math.max(prevGrid.length, y + 1);
  const width = Math.max(
    ...prevGrid.map((row: any) => (Array.isArray(row) ? row.length : 0)),
    x + 1
  );
  const nextTiles = Array.from({ length: height }, (_, rowY) => {
    const src = Array.isArray(prevGrid[rowY]) ? prevGrid[rowY] : [];
    const row = Array.from({ length: width }, (_, colX) => src[colX] ?? null);
    if (rowY === y) {
      row[x] = { ...(row[x] || {}), ...patch };
    }
    return row;
  });

  return {
    ...gameData,
    map_state: {
      ...gameData.map_state,
      unlock_tiles: nextTiles,
    },
  };
}

export type CtfJailInfo = { x: number; y: number; owner: number };

export function listCtfJails(gameData: any): CtfJailInfo[] {
  const specialTiles = gameData?.map?.tile_data?.special_tiles;
  if (!Array.isArray(specialTiles)) return [];
  const jails: CtfJailInfo[] = [];
  for (let y = 0; y < specialTiles.length; y++) {
    const row = specialTiles[y];
    if (!Array.isArray(row)) continue;
    for (let x = 0; x < row.length; x++) {
      const parsed = parseCtfJailTile(row[x]);
      if (parsed) jails.push({ x, y, owner: parsed.owner });
    }
  }
  return jails;
}

export function getCtfJailAt(gameData: any, x: number, y: number): CtfJailInfo | null {
  const parsed = parseCtfJailTile(gameData?.map?.tile_data?.special_tiles?.[y]?.[x]);
  return parsed ? { x, y, owner: parsed.owner } : null;
}

function readCtfObjectiveHp(
  cell: { hp?: number; max_hp?: number } | null | undefined,
  fallbackMax: number
): { hp: number; max_hp: number } {
  const max_hp = Number(cell?.max_hp ?? fallbackMax) || fallbackMax;
  const hp = Number(cell?.hp ?? max_hp);
  return { hp, max_hp };
}

export type CtfActionTarget =
  | { kind: "flag"; x: number; y: number; hp: number; max_hp: number }
  | { kind: "unlock"; x: number; y: number; owner: number; hp: number; max_hp: number };

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
  if (activeUnit.jailed || activeUnit.flags?.jailed) return null;

  const playerNumber = getCtfPlayerNumber(gameData, userId);
  if (playerNumber <= 0) return null;

  const [x, y] = activeUnit.tile ?? [activeUnit.current_x, activeUnit.current_y];
  const flagCell = gameData.map_state?.flag_tiles?.[y]?.[x];
  if (flagCell && Number(flagCell.owner ?? 0) !== playerNumber) {
    return { kind: "flag", x, y, ...readCtfObjectiveHp(flagCell, CTF_FLAG_MAX_HP) };
  }

  const jail = getCtfJailAt(gameData, x, y);
  if (jail) {
    const unlockCell = gameData.map_state?.unlock_tiles?.[y]?.[x];
    return {
      kind: "unlock",
      x,
      y,
      owner: jail.owner,
      ...readCtfObjectiveHp(unlockCell, CTF_JAIL_MAX_HP),
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
  const flagImageRef = useRef<HTMLImageElement | null>(null);
  const jailImageRef = useRef<HTMLImageElement | null>(null);
  const [ctfIconsReady, setCtfIconsReady] = useState(0);

  useEffect(() => {
    const bump = () => setCtfIconsReady((count) => count + 1);
    if (!flagImageRef.current) {
      const img = new Image();
      img.src = getCtfFlagUrl();
      img.onload = bump;
      img.onerror = bump;
      flagImageRef.current = img;
    }
    if (!jailImageRef.current) {
      const img = new Image();
      img.src = getCtfJailUrl();
      img.onload = bump;
      img.onerror = bump;
      jailImageRef.current = img;
    }
  }, []);

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
          const tileSize = TILE_SIZE * TILE_SCALE;
          drawCtfMapIcon(
            ctx,
            flagImageRef.current,
            x,
            y,
            resolvePlayerSlotOverlayColor(owner, playerOrder, getPlayerColor),
            tileSize
          );
          const { hp, max_hp } = readCtfObjectiveHp(cell, CTF_FLAG_MAX_HP);
          drawTileHealthBar(ctx, x, y, hp, max_hp, tileSize);
        }
      }

      for (let y = 0; y < specialTiles.length; y++) {
        const row = specialTiles[y];
        if (!Array.isArray(row)) continue;
        for (let x = 0; x < row.length; x++) {
          const jail = parseCtfJailTile(row[x]);
          if (!jail) continue;
          const tileSize = TILE_SIZE * TILE_SCALE;
          drawCtfMapIcon(
            ctx,
            jailImageRef.current,
            x,
            y,
            resolvePlayerSlotOverlayColor(jail.owner, playerOrder, getPlayerColor),
            tileSize
          );
          const { hp, max_hp } = readCtfObjectiveHp(unlockTiles[y]?.[x], CTF_JAIL_MAX_HP);
          drawTileHealthBar(ctx, x, y, hp, max_hp, tileSize);
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
      ctfIconsReady,
    ]
  );

  useMapRenderer("mapCanvas", gameData, drawOverlay);

  const ownedFlags = flagTiles.flat().filter((cell: any) => cell && Number(cell.owner) === playerNumber)
    .length;
  const totalFlags = flagTiles.flat().filter((cell: any) => cell).length;

  return (
    <div className="mt-2 text-white text-sm space-y-1">
      <p className="italic text-cyan-300">
        Capture The Flag: Claim every banner, stand on a jail to free its prisoners, and outlast the turn limit.
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
