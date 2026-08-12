import { MAP_TILE_DRAW_SIZE } from "@/utils/pixelCanvas";
import { drawImageWithPlayerOverlay } from "@/utils/spriteOverlay";

export function drawCtfMapIcon(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement | null | undefined,
  tileX: number,
  tileY: number,
  overlayColor: string | null,
  tileSize = MAP_TILE_DRAW_SIZE
): boolean {
  if (!image?.complete || image.naturalWidth <= 0) return false;
  drawImageWithPlayerOverlay(
    ctx,
    image,
    0,
    0,
    image.naturalWidth,
    image.naturalHeight,
    tileX * tileSize,
    tileY * tileSize,
    tileSize,
    tileSize,
    overlayColor
  );
  return true;
}
