import { type RefObject, useEffect, useRef } from "react";
import { RANDOM_TM_ITEM_ID } from "@/types/mapData";
import { getTmMachineUrl, TM_SOURCE_SIZE } from "@/utils/gameAssets";
import { MAP_TILE_DRAW_SIZE, setupPixelCanvas } from "@/utils/pixelCanvas";

const RANDOM_TM_DISPLAY_TYPE = "Normal";

export function useMapItemRenderer(
  canvasRef: RefObject<HTMLCanvasElement | null>,
  mapPixelWidth: number,
  mapPixelHeight: number,
  itemIdTiles: (number | null)[][] | null | undefined,
  itemMoveTypeById: Record<number, string>
) {
  const tmImagesRef = useRef<Record<string, HTMLImageElement>>({});

  useEffect(() => {
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

      if (!itemIdTiles) return;

      for (let y = 0; y < itemIdTiles.length; y++) {
        const row = itemIdTiles[y];
        if (!Array.isArray(row)) continue;
        for (let x = 0; x < row.length; x++) {
          const itemId = row[x];
          if (itemId == null) continue;

          const moveType =
            itemId === RANDOM_TM_ITEM_ID
              ? RANDOM_TM_DISPLAY_TYPE
              : itemMoveTypeById[itemId];
          if (!moveType) continue;

          const img = tmImagesRef.current[moveType];
          if (!img?.complete || img.naturalWidth <= 0) continue;

          ctx.drawImage(
            img,
            0,
            0,
            TM_SOURCE_SIZE,
            TM_SOURCE_SIZE,
            x * MAP_TILE_DRAW_SIZE,
            y * MAP_TILE_DRAW_SIZE,
            MAP_TILE_DRAW_SIZE,
            MAP_TILE_DRAW_SIZE
          );
        }
      }
    };

    const neededTypes = new Set<string>();
    if (itemIdTiles) {
      for (const row of itemIdTiles) {
        if (!Array.isArray(row)) continue;
        for (const itemId of row) {
          if (itemId == null) continue;
          const moveType =
            itemId === RANDOM_TM_ITEM_ID
              ? RANDOM_TM_DISPLAY_TYPE
              : itemMoveTypeById[itemId];
          if (moveType) neededTypes.add(moveType);
        }
      }
    }

    if (neededTypes.size === 0) {
      draw();
      return () => {
        cancelled = true;
      };
    }

    let pending = 0;

    for (const moveType of neededTypes) {
      const existing = tmImagesRef.current[moveType];
      if (existing?.complete && existing.naturalWidth > 0) continue;

      if (!existing) {
        const img = new Image();
        img.src = getTmMachineUrl(moveType);
        tmImagesRef.current[moveType] = img;
      }

      pending += 1;
      const img = tmImagesRef.current[moveType];
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
  }, [canvasRef, mapPixelWidth, mapPixelHeight, itemIdTiles, itemMoveTypeById]);
}
