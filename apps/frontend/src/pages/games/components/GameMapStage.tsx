import UnitIdleSprite from "@/components/units/UnitIdleSprite";

type PlacedUnit = {
  id?: number;
  unit: any;
  tile: [number, number];
  current_hp: number;
  user_id: number;
  can_move?: boolean;
};

type GameMapStageProps = {
  mapWidth: number;
  mapHeight: number;
  canvasRef: any;
  overlayRef: any;
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

export default function GameMapStage({
  mapWidth,
  mapHeight,
  canvasRef,
  overlayRef,
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
  return (
    <div ref={mapStageRef} className="relative" style={{ width: mapWidth, height: mapHeight }}>
      <canvas ref={canvasRef} id="mapCanvas" width={mapWidth} height={mapHeight} />
      <canvas
        ref={overlayRef}
        id="overlayCanvas"
        width={mapWidth}
        height={mapHeight}
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          pointerEvents: overlayPointerEventsEnabled ? "auto" : "none",
        }}
      />

      {placedUnits.map((unitState) => {
        const { id, unit, tile, current_hp, user_id, can_move } = unitState;
        return (
          <div
            key={id}
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
              pointerEvents: moveTargeting ? "none" : "auto",
              cursor: moveTargeting ? "default" : "pointer",
            }}
          >
            <div style={{ position: "relative", width: "100%", height: "100%", pointerEvents: "none" }}>
              <UnitIdleSprite
                assetFolder={unit.asset_folder}
                onFrameSize={onSpriteFrameSize}
                isMapPlacement
                overlayColor={can_move === false ? "#777777" : getPlayerColor(user_id)}
              />

              <div
                style={{
                  position: "absolute",
                  bottom: 1,
                  right: 2,
                  fontSize: "10px",
                  color: "white",
                  fontWeight: 600,
                  zIndex: 2,
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
          </div>
        );
      })}
    </div>
  );
}
