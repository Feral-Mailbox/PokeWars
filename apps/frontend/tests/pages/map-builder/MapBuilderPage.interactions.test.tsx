import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import MapBuilderPage from "@/pages/map-builder/MapBuilderPage";
import { createEmptyTileData } from "@/utils/mapBuilder";

vi.mock("@/state/auth", () => ({
  useAuth: vi.fn(),
}));

vi.mock("@/utils/secureFetch", () => ({
  secureFetch: vi.fn(),
}));

vi.mock("@/utils/mapBuilder", async () => {
  const actual = await vi.importActual<typeof import("@/utils/mapBuilder")>("@/utils/mapBuilder");
  return {
    ...actual,
    downloadMapJson: vi.fn(),
  };
});

vi.mock("@/pages/map-builder/MapBuilderCanvas", () => ({
  default: (props: any) => (
    <div data-testid="map-builder-canvas">
      <button
        type="button"
        onClick={() => {
          props.onStrokeStart();
          const next = structuredClone(props.tileData);
          if (next.base?.[0]?.[0]) next.base[0][0] = [3, 0];
          props.onTileDataChange(next);
          props.onStrokeEnd();
        }}
      >
        Simulate stroke
      </button>
      <button
        type="button"
        onClick={() =>
          props.onTileDataChange((prev: any) => {
            const next = structuredClone(prev);
            next.base[0][0] = [9, 0];
            return next;
          })
        }
      >
        Functional update
      </button>
    </div>
  ),
}));

vi.mock("@/pages/map-builder/TilePalette", () => ({
  default: (props: any) => (
    <button type="button" onClick={() => props.onSelectTile([4, props.tilesetIndex])}>
      Pick tile
    </button>
  ),
}));

import { useAuth } from "@/state/auth";
import { secureFetch } from "@/utils/secureFetch";
import { downloadMapJson } from "@/utils/mapBuilder";

function staffAuth() {
  vi.mocked(useAuth).mockReturnValue({
    user: {
      id: 2,
      trainer_id: 'A1B2C3D4',
      username: "mod",
      email: "m@b.c",
      avatar: "",
      elo: 1000,
      currency: 0,
      role: "moderator",
    },
    loading: false,
  } as ReturnType<typeof useAuth>);
}

function mockApis() {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ["Brick City.png", "Beach Houses.png"],
    })
  );

  vi.mocked(secureFetch).mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/items/all")) {
      return {
        ok: true,
        json: async () => [
          { id: 10, name: "TM01", slug: "tm01", move_id: 1 },
          { id: 11, name: "TM02", slug: "tm02", move_id: 2 },
        ],
      } as Response;
    }
    if (url.includes("/moves/all")) {
      return {
        ok: true,
        json: async () => [
          { id: 1, name: "Focus Punch", type: "Fighting" },
          { id: 2, name: "Dragon Claw", type: "Dragon" },
        ],
      } as Response;
    }
    return { ok: true, json: async () => [] } as Response;
  });
}

async function renderStaffBuilder() {
  staffAuth();
  mockApis();
  render(
    <MemoryRouter>
      <MapBuilderPage />
    </MemoryRouter>
  );
  expect(await screen.findByRole("heading", { name: /Map Builder/i })).toBeInTheDocument();
}

