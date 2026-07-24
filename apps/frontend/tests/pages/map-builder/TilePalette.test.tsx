import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TilePalette from "@/pages/map-builder/TilePalette";

describe("TilePalette", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        naturalWidth = 32;
        naturalHeight = 16;
        set src(_val: string) {
          queueMicrotask(() => this.onload?.());
        }
      } as any
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("loads tiles and selects one", async () => {
    const user = userEvent.setup();
    const onSelectTile = vi.fn();
    render(
      <TilePalette
        tilesetName="Brick City.png"
        selectedTile={null}
        onSelectTile={onSelectTile}
        tilesetIndex={0}
      />
    );

    expect(screen.getByText(/Loading tileset/i)).toBeInTheDocument();
    expect(await screen.findByText(/2 tiles/i)).toBeInTheDocument();
    await user.click(screen.getByTitle("Tile 0"));
    expect(onSelectTile).toHaveBeenCalledWith([0, 0]);
  });

  it("shows an error when the tileset fails to load", async () => {
    vi.stubGlobal(
      "Image",
      class {
        onload: (() => void) | null = null;
        onerror: (() => void) | null = null;
        naturalWidth = 0;
        naturalHeight = 0;
        set src(_val: string) {
          queueMicrotask(() => this.onerror?.());
        }
      } as any
    );

    render(
      <TilePalette
        tilesetName="missing.png"
        selectedTile={null}
        onSelectTile={() => {}}
        tilesetIndex={0}
      />
    );

    await waitFor(() => {
      expect(screen.getByText(/Failed to load tileset: missing.png/i)).toBeInTheDocument();
    });
  });
});
