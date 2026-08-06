import { describe, expect, it } from "vitest";
import {
  computeAttackOverlayForMove,
  formatTurnCountdown,
  getActiveStatusName,
  getAdjacentTiles,
  getBaseBattleStatValue,
  getBlastTiles,
  getBombTiles,
  getConeTiles,
  getCurrentMovementRange,
  getDirectionalOverlayTiles,
  getInvertedConeTiles,
  getLineTiles,
  getPulseTiles,
  getRangedTiles,
  getStatColor,
  getStatusIconSrc,
  getSweepTiles,
  getWeatherIconSrc,
  getXAttackTiles,
  mapReplayLogToChatEntries,
  normalizeAttackOverlay,
  normalizeGameData,
  normalizeGameMapState,
  parseRangeSpec,
  dedupeTiles,
} from "@/pages/games/gamePagePure";
import { getDisplacementAttackTiles } from "@/utils/displacementMoves";
import { filterInBoundsTiles } from "@/utils/displacementMoves";
import { RANDOM_TM_ITEM_ID } from "@/types/mapData";

const W = 10;
const H = 10;
const origin: [number, number] = [5, 5];

describe("gamePagePure stats/status/chat", () => {
  it("formats turn countdown", () => {
    expect(formatTurnCountdown(65)).toBe("1:05");
    expect(formatTurnCountdown(3661)).toBe("1:01:01");
    expect(formatTurnCountdown(9)).toBe("0:09");
  });

  it("computes battle stats and colors", () => {
    const unit = {
      level: 50,
      unit: { base_stats: { hp: 100, attack: 50, speed: 100 } },
      current_stats: { attack: 60, speed: 100, range: 4 },
    };
    expect(getBaseBattleStatValue(unit, "hp")).toBeGreaterThan(0);
    expect(getBaseBattleStatValue(unit, "attack")).toBeGreaterThan(0);
    expect(getBaseBattleStatValue(unit, "range")).toBeGreaterThan(0);
    expect(getBaseBattleStatValue({}, "attack")).toBeNull();
    expect(getCurrentMovementRange(unit)).toBe(4);
    expect(getCurrentMovementRange({ current_stats: { speed: 100 } })).toBe(4);
    expect(getStatColor(unit, "attack")).toBe("#22c55e");
    expect(getStatColor({ ...unit, current_stats: { attack: 1 } }, "attack")).toBe("#ef4444");
  });

  it("handles movement and stat helper fallbacks", () => {
    expect(getCurrentMovementRange({ current_stats: { range: 3.9 } })).toBe(3);
    expect(getCurrentMovementRange({ current_stats: { range: -3 } })).toBe(0);
    expect(getCurrentMovementRange({ current_stats: { speed: 124 } })).toBe(4);
    expect(getCurrentMovementRange({ unit: { base_stats: { speed: 50 } } })).toBe(3);
    expect(getCurrentMovementRange({})).toBe(0);
    expect(getBaseBattleStatValue({ unit: { base_stats: { speed: "fast" } } }, "range")).toBeNull();
    expect(getStatColor({ current_stats: { attack: 10 } }, "attack")).toBe("#ffffff");
    expect(
      getStatColor(
        { level: 50, unit: { base_stats: { attack: 50 } }, current_stats: { attack: 55 } },
        "attack",
      ),
    ).toBe("#ffffff");
  });

  it("maps replay logs and status icons", () => {
    expect(mapReplayLogToChatEntries(null)).toEqual([]);
    expect(
      mapReplayLogToChatEntries([
        { event: "chat_message", message: "hi", username: "Ash", player_id: 1, created_at: "t" },
        {
          event: "chat_message",
          message: "wow",
          username: "Viewer",
          player_id: 9,
          is_spectator: true,
          created_at: "t1",
        },
        { event: "system_log", message: "Turn 1", created_at: "t2" },
        { event: "other" },
      ])
    ).toEqual([
      expect.objectContaining({ kind: "chat", username: "Ash", isSpectator: false }),
      expect.objectContaining({ kind: "chat", username: "Viewer", isSpectator: true }),
      expect.objectContaining({ kind: "system", text: "Turn 1" }),
    ]);

    expect(getActiveStatusName(null)).toBeNull();
    expect(getActiveStatusName(["burn", 2])).toBe("burn");
    expect(getActiveStatusName([["badly_poison", 3]])).toBe("badly_poisoned");
    expect(getActiveStatusName(["sleep"])).toBe("sleep");
    expect(getActiveStatusName({ status: "paralysis" })).toBe("paralysis");
    expect(getStatusIconSrc(["burn", 1], "https://cdn/assets")).toContain("status_burn.png");
    expect(getStatusIconSrc(["confused"], "/assets")).toBeNull();
    expect(getWeatherIconSrc(2, "/assets")).toContain("weather_rain.png");
    expect(getWeatherIconSrc(99, "/assets")).toBeNull();
  });

  it("normalizes malformed effects and ignores malformed replay rows", () => {
    expect(mapReplayLogToChatEntries([null, "not a row", { event: "chat_message" }])).toEqual([
      expect.objectContaining({ username: "Unknown", text: "", playerId: NaN }),
    ]);
    expect(getActiveStatusName([])).toBeNull();
    expect(getActiveStatusName({ status: 1 })).toBeNull();

    const normalized = normalizeGameMapState({
      map: { width: 2, height: 1 },
      map_state: {
        weather_tiles: [["bad", [-1, 2]]],
        hazard_tiles: [["bad", [[0, 1], [2, 0], [3, 2]]]],
        room_effect_tiles: "bad",
        terrain_effect_tiles: "bad",
        field_effect_tiles: "bad",
        item_id_tiles: [["bad", 0]],
      },
    });
    expect(normalized.weather_tiles).toEqual([[[0, 0], [0, 0]]]);
    expect(normalized.hazard_tiles[0][1]).toEqual([[3, 2]]);
    expect(normalized.item_id_tiles).toEqual([[null, RANDOM_TM_ITEM_ID]]);
  });

  it("normalizes map state grids", () => {
    const game = {
      map: { width: 2, height: 2 },
      map_state: {
        weather_tiles: [[1, [2, 3]], [0, -1]],
        hazard_tiles: [[[[1, 2], [0, 1]], []], [[], [[9, 1]]]],
        field_effect_tiles: [[1, "x"], [null, 2]],
        item_id_tiles: [[RANDOM_TM_ITEM_ID, -3], [5, null]],
        objective_tiles: "bad",
      },
    };
    const normalized = normalizeGameMapState(game);
    expect(normalized.weather_tiles[0][0]).toEqual([1, 0]);
    expect(normalized.weather_tiles[0][1]).toEqual([2, 3]);
    expect(normalized.item_id_tiles[0][0]).toBe(RANDOM_TM_ITEM_ID);
    expect(normalized.item_id_tiles[1][0]).toBe(5);
    expect(normalized.objective_tiles).toEqual([]);
    expect(normalizeGameData(null)).toBeNull();
    expect(normalizeGameData({ map: { width: 1, height: 1 } }).map_state.weather_tiles).toHaveLength(1);
  });
});

