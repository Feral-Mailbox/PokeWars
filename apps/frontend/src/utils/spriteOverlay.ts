/** Matches UnitIdleSprite map placement tint strength. */
export const SPRITE_OVERLAY_ALPHA = 0.7;

export function applyOpaquePixelOverlay(
  ctx: CanvasRenderingContext2D,
  imageData: ImageData,
  offsetX: number,
  offsetY: number,
  overlayColor: string
) {
  const { width, height, data } = imageData;
  ctx.fillStyle = overlayColor;
  ctx.globalAlpha = SPRITE_OVERLAY_ALPHA;
  for (let y = 0; y < height; y++) {
    for (let x = 0; x < width; x++) {
      const i = (y * width + x) * 4;
      if (data[i + 3] > 0) {
        ctx.fillRect(offsetX + x, offsetY + y, 1, 1);
      }
    }
  }
  ctx.globalAlpha = 1.0;
}

export function drawImageWithPlayerOverlay(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  sx: number,
  sy: number,
  sw: number,
  sh: number,
  dx: number,
  dy: number,
  dw: number,
  dh: number,
  overlayColor: string | null | undefined
) {
  ctx.drawImage(image, sx, sy, sw, sh, dx, dy, dw, dh);
  if (!overlayColor || overlayColor === "#00000000") return;

  const frameCanvas = document.createElement("canvas");
  frameCanvas.width = dw;
  frameCanvas.height = dh;
  const frameCtx = frameCanvas.getContext("2d");
  if (!frameCtx) return;

  frameCtx.drawImage(image, sx, sy, sw, sh, 0, 0, dw, dh);
  applyOpaquePixelOverlay(ctx, frameCtx.getImageData(0, 0, dw, dh), dx, dy, overlayColor);
}
