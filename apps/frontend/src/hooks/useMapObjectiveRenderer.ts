import { type RefObject, useEffect, useRef } from "react";
import {
  getMasterBallUrl,
  getPokeballUrl,
  POKEBALL_SOURCE_SIZE,
} from "@/utils/gameAssets";
import { MAP_TILE_DRAW_SIZE, setupPixelCanvas } from "@/utils/pixelCanvas";
import { resolvePlayerSlotOverlayColor } from "@/utils/playerOverlayColor";
import { drawTileHealthBar } from "@/utils/mapHealthBar";
import { drawImageWithPlayerOverlay } from "@/utils/spriteOverlay";

export type ObjectiveTileState = {
  kind: "pokeball" | "master_ball";
  owner: number;
  hp: number;
  max_hp: number;
  last_summon_round?: number | null;
  original_owner?: number;
};

type ObjectiveRendererOptions = {
  selectedTile?: [number, number] | null;
  playerOrder?: number[];
  getPlayerColor?: (playerId: number) => string;
};

export function useMapObjectiveRenderer(
  canvasRef: RefObject<HTMLCanvasElement | null> | null | undefined,
  mapPixelWidth: number,
  mapPixelHeight: number,
  objectiveTiles: (ObjectiveTileState | null)[][] | null | undefined,
  options: ObjectiveRendererOptions = {}
) {
  const imagesRef = useRef<Record<string, HTMLImageElement>>({});
  const { selectedTile = null, playerOrder = [], getPlayerColor } = options;

  useEffect(() => {
    if (!canvasRef) return;
    const canvas = canvasRef.current;
    if (!canvas || !mapPixelWidth || !mapPixelHeight) return;

    let cancelled = false;

    const draw = () => {
      if (cancelled) return;

      const dpr = setupPixelCanvas(canvas, mapPixelWidth, mapPixelHeight);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.imageSmoothingEnabled = false;

      if (!objectiveTiles?.length) return;

      for (let y = 0; y < objectiveTiles.length; y++) {
        const row = objectiveTiles[y];
        if (!Array.isArray(row)) continue;
        for (let x = 0; x < row.length; x++) {
          const cell = row[x];
          if (!cell) continue;

          const px = x * MAP_TILE_DRAW_SIZE;
          const py = y * MAP_TILE_DRAW_SIZE;
          const size = MAP_TILE_DRAW_SIZE;

          const overlayColor = resolvePlayerSlotOverlayColor(cell.owner, playerOrder, getPlayerColor);

          const imageKey = cell.kind === "master_ball" ? "master_ball" : "pokeball";
          const img = imagesRef.current[imageKey];
          if (img?.complete && img.naturalWidth > 0) {
            drawImageWithPlayerOverlay(
              ctx,
              img,
              0,
              0,
              POKEBALL_SOURCE_SIZE,
              POKEBALL_SOURCE_SIZE,
              px,
              py,
              size,
              size,
              overlayColor
            );
          }

          const isSelected = selectedTile?.[0] === x && selectedTile?.[1] === y;
          if (isSelected) {
            ctx.strokeStyle = "#ffffff";
            ctx.lineWidth = 2;
            ctx.strokeRect(px + 1, py + 1, size - 2, size - 2);
          }

          const maxHp = cell.max_hp || 20;
          const hp = cell.hp ?? maxHp;
          drawTileHealthBar(ctx, x, y, hp, maxHp, size);
        }
      }
    };

    const neededKeys = new Set<string>();
    if (objectiveTiles) {
      for (const row of objectiveTiles) {
        if (!Array.isArray(row)) continue;
        for (const cell of row) {
          if (!cell) continue;
          neededKeys.add(cell.kind === "master_ball" ? "master_ball" : "pokeball");
        }
      }
    }

    if (neededKeys.size === 0) {
      draw();
      return () => {
        cancelled = true;
      };
    }

    let pending = 0;
    const urlByKey: Record<string, string> = {
      pokeball: getPokeballUrl(),
      master_ball: getMasterBallUrl(),
    };

    for (const key of neededKeys) {
      const existing = imagesRef.current[key];
      if (existing?.complete && existing.naturalWidth > 0) continue;

      if (!existing) {
        const img = new Image();
        img.src = urlByKey[key];
        imagesRef.current[key] = img;
      }

      pending += 1;
      const img = imagesRef.current[key];
      const onDone = () => {
        pending -= 1;
        if (!cancelled && pending <= 0) draw();
      };
      img.onload = onDone;
      img.onerror = onDone;
      if (img.complete) onDone();
    }

    if (pending <= 0) draw();

    return () => {
      cancelled = true;
    };
  }, [
    canvasRef,
    mapPixelWidth,
    mapPixelHeight,
    objectiveTiles,
    selectedTile,
    playerOrder,
    getPlayerColor,
  ]);
}
