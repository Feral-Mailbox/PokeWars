import { describe, expect, it } from "vitest";
import {
  buildMovementCostGrid,
  canEnterTile,
  filterMovementTilesForUnit,
  findShortestPath,
  getMovementRangeWithTerrain,
  getSpecialTile,
  IMPASSABLE_TILE,
  IMPOSSIBLE_MOVEMENT_COST,
  isIceTile,
  isLedgeTile,
  isRockTile,
  isSandTile,
  isValidMovementDestination,
  isWaterTile,
  LEDGE_DOWN,
  LEDGE_LEFT,
  LEDGE_RIGHT,
  LEDGE_UP,
  ledgeAllowsEntry,
  normalizeSpecialTile,
  resolveMovementDestination,
  ROCK_TILE,
  SAND_MOVEMENT_COST,
  SAND_TILE,
  slideOnIceFrom,
  unitCanCrossRock,
  unitCanCrossWater,
  unitCanOccupyTile,
  unitCanPassThroughUnits,
  unitCanStandOnLedge,
  unitHasLevitate,
  unitIgnoresIceSlide,
  unitIgnoresSandSlow,
  WATER_TILE,
  ICE_TILE,
} from "@/utils/mapMovement";

describe("mapMovement", () => {
  const special = [
    [null, WATER_TILE, ROCK_TILE],
    [SAND_TILE, ICE_TILE, LEDGE_UP],
    [LEDGE_DOWN, LEDGE_LEFT, LEDGE_RIGHT],
  ];

  it("normalizes and reads special tiles", () => {
    expect(normalizeSpecialTile(null)).toBeNull();
    expect(normalizeSpecialTile(" Water ")).toBe("water");
    expect(normalizeSpecialTile(12)).toBeNull();
    expect(getSpecialTile(null, 0, 0)).toBeNull();
    expect(getSpecialTile(special, 1, 0)).toBe(WATER_TILE);
    expect(isWaterTile(special, 1, 0)).toBe(true);
    expect(isRockTile(special, 2, 0)).toBe(true);
    expect(isSandTile(special, 0, 1)).toBe(true);
    expect(isIceTile(special, 1, 1)).toBe(true);
    expect(isLedgeTile(special, 2, 1)).toBe(true);
  });

  it("applies type/ability movement permissions", () => {
    expect(unitHasLevitate(["normal"], ["Levitate"])).toBe(true);
    expect(unitCanCrossWater(["Water"], [])).toBe(true);
    expect(unitCanCrossWater(["normal"], ["levitate"])).toBe(true);
    expect(unitCanCrossWater(["fire"], [])).toBe(false);
    expect(unitCanCrossRock(["Flying"], [])).toBe(true);
    expect(unitCanCrossRock(["rock"], [])).toBe(true);
    expect(unitCanStandOnLedge(["flying"], [])).toBe(true);
    expect(unitCanStandOnLedge(["normal"], [])).toBe(false);
    expect(unitCanPassThroughUnits(["Ghost"])).toBe(true);
    expect(unitIgnoresSandSlow(["ground"], [])).toBe(true);
    expect(unitIgnoresIceSlide(["ice"], [])).toBe(true);
  });

  it("enforces ledge entry directions", () => {
    expect(ledgeAllowsEntry(LEDGE_UP, 1, 2, 1, 1)).toBe(true);
    expect(ledgeAllowsEntry(LEDGE_DOWN, 1, 1, 1, 2)).toBe(true);
    expect(ledgeAllowsEntry(LEDGE_LEFT, 2, 1, 1, 1)).toBe(true);
    expect(ledgeAllowsEntry(LEDGE_RIGHT, 1, 1, 2, 1)).toBe(true);
    expect(ledgeAllowsEntry(LEDGE_UP, 1, 1, 1, 2)).toBe(false);
    expect(ledgeAllowsEntry("grass", 0, 0, 0, 1)).toBe(false);
  });

  it("builds cost grids and occupy checks for terrain", () => {
    const base = [
      [1, 1, 1],
      [1, 1, 1],
      [1, 1, 1],
    ];
    const withImpassable = [
      [null, WATER_TILE, IMPASSABLE_TILE],
      [SAND_TILE, null, LEDGE_UP],
      [null, null, null],
    ];

    const groundCosts = buildMovementCostGrid(base, withImpassable, ["normal"], []);
    expect(groundCosts[0][1]).toBe(IMPOSSIBLE_MOVEMENT_COST);
    expect(groundCosts[0][2]).toBe(IMPOSSIBLE_MOVEMENT_COST);
    expect(groundCosts[1][0]).toBe(SAND_MOVEMENT_COST);
    expect(groundCosts[1][2]).toBe(0);

    const flyerCosts = buildMovementCostGrid(base, withImpassable, ["flying"], []);
    expect(flyerCosts[0][1]).toBe(1);
    expect(flyerCosts[1][0]).toBe(1);

    expect(unitCanOccupyTile(withImpassable, 0, 2, ["normal"], [])).toBe(true);
    expect(unitCanOccupyTile(withImpassable, 1, 0, ["normal"], [])).toBe(false);
    expect(unitCanOccupyTile(withImpassable, 2, 0, ["normal"], [])).toBe(false);
  });

  it("finds shortest paths and movement ranges on tiny grids", () => {
    const costs = [
      [1, 1, 1],
      [1, IMPOSSIBLE_MOVEMENT_COST, 1],
      [1, 1, 1],
    ];
    const tiles = [
      [null, null, null],
      [null, ROCK_TILE, null],
      [null, null, null],
    ];

    expect(findShortestPath([0, 0], [0, 0], costs, tiles, 3, 3, ["normal"])).toEqual([
      [0, 0],
    ]);
    expect(findShortestPath([0, 0], [2, 0], costs, tiles, 3, 3, ["normal"])).toEqual([
      [0, 0],
      [1, 0],
      [2, 0],
    ]);
    expect(findShortestPath([0, 0], [1, 1], costs, tiles, 3, 3, ["normal"])).toBeNull();

    const range = getMovementRangeWithTerrain(
      [0, 0],
      1,
      [
        [1, 1],
        [1, 1],
      ],
      [
        [null, null],
        [null, null],
      ],
      2,
      2,
      ["normal"]
    );
    expect(range).toEqual(
      expect.arrayContaining([
        [0, 0],
        [1, 0],
        [0, 1],
      ])
    );
  });

  it("slides on ice and resolves destinations", () => {
    const iceRow = [
      [null, ICE_TILE, ICE_TILE, null],
    ];
    const costs = [[1, 1, 1, 1]];

    expect(
      slideOnIceFrom(1, 0, 1, 0, iceRow, 4, 1, ["normal"], [], new Set())
    ).toEqual([3, 0]);

    expect(
      resolveMovementDestination(
        0,
        0,
        1,
        0,
        costs,
        iceRow,
        4,
        1,
        ["ice"],
        []
      )
    ).toEqual({ x: 1, y: 0, slid: false });

    const slid = resolveMovementDestination(
      0,
      0,
      1,
      0,
      costs,
      iceRow,
      4,
      1,
      ["normal"],
      []
    );
    expect(slid.slid).toBe(true);
    expect(slid.x).toBe(3);
  });

  it("filters invalid stop tiles and ledge entry", () => {
    const tiles = [
      [LEDGE_UP, null],
      [null, null],
    ];
    expect(canEnterTile(tiles, 0, 1, 0, 0, ["normal"], [])).toBe(true);
    expect(canEnterTile(tiles, 1, 0, 0, 0, ["normal"], [])).toBe(false);
    expect(isValidMovementDestination(tiles, 0, 0, ["normal"], [])).toBe(false);
    expect(
      filterMovementTilesForUnit(
        [
          [0, 0],
          [1, 0],
        ],
        tiles,
        ["normal"],
        []
      )
    ).toEqual([[1, 0]]);
  });

  it("handles bounds, blocked paths, and terrain edge cases", () => {
    expect(getSpecialTile([[null]], -1, 0)).toBeNull();
    expect(getSpecialTile([null as unknown as unknown[]], 0, 0)).toBeNull();
    expect(buildMovementCostGrid([[3]], null, ["normal"])).toEqual([[3]]);
    expect(filterMovementTilesForUnit([[0, 0]], null, ["normal"])).toEqual([[0, 0]]);

    expect(
      findShortestPath(
        [0, 0],
        [1, 0],
        [[1, 1]],
        [[null, null]],
        2,
        1,
        ["normal"],
        [],
        new Set(["1,0"])
      )
    ).toBeNull();
    expect(
      slideOnIceFrom(0, 0, 1, 0, [[ICE_TILE, null]], 2, 1, ["normal"], [], new Set(["1,0"]))
    ).toEqual([0, 0]);
    expect(
      slideOnIceFrom(0, 0, 1, 0, [[ICE_TILE, WATER_TILE]], 2, 1, ["normal"])
    ).toEqual([0, 0]);
    expect(
      resolveMovementDestination(0, 0, 1, 0, [[1, IMPOSSIBLE_MOVEMENT_COST]], [[null, null]], 2, 1, ["normal"])
    ).toEqual({ x: 1, y: 0, slid: false });
    expect(
      resolveMovementDestination(0, 0, 1, 0, [[1, 1]], [[null, null]], 2, 1, ["normal"])
    ).toEqual({ x: 1, y: 0, slid: false });
    expect(unitCanOccupyTile([[LEDGE_UP]], 0, 0, ["flying"], [])).toBe(true);
    expect(unitCanOccupyTile([[ROCK_TILE]], 0, 0, ["flying"], [])).toBe(true);
  });
});
