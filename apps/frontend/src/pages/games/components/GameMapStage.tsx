import { useLayoutEffect, useMemo } from "react";
import UnitIdleSprite from "@/components/units/UnitIdleSprite";
import { useMapItemRenderer } from "@/hooks/useMapItemRenderer";
import {
  useMapObjectiveRenderer,
  type ObjectiveTileState,
} from "@/hooks/useMapObjectiveRenderer";
import { useOverlay2Renderer } from "@/hooks/useOverlay2Renderer";
import { useOverlay3Renderer } from "@/hooks/useOverlay3Renderer";
import { buildOverlay2TileSet } from "@/utils/mapTileDrawing";
import { setupPixelCanvas } from "@/utils/pixelCanvas";
import { buildTitanicOcclusionMap } from "@/utils/titanicOcclusion";

type PlacedUnit = {
  id?: number;
  unit: any;
  tile: [number, number];
  current_hp: number;
  user_id: number;
  can_move?: boolean;
  jailed?: boolean;
};

type MapRenderData = {
  width: number;
  height: number;
  tileset_names: string[];
  tile_data: {
    base: [number, number][][];
    overlay: ([number, number] | null)[][];
    overlay2?: ([number, number] | null)[][];
    overlay3?: ([number, number] | null)[][];
  };
};

type GameMapStageProps = {
  mapWidth: number;
  mapHeight: number;
  displayScale?: number;
  mapRenderData?: MapRenderData | null;
  canvasRef: any;
  overlayRef: any;
  overlay2Ref: any;
  overlay3Ref: any;
  mapStageRef: any;
  overlayPointerEventsEnabled: boolean;
  placedUnits: PlacedUnit[];
  tileDrawSize: number;
  moveTargeting: boolean;
  getPlayerColor: (playerId: number) => string;
  onSpriteFrameSize?: (frame: [number, number]) => void;
  onUnitMouseEnter: (unitState: PlacedUnit) => void;
  onUnitMouseLeave: (unitState: PlacedUnit) => void;
  onUnitClick: (unitState: PlacedUnit) => void;
  itemsCanvasRef?: any;
  itemIdTiles?: (number | null)[][] | null;
  itemMoveTypeById?: Record<number, string>;
  objectivesCanvasRef?: any;
  objectiveTiles?: (ObjectiveTileState | null)[][] | null;
  objectiveSelectedTile?: [number, number] | null;
  playerOrder?: number[];
  showMapItemTooltips?: boolean;
  onMapItemHover?: (itemId: number, clientX: number, clientY: number) => void;
  onMapItemLeave?: () => void;
  jailTiles?: { x: number; y: number; owner: number }[];
  onJailHover?: (
    jail: { x: number; y: number; owner: number },
    clientX: number,
    clientY: number
  ) => void;
  onJailLeave?: () => void;
};

const pixelatedCanvasStyle = { imageRendering: "pixelated" as const };

