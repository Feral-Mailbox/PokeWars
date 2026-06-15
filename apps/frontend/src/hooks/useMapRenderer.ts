import { useEffect } from "react";
import { installMapTileRenderer } from "@/utils/mapTileDrawing";

export function useMapRenderer(
  canvasId: string,
  gameData: any,
  overlayCallback?: (ctx: CanvasRenderingContext2D) => void
) {
  useEffect(() => {
    const canvas = document.getElementById(canvasId) as HTMLCanvasElement;
    if (!canvas || !gameData?.map?.tile_data || !gameData.map.tileset_names) return;

    return installMapTileRenderer(
      canvas,
      {
        width: gameData.map.width,
        height: gameData.map.height,
        tileset_names: gameData.map.tileset_names,
        tile_data: gameData.map.tile_data,
      },
      ["base", "overlay"],
      overlayCallback
    );
  }, [gameData, canvasId, overlayCallback]);
}
