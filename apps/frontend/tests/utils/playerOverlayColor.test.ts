import { describe, expect, it, vi } from "vitest";
import {
  DEFAULT_PLAYER_OVERLAY_COLORS,
  resolvePlayerSlotOverlayColor,
} from "@/utils/playerOverlayColor";

describe("resolvePlayerSlotOverlayColor", () => {
  it("returns null for unowned slots", () => {
    expect(resolvePlayerSlotOverlayColor(0)).toBeNull();
    expect(resolvePlayerSlotOverlayColor(-1)).toBeNull();
  });

  it("uses joined player color when available", () => {
    const getPlayerColor = vi.fn((id: number) => (id === 10 ? "#abcdef80" : "#00000000"));
    expect(resolvePlayerSlotOverlayColor(1, [10, 20], getPlayerColor)).toBe("#abcdef80");
    expect(getPlayerColor).toHaveBeenCalledWith(10);
  });

  it("falls back to the war palette when the player color is missing or transparent", () => {
    expect(resolvePlayerSlotOverlayColor(2)).toBe(DEFAULT_PLAYER_OVERLAY_COLORS[1]);
    expect(resolvePlayerSlotOverlayColor(1, [10], () => "#00000000")).toBe(
      DEFAULT_PLAYER_OVERLAY_COLORS[0]
    );
  });
});
