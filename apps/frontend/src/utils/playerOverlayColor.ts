/** Same palette as GamePage PLAYER_COLORS — used when owner slot has no joined user yet. */
export const DEFAULT_PLAYER_OVERLAY_COLORS = [
  "#0000FF80",
  "#FF000080",
  "#FFFF0080",
  "#00FF0080",
  "#88888880",
  "#80008080",
  "#FF00FF80",
  "#00FFFF80",
];

export function resolvePlayerSlotOverlayColor(
  slot: number,
  playerOrder: number[] = [],
  getPlayerColor?: (playerId: number) => string
): string | null {
  if (slot <= 0) return null;
  const ownerId = playerOrder[slot - 1];
  if (ownerId != null && getPlayerColor) {
    const color = getPlayerColor(ownerId);
    if (color && color !== "#00000000") return color;
  }
  return DEFAULT_PLAYER_OVERLAY_COLORS[(slot - 1) % DEFAULT_PLAYER_OVERLAY_COLORS.length] ?? null;
}
