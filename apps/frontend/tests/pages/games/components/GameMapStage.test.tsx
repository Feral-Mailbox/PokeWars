import { createRef } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import GameMapStage from "@/pages/games/components/GameMapStage";

vi.mock("@/components/units/UnitIdleSprite", () => ({
  default: ({ overlayColor, outlineOnly }: any) => (
    <div
      data-testid="unit-sprite"
      data-overlay={overlayColor}
      data-outline={outlineOnly ? "1" : "0"}
    />
  ),
}));

vi.mock("@/hooks/useMapItemRenderer", () => ({
  useMapItemRenderer: vi.fn(),
}));
vi.mock("@/hooks/useMapObjectiveRenderer", () => ({
  useMapObjectiveRenderer: vi.fn(),
}));
vi.mock("@/hooks/useOverlay2Renderer", () => ({
  useOverlay2Renderer: vi.fn(),
}));
vi.mock("@/hooks/useOverlay3Renderer", () => ({
  useOverlay3Renderer: vi.fn(),
}));
vi.mock("@/utils/mapTileDrawing", () => ({
  buildOverlay2TileSet: vi.fn((overlay2) => {
    const set = new Set<string>();
    if (!overlay2) return set;
    for (let y = 0; y < overlay2.length; y++) {
      for (let x = 0; x < overlay2[y].length; x++) {
        if (overlay2[y][x]) set.add(`${x},${y}`);
      }
    }
    return set;
  }),
}));

