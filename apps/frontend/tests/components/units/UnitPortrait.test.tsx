import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import UnitPortrait from "@/components/units/UnitPortrait";

describe("UnitPortrait", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        complete = false;
        naturalWidth = 0;
        set src(_val: string) {
          this.complete = true;
          this.naturalWidth = 80;
          this.onload?.();
        }
      } as any
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads the base portrait when available", async () => {
    render(<UnitPortrait assetFolder="025_pikachu" size={40} />);
    const img = await screen.findByAltText("Unit Portrait");
    expect(img.getAttribute("src")).toContain("/units/025_pikachu/portraits/portrait.png");
  });

  it("falls back to male portrait when base is missing", async () => {
    let calls = 0;
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        complete = false;
        naturalWidth = 0;
        set src(val: string) {
          calls += 1;
          queueMicrotask(() => {
            if (String(val).includes("/male/")) {
              this.complete = true;
              this.naturalWidth = 80;
              this.onload?.();
            } else {
              this.onerror?.();
            }
          });
        }
      } as any
    );

    render(<UnitPortrait assetFolder="025_pikachu" />);
    const img = await screen.findByAltText("Unit Portrait");
    expect(img.getAttribute("src")).toContain("/portraits/male/portrait.png");
    expect(calls).toBeGreaterThanOrEqual(2);
  });

  it("renders nothing when no portrait exists", async () => {
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        complete = false;
        naturalWidth = 0;
        set src(_val: string) {
          queueMicrotask(() => this.onerror?.());
        }
      } as any
    );

    const { container } = render(<UnitPortrait assetFolder="missing_unit" />);
    await waitFor(() => {
      expect(container.querySelector("img")).toBeNull();
    });
  });

  it("applies frame offsets after image load when the sprite sheet is large enough", async () => {
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        complete = false;
        naturalWidth = 0;
        set src(_val: string) {
          this.complete = true;
          this.naturalWidth = 200;
          this.onload?.();
        }
      } as any
    );

    render(<UnitPortrait assetFolder="025_pikachu" size={40} frameX={40} frameY={40} />);
    const img = await screen.findByAltText("Unit Portrait");
    Object.defineProperty(img, "naturalWidth", { value: 200 });
    Object.defineProperty(img, "naturalHeight", { value: 200 });
    img.dispatchEvent(new Event("load"));
    await waitFor(() => {
      expect(img.style.objectPosition).toBe("-40px -40px");
    });
  });
});
