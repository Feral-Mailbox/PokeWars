import { MAP_TILE_DRAW_SIZE } from "@/utils/pixelCanvas";

export function drawTileHealthBar(
  ctx: CanvasRenderingContext2D,
  tileX: number,
  tileY: number,
  hp: number,
  maxHp: number,
  tileSize = MAP_TILE_DRAW_SIZE
): void {
  const max = Math.max(1, Number(maxHp) || 1);
  const current = Math.max(0, Number(hp) || 0);
  const barWidth = tileSize - 4;
  const barHeight = 4;
  const barX = tileX * tileSize + 2;
  const barY = tileY * tileSize + tileSize - barHeight - 2;
  ctx.fillStyle = "rgba(0, 0, 0, 0.6)";
  ctx.fillRect(barX, barY, barWidth, barHeight);
  ctx.fillStyle = current < max ? "#f97316" : "#22c55e";
  ctx.fillRect(barX, barY, barWidth * (current / max), barHeight);
}
