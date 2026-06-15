import { useCallback, useEffect, useRef } from "react";
import {
  MAP_TILE_DRAW_SIZE,
  MAP_TILE_SCALE,
  MAP_TILE_SIZE,
  setupPixelCanvas,
} from "@/utils/pixelCanvas";
import { getTilesetUrl } from "@/utils/gameAssets";
import type { MapLayer, MapTileData, TileRef } from "@/types/mapData";
import { DEFAULT_MOVEMENT_COST } from "@/types/mapData";
import type { DrawingTool } from "./drawingTools";
import { fillRectOnMap, normalizeRect, paintCellOnMap } from "./drawingTools";

type MapBuilderCanvasProps = {
  width: number;
  height: number;
  tileData: MapTileData;
  tilesetNames: string[];
  activeLayer: MapLayer;
  tool: DrawingTool;
  selectedTile: TileRef;
  spawnBrush: number | null;
  specialBrush: string;
  flagBrush: number | null;
  movementCostBrush: number;
  onStrokeStart: () => void;
  onStrokeEnd: () => void;
  onTileDataChange: (next: MapTileData | ((prev: MapTileData) => MapTileData)) => void;
};

const SPECIAL_COLORS: Record<string, string> = {
  impassable: "#1f2937",
  water: "#3b82f6",
  grass: "#22c55e",
  stump: "#92400e",
  rock: "#78716c",
  sand: "#eab308",
  ice: "#67e8f9",
  ledge_up: "#f97316",
  ledge_down: "#fb7185",
  ledge_left: "#a855f7",
  ledge_right: "#ec4899",
};

const SPAWN_COLORS = [
  "#ef4444",
  "#3b82f6",
  "#22c55e",
  "#eab308",
  "#a855f7",
  "#f97316",
  "#06b6d4",
  "#f43f5e",
];

function drawTile(
  ctx: CanvasRenderingContext2D,
  tilesets: HTMLImageElement[],
  tile: TileRef | null,
  x: number,
  y: number
) {
  if (!tile) return;
  const [tileIndex, tilesetIndex] = tile;
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
}

