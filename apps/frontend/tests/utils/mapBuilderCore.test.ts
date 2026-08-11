import { describe, expect, it, vi } from "vitest";
import { normalizeAllowedModes } from "@/types/mapData";
import {
  buildMapExport,
  canExportMap,
  createEmptyTileData,
  downloadMapJson,
  normalizeTileData,
  parseMapImport,
  resizeTileData,
  slugifyMapName,
  validateConquestSpawnExport,
  validateCtfMapExport,
  validateWarMapExport,
} from "@/utils/mapBuilder";

describe("mapBuilder core helpers", () => {
  it("slugifies map names", () => {
    expect(slugifyMapName("  My Cool Map!! ")).toBe("my_cool_map");
    expect(slugifyMapName("___")).toBe("");
  });

  it("normalizes partial tile data into a full grid", () => {
    const raw = {
      base: [[[1, 2]]],
      overlay: [[[3, 4]]],
      spawn_points: [[2]],
      special_tiles: [["water"]],
      flags: [[1]],
      movement_cost: [[3]],
      item_id_tiles: [[9]],
    };
    const normalized = normalizeTileData(raw, 2, 2);
    expect(normalized.base[0][0]).toEqual([1, 2]);
    expect(normalized.overlay[0][0]).toEqual([3, 4]);
    expect(normalized.spawn_points[0][0]).toBe(2);
    expect(normalized.special_tiles[0][0]).toBe("water");
    expect(normalized.flags[0][0]).toBe(1);
    expect(normalized.movement_cost[0][0]).toBe(3);
    expect(normalized.item_id_tiles[0][0]).toBe(9);
    expect(normalized.base[1][1]).toBeNull();
    expect(normalized.background_color).toBe("#000000");
    expect(normalizeTileData({}, 1, 1).base).toHaveLength(1);
    expect(normalizeTileData({ base: [[[1, 0]]], background_color: "#cde" }, 1, 1).background_color).toBe(
      "#cde"
    );
    expect(normalizeTileData({ base: [[[1, 0]]], background_color: "red" }, 1, 1).background_color).toBe(
      "#000000"
    );
    expect(normalizeTileData({ base: [[[0, 0], [4, 0]]] }, 2, 1).base[0]).toEqual([[0, 0], [4, 0]]);
    expect(normalizeTileData({ base: [[[0, 0], null]] }, 2, 1).base[0]).toEqual([[0, 0], null]);
  });

  it("resizes tile data while preserving overlapping cells", () => {
    const data = createEmptyTileData(2, 2);
    data.base[0][0] = [5, 6];
    data.spawn_points[1][1] = 3;
    const grown = resizeTileData(data, 2, 2, 3, 3);
    expect(grown.base).toHaveLength(3);
    expect(grown.base[0]).toHaveLength(3);
    expect(grown.base[0][0]).toEqual([5, 6]);
    expect(grown.spawn_points[1][1]).toBe(3);
    expect(grown.base[2][2]).toBeNull();

    const shrunk = resizeTileData(data, 2, 2, 1, 1);
    expect(shrunk.base).toHaveLength(1);
    expect(shrunk.base[0][0]).toEqual([5, 6]);

    data.background_color = "#112233";
    expect(resizeTileData(data, 2, 2, 3, 3).background_color).toBe("#112233");
  });

  it("builds and parses map export payloads", () => {
    const tileData = createEmptyTileData(2, 2);
    const exported = buildMapExport({
      name: "Forest Arena",
      tilesetNames: ["Brick City.png"],
      allowedPlayerCounts: [2],
      width: 2,
      height: 2,
      tileData,
    });
    expect(exported.name).toBe("Forest Arena");
    expect(exported.preview_image).toBe("previews/forest_arena.png");
    expect(exported.is_official).toBe(false);
    expect(exported.allowed_modes).toEqual(["Conquest", "War"]);
    expect(parseMapImport(exported).name).toBe("Forest Arena");
    expect(parseMapImport({ ...exported, allowed_modes: ["War"] }).allowed_modes).toEqual([
      "Conquest",
      "War",
    ]);
    expect(() => parseMapImport(null)).toThrow(/Invalid map file/);
    expect(() => parseMapImport({ name: "x" })).toThrow(/missing required fields/);
  });

  it("downloads map json via an anchor click", () => {
    const createObjectURL = vi.fn(() => "blob:map");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });

    const click = vi.fn();
    const createElement = vi.spyOn(document, "createElement").mockReturnValue({
      href: "",
      download: "",
      click,
    } as unknown as HTMLAnchorElement);

    downloadMapJson(
      buildMapExport({
        name: "Test",
        tilesetNames: ["a.png"],
        allowedPlayerCounts: [2],
        width: 1,
        height: 1,
        tileData: createEmptyTileData(1, 1),
      })
    );

    expect(createObjectURL).toHaveBeenCalled();
    expect(click).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:map");
    createElement.mockRestore();
    vi.unstubAllGlobals();
  });

  it("validates required spawns, master balls, and export prerequisites", () => {
    const data = createEmptyTileData(2, 1);
    expect(validateConquestSpawnExport(data, [])).toMatchObject({ ok: false });
    expect(validateConquestSpawnExport(data, [2])).toMatchObject({ ok: false, message: expect.stringContaining("Player 1") });
    data.spawn_points[0][0] = 1;
    data.spawn_points[0][1] = 2;
    expect(validateConquestSpawnExport(data, [2])).toEqual({ ok: true, message: null });

    expect(validateWarMapExport(data, [])).toMatchObject({ ok: false });
    data.special_tiles[0][0] = "master_ball_p1";
    expect(validateWarMapExport(data, [2])).toMatchObject({ ok: false, message: expect.stringContaining("Player 2") });
    data.special_tiles[0][1] = "master_ball_p2";
    expect(validateWarMapExport(data, [2])).toEqual({ ok: true, message: null });
    expect(canExportMap([], [2], data)).toMatchObject({ ok: false, message: expect.stringContaining("tileset") });
    expect(canExportMap(["a.png"], [2], data)).toEqual({ ok: true, message: null });

    data.flags[0][0] = 1;
    expect(validateCtfMapExport(data)).toMatchObject({ ok: false, message: expect.stringContaining("jail") });
    data.special_tiles[0][0] = "ctf_jail_p1";
    expect(validateCtfMapExport(data)).toMatchObject({ ok: false, message: expect.stringContaining("P2") });
    data.special_tiles[0][1] = "ctf_jail_p2";
    expect(validateCtfMapExport(data)).toEqual({ ok: true, message: null });
  });

  it("always includes Conquest and only validates selected extra modes", () => {
    expect(normalizeAllowedModes(null)).toEqual(["Conquest"]);
    expect(normalizeAllowedModes(["War", "bogus"])).toEqual(["Conquest", "War"]);
    expect(normalizeAllowedModes(["Capture The Flag"])).toEqual(["Conquest", "Capture The Flag"]);

    const data = createEmptyTileData(2, 1);
    data.spawn_points[0][0] = 1;
    data.spawn_points[0][1] = 2;
    expect(canExportMap(["a.png"], [2], data, ["Conquest"])).toEqual({ ok: true, message: null });
    expect(canExportMap(["a.png"], [2], data, ["Conquest", "War"])).toMatchObject({
      ok: false,
      message: expect.stringContaining("master ball"),
    });
    expect(canExportMap(["a.png"], [2], data, ["Conquest", "Capture The Flag"])).toMatchObject({
      ok: false,
      message: expect.stringContaining("flag"),
    });
    expect(validateCtfMapExport(data, true)).toMatchObject({
      ok: false,
      message: expect.stringContaining("flag"),
    });

    const conquestOnly = buildMapExport({
      name: "Spawns Only",
      tilesetNames: ["a.png"],
      allowedPlayerCounts: [2],
      width: 2,
      height: 1,
      tileData: data,
      allowedModes: ["Conquest"],
    });
    expect(conquestOnly.allowed_modes).toEqual(["Conquest"]);

    const withCtf = buildMapExport({
      name: "CTF Arena",
      tilesetNames: ["a.png"],
      allowedPlayerCounts: [2],
      width: 2,
      height: 1,
      tileData: data,
      allowedModes: ["Capture The Flag"],
    });
    expect(withCtf.allowed_modes).toEqual(["Conquest", "Capture The Flag"]);
  });

  it("keeps defaults for invalid imported cells and defaults export names", () => {
    const normalized = normalizeTileData(
      { base: [[[1, 1]]], movement_cost: [[0]], item_id_tiles: [[-1]] },
      1,
      1
    );
    expect(normalized.movement_cost[0][0]).toBe(1);
    expect(normalized.item_id_tiles[0][0]).toBeNull();
    const exported = buildMapExport({
      name: " ",
      tilesetNames: [],
      allowedPlayerCounts: [],
      width: 1,
      height: 1,
      tileData: createEmptyTileData(1, 1),
    });
    expect(exported.name).toBe("Untitled Map");
    expect(exported.preview_image).toBe("previews/custom_map.png");
  });
});
