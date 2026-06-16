export const UNIT_SPRITE_SCALE = 1.33;

export function spriteCanvasPixelToMapCoords(
  px: number,
  py: number,
  tile: [number, number],
  tileDrawSize: number,
  frameHeight: number,
  frameWidth: number,
  spriteScale = UNIT_SPRITE_SCALE
): [number, number] {
  const mapX = tile[0] * tileDrawSize + (tileDrawSize - frameWidth * spriteScale) / 2 + px * spriteScale;
  const mapY = tile[1] * tileDrawSize + tileDrawSize - (frameHeight - py) * spriteScale;
  return [mapX, mapY];
}

export function getUnitSpriteBoundsOnMap(
  tile: [number, number],
  tileDrawSize: number,
  frameWidth: number,
  frameHeight: number,
  spriteScale = UNIT_SPRITE_SCALE
): { minX: number; minY: number; maxX: number; maxY: number } {
  const minX = tile[0] * tileDrawSize + (tileDrawSize - frameWidth * spriteScale) / 2;
  const maxX = minX + frameWidth * spriteScale;
  const maxY = tile[1] * tileDrawSize + tileDrawSize;
  const minY = maxY - frameHeight * spriteScale;
  return { minX, minY, maxX, maxY };
}

export function getUnitSpriteCanvasStyle(
  tile: [number, number],
  tileDrawSize: number,
  frameWidth: number,
  frameHeight: number,
  spriteScale = UNIT_SPRITE_SCALE
) {
  const displayWidth = frameWidth * spriteScale;
  const displayHeight = frameHeight * spriteScale;

  return {
    position: "absolute" as const,
    left: tile[0] * tileDrawSize + (tileDrawSize - displayWidth) / 2,
    top: tile[1] * tileDrawSize + tileDrawSize - displayHeight,
    width: frameWidth,
    height: frameHeight,
    transform: `scale(${spriteScale})`,
    transformOrigin: "bottom center" as const,
    imageRendering: "pixelated" as const,
    pointerEvents: "none" as const,
  };
}
