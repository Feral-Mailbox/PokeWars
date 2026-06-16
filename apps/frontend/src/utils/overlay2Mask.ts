export type Overlay2Mask = {
  data: Uint8ClampedArray;
  width: number;
  height: number;
  dpr: number;
};

export function captureOverlay2Mask(canvas: HTMLCanvasElement): Overlay2Mask | null {
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx || canvas.width <= 0 || canvas.height <= 0) return null;

  const cssWidth = canvas.clientWidth || canvas.width;
  const dpr = cssWidth > 0 ? canvas.width / cssWidth : 1;

  return {
    data: ctx.getImageData(0, 0, canvas.width, canvas.height).data,
    width: canvas.width,
    height: canvas.height,
    dpr,
  };
}

export function sampleOverlay2Mask(mask: Overlay2Mask | null | undefined, mapX: number, mapY: number): number {
  if (!mask) return 0;

  const x = Math.floor(mapX * mask.dpr);
  const y = Math.floor(mapY * mask.dpr);
  if (x < 0 || y < 0 || x >= mask.width || y >= mask.height) return 0;

  return mask.data[(y * mask.width + x) * 4 + 3];
}

export function overlay2MaskHasCoverage(
  mask: Overlay2Mask | null | undefined,
  minX: number,
  minY: number,
  maxX: number,
  maxY: number
): boolean {
  if (!mask) return false;

  const startX = Math.max(0, Math.floor(minX * mask.dpr));
  const startY = Math.max(0, Math.floor(minY * mask.dpr));
  const endX = Math.min(mask.width - 1, Math.ceil(maxX * mask.dpr));
  const endY = Math.min(mask.height - 1, Math.ceil(maxY * mask.dpr));

  for (let y = startY; y <= endY; y++) {
    for (let x = startX; x <= endX; x++) {
      if (mask.data[(y * mask.width + x) * 4 + 3] > 0) return true;
    }
  }

  return false;
}