export default function MapBuilderCanvas({
  width,
  height,
  tileData,
  tilesetNames,
  activeLayer,
  tool,
  selectedTile,
  spawnBrush,
  specialBrush,
  flagBrush,
  movementCostBrush,
  onStrokeStart,
  onStrokeEnd,
  onTileDataChange,
}: MapBuilderCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const tilesetsRef = useRef<HTMLImageElement[]>([]);
  const loadedRef = useRef<Set<number>>(new Set());
  const paintingRef = useRef(false);
  const strokeSnapshotRef = useRef<MapTileData | null>(null);
  const anchorRef = useRef<{ x: number; y: number } | null>(null);
  const lastCellRef = useRef<{ x: number; y: number } | null>(null);
  const boxPreviewRef = useRef<{ x: number; y: number } | null>(null);

  const fillOptions = useCallback(
    (erase: boolean) => ({
      layer: activeLayer,
      erase,
      selectedTile,
      spawnBrush,
      specialBrush,
      flagBrush,
      movementCostBrush,
    }),
    [activeLayer, selectedTile, spawnBrush, specialBrush, flagBrush, movementCostBrush]
  );

  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const logicalWidth = width * MAP_TILE_DRAW_SIZE;
    const logicalHeight = height * MAP_TILE_DRAW_SIZE;
    const dpr = setupPixelCanvas(canvas, logicalWidth, logicalHeight);

    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.setTransform(dpr * MAP_TILE_SCALE, 0, 0, dpr * MAP_TILE_SCALE, 0, 0);
    ctx.imageSmoothingEnabled = false;

    const mapHeight = Math.min(height, tileData.base.length);
    const mapWidth = Math.min(width, tileData.base[0]?.length ?? 0);

    for (let y = 0; y < mapHeight; y++) {
      for (let x = 0; x < mapWidth; x++) {
        drawTile(ctx, tilesetsRef.current, tileData.base[y]?.[x] ?? null, x, y);
        drawTile(ctx, tilesetsRef.current, tileData.overlay[y]?.[x] ?? null, x, y);
        drawTile(ctx, tilesetsRef.current, tileData.overlay2[y]?.[x] ?? null, x, y);
      }
    }

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.font = "bold 10px sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";

    for (let y = 0; y < mapHeight; y++) {
      for (let x = 0; x < mapWidth; x++) {
        const px = x * MAP_TILE_DRAW_SIZE + MAP_TILE_DRAW_SIZE / 2;
        const py = y * MAP_TILE_DRAW_SIZE + MAP_TILE_DRAW_SIZE / 2;

        if (activeLayer === "spawn_points" || tileData.spawn_points[y]?.[x] != null) {
          const spawn = tileData.spawn_points[y]?.[x];
          if (spawn != null) {
            ctx.fillStyle = `${SPAWN_COLORS[spawn - 1] ?? "#fff"}88`;
            ctx.fillRect(x * MAP_TILE_DRAW_SIZE, y * MAP_TILE_DRAW_SIZE, MAP_TILE_DRAW_SIZE, MAP_TILE_DRAW_SIZE);
            ctx.fillStyle = "#fff";
            ctx.fillText(String(spawn), px, py);
          }
        }

        const special = tileData.special_tiles[y]?.[x];
        if (special) {
          ctx.fillStyle = `${SPECIAL_COLORS[special] ?? "#fff"}99`;
          ctx.fillRect(x * MAP_TILE_DRAW_SIZE + 2, y * MAP_TILE_DRAW_SIZE + 2, MAP_TILE_DRAW_SIZE - 4, 8);
        }

        const flag = tileData.flags[y]?.[x];
        if (flag != null && activeLayer === "flags") {
          ctx.fillStyle = "#facc1588";
          ctx.fillRect(x * MAP_TILE_DRAW_SIZE, y * MAP_TILE_DRAW_SIZE, MAP_TILE_DRAW_SIZE, MAP_TILE_DRAW_SIZE);
          ctx.fillStyle = "#000";
          ctx.fillText(`F${flag}`, px, py);
        }

        const cost = tileData.movement_cost[y]?.[x] ?? DEFAULT_MOVEMENT_COST;
        if (activeLayer === "movement_cost") {
          ctx.fillStyle = cost === DEFAULT_MOVEMENT_COST ? "#ffffff66" : "#ffffff";
          ctx.fillText(String(cost), px, py);
        }
      }
    }

    if (tool === "box" && paintingRef.current && anchorRef.current && boxPreviewRef.current) {
      const { minX, minY, maxX, maxY } = normalizeRect(
        anchorRef.current.x,
        anchorRef.current.y,
        boxPreviewRef.current.x,
        boxPreviewRef.current.y
      );
      ctx.strokeStyle = tool === "box" ? "#facc15" : "#ffffff";
      ctx.lineWidth = 2;
      ctx.setLineDash([4, 4]);
      ctx.strokeRect(
        minX * MAP_TILE_DRAW_SIZE + 1,
        minY * MAP_TILE_DRAW_SIZE + 1,
        (maxX - minX + 1) * MAP_TILE_DRAW_SIZE - 2,
        (maxY - minY + 1) * MAP_TILE_DRAW_SIZE - 2
      );
      ctx.setLineDash([]);
    }

    ctx.strokeStyle = "#ffffff22";
    ctx.lineWidth = 1;
    for (let x = 0; x <= width; x++) {
      ctx.beginPath();
      ctx.moveTo(x * MAP_TILE_DRAW_SIZE, 0);
      ctx.lineTo(x * MAP_TILE_DRAW_SIZE, height * MAP_TILE_DRAW_SIZE);
      ctx.stroke();
    }
    for (let y = 0; y <= height; y++) {
      ctx.beginPath();
      ctx.moveTo(0, y * MAP_TILE_DRAW_SIZE);
      ctx.lineTo(width * MAP_TILE_DRAW_SIZE, y * MAP_TILE_DRAW_SIZE);
      ctx.stroke();
    }
  }, [width, height, tileData, activeLayer, tool]);

  useEffect(() => {
    loadedRef.current = new Set();
    tilesetsRef.current = tilesetNames.map((name) => {
      const img = new Image();
      img.src = getTilesetUrl(name);
      return img;
    });

    const tryRedraw = (index: number) => {
      if (loadedRef.current.has(index)) return;
      loadedRef.current.add(index);
      if (loadedRef.current.size === tilesetNames.length) {
        redraw();
      }
    };

    tilesetsRef.current.forEach((img, index) => {
      img.onload = () => tryRedraw(index);
      img.onerror = () => tryRedraw(index);
      if (img.complete) tryRedraw(index);
    });
  }, [tilesetNames, redraw]);

  useEffect(() => {
    redraw();
  }, [redraw]);

  const cellFromEvent = (event: React.MouseEvent<HTMLCanvasElement>) => {
    const canvas = canvasRef.current;
    if (!canvas) return null;
    const rect = canvas.getBoundingClientRect();
    const x = Math.floor(((event.clientX - rect.left) / rect.width) * width);
    const y = Math.floor(((event.clientY - rect.top) / rect.height) * height);
    if (x < 0 || y < 0 || x >= width || y >= height) return null;
    return { x, y };
  };

  const applyAtCell = (cell: { x: number; y: number }, erase: boolean) => {
    const snapshot = strokeSnapshotRef.current;
    if (!snapshot) return;

    if (tool === "box" && anchorRef.current) {
      boxPreviewRef.current = cell;
      onTileDataChange(
        fillRectOnMap(
          snapshot,
          anchorRef.current.x,
          anchorRef.current.y,
          cell.x,
          cell.y,
          fillOptions(erase)
        )
      );
      return;
    }

    if (
      lastCellRef.current &&
      lastCellRef.current.x === cell.x &&
      lastCellRef.current.y === cell.y
    ) {
      return;
    }
    lastCellRef.current = cell;

    onTileDataChange((current) => paintCellOnMap(current, cell.x, cell.y, fillOptions(erase)));
  };

  const handlePointerDown = (event: React.MouseEvent<HTMLCanvasElement>) => {
    event.preventDefault();
    if (event.button !== 0) return;
    const cell = cellFromEvent(event);
    if (!cell) return;

    paintingRef.current = true;
    strokeSnapshotRef.current = structuredClone(tileData);
    anchorRef.current = cell;
    lastCellRef.current = null;
    boxPreviewRef.current = cell;
    onStrokeStart();

    const erase = tool === "eraser";
    applyAtCell(cell, erase);
  };

  const handlePointerMove = (event: React.MouseEvent<HTMLCanvasElement>) => {
    if (!paintingRef.current) return;
    const cell = cellFromEvent(event);
    if (!cell) return;
    applyAtCell(cell, tool === "eraser");
  };

  const stopPainting = () => {
    if (paintingRef.current) {
      onStrokeEnd();
    }
    paintingRef.current = false;
    strokeSnapshotRef.current = null;
    anchorRef.current = null;
    lastCellRef.current = null;
    boxPreviewRef.current = null;
  };

  const cursorClass =
    tool === "eraser" ? "cursor-cell" : tool === "box" ? "cursor-crosshair" : "cursor-crosshair";

  return (
    <canvas
      ref={canvasRef}
      className={`${cursorClass} rounded border border-gray-700 bg-black`}
      style={{
        width: width * MAP_TILE_DRAW_SIZE,
        height: height * MAP_TILE_DRAW_SIZE,
        imageRendering: "pixelated",
      }}
      onMouseDown={handlePointerDown}
      onMouseMove={handlePointerMove}
      onMouseUp={stopPainting}
      onMouseLeave={stopPainting}
      onContextMenu={(event) => event.preventDefault()}
    />
  );
}
