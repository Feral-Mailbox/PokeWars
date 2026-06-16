import { useLayoutEffect, useMemo } from "react";
import UnitIdleSprite from "@/components/units/UnitIdleSprite";
import { useOverlay2Renderer } from "@/hooks/useOverlay2Renderer";
import { useOverlay3Renderer } from "@/hooks/useOverlay3Renderer";
import { buildOverlay2TileSet } from "@/utils/mapTileDrawing";
import { setupPixelCanvas } from "@/utils/pixelCanvas";

type PlacedUnit = {
  id?: number;
  unit: any;
  tile: [number, number];
  current_hp: number;
  user_id: number;
  can_move?: boolean;
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
  onSpriteFrameSize: (frame: [number, number]) => void;
  onUnitMouseEnter: (unitState: PlacedUnit) => void;
  onUnitMouseLeave: (unitState: PlacedUnit) => void;
  onUnitClick: (unitState: PlacedUnit) => void;
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
}: GameMapStageProps) {
  const overlay2TileSet = useMemo(
    () => buildOverlay2TileSet(mapRenderData?.tile_data.overlay2),
    [mapRenderData?.tile_data.overlay2]
  );

  useLayoutEffect(() => {
    if (!mapWidth || !mapHeight) return;
    if (canvasRef.current) setupPixelCanvas(canvasRef.current, mapWidth, mapHeight);
    if (overlayRef.current) setupPixelCanvas(overlayRef.current, mapWidth, mapHeight);
    if (overlay2Ref.current) setupPixelCanvas(overlay2Ref.current, mapWidth, mapHeight);
    if (overlay3Ref.current) setupPixelCanvas(overlay3Ref.current, mapWidth, mapHeight);
  }, [mapWidth, mapHeight, canvasRef, overlayRef, overlay2Ref, overlay3Ref]);

  useOverlay2Renderer(overlay2Ref, mapRenderData);
  useOverlay3Renderer(overlay3Ref, mapRenderData);

  const scaledWidth = mapWidth * displayScale;
  const scaledHeight = mapHeight * displayScale;

  const isBehindOverlay2 = (tile: [number, number]) =>
    overlay2TileSet.has(`${tile[0]},${tile[1]}`);

  const renderUnit = (unitState: PlacedUnit) => {
    const { id, unit, tile, user_id, can_move } = unitState;
    const behindOverlay2 = isBehindOverlay2(tile);
    const playerColor = can_move === false ? "#777777" : getPlayerColor(user_id);

    return (
      <div
        key={`${id}-${tile[0]}-${tile[1]}`}
        data-unit
        onMouseEnter={() => onUnitMouseEnter(unitState)}
        onMouseLeave={() => onUnitMouseLeave(unitState)}
        onClick={() => onUnitClick(unitState)}
        style={{
          position: "absolute",
          left: tile[0] * tileDrawSize,
          top: tile[1] * tileDrawSize,
          width: tileDrawSize,
          height: tileDrawSize,
          zIndex: behindOverlay2 ? 3 : 1,
          pointerEvents: moveTargeting ? "none" : "auto",
          cursor: moveTargeting ? "default" : "pointer",
        }}
      >
        <div style={{ position: "relative", width: "100%", height: "100%", pointerEvents: "none" }}>
          <UnitIdleSprite
            key={behindOverlay2 ? "outline" : "sprite"}
            assetFolder={unit.asset_folder}
            onFrameSize={onSpriteFrameSize}
            isMapPlacement
            overlayColor={playerColor}
            outlineOnly={behindOverlay2}
          />
        </div>
      </div>
    );
  };

  const renderUnitHealth = (unitState: PlacedUnit) => {
    const { id, tile, current_hp } = unitState;

    return (
      <div
        key={`hp-${id}-${tile[0]}-${tile[1]}`}
        style={{
          position: "absolute",
          left: tile[0] * tileDrawSize,
          top: tile[1] * tileDrawSize,
          width: tileDrawSize,
          height: tileDrawSize,
          zIndex: 5,
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

        {placedUnits.map((unitState) => renderUnit(unitState))}

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

        {placedUnits.map((unitState) => renderUnitHealth(unitState))}

        <canvas
          ref={overlayRef}
          id="overlayCanvas"
          style={{
            ...pixelatedCanvasStyle,
            position: "absolute",
            top: 0,
            left: 0,
            zIndex: 6,
            pointerEvents: overlayPointerEventsEnabled ? "auto" : "none",
          }}
        />
      </div>
    </div>
  );
}
