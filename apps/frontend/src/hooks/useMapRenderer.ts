import { useEffect } from "react";

export function useMapRenderer(canvasId: string, gameData: any, overlayCallback?: (ctx: CanvasRenderingContext2D) => void) {
  useEffect(() => {
    const canvas = document.getElementById(canvasId) as HTMLCanvasElement;
    const ctx = canvas?.getContext("2d");
    if (!ctx || !gameData?.map?.tile_data || !gameData.map.tileset_names) return;

    const TILE_SIZE = 16;
    const TILE_SCALE = 2;
    const { base, overlay } = gameData.map.tile_data;

    const tilesetPaths = gameData.map.tileset_names.map(name =>
      `${window.location.origin.replace(":5173", "")}/assets/tilesets/${name}`
    );

    const tilesets = tilesetPaths.map(src => {
      const img = new Image();
      img.src = src;
      return img;
    });

    let loadedCount = 0;
    tilesets.forEach(img => {
      img.onload = () => {
        loadedCount++;
        if (loadedCount === tilesets.length) drawAll();
      };
    });

    function drawTile(tile: any, x: number, y: number) {
      if (!tile || !Array.isArray(tile)) return;
      const [tileIndex, tilesetIndex] = tile;
      if (tileIndex == null || tileIndex < 0 || tilesetIndex == null) return;

      const tileset = tilesets[tilesetIndex];
      const tilesPerRow = Math.floor(tileset.width / TILE_SIZE);
      const sx = (tileIndex % tilesPerRow) * TILE_SIZE;
      const sy = Math.floor(tileIndex / tilesPerRow) * TILE_SIZE;
      ctx.drawImage(
        tileset,
        sx, sy,
        TILE_SIZE, TILE_SIZE,
        x * TILE_SIZE * TILE_SCALE, y * TILE_SIZE * TILE_SCALE,
        TILE_SIZE * TILE_SCALE, TILE_SIZE * TILE_SCALE
      );
    }

    function drawAll() {
      for (let y = 0; y < gameData.map.height; y++) {
        for (let x = 0; x < gameData.map.width; x++) {
          drawTile(base[y][x], x, y);
          drawTile(overlay[y][x], x, y);
        }
      }

      overlayCallback?.(ctx);
    }
  }, [gameData, canvasId, overlayCallback]);
}