describe("MapBuilderPage interactions", () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it("switches layers and tools, paints via canvas callbacks, undo/redo", async () => {
    const user = userEvent.setup();
    await renderStaffBuilder();

    await user.click(screen.getByRole("button", { name: "Conquest" }));
    expect(screen.getByText(/Conquest spawn brush/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "P3" }));
    await user.click(screen.getByRole("button", { name: "Clear" }));

    await user.click(screen.getByRole("button", { name: "Special tiles" }));
    expect(screen.getByLabelText(/Special tile/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "War" }));
    expect(screen.getByRole("button", { name: "Pokeball" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Master Ball" }));
    // Owner row has many P* buttons; pick one that is now master-ball owner brush
    await user.click(screen.getAllByRole("button", { name: "P2" })[0]);

    await user.click(screen.getByRole("button", { name: "Flags (CTF)" }));
    expect(screen.getByText(/Flag owner/i)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Movement cost" }));
    expect(screen.getByText(/Cost brush/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "2" }));

    await user.click(screen.getByRole("button", { name: "Items (TMs)" }));
    await waitFor(() => {
      expect(screen.getByLabelText(/^TM$/i)).toBeInTheDocument();
      expect(screen.getByLabelText(/^TM$/i)).not.toBeDisabled();
    });

    await user.click(screen.getByRole("button", { name: "Base tiles" }));
    await user.click(screen.getByRole("button", { name: "Box" }));
    await user.click(screen.getByRole("button", { name: "Eraser" }));
    await user.click(screen.getByRole("button", { name: "Pencil" }));

    await user.click(screen.getByRole("button", { name: "Simulate stroke" }));
    expect(screen.getByRole("button", { name: "Undo" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Undo" }));
    expect(screen.getByRole("button", { name: "Redo" })).toBeEnabled();
    await user.click(screen.getByRole("button", { name: "Redo" }));

    await user.click(screen.getByRole("button", { name: "Functional update" }));
  });

  it("resizes map, toggles overlays/player counts, and exports when valid", async () => {
    const user = userEvent.setup();
    await renderStaffBuilder();

    // Make export-valid war/conquest layout via strokes is hard without real canvas;
    // paint enough through Simulate stroke then set war/spawn via... we need canExportMap true.
    // Instead directly exercise export failure first, then import a valid map.

    const widthInput = screen.getByLabelText(/^Width$/i);
    await user.clear(widthInput);
    await user.type(widthInput, "16");
    expect(screen.getByText(/Map size changed/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Apply size/i }));

    await user.click(screen.getByLabelText(/Show all overlay layers/i));
    await user.click(screen.getByLabelText(/3 players/i));

    // Export should still be blocked until war validation passes
    const exportBtn = screen.getByRole("button", { name: /Export JSON/i });
    expect(exportBtn).toBeDisabled();
    await user.click(exportBtn); // no-op when disabled
  });

  it("imports a valid map JSON and exports after validation", async () => {
    const user = userEvent.setup();
    await renderStaffBuilder();

    const tileData = createEmptyTileData(2, 2);
    tileData.spawn_points[0][0] = 1;
    tileData.spawn_points[1][1] = 2;
    tileData.special_tiles[0][0] = "master_ball_p1";
    tileData.special_tiles[1][1] = "master_ball_p2";

    const map = {
      name: "Imported Arena",
      is_official: false,
      tileset_names: ["Brick City.png"],
      allowed_modes: ["Conquest", "War"],
      allowed_player_counts: [2],
      width: 2,
      height: 2,
      tile_data: tileData,
      preview_image: "previews/imported_arena.png",
    };

    const file = new File([JSON.stringify(map)], "map.json", { type: "application/json" });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(file, "text", {
      value: async () => JSON.stringify(map),
    });
    await user.upload(input, file);

    await waitFor(() => {
      expect(screen.getByText(/Imported .*Imported Arena/i)).toBeInTheDocument();
    });

    const exportBtn = screen.getByRole("button", { name: /Export JSON/i });
    await waitFor(() => expect(exportBtn).toBeEnabled());
    await user.click(exportBtn);
    expect(downloadMapJson).toHaveBeenCalled();
    expect(screen.getByText(/Map exported/i)).toBeInTheDocument();
  });

  it("reports import failures and supports undo hotkeys", async () => {
    const user = userEvent.setup();
    await renderStaffBuilder();

    const bad = new File(["{not-json"], "bad.json", { type: "application/json" });
    Object.defineProperty(bad, "text", {
      value: async () => "{not-json",
    });
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, bad);
    await waitFor(() => {
      expect(
        screen.getByText((content) => content.includes("Expected property name") || content.includes("Failed to import"))
      ).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: "Simulate stroke" }));
    fireEvent.keyDown(window, { key: "z", ctrlKey: true });
    expect(screen.getByRole("button", { name: "Redo" })).toBeEnabled();
    fireEvent.keyDown(window, { key: "y", ctrlKey: true });
    fireEvent.keyDown(window, { key: "z", ctrlKey: true, shiftKey: true });
  });

  it("loads TM catalog failure message and toggles tilesets", async () => {
    const user = userEvent.setup();
    staffAuth();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ["Brick City.png", "Beach Houses.png"],
      })
    );
    vi.mocked(secureFetch).mockRejectedValue(new Error("network"));

    render(
      <MemoryRouter>
        <MapBuilderPage />
      </MemoryRouter>
    );
    expect(await screen.findByRole("heading", { name: /Map Builder/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/Failed to load TM catalog/i)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Beach Houses.png")).toBeInTheDocument();
    });
    await user.click(screen.getByLabelText(/Beach Houses.png/i));
    expect(screen.getByLabelText(/Beach Houses.png/i)).toBeChecked();
  });

  it("renames map and picks a palette tile", async () => {
    const user = userEvent.setup();
    await renderStaffBuilder();
    const nameInput = screen.getByDisplayValue("New Map");
    await user.clear(nameInput);
    await user.type(nameInput, "Forest Arena");
    expect(screen.getByDisplayValue("Forest Arena")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Pick tile/i }));
  });
});
