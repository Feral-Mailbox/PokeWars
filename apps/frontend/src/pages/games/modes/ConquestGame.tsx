import { useCallback, useEffect } from "react";
import { useMapRenderer } from "@/hooks/useMapRenderer";
import { pointerToTileCoords } from "@/utils/mapPointer";

const TILE_SIZE = 16;
const TILE_SCALE = 2;

export default function ConquestGame({
  gameData,
  userId,
  onTileSelect,
  selectedTile,
  selectedUnit,
  occupiedTile,
  isReady,
}: {
  gameData: any;
  userId: number;
  onTileSelect: (tile: [number, number] | null) => void;
  selectedTile: [number, number] | null;
  selectedUnit: any | null;
  occupiedTile: [number, number] | null;
  isReady: boolean;
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
        if (spawnGrid[y][x] === playerNumber) {
          const isOccupied = occupiedTile?.[0] === x && occupiedTile?.[1] === y;
          ctx.fillStyle = isOccupied ? "rgba(255, 165, 0, 0.5)" : "rgba(255, 255, 0, 0.35)";
          ctx.fillRect(
            x * TILE_SIZE * TILE_SCALE,
            y * TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE
          );
        }
      }
    }
  }, [spawnGrid, playerNumber, isPreparationPhase, occupiedTile, isReady]);

  useMapRenderer("mapCanvas", gameData, drawOverlay);
  return null;
}
