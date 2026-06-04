import { useEffect } from "react";
import {
  MAP_TILE_DRAW_SIZE,
  MAP_TILE_SCALE,
  MAP_TILE_SIZE,
  setupPixelCanvas,
} from "@/utils/pixelCanvas";

export function useMapRenderer(
  canvasId: string,
  gameData: any,
  overlayCallback?: (ctx: CanvasRenderingContext2D) => void
) {
  useEffect(() => {
    const canvas = document.getElementById(canvasId) as HTMLCanvasElement;
    const ctx = canvas?.getContext("2d");
    if (!ctx || !gameData?.map?.tile_data || !gameData.map.tileset_names) return;

    const { base, overlay } = gameData.map.tile_data;
    const logicalWidth = gameData.map.width * MAP_TILE_DRAW_SIZE;
    const logicalHeight = gameData.map.height * MAP_TILE_DRAW_SIZE;
    const dpr = setupPixelCanvas(canvas, logicalWidth, logicalHeight);

    const assetBase = (import.meta as any).env?.VITE_ASSET_BASE ?? "/game-assets";
    const normalizedBase = assetBase.startsWith("http")
      ? assetBase
      : `${window.location.origin}${assetBase.startsWith("/") ? "" : "/"}${assetBase}`;
    const tilesetBase = normalizedBase.replace(/\/$/, "");
    const tilesetPaths = gameData.map.tileset_names.map(
      (name: string) => `${tilesetBase}/tilesets/${name}`
    );

    const tilesets = tilesetPaths.map((src) => {
      const img = new Image();
      img.src = src;
      return img;
    });

    const loadedTilesets = new Set<number>();
    const onTilesetReady = (index: number) => {
      if (loadedTilesets.has(index)) return;
      loadedTilesets.add(index);
      if (loadedTilesets.size === tilesets.length) drawAll();
    };
    tilesets.forEach((img, index) => {
      img.onload = () => onTilesetReady(index);
      img.onerror = () => {
        console.error(`[MapRenderer] Failed to load tileset: ${tilesetPaths[index]}`);
      };
      if (img.complete) onTilesetReady(index);
    });

    function drawTile(tile: any, x: number, y: number) {
      if (!tile || !Array.isArray(tile)) return;
      const [tileIndex, tilesetIndex] = tile;
      if (tileIndex == null || tileIndex < 0 || tilesetIndex == null) return;

      const tileset = tilesets[tilesetIndex];
      if (!tileset?.width) {
        console.warn(
          `[MapRenderer] Missing tileset ${tilesetIndex} at (${x}, ${y}); ` +
            `map defines ${gameData.map.tileset_names?.length ?? 0} tileset(s)`
        );
        return;
      }

      const tilesPerRow = Math.floor(tileset.width / MAP_TILE_SIZE);
      const sx = (tileIndex % tilesPerRow) * MAP_TILE_SIZE;
      const sy = Math.floor(tileIndex / tilesPerRow) * MAP_TILE_SIZE;

      // Draw 1:1 in tile-space; MAP_TILE_SCALE on the context handles 2× upscaling
      // without per-tile drawImage scaling (avoids atlas bleeding).
      ctx.drawImage(
        tileset,
        sx,
        sy,
        MAP_TILE_SIZE,
        MAP_TILE_SIZE,
        x * MAP_TILE_SIZE,
        y * MAP_TILE_SIZE,
        MAP_TILE_SIZE,
        MAP_TILE_SIZE
      );
    }

    function drawAll() {
      setupPixelCanvas(canvas, logicalWidth, logicalHeight);

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      ctx.setTransform(dpr * MAP_TILE_SCALE, 0, 0, dpr * MAP_TILE_SCALE, 0, 0);
      ctx.imageSmoothingEnabled = false;

      for (let y = 0; y < gameData.map.height; y++) {
        for (let x = 0; x < gameData.map.width; x++) {
          drawTile(base[y][x], x, y);
          drawTile(overlay[y][x], x, y);
        }
      }

      // Overlays use MAP_TILE_DRAW_SIZE (CSS pixel) coordinates.
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      overlayCallback?.(ctx);
      ctx.setTransform(1, 0, 0, 1, 0, 0);
    }
  }, [gameData, canvasId, overlayCallback]);
}