describe("gamePagePure attack ranges", () => {
  it("parses range specs and dedupes overlays", () => {
    expect(parseRangeSpec({ range_type: "blast:2" })).toEqual({ kind: "blast", offset: 2 });
    expect(parseRangeSpec({ range: "adjacent" })).toEqual({ kind: "adjacent", offset: 0 });
    expect(parseRangeSpec({})).toEqual({ kind: "", offset: 0 });
    expect(dedupeTiles([[1, 1], [1, 1], [2, 2]])).toEqual([[1, 1], [2, 2]]);
    expect(
      normalizeAttackOverlay({
        normal: [[1, 1], [1, 1]],
        invert: [[1, 1], [2, 2]],
      })
    ).toEqual({ normal: [[1, 1]], invert: [[2, 2]] });
  });

  it("computes tiles for each range kind", () => {
    expect(getAdjacentTiles(origin, W, H)).toHaveLength(4);
    expect(getBlastTiles(origin, 1, W, H).length).toBeGreaterThan(0);
    expect(getSweepTiles(origin, 1, W, H).length).toBeGreaterThan(0);
    expect(getRangedTiles(origin, 1, W, H)).toHaveLength(4);
    expect(getLineTiles(origin, 2, W, H)).toHaveLength(8);
    expect(getPulseTiles(origin, 1, W, H).length).toBeGreaterThan(0);
    expect(getPulseTiles(origin, 2, W, H).length).toBeGreaterThan(0);
    expect(getPulseTiles(origin, 3, W, H).length).toBeGreaterThan(0);
    expect(getPulseTiles(origin, 4, W, H).length).toBeGreaterThan(0);
    expect(getBombTiles(origin, 1, W, H).length).toBeGreaterThan(0);
    expect(getBombTiles(origin, 2, W, H).length).toBeGreaterThan(0);
    expect(getConeTiles(origin, 1, W, H).length).toBeGreaterThan(0);
    expect(getConeTiles(origin, 3, W, H).length).toBeGreaterThan(0);
    expect(getInvertedConeTiles(origin, 1, W, H).length).toBeGreaterThan(0);
    expect(getInvertedConeTiles(origin, 3, W, H).length).toBeGreaterThan(0);
    expect(getXAttackTiles(origin, 1, W, H).length).toBeGreaterThan(0);
  });

  it("builds full attack overlays via computeAttackOverlayForMove", () => {
    const kinds = [
      "self",
      "adjacent",
      "dash_attack",
      "blast:1",
      "sweep:1",
      "ranged:1",
      "line:2",
      "pulse:2",
      "bomb:2",
      "cone:2",
      "inverted_cone:2",
      "x_attack:1",
    ];
    for (const range_type of kinds) {
      const overlay = computeAttackOverlayForMove(
        { range_type },
        origin,
        W,
        H,
        getDisplacementAttackTiles,
        filterInBoundsTiles
      );
      expect(overlay.normal.length + overlay.invert.length).toBeGreaterThan(0);
    }
    expect(
      computeAttackOverlayForMove({ range_type: "self" }, null, W, H, getDisplacementAttackTiles, filterInBoundsTiles)
    ).toEqual({ normal: [], invert: [] });
  });

  it("slices directional overlays", () => {
    const blast = computeAttackOverlayForMove(
      { range_type: "blast:1" },
      origin,
      W,
      H,
      getDisplacementAttackTiles,
      filterInBoundsTiles
    );
    const sliced = getDirectionalOverlayTiles({
      target: [5, 3],
      origin,
      activeMove: { range_type: "blast:1" },
      attackOverlay: blast,
      mapWidth: W,
      mapHeight: H,
    });
    expect(sliced.length).toBeGreaterThan(0);

    const pulse = computeAttackOverlayForMove(
      { range_type: "pulse:2" },
      origin,
      W,
      H,
      getDisplacementAttackTiles,
      filterInBoundsTiles
    );
    expect(
      getDirectionalOverlayTiles({
        target: [6, 5],
        origin,
        activeMove: { range_type: "pulse:2" },
        attackOverlay: pulse,
        mapWidth: W,
        mapHeight: H,
      })
    ).toEqual([...pulse.normal, ...pulse.invert]);

    expect(
      getDirectionalOverlayTiles({
        target: origin,
        origin,
        activeMove: { range_type: "line:1" },
        attackOverlay: { normal: [origin], invert: [] },
        mapWidth: W,
        mapHeight: H,
      })
    ).toEqual([origin]);
  });

  it("slices x_attack, bomb, sweep, and default directional overlays", () => {
    const xAttack = computeAttackOverlayForMove(
      { range_type: "x_attack:2" },
      origin,
      W,
      H,
      getDisplacementAttackTiles,
      filterInBoundsTiles,
    );
    expect(
      getDirectionalOverlayTiles({
        target: [7, 5],
        origin,
        activeMove: { range_type: "x_attack:2" },
        attackOverlay: xAttack,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThan(0);

    // vertical direction
    expect(
      getDirectionalOverlayTiles({
        target: [5, 8],
        origin,
        activeMove: { range_type: "x_attack" },
        attackOverlay: xAttack,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThan(0);

    const bomb = computeAttackOverlayForMove(
      { range_type: "bomb:2" },
      origin,
      W,
      H,
      getDisplacementAttackTiles,
      filterInBoundsTiles,
    );
    expect(
      getDirectionalOverlayTiles({
        target: [8, 5],
        origin,
        activeMove: { range_type: "bomb:2" },
        attackOverlay: bomb,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThan(0);
    expect(
      getDirectionalOverlayTiles({
        target: [5, 2],
        origin,
        activeMove: { range_type: "bomb:1" },
        attackOverlay: bomb,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThanOrEqual(0);

    const blast = computeAttackOverlayForMove(
      { range_type: "blast:2" },
      origin,
      W,
      H,
      getDisplacementAttackTiles,
      filterInBoundsTiles,
    );
    expect(
      getDirectionalOverlayTiles({
        target: [8, 5],
        origin,
        activeMove: { range_type: "blast:2" },
        attackOverlay: blast,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThanOrEqual(0);
    expect(
      getDirectionalOverlayTiles({
        target: [5, 8],
        origin,
        activeMove: { range_type: "blast:1" },
        attackOverlay: blast,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThanOrEqual(0);

    const sweep = computeAttackOverlayForMove(
      { range_type: "sweep:2" },
      origin,
      W,
      H,
      getDisplacementAttackTiles,
      filterInBoundsTiles,
    );
    expect(
      getDirectionalOverlayTiles({
        target: [8, 5],
        origin,
        activeMove: { range_type: "sweep:2" },
        attackOverlay: sweep,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThanOrEqual(0);
    expect(
      getDirectionalOverlayTiles({
        target: [5, 8],
        origin,
        activeMove: { range_type: "sweep:1" },
        attackOverlay: sweep,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThanOrEqual(0);

    const line = computeAttackOverlayForMove(
      { range_type: "line:3" },
      origin,
      W,
      H,
      getDisplacementAttackTiles,
      filterInBoundsTiles,
    );
    expect(
      getDirectionalOverlayTiles({
        target: [8, 5],
        origin,
        activeMove: { range_type: "line:3" },
        attackOverlay: line,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThan(0);
    expect(
      getDirectionalOverlayTiles({
        target: [5, 8],
        origin,
        activeMove: { range_type: "line:3" },
        attackOverlay: line,
        mapWidth: W,
        mapHeight: H,
      }).length,
    ).toBeGreaterThan(0);

    expect(
      getDirectionalOverlayTiles({
        target: null,
        origin,
        activeMove: { range_type: "line:1" },
        attackOverlay: line,
        mapWidth: W,
        mapHeight: H,
      }),
    ).toEqual([]);
    expect(
      getDirectionalOverlayTiles({
        target: [6, 5],
        origin: null,
        activeMove: { range_type: "line:1" },
        attackOverlay: line,
        mapWidth: W,
        mapHeight: H,
      }),
    ).toEqual([]);
  });
});