export default function GameMapStage({
  mapWidth,
  mapHeight,
  displayScale = 1,
  mapRenderData,
  canvasRef,
  overlayRef,
  overlay2Ref,
  overlay3Ref,
  mapStageRef,
  overlayPointerEventsEnabled,
  placedUnits,
  tileDrawSize,
  moveTargeting,
  getPlayerColor,
  onSpriteFrameSize,
  onUnitMouseEnter,
  onUnitMouseLeave,
  onUnitClick,
  itemsCanvasRef,
  itemIdTiles,
  itemMoveTypeById = {},
  objectivesCanvasRef,
  objectiveTiles,
  objectiveSelectedTile = null,
  playerOrder = [],
  showMapItemTooltips = false,
  onMapItemHover,
  onMapItemLeave,
  jailTiles = [],
  onJailHover,
  onJailLeave,
}: GameMapStageProps) {
  const overlay2TileSet = useMemo(
    () => buildOverlay2TileSet(mapRenderData?.tile_data.overlay2),
    [mapRenderData?.tile_data.overlay2]
  );

  const mapUnits = useMemo(
    () => placedUnits.filter((unit) => !unit.jailed),
    [placedUnits]
  );

  // Titanic sprites spill north/sideways; tiles they cover need outline-on-top.
  const titanicOcclusion = useMemo(
    () => buildTitanicOcclusionMap(mapUnits),
    [mapUnits]
  );

  // Painter's algorithm: lower tile Y draws first so southern (higher-Y) sprites
  // cover northern ones when tall sprites spill across tile bounds.
  const sortedMapUnits = useMemo(() => {
    return [...mapUnits].sort((a, b) => {
      const dy = a.tile[1] - b.tile[1];
      if (dy !== 0) return dy;
      const dx = a.tile[0] - b.tile[0];
      if (dx !== 0) return dx;
      return Number(a.id ?? 0) - Number(b.id ?? 0);
    });
  }, [mapUnits]);

  const occupiedTileKeys = useMemo(() => {
    const keys = new Set<string>();
    for (const unit of mapUnits) {
      keys.add(`${unit.tile[0]},${unit.tile[1]}`);
    }
    return keys;
  }, [mapUnits]);

  useLayoutEffect(() => {
    if (!mapWidth || !mapHeight) return;
    if (canvasRef.current) setupPixelCanvas(canvasRef.current, mapWidth, mapHeight);
    if (itemsCanvasRef?.current) setupPixelCanvas(itemsCanvasRef.current, mapWidth, mapHeight);
    if (objectivesCanvasRef?.current) {
      setupPixelCanvas(objectivesCanvasRef.current, mapWidth, mapHeight);
    }
    if (overlayRef.current) setupPixelCanvas(overlayRef.current, mapWidth, mapHeight);
    if (overlay2Ref.current) setupPixelCanvas(overlay2Ref.current, mapWidth, mapHeight);
    if (overlay3Ref.current) setupPixelCanvas(overlay3Ref.current, mapWidth, mapHeight);
  }, [mapWidth, mapHeight, canvasRef, itemsCanvasRef, objectivesCanvasRef, overlayRef, overlay2Ref, overlay3Ref]);

  useMapItemRenderer(
    itemsCanvasRef,
    mapWidth,
    mapHeight,
    itemIdTiles,
    itemMoveTypeById
  );

  useMapObjectiveRenderer(
    objectivesCanvasRef,
    mapWidth,
    mapHeight,
    objectiveTiles,
    {
      selectedTile: objectiveSelectedTile,
      playerOrder,
      getPlayerColor,
    }
  );

  useOverlay2Renderer(overlay2Ref, mapRenderData);
  useOverlay3Renderer(overlay3Ref, mapRenderData);

  const scaledWidth = mapWidth * displayScale;
  const scaledHeight = mapHeight * displayScale;

  const isBehindOverlay2 = (tile: [number, number]) =>
    overlay2TileSet.has(`${tile[0]},${tile[1]}`);

  const renderUnit = (unitState: PlacedUnit) => {
    const { id, unit, tile, user_id, can_move } = unitState;
    const behindOverlay2 = isBehindOverlay2(tile);
    const titanicOccluderY = titanicOcclusion.get(`${tile[0]},${tile[1]}`);
    const behindTitanic = titanicOccluderY !== undefined;
    const isTitanic = Boolean(unit?.is_titanic);
    // Titanic-behind-titanic keeps a full sprite (Y-sort stacks it under the southern one).
    // Normal units behind a titanic use the team-colored outline on top of the occluder.
    const outlineOnly = behindOverlay2 || (behindTitanic && !isTitanic);
    const playerColor = can_move === false ? "#777777" : getPlayerColor(user_id);
    // Overlay2 silhouettes stay under trees (z≈3). Titanic occlusion outlines sit
    // just above the occluder so they read on top of the large sprite. Otherwise
    // use Y-based z-index so southern tiles stack above northern ones.
    let zIndex = 100 + tile[1];
    if (behindOverlay2) {
      zIndex = 3;
    } else if (behindTitanic && !isTitanic) {
      zIndex = 100 + titanicOccluderY + 1;
    }

    return (
      <div
        key={`${id}-${tile[0]}-${tile[1]}`}
        data-unit
        data-tile-y={tile[1]}
        onMouseEnter={() => onUnitMouseEnter(unitState)}
        onMouseLeave={() => onUnitMouseLeave(unitState)}
        onClick={() => onUnitClick(unitState)}
        style={{
          position: "absolute",
          left: tile[0] * tileDrawSize,
          top: tile[1] * tileDrawSize,
          width: tileDrawSize,
          height: tileDrawSize,
          zIndex,
          pointerEvents: moveTargeting ? "none" : "auto",
          cursor: moveTargeting ? "default" : "pointer",
        }}
      >
        <div style={{ position: "relative", width: "100%", height: "100%", pointerEvents: "none" }}>
          {unit?.asset_folder ? (
            <UnitIdleSprite
              key={outlineOnly ? "outline" : "sprite"}
              assetFolder={unit.asset_folder}
              onFrameSize={onSpriteFrameSize}
              isMapPlacement
              overlayColor={playerColor}
              outlineOnly={outlineOnly}
            />
          ) : null}
        </div>
      </div>
    );
  };

  const renderUnitHealth = (unitState: PlacedUnit) => {
    const { id, tile, current_hp } = unitState;

    return (
      <div
        key={`hp-${id}-${tile[0]}-${tile[1]}`}
        data-unit-hp
        style={{
          position: "absolute",
          left: tile[0] * tileDrawSize,
          top: tile[1] * tileDrawSize,
          width: tileDrawSize,
          height: tileDrawSize,
          // Always above every unit sprite band (100 + y).
          zIndex: 1000,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            position: "absolute",
            bottom: 1,
            right: 2,
            fontSize: "10px",
            color: "white",
            fontWeight: 600,
            pointerEvents: "none",
            textShadow: `
              -1px -1px 0 #000,
              1px -1px 0 #000,
              -1px  1px 0 #000,
              1px  1px 0 #000
            `,
          }}
        >
          {current_hp ?? "?"}
        </div>
      </div>
    );
  };

  return (
    <div className="shrink-0" style={{ width: scaledWidth, height: scaledHeight }}>
      <div
        ref={mapStageRef}
        className="relative"
        style={{
          transform: `scale(${displayScale})`,
          transformOrigin: "top left",
          width: mapWidth,
          height: mapHeight,
        }}
      >
        <canvas ref={canvasRef} id="mapCanvas" style={pixelatedCanvasStyle} />

        {objectivesCanvasRef && (
          <canvas
            ref={objectivesCanvasRef}
            id="objectivesCanvas"
            style={{
              ...pixelatedCanvasStyle,
              position: "absolute",
              top: 0,
              left: 0,
              zIndex: 1,
              pointerEvents: "none",
            }}
          />
        )}

        {itemsCanvasRef && (
          <canvas
            ref={itemsCanvasRef}
            id="itemsCanvas"
            style={{
              ...pixelatedCanvasStyle,
              position: "absolute",
              top: 0,
              left: 0,
              zIndex: 1,
              pointerEvents: "none",
            }}
          />
        )}

        {sortedMapUnits.map((unitState) => renderUnit(unitState))}

        {showMapItemTooltips &&
          itemIdTiles?.map((row, y) =>
            row.map((itemId, x) => {
              if (itemId == null) return null;
              if (occupiedTileKeys.has(`${x},${y}`)) return null;
              return (
                <div
                  key={`map-item-hit-${x}-${y}`}
                  style={{
                    position: "absolute",
                    left: x * tileDrawSize,
                    top: y * tileDrawSize,
                    width: tileDrawSize,
                    height: tileDrawSize,
                    zIndex: 3,
                    pointerEvents: moveTargeting ? "none" : "auto",
                    cursor: "help",
                  }}
                  onMouseEnter={(e) => onMapItemHover?.(itemId, e.clientX, e.clientY)}
                  onMouseMove={(e) => onMapItemHover?.(itemId, e.clientX, e.clientY)}
                  onMouseLeave={() => onMapItemLeave?.()}
                />
              );
            })
          )}

        {jailTiles.map((jail) => (
          <div
            key={`jail-hit-${jail.x}-${jail.y}`}
            style={{
              position: "absolute",
              left: jail.x * tileDrawSize,
              top: jail.y * tileDrawSize,
              width: tileDrawSize,
              height: tileDrawSize,
              zIndex: 4,
              pointerEvents: moveTargeting ? "none" : "auto",
              cursor: "help",
            }}
            onMouseEnter={(e) => onJailHover?.(jail, e.clientX, e.clientY)}
            onMouseMove={(e) => onJailHover?.(jail, e.clientX, e.clientY)}
            onMouseLeave={() => onJailLeave?.()}
          />
        ))}

        <canvas
          ref={overlay2Ref}
          id="overlay2Canvas"
          style={{
            ...pixelatedCanvasStyle,
            position: "absolute",
            top: 0,
            left: 0,
            zIndex: 2,
            pointerEvents: "none",
          }}
        />

        <canvas
          ref={overlay3Ref}
          id="overlay3Canvas"
          style={{
            ...pixelatedCanvasStyle,
            position: "absolute",
            top: 0,
            left: 0,
            zIndex: 4,
            pointerEvents: "none",
          }}
        />

        {sortedMapUnits.map((unitState) => renderUnitHealth(unitState))}

        <canvas
          ref={overlayRef}
          id="overlayCanvas"
          style={{
            ...pixelatedCanvasStyle,
            position: "absolute",
            top: 0,
            left: 0,
            zIndex: 1100,
            pointerEvents: overlayPointerEventsEnabled ? "auto" : "none",
          }}
        />
      </div>
    </div>
  );
}
