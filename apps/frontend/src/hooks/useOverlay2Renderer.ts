import { type RefObject, useEffect } from "react";
import { installMapTileRenderer } from "@/utils/mapTileDrawing";

type MapRenderData = {
  width: number;
  height: number;
  tileset_names: string[];
  tile_data: {
    base: [number, number][][];
    overlay: ([number, number] | null)[][];
    overlay2?: ([number, number] | null)[][];
  };
};

export function useOverlay2Renderer(
  canvasRef: RefObject<HTMLCanvasElement | null>,
  map: MapRenderData | null | undefined
) {
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !map?.tile_data?.overlay2 || !map.tileset_names?.length) return;

    return installMapTileRenderer(canvas, map, ["overlay2"]);
  }, [canvasRef, map]);
}
