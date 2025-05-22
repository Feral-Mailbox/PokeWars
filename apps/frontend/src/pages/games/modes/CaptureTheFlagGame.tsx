import { useCallback } from "react";
import { useMapRenderer } from "@/hooks/useMapRenderer";

export default function CaptureTheFlagGame({ gameData, userId }: { gameData: any, userId: number }) {
  const drawOverlay = useCallback((ctx: CanvasRenderingContext2D) => {
    const TILE_SIZE = 16;
    const TILE_SCALE = 2;
    const flagData = gameData.map.tile_data?.flag_data;

    if (!flagData) return;

    for (let y = 0; y < flagData.length; y++) {
      for (let x = 0; x < flagData[y].length; x++) {
        if (flagData[y][x] !== 0) {
          ctx.fillStyle = "rgba(0, 200, 255, 0.4)";
          ctx.fillRect(
            x * TILE_SIZE * TILE_SCALE,
            y * TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE,
            TILE_SIZE * TILE_SCALE
          );
        }
      }
    }
  }, [gameData]);

  useMapRenderer("mapCanvas", gameData, drawOverlay);

  return (
    <div className="mt-4 text-white">
      <p className="italic text-sm text-cyan-300">Capture the Flag: Seize your opponent’s banner and return safely!</p>
    </div>
  );
}
