import { describe, expect, it } from "vitest";
import { encodeWarObjective, isWarObjectiveTile, parseWarObjectiveTile } from "@/types/mapData";
import { canExportMap, createEmptyTileData, validateConquestSpawnExport, validateWarMapExport } from "@/utils/mapBuilder";

describe("war map builder helpers", () => {
  it("encodes pokeball and master ball objectives", () => {
    expect(encodeWarObjective("pokeball", null)).toBe("pokeball");
    expect(encodeWarObjective("pokeball", 2)).toBe("pokeball_p2");
    expect(encodeWarObjective("master_ball", 1)).toBe("master_ball_p1");
  });

  it("detects and parses war objective tiles", () => {
    expect(isWarObjectiveTile("pokeball")).toBe(true);
    expect(isWarObjectiveTile("master_ball_p3")).toBe(true);
    expect(isWarObjectiveTile("grass")).toBe(false);
    expect(parseWarObjectiveTile("pokeball_p4")).toEqual({ kind: "pokeball", owner: 4 });
  });

  it("requires exactly one master ball per player up to max count", () => {
    const tileData = createEmptyTileData(3, 3);
    tileData.spawn_points[0][0] = 1;
    tileData.spawn_points[0][1] = 2;
    tileData.special_tiles[0][0] = "master_ball_p1";
    tileData.special_tiles[0][1] = "master_ball_p2";
    tileData.special_tiles[1][1] = "pokeball";

    expect(validateWarMapExport(tileData, [2]).ok).toBe(true);
    expect(validateWarMapExport(tileData, [3]).ok).toBe(false);

    tileData.spawn_points[2][2] = 3;
    tileData.special_tiles[2][2] = "master_ball_p3";
    expect(validateWarMapExport(tileData, [3]).ok).toBe(true);
  });

  it("rejects export when a player has multiple master balls", () => {
    const tileData = createEmptyTileData(2, 2);
    tileData.spawn_points[0][0] = 1;
    tileData.spawn_points[1][1] = 2;
    tileData.special_tiles[0][0] = "master_ball_p1";
    tileData.special_tiles[0][1] = "master_ball_p1";
    tileData.special_tiles[1][0] = "master_ball_p2";

    const result = validateWarMapExport(tileData, [2]);
    expect(result.ok).toBe(false);
    expect(result.message).toMatch(/Player 1 must have exactly one master ball/);
  });

  it("canExportMap checks tilesets and war validation", () => {
    const tileData = createEmptyTileData(2, 2);
    tileData.spawn_points[0][0] = 1;
    tileData.spawn_points[1][1] = 2;
    tileData.special_tiles[0][0] = "master_ball_p1";
    tileData.special_tiles[1][1] = "master_ball_p2";

    expect(canExportMap([], [2], tileData).ok).toBe(false);
    expect(canExportMap(["Brick City.png"], [2], tileData).ok).toBe(true);
  });

  it("requires at least one conquest spawn per player", () => {
    const tileData = createEmptyTileData(2, 2);
    tileData.spawn_points[0][0] = 1;
    tileData.special_tiles[0][0] = "master_ball_p1";
    tileData.special_tiles[1][1] = "master_ball_p2";

    const result = validateConquestSpawnExport(tileData, [2]);
    expect(result.ok).toBe(false);
    expect(result.message).toMatch(/Player 2 must have at least one Conquest spawn point/);

    tileData.spawn_points[1][1] = 2;
    expect(validateConquestSpawnExport(tileData, [2]).ok).toBe(true);
  });
});
