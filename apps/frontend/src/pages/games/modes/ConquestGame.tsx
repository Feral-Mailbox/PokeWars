import { useCallback, useEffect } from "react";
import { useMapRenderer } from "@/hooks/useMapRenderer";

const TILE_SIZE = 16;
const TILE_SCALE = 2;

export default function ConquestGame({
  gameData,
  userId,
  onTileSelect,
}: {
  gameData: any;
  userId: number;
  onTileSelect: (tile: [number, number] | null) => void;
}) {
  const isPreparationPhase = gameData.status === "preparation";
  const playerIndex = gameData.players.findIndex((p: any) => p.id === userId);
  const playerNumber = playerIndex + 1;
  const spawnGrid = gameData.map.tile_data?.spawn_points;

  useEffect(() => {
    if (!isPreparationPhase) return;
    const canvas = document.getElementById("mapCanvas") as HTMLCanvasElement;
    if (!canvas || !spawnGrid) return;

    const handleClick = (e: MouseEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = Math.floor((e.clientX - rect.left) / (TILE_SIZE * TILE_SCALE));
      const y = Math.floor((e.clientY - rect.top) / (TILE_SIZE * TILE_SCALE));
      if (spawnGrid[y]?.[x] === playerNumber) {
        onTileSelect([x, y]);
      } else {
        onTileSelect(null);
      }
    };

    canvas.addEventListener("click", handleClick);
    return () => canvas.removeEventListener("click", handleClick);
  }, [spawnGrid, playerNumber, isPreparationPhase]);

  const drawOverlay = useCallback((ctx: CanvasRenderingContext2D) => {
    if (!isPreparationPhase || !spawnGrid) return;
    ctx.fillStyle = "rgba(255, 255, 0, 0.35)";
    for (let y = 0; y < spawnGrid.length; y++) {
      for (let x = 0; x < spawnGrid[y].length; x++) {
        if (spawnGrid[y][x] === playerNumber) {
          ctx.fillRect(
            x * TILE_SIZE * TILE_SCALE,
            y * TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE
          );
        }
      }
    }
  }, [spawnGrid, playerNumber, isPreparationPhase]);

  useMapRenderer("mapCanvas", gameData, drawOverlay);
  return null;
}
