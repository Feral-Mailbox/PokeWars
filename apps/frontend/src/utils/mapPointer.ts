/** Reserved horizontal space for the fixed chat panel, page padding, and gaps. */
export const MAP_DISPLAY_LAYOUT = {
  maxWidth: 960,
  maxHeight: 640,
  chatPanelWidth: 340,
  chatPanelGap: 24,
  horizontalPadding: 64,
  verticalHeaderOffset: 240,
} as const;

export function getMapDisplayMaxSize(): { maxWidth: number; maxHeight: number } {
  const {
    maxWidth,
    maxHeight,
    chatPanelWidth,
    chatPanelGap,
    horizontalPadding,
    verticalHeaderOffset,
  } = MAP_DISPLAY_LAYOUT;

  return {
    maxWidth: Math.min(
      maxWidth,
      window.innerWidth - chatPanelWidth - chatPanelGap - horizontalPadding
    ),
    maxHeight: Math.min(maxHeight, window.innerHeight - verticalHeaderOffset),
  };
}

export function computeMapDisplayScale(
  logicalWidth: number,
  logicalHeight: number,
  maxWidth: number,
  maxHeight: number
): number {
  if (logicalWidth <= 0 || logicalHeight <= 0) return 1;
  return Math.min(1, maxWidth / logicalWidth, maxHeight / logicalHeight);
}

/** Convert a screen pointer position to map tile coordinates for a scaled canvas. */
export function pointerToTileCoords(
  canvas: HTMLCanvasElement,
  mapTilesW: number,
  mapTilesH: number,
  clientX: number,
  clientY: number
): [number, number] {
  const rect = canvas.getBoundingClientRect();
  const x = Math.floor(((clientX - rect.left) / rect.width) * mapTilesW);
  const y = Math.floor(((clientY - rect.top) / rect.height) * mapTilesH);
  return [x, y];
}
