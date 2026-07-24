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
});
