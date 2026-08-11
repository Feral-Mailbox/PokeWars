import {
  MAP_TILE_DRAW_SIZE,
  MAP_TILE_SCALE,
  MAP_TILE_SIZE,
  setupPixelCanvas,
} from "@/utils/pixelCanvas";
import {
  isValidTileRef,
  normalizeBackgroundColor,
  type TileRef,
} from "@/types/mapData";

export type DrawableMapLayer = "base" | "overlay" | "overlay2" | "overlay3";

function resolveTilesetBase(): string {
  const assetBase = (import.meta as any).env?.VITE_ASSET_BASE ?? "/game-assets";
  const normalizedBase = assetBase.startsWith("http")
    ? assetBase
    : `${window.location.origin}${assetBase.startsWith("/") ? "" : "/"}${assetBase}`;
  return normalizedBase.replace(/\/$/, "");
}

export function isTileRefPresent(tile: TileRef | null | undefined): boolean {
  return isValidTileRef(tile);
}

export function getTileDrawSource(
  tile: TileRef | null | undefined,
  tilesets: HTMLImageElement[]
): { image: HTMLImageElement; sx: number; sy: number } | null {
  if (!isValidTileRef(tile)) return null;
  const tileIndex = Number(tile[0]);
  const tilesetIndex = Number(tile[1]);
  const image = tilesets[tilesetIndex];
  if (!image?.width) return null;

  const tilesPerRow = Math.floor(image.width / MAP_TILE_SIZE);
  if (tilesPerRow <= 0) return null;

  const imageHeight = image.naturalHeight || image.height || 0;
  if (imageHeight >= MAP_TILE_SIZE) {
    const tileCount = tilesPerRow * Math.floor(imageHeight / MAP_TILE_SIZE);
    if (tileIndex >= tileCount) return null;
  }

  return {
    image,
    sx: (tileIndex % tilesPerRow) * MAP_TILE_SIZE,
    sy: Math.floor(tileIndex / tilesPerRow) * MAP_TILE_SIZE,
  };
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
    base: (TileRef | null)[][];
    overlay: (TileRef | null)[][];
    overlay2?: (TileRef | null)[][];
    overlay3?: (TileRef | null)[][];
    background_color?: string;
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
    const source = getTileDrawSource(tile, tilesets);
    if (!source) return;

    ctx.drawImage(
      source.image,
      source.sx,
      source.sy,
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
    const background = normalizeBackgroundColor(map.tile_data.background_color);

    for (let y = 0; y < map.height; y++) {
      for (let x = 0; x < map.width; x++) {
        if (layers.includes("base")) {
          const baseTile = base[y]?.[x];
          if (getTileDrawSource(baseTile, tilesets)) {
            drawTile(ctx, baseTile, x, y);
          } else {
            ctx.fillStyle = background;
            ctx.fillRect(x * MAP_TILE_SIZE, y * MAP_TILE_SIZE, MAP_TILE_SIZE, MAP_TILE_SIZE);
          }
        }
        if (layers.includes("overlay")) drawTile(ctx, overlay[y]?.[x], x, y);
        if (layers.includes("overlay2") && overlay2) drawTile(ctx, overlay2[y]?.[x], x, y);
        if (layers.includes("overlay3") && overlay3) drawTile(ctx, overlay3[y]?.[x], x, y);
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
