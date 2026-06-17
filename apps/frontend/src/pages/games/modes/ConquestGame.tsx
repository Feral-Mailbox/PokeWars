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

export default function ConquestGame({
  gameData,
  userId,
  onTileSelect,
  selectedTile,
  selectedUnit,
  occupiedTile,
  isReady,
  getPlayerColor,
}: {
  gameData: any;
  userId: number;
  onTileSelect: (tile: [number, number] | null) => void;
  selectedTile: [number, number] | null;
  selectedUnit: any | null;
  occupiedTile: [number, number] | null;
  isReady: boolean;
  getPlayerColor?: (playerId: number) => string;
}) {
  const isPreparationPhase = gameData.status === "preparation";
  const playerOrder: number[] = Array.isArray(gameData.player_order) ? gameData.player_order : [];
  const playerIndex = playerOrder.indexOf(userId);
  const playerNumber = playerIndex >= 0 ? playerIndex + 1 : 0;
  const spawnGrid = gameData.map.tile_data?.spawn_points;

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
  }, [spawnGrid, playerNumber, isPreparationPhase, isReady, gameData.map.width, gameData.map.height]);


  const drawOverlay = useCallback((ctx: CanvasRenderingContext2D) => {
    if (!isPreparationPhase || isReady || !spawnGrid) return;

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
  }, [spawnGrid, playerNumber, playerOrder, isPreparationPhase, occupiedTile, isReady, getPlayerColor]);

  useMapRenderer("mapCanvas", gameData, drawOverlay);
  return null;
}
