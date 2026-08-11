import { describe, expect, it, vi } from "vitest";
import { drawCtfMapIcon } from "@/utils/ctfIcons";

vi.mock("@/utils/spriteOverlay", () => ({
  drawImageWithPlayerOverlay: vi.fn(),
}));

import { drawImageWithPlayerOverlay } from "@/utils/spriteOverlay";

describe("drawCtfMapIcon", () => {
  it("skips drawing when the sprite is not ready", () => {
    const ctx = {} as CanvasRenderingContext2D;
    expect(drawCtfMapIcon(ctx, null, 1, 2, "#0000FF80")).toBe(false);
    expect(
      drawCtfMapIcon(ctx, { complete: true, naturalWidth: 0 } as HTMLImageElement, 1, 2, null)
    ).toBe(false);
    expect(drawImageWithPlayerOverlay).not.toHaveBeenCalled();
  });

  it("draws with natural source size and war overlay color", () => {
    const ctx = {} as CanvasRenderingContext2D;
    const image = { complete: true, naturalWidth: 60, naturalHeight: 60 } as HTMLImageElement;
    expect(drawCtfMapIcon(ctx, image, 2, 3, "#FF000080")).toBe(true);
    expect(drawImageWithPlayerOverlay).toHaveBeenCalledWith(
      ctx,
      image,
      0,
      0,
      60,
      60,
      64,
      96,
      32,
      32,
      "#FF000080"
    );
  });
});
