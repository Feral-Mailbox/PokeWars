/** Logical map tile size in pixels (16px source × 2 scale). */
export const MAP_TILE_SIZE = 16;
export const MAP_TILE_SCALE = 2;
export const MAP_TILE_DRAW_SIZE = MAP_TILE_SIZE * MAP_TILE_SCALE;

export function getDevicePixelRatio(): number {
  return Math.max(1, window.devicePixelRatio || 1);
}

/**
 * Size the canvas bitmap for the current display DPR so the browser does not
 * soft-scale a low-res buffer (a common cause of tile seams on HiDPI screens).
 */
export function setupPixelCanvas(
  canvas: HTMLCanvasElement,
  logicalWidth: number,
  logicalHeight: number
): number {
  const dpr = getDevicePixelRatio();
  const bufferWidth = Math.round(logicalWidth * dpr);
  const bufferHeight = Math.round(logicalHeight * dpr);

  if (canvas.width !== bufferWidth || canvas.height !== bufferHeight) {
    canvas.width = bufferWidth;
    canvas.height = bufferHeight;
  }
  canvas.style.width = `${logicalWidth}px`;
  canvas.style.height = `${logicalHeight}px`;

  return dpr;
}
