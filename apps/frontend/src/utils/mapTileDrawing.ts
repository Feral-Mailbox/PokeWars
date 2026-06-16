import {
  MAP_TILE_DRAW_SIZE,
  MAP_TILE_SCALE,
  MAP_TILE_SIZE,
  setupPixelCanvas,
} from "@/utils/pixelCanvas";
import type { TileRef } from "@/types/mapData";

export type DrawableMapLayer = "base" | "overlay" | "overlay2" | "overlay3";

function resolveTilesetBase(): string {
  const assetBase = (import.meta as any).env?.VITE_ASSET_BASE ?? "/game-assets";
  const normalizedBase = assetBase.startsWith("http")
    ? assetBase
    : `${window.location.origin}${assetBase.startsWith("/") ? "" : "/"}${assetBase}`;
  return normalizedBase.replace(/\/$/, "");
}

export function isTileRefPresent(tile: TileRef | null | undefined): boolean {
  if (!tile || !Array.isArray(tile)) return false;
  const [tileIndex, tilesetIndex] = tile;
  return tileIndex != null && tileIndex >= 0 && tilesetIndex != null;
}

export function buildOverlay2TileSet(
  overlay2: (TileRef | null)[][] | undefined
): Set<string> {
  const tiles = new Set<string>();
  if (!overlay2) return tiles;

  for (let y = 0; y < overlay2.length; y++) {
    for (let x = 0; x < overlay2[y].length; x++) {
      if (isTileRefPresent(overlay2[y][x])) {
        tiles.add(`${x},${y}`);
      }
    }
  }

  return tiles;
}

type MapRenderInput = {
  width: number;
  height: number;
  tileset_names: string[];
  tile_data: {
    base: TileRef[][];
    overlay: (TileRef | null)[][];
    overlay2?: (TileRef | null)[][];
    overlay3?: (TileRef | null)[][];
  };
};

export function installMapTileRenderer(
  canvas: HTMLCanvasElement,
  map: MapRenderInput,
  layers: DrawableMapLayer[],
  overlayCallback?: (ctx: CanvasRenderingContext2D) => void
): () => void {
  const { base, overlay, overlay2, overlay3 } = map.tile_data;
  const logicalWidth = map.width * MAP_TILE_DRAW_SIZE;
  const logicalHeight = map.height * MAP_TILE_DRAW_SIZE;
  const dpr = setupPixelCanvas(canvas, logicalWidth, logicalHeight);

  const tilesetBase = resolveTilesetBase();
  const tilesetPaths = map.tileset_names.map((name) => `${tilesetBase}/tilesets/${name}`);

  const tilesets = tilesetPaths.map((src) => {
    const img = new Image();
    img.src = src;
    return img;
  });

  const loadedTilesets = new Set<number>();
  let cancelled = false;

  const drawTile = (
    ctx: CanvasRenderingContext2D,
    tile: TileRef | null | undefined,
    x: number,
    y: number
  ) => {
    if (!isTileRefPresent(tile)) return;
    const [tileIndex, tilesetIndex] = tile!;
    const tileset = tilesets[tilesetIndex];
    if (!tileset?.width) return;

    const tilesPerRow = Math.floor(tileset.width / MAP_TILE_SIZE);
    const sx = (tileIndex % tilesPerRow) * MAP_TILE_SIZE;
    const sy = Math.floor(tileIndex / tilesPerRow) * MAP_TILE_SIZE;

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
  };

  const drawAll = () => {
    if (cancelled) return;

    setupPixelCanvas(canvas, logicalWidth, logicalHeight);
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    ctx.setTransform(dpr * MAP_TILE_SCALE, 0, 0, dpr * MAP_TILE_SCALE, 0, 0);
    ctx.imageSmoothingEnabled = false;

    for (let y = 0; y < map.height; y++) {
      for (let x = 0; x < map.width; x++) {
        if (layers.includes("base")) drawTile(ctx, base[y][x], x, y);
        if (layers.includes("overlay")) drawTile(ctx, overlay[y][x], x, y);
        if (layers.includes("overlay2") && overlay2) drawTile(ctx, overlay2[y][x], x, y);
        if (layers.includes("overlay3") && overlay3) drawTile(ctx, overlay3[y][x], x, y);
      }
    }

    if (overlayCallback) {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      overlayCallback(ctx);
    }

    ctx.setTransform(1, 0, 0, 1, 0, 0);
  };

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

  return () => {
    cancelled = true;
  };
}