describe("GameMapStage", () => {
  function renderStage(overrides: Record<string, unknown> = {}) {
    const canvasRef = createRef<HTMLCanvasElement>();
    const overlayRef = createRef<HTMLCanvasElement>();
    const overlay2Ref = createRef<HTMLCanvasElement>();
    const overlay3Ref = createRef<HTMLCanvasElement>();
    const mapStageRef = createRef<HTMLDivElement>();
    const itemsCanvasRef = createRef<HTMLCanvasElement>();
    const objectivesCanvasRef = createRef<HTMLCanvasElement>();

    const onUnitClick = vi.fn();
    const onUnitMouseEnter = vi.fn();
    const onUnitMouseLeave = vi.fn();
    const onMapItemHover = vi.fn();
    const onMapItemLeave = vi.fn();

    render(
      <GameMapStage
        mapWidth={64}
        mapHeight={64}
        displayScale={1}
        mapRenderData={{
          width: 2,
          height: 2,
          tileset_names: ["a.png"],
          tile_data: {
            base: [
              [
                [0, 0],
                [0, 0],
              ],
              [
                [0, 0],
                [0, 0],
              ],
            ],
            overlay: [
              [null, null],
              [null, null],
            ],
            overlay2: [
              [[1, 0], null],
              [null, null],
            ],
          },
        }}
        canvasRef={canvasRef}
        overlayRef={overlayRef}
        overlay2Ref={overlay2Ref}
        overlay3Ref={overlay3Ref}
        mapStageRef={mapStageRef}
        overlayPointerEventsEnabled
        placedUnits={[
          {
            id: 1,
            unit: { asset_folder: "025_pikachu" },
            tile: [0, 0],
            current_hp: 22,
            user_id: 7,
            can_move: true,
          },
          {
            id: 2,
            unit: { asset_folder: "007_squirtle" },
            tile: [1, 0],
            current_hp: 10,
            user_id: 8,
            can_move: false,
          },
        ]}
        tileDrawSize={32}
        moveTargeting={false}
        getPlayerColor={() => "#00FF0080"}
        onSpriteFrameSize={() => {}}
        onUnitMouseEnter={onUnitMouseEnter}
        onUnitMouseLeave={onUnitMouseLeave}
        onUnitClick={onUnitClick}
        itemsCanvasRef={itemsCanvasRef}
        itemIdTiles={[
          [5, null],
          [null, 6],
        ]}
        itemMoveTypeById={{ 5: "Fire", 6: "Water" }}
        objectivesCanvasRef={objectivesCanvasRef}
        objectiveTiles={[[{ kind: "pokeball", owner: 1, hp: 20, max_hp: 20 }]]}
        showMapItemTooltips
        onMapItemHover={onMapItemHover}
        onMapItemLeave={onMapItemLeave}
        {...overrides}
      />
    );

    return {
      onUnitClick,
      onUnitMouseEnter,
      onUnitMouseLeave,
      onMapItemHover,
      onMapItemLeave,
    };
  }

  it("does not draw jailed units on the map", () => {
    renderStage({
      placedUnits: [
        {
          id: 4,
          unit: { asset_folder: "098_lanturn" },
          tile: [0, 0],
          current_hp: 155,
          user_id: 7,
          can_move: false,
          jailed: true,
        },
      ],
    });
    expect(screen.queryAllByTestId("unit-sprite")).toHaveLength(0);
    expect(screen.queryByText("155")).not.toBeInTheDocument();
  });

  it("keeps rendering when a placed unit has no catalog object", () => {
    renderStage({
      placedUnits: [
        {
          id: 3,
          unit: undefined,
          tile: [0, 1],
          current_hp: 40,
          user_id: 7,
          can_move: true,
        },
      ],
    });
    expect(document.getElementById("mapCanvas")).toBeTruthy();
    expect(screen.queryAllByTestId("unit-sprite")).toHaveLength(0);
    expect(screen.getByText("40")).toBeInTheDocument();
  });

  it("renders map canvases, units, and health", () => {
    renderStage();
    expect(document.getElementById("mapCanvas")).toBeTruthy();
    expect(document.getElementById("itemsCanvas")).toBeTruthy();
    expect(document.getElementById("objectivesCanvas")).toBeTruthy();
    expect(screen.getAllByTestId("unit-sprite")).toHaveLength(2);
    expect(screen.getByText("22")).toBeInTheDocument();
    expect(screen.getByText("10")).toBeInTheDocument();

    const sprites = screen.getAllByTestId("unit-sprite");
    expect(sprites[0]).toHaveAttribute("data-outline", "1");
    expect(sprites[1]).toHaveAttribute("data-overlay", "#777777");
  });

  it("handles unit and map-item pointer interactions", async () => {
    const user = userEvent.setup();
    const handlers = renderStage();

    const unitNodes = document.querySelectorAll("[data-unit]");
    await user.hover(unitNodes[1]);
    expect(handlers.onUnitMouseEnter).toHaveBeenCalled();
    await user.click(unitNodes[1]);
    expect(handlers.onUnitClick).toHaveBeenCalled();
    await user.unhover(unitNodes[1]);
    expect(handlers.onUnitMouseLeave).toHaveBeenCalled();

    // Item at (1,1) is free; item at (0,0) is occupied by a unit and skipped.
    const itemHits = Array.from(document.querySelectorAll("div")).filter(
      (el) => (el as HTMLElement).style.cursor === "help"
    );
    expect(itemHits.length).toBeGreaterThan(0);
    await user.hover(itemHits[0]);
    expect(handlers.onMapItemHover).toHaveBeenCalled();
    await user.unhover(itemHits[0]);
    expect(handlers.onMapItemLeave).toHaveBeenCalled();
  });

  it("disables item and unit interactions while targeting moves", () => {
    renderStage({
      moveTargeting: true,
      placedUnits: [
        {
          id: 3,
          unit: { asset_folder: "001_bulbasaur" },
          tile: [1, 1],
          current_hp: undefined,
          user_id: 7,
        },
      ],
      itemIdTiles: [[null, 5]],
    });

    expect(screen.getByText("?")).toBeInTheDocument();
    expect(document.querySelector("[data-unit]")).toHaveStyle({ pointerEvents: "none", cursor: "default" });
    const itemHit = Array.from(document.querySelectorAll("div")).find(
      (element) => (element as HTMLElement).style.cursor === "help",
    );
    expect(itemHit).toHaveStyle({ pointerEvents: "none" });
  });

  it("outlines units behind titanic sprites above the occluder", () => {
    renderStage({
      mapRenderData: {
        width: 3,
        height: 4,
        tileset_names: ["a.png"],
        tile_data: {
          base: [
            [[0, 0], [0, 0], [0, 0]],
            [[0, 0], [0, 0], [0, 0]],
            [[0, 0], [0, 0], [0, 0]],
            [[0, 0], [0, 0], [0, 0]],
          ],
          overlay: [
            [null, null, null],
            [null, null, null],
            [null, null, null],
            [null, null, null],
          ],
          overlay2: [
            [null, null, null],
            [null, null, null],
            [null, null, null],
            [null, null, null],
          ],
        },
      },
      placedUnits: [
        {
          id: 1,
          unit: {
            asset_folder: "025_pikachu",
            is_titanic: false,
          },
          tile: [1, 1],
          current_hp: 35,
          user_id: 7,
          can_move: true,
        },
        {
          id: 2,
          unit: {
            asset_folder: "130_gyarados",
            is_titanic: true,
            titanic_footprint: { north: 3, west: 1, east: 1 },
          },
          tile: [1, 3],
          current_hp: 95,
          user_id: 8,
          can_move: true,
        },
      ],
    });

    const unitNodes = Array.from(document.querySelectorAll("[data-unit]")) as HTMLElement[];
    expect(unitNodes).toHaveLength(2);
    const behind = unitNodes.find((node) => node.getAttribute("data-tile-y") === "1")!;
    const titanic = unitNodes.find((node) => node.getAttribute("data-tile-y") === "3")!;
    expect(behind.querySelector("[data-testid='unit-sprite']")).toHaveAttribute(
      "data-outline",
      "1"
    );
    expect(titanic.querySelector("[data-testid='unit-sprite']")).toHaveAttribute(
      "data-outline",
      "0"
    );
    expect(Number(behind.style.zIndex)).toBeGreaterThan(Number(titanic.style.zIndex));
  });

  it("keeps full sprites for titanic units behind other titanics", () => {
    renderStage({
      mapRenderData: {
        width: 3,
        height: 4,
        tileset_names: ["a.png"],
        tile_data: {
          base: [
            [[0, 0], [0, 0], [0, 0]],
            [[0, 0], [0, 0], [0, 0]],
            [[0, 0], [0, 0], [0, 0]],
            [[0, 0], [0, 0], [0, 0]],
          ],
          overlay: [
            [null, null, null],
            [null, null, null],
            [null, null, null],
            [null, null, null],
          ],
          overlay2: [
            [null, null, null],
            [null, null, null],
            [null, null, null],
            [null, null, null],
          ],
        },
      },
      placedUnits: [
        {
          id: 1,
          unit: {
            asset_folder: "130_gyarados",
            is_titanic: true,
            titanic_footprint: { north: 3, west: 1, east: 1 },
          },
          tile: [1, 1],
          current_hp: 155,
          user_id: 7,
          can_move: true,
        },
        {
          id: 2,
          unit: {
            asset_folder: "130_gyarados",
            is_titanic: true,
            titanic_footprint: { north: 3, west: 1, east: 1 },
          },
          tile: [1, 3],
          current_hp: 155,
          user_id: 8,
          can_move: true,
        },
      ],
    });

    const unitNodes = Array.from(document.querySelectorAll("[data-unit]")) as HTMLElement[];
    const rear = unitNodes.find((node) => node.getAttribute("data-tile-y") === "1")!;
    const front = unitNodes.find((node) => node.getAttribute("data-tile-y") === "3")!;
    expect(rear.querySelector("[data-testid='unit-sprite']")).toHaveAttribute("data-outline", "0");
    expect(front.querySelector("[data-testid='unit-sprite']")).toHaveAttribute("data-outline", "0");
    expect(Number(rear.style.zIndex)).toBeLessThan(Number(front.style.zIndex));
  });

  it("stacks southern units above northern ones and keeps HP above sprites", () => {
    renderStage({
      mapRenderData: {
        width: 2,
        height: 3,
        tileset_names: ["a.png"],
        tile_data: {
          base: [
            [[0, 0], [0, 0]],
            [[0, 0], [0, 0]],
            [[0, 0], [0, 0]],
          ],
          overlay: [
            [null, null],
            [null, null],
            [null, null],
          ],
          overlay2: [
            [null, null],
            [null, null],
            [null, null],
          ],
        },
      },
      // Intentionally reverse of Y order: northern unit listed last (would formerly paint on top).
      placedUnits: [
        {
          id: 20,
          unit: { asset_folder: "big_tyrantrum" },
          tile: [0, 2],
          current_hp: 142,
          user_id: 7,
        },
        {
          id: 10,
          unit: { asset_folder: "small_victini" },
          tile: [0, 0],
          current_hp: 160,
          user_id: 8,
        },
      ],
    });

    const unitNodes = Array.from(document.querySelectorAll("[data-unit]")) as HTMLElement[];
    expect(unitNodes).toHaveLength(2);
    expect(unitNodes.map((node) => node.getAttribute("data-tile-y"))).toEqual(["0", "2"]);
    expect(Number(unitNodes[0].style.zIndex)).toBeLessThan(Number(unitNodes[1].style.zIndex));

    const hpNodes = Array.from(document.querySelectorAll("[data-unit-hp]")) as HTMLElement[];
    expect(hpNodes).toHaveLength(2);
    for (const hp of hpNodes) {
      expect(Number(hp.style.zIndex)).toBeGreaterThan(Number(unitNodes[1].style.zIndex));
    }
  });

  it("renders without optional item and objective canvases", () => {
    renderStage({
      mapWidth: 0,
      mapHeight: 0,
      itemsCanvasRef: undefined,
      objectivesCanvasRef: undefined,
      showMapItemTooltips: false,
      placedUnits: [],
    });
    expect(document.getElementById("itemsCanvas")).toBeNull();
    expect(document.getElementById("objectivesCanvas")).toBeNull();
  });
});
