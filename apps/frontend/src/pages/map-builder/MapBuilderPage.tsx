import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useAuth } from "@/state/auth";
import { isStaff } from "@/types/user";
import NotFound from "../NotFound";
import MapBuilderCanvas from "./MapBuilderCanvas";
import TilePalette from "./TilePalette";
import { useMapBuilderHistory } from "./useMapBuilderHistory";
import { DRAWING_TOOL_LABELS, type DrawingTool } from "./drawingTools";
import {
  DEFAULT_MOVEMENT_COST,
  encodeWarObjective,
  MOVEMENT_COST_VALUES,
  PLAYER_COUNTS,
  PLAYER_IDS,
  SPECIAL_TILE_TYPES,
  type MapLayer,
  type MapTileData,
  type WarObjectiveKind,
  RANDOM_TM_ITEM_ID,
  type TileRef,
} from "@/types/mapData";
import {
  buildMapExport,
  canExportMap,
  createEmptyTileData,
  downloadMapJson,
  parseMapImport,
  resizeTileData,
} from "@/utils/mapBuilder";
import { getTilesetManifestUrl, getTmMachineUrl, getPokeballUrl, getMasterBallUrl } from "@/utils/gameAssets";
import { secureFetch } from "@/utils/secureFetch";

const LAYER_LABELS: Record<MapLayer, string> = {
  base: "Base tiles",
  overlay: "Overlay 1",
  overlay2: "Overlay 2",
  overlay3: "Overlay 3",
  spawn_points: "Conquest",
  special_tiles: "Special tiles",
  war: "War",
  flags: "Flags (CTF)",
  movement_cost: "Movement cost",
  items: "Items (TMs)",
};

const INITIAL_WIDTH = 12;
const INITIAL_HEIGHT = 8;

type TmItemOption = {
  id: number;
  name: string;
  slug: string;
  moveName: string;
  moveType: string;
};

export default function MapBuilderPage() {
  const { user, loading: authLoading } = useAuth();
  const [mapName, setMapName] = useState("New Map");
  const [mapWidth, setMapWidth] = useState(INITIAL_WIDTH);
  const [mapHeight, setMapHeight] = useState(INITIAL_HEIGHT);
  const [draftWidth, setDraftWidth] = useState(INITIAL_WIDTH);
  const [draftHeight, setDraftHeight] = useState(INITIAL_HEIGHT);
  const {
    tileData,
    setTileData,
    pushHistory,
    undo,
    redo,
    resetHistory,
    canUndo,
    canRedo,
  } = useMapBuilderHistory(createEmptyTileData(INITIAL_WIDTH, INITIAL_HEIGHT));
  const [tilesetNames, setTilesetNames] = useState<string[]>(["Brick City.png"]);
  const [activeTileset, setActiveTileset] = useState("Brick City.png");
  const [availableTilesets, setAvailableTilesets] = useState<string[]>([]);
  const [allowedPlayerCounts, setAllowedPlayerCounts] = useState<number[]>([2, 3, 4]);
  const [showAllOverlays, setShowAllOverlays] = useState(false);
  const [activeLayer, setActiveLayer] = useState<MapLayer>("base");
  const [drawingTool, setDrawingTool] = useState<DrawingTool>("pencil");
  const [selectedTile, setSelectedTile] = useState<TileRef>([0, 0]);
  const [spawnBrush, setSpawnBrush] = useState<number | null>(1);
  const [flagBrush, setFlagBrush] = useState<number | null>(1);
  const [specialBrush, setSpecialBrush] = useState<string>("grass");
  const [warObjectiveKind, setWarObjectiveKind] = useState<WarObjectiveKind>("pokeball");
  const [warOwnerBrush, setWarOwnerBrush] = useState<number | null>(null);
  const [movementCostBrush, setMovementCostBrush] = useState(DEFAULT_MOVEMENT_COST);
  const [itemBrush, setItemBrush] = useState<number | null>(null);
  const [tmItems, setTmItems] = useState<TmItemOption[]>([]);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const strokeRecordedRef = useRef(false);
  const tileDataRef = useRef(tileData);
  tileDataRef.current = tileData;

  useEffect(() => {
    fetch(getTilesetManifestUrl())
      .then((res) => (res.ok ? res.json() : []))
      .then((names: string[]) => {
        if (Array.isArray(names) && names.length > 0) {
          setAvailableTilesets(names);
        }
      })
      .catch(() => {
        setAvailableTilesets(["Brick City.png", "Beach Houses.png", "Route 224.png"]);
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadTmItems = async () => {
      try {
        const [itemsRes, movesRes] = await Promise.all([
          secureFetch("/api/items/all?category=tm"),
          secureFetch("/api/moves/all"),
        ]);
        if (!itemsRes.ok || !movesRes.ok) return;
        const items = (await itemsRes.json()) as Array<{
          id: number;
          name: string;
          slug: string;
          move_id: number | null;
        }>;
        const moves = (await movesRes.json()) as Array<{ id: number; name: string; type: string }>;
        if (cancelled) return;
        const moveById = new Map(moves.map((move) => [move.id, move]));
        const options = items
          .filter((item) => item.move_id != null && moveById.has(item.move_id))
          .map((item) => {
            const move = moveById.get(item.move_id!)!;
            return {
              id: item.id,
              name: item.name,
              slug: item.slug,
              moveName: move.name,
              moveType: move.type,
            };
          })
          .sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true }));
        setTmItems(options);
        if (options.length > 0) {
          setItemBrush((prev) => (prev == null ? RANDOM_TM_ITEM_ID : prev));
        }
      } catch {
        if (!cancelled) {
          setStatusMessage("Failed to load TM catalog for item placement.");
        }
      }
    };
    loadTmItems();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!(event.ctrlKey || event.metaKey)) return;
      const target = event.target as HTMLElement | null;
      if (target?.tagName === "INPUT" || target?.tagName === "TEXTAREA" || target?.tagName === "SELECT") {
        return;
      }
      if (event.key === "z" && !event.shiftKey) {
        event.preventDefault();
        undo();
      } else if (event.key === "z" && event.shiftKey) {
        event.preventDefault();
        redo();
      } else if (event.key === "y") {
        event.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [undo, redo]);

  const activeTilesetIndex = useMemo(
    () => Math.max(0, tilesetNames.indexOf(activeTileset)),
    [tilesetNames, activeTileset]
  );

  const itemMoveTypeById = useMemo(
    () => Object.fromEntries(tmItems.map((item) => [item.id, item.moveType])),
    [tmItems]
  );

  const selectedTm = useMemo(
    () => tmItems.find((item) => item.id === itemBrush) ?? null,
    [tmItems, itemBrush]
  );

  const warBrush = useMemo(() => {
    const owner =
      warObjectiveKind === "master_ball"
        ? warOwnerBrush ?? 1
        : warOwnerBrush;
    return encodeWarObjective(warObjectiveKind, owner);
  }, [warObjectiveKind, warOwnerBrush]);

  const exportValidation = useMemo(
    () => canExportMap(tilesetNames, allowedPlayerCounts, tileData),
    [tilesetNames, allowedPlayerCounts, tileData]
  );

  const applyResize = useCallback(() => {
    const nextWidth = Math.max(1, Math.min(64, draftWidth));
    const nextHeight = Math.max(1, Math.min(64, draftHeight));
    if (nextWidth === mapWidth && nextHeight === mapHeight) return;

    pushHistory(tileDataRef.current);
    setMapWidth(nextWidth);
    setMapHeight(nextHeight);
    setDraftWidth(nextWidth);
    setDraftHeight(nextHeight);
    setTileData((prev) =>
      resizeTileData(prev, prev.base[0]?.length ?? 0, prev.base.length, nextWidth, nextHeight)
    );
  }, [draftWidth, draftHeight, mapWidth, mapHeight, pushHistory, setTileData]);

  const handleStrokeStart = useCallback(() => {
    if (strokeRecordedRef.current) return;
    pushHistory(tileDataRef.current);
    strokeRecordedRef.current = true;
  }, [pushHistory]);

  const handleStrokeEnd = useCallback(() => {
    strokeRecordedRef.current = false;
  }, []);

  const handleTileDataChange = useCallback(
    (next: MapTileData | ((prev: MapTileData) => MapTileData)) => {
      setTileData(next);
    },
    [setTileData]
  );

  const toggleTileset = (name: string) => {
    setTilesetNames((prev) => {
      if (prev.includes(name)) {
        const next = prev.filter((entry) => entry !== name);
        if (next.length === 0) return prev;
        if (activeTileset === name) {
          setActiveTileset(next[0]);
        }
        return next;
      }
      return [...prev, name];
    });
  };

  useEffect(() => {
    setSelectedTile((prev) => [prev[0], activeTilesetIndex]);
  }, [activeTilesetIndex]);

  const handleExport = () => {
    if (!exportValidation.ok) {
      setStatusMessage(exportValidation.message ?? "Cannot export this map.");
      return;
    }
    const map = buildMapExport({
      name: mapName,
      tilesetNames,
      allowedPlayerCounts,
      width: mapWidth,
      height: mapHeight,
      tileData,
    });
    downloadMapJson(map);
    setStatusMessage("Map exported.");
  };

  const handleImport = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    try {
      const text = await file.text();
      const map = parseMapImport(JSON.parse(text));
      setMapName(map.name);
      setMapWidth(map.width);
      setMapHeight(map.height);
      setDraftWidth(map.width);
      setDraftHeight(map.height);
      resetHistory(map.tile_data);
      setTilesetNames(map.tileset_names);
      setActiveTileset(map.tileset_names[0] ?? "Brick City.png");
      setAllowedPlayerCounts(map.allowed_player_counts);
      setStatusMessage(`Imported "${map.name}".`);
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : "Failed to import map.");
    }
  };

  const sizePending =
    draftWidth !== mapWidth ||
    draftHeight !== mapHeight ||
    draftWidth < 1 ||
    draftHeight < 1;

  if (!authLoading && (!user || !isStaff(user))) {
    return <NotFound />;
  }

  return (
    <div className="mx-auto max-w-7xl px-4 pt-20 pb-16 text-left">
      <header className="mb-8">
        <p className="text-sm font-semibold uppercase tracking-wide text-yellow-300">Staff tools</p>
        <h1 className="mt-2 text-3xl font-bold text-white">Map Builder</h1>
        <p className="mt-2 max-w-2xl text-gray-300">
          Paint tiles and export a map JSON compatible with the seed maps in{" "}
          <code className="text-sm text-gray-400">apps/backend/seed/maps</code>.
        </p>
      </header>

      {statusMessage && (
        <p className="mb-4 rounded border border-gray-700 bg-gray-800/80 px-3 py-2 text-sm text-gray-200">
          {statusMessage}
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <section className="space-y-4">
          <div className="flex flex-wrap items-end gap-3 rounded-lg border border-gray-700 bg-gray-900/70 p-4">
            <label className="flex flex-col gap-1 text-sm text-gray-300">
              Map name
              <input
                className="rounded bg-gray-800 px-2 py-1 text-white"
                value={mapName}
                onChange={(e) => setMapName(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-gray-300">
              Width
              <input
                type="number"
                min={1}
                max={64}
                className="w-20 rounded bg-gray-800 px-2 py-1 text-white"
                value={draftWidth}
                onChange={(e) => setDraftWidth(Number(e.target.value))}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-gray-300">
              Height
              <input
                type="number"
                min={1}
                max={64}
                className="w-20 rounded bg-gray-800 px-2 py-1 text-white"
                value={draftHeight}
                onChange={(e) => setDraftHeight(Number(e.target.value))}
              />
            </label>
            <button
              type="button"
              onClick={applyResize}
              disabled={!sizePending}
              className="rounded bg-gray-700 px-3 py-1.5 text-sm text-white hover:bg-gray-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Apply size
            </button>
            <button
              type="button"
              onClick={undo}
              disabled={!canUndo}
              title="Undo (Ctrl+Z)"
              className="rounded bg-gray-700 px-3 py-1.5 text-sm text-white hover:bg-gray-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Undo
            </button>
            <button
              type="button"
              onClick={redo}
              disabled={!canRedo}
              title="Redo (Ctrl+Shift+Z)"
              className="rounded bg-gray-700 px-3 py-1.5 text-sm text-white hover:bg-gray-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Redo
            </button>
            <button
              type="button"
              onClick={handleExport}
              disabled={!exportValidation.ok}
              title={exportValidation.message ?? undefined}
              className="rounded bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Export JSON
            </button>
            <label className="cursor-pointer rounded bg-gray-700 px-3 py-1.5 text-sm text-white hover:bg-gray-600">
              Import JSON
              <input type="file" accept="application/json,.json" className="hidden" onChange={handleImport} />
            </label>
          </div>

          {sizePending && (
            <p className="text-sm text-yellow-400">
              Map size changed — click Apply size to update the canvas ({mapWidth}×{mapHeight} → {draftWidth}×
              {draftHeight}).
            </p>
          )}

          {!exportValidation.ok && exportValidation.message && (
            <p className="text-sm text-amber-400">{exportValidation.message}</p>
          )}

          <div className="flex flex-wrap gap-2">
            {(Object.keys(LAYER_LABELS) as MapLayer[]).map((layer) => (
              <button
                key={layer}
                type="button"
                onClick={() => setActiveLayer(layer)}
                className={`rounded px-3 py-1.5 text-sm ${
                  activeLayer === layer
                    ? "bg-yellow-500 text-gray-900"
                    : "bg-gray-800 text-gray-200 hover:bg-gray-700"
                }`}
              >
                {LAYER_LABELS[layer]}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm text-gray-400">Tool:</span>
            {(Object.keys(DRAWING_TOOL_LABELS) as DrawingTool[]).map((tool) => (
              <button
                key={tool}
                type="button"
                onClick={() => setDrawingTool(tool)}
                className={`rounded px-3 py-1.5 text-sm ${
                  drawingTool === tool
                    ? "bg-blue-600 text-white"
                    : "bg-gray-800 text-gray-200 hover:bg-gray-700"
                }`}
              >
                {DRAWING_TOOL_LABELS[tool]}
              </button>
            ))}
          </div>

          {(activeLayer === "base" || activeLayer === "overlay" || activeLayer === "overlay2" || activeLayer === "overlay3") && (
            <p className="text-sm text-gray-400">
              {drawingTool === "pencil" && "Drag to paint individual tiles"}
              {drawingTool === "box" && "Drag to fill a rectangle"}
              {drawingTool === "eraser" && "Drag to erase tiles"}
              {" · "}tileset index {activeTilesetIndex} · Ctrl+Z / Ctrl+Shift+Z
            </p>
          )}
          {(activeLayer !== "base" && activeLayer !== "overlay" && activeLayer !== "overlay2" && activeLayer !== "overlay3") && (
            <p className="text-sm text-gray-400">
              {drawingTool === "pencil" && "Drag to paint cells"}
              {drawingTool === "box" && "Drag to fill a rectangle with the current brush"}
              {drawingTool === "eraser" && "Drag to clear cells"}
            </p>
          )}
          {activeLayer === "spawn_points" && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-gray-300">
              Conquest spawn brush:
              {PLAYER_IDS.map((player) => (
                <button
                  key={player}
                  type="button"
                  onClick={() => setSpawnBrush(player)}
                  className={`rounded px-2 py-1 ${
                    spawnBrush === player ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-200"
                  }`}
                >
                  P{player}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setSpawnBrush(null)}
                className={`rounded px-2 py-1 ${
                  spawnBrush === null ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-200"
                }`}
              >
                Clear
              </button>
            </div>
          )}
          {activeLayer === "special_tiles" && (
            <label className="flex items-center gap-2 text-sm text-gray-300">
              Special tile
              <select
                className="rounded bg-gray-800 px-2 py-1 text-white"
                value={specialBrush}
                onChange={(e) => setSpecialBrush(e.target.value)}
              >
                {SPECIAL_TILE_TYPES.map((type) => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </label>
          )}
          {activeLayer === "war" && (
            <div className="flex flex-wrap items-center gap-3 text-sm text-gray-300">
              <div className="flex flex-wrap items-center gap-2">
                <span>Objective:</span>
                <button
                  type="button"
                  onClick={() => setWarObjectiveKind("pokeball")}
                  className={`rounded px-2 py-1 ${
                    warObjectiveKind === "pokeball" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-200"
                  }`}
                >
                  Pokeball
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setWarObjectiveKind("master_ball");
                    setWarOwnerBrush((prev) => prev ?? 1);
                  }}
                  className={`rounded px-2 py-1 ${
                    warObjectiveKind === "master_ball" ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-200"
                  }`}
                >
                  Master Ball
                </button>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <span>Owner:</span>
                {warObjectiveKind === "pokeball" && (
                  <button
                    type="button"
                    onClick={() => setWarOwnerBrush(null)}
                    className={`rounded px-2 py-1 ${
                      warOwnerBrush === null ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-200"
                    }`}
                  >
                    None
                  </button>
                )}
                {PLAYER_IDS.map((player) => (
                  <button
                    key={player}
                    type="button"
                    onClick={() => setWarOwnerBrush(player)}
                    className={`rounded px-2 py-1 ${
                      warOwnerBrush === player ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-200"
                    }`}
                  >
                    P{player}
                  </button>
                ))}
              </div>
              <img
                src={warObjectiveKind === "master_ball" ? getMasterBallUrl() : getPokeballUrl()}
                alt={warObjectiveKind === "master_ball" ? "Master Ball" : "Pokeball"}
                className="h-8 w-8"
                style={{ imageRendering: "pixelated" }}
              />
              <span className="text-gray-500">
                · Eraser removes objectives only · Each player needs exactly one master ball to export
              </span>
            </div>
          )}
          {activeLayer === "flags" && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-gray-300">
              Flag owner:
              {PLAYER_IDS.map((player) => (
                <button
                  key={player}
                  type="button"
                  onClick={() => setFlagBrush(player)}
                  className={`rounded px-2 py-1 ${
                    flagBrush === player ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-200"
                  }`}
                >
                  P{player}
                </button>
              ))}
              <button
                type="button"
                onClick={() => setFlagBrush(null)}
                className={`rounded px-2 py-1 ${
                  flagBrush === null ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-200"
                }`}
              >
                Clear
              </button>
            </div>
          )}
          {activeLayer === "movement_cost" && (
            <div className="flex flex-wrap items-center gap-2 text-sm text-gray-300">
              <span>Cost brush:</span>
              {MOVEMENT_COST_VALUES.map((cost) => (
                <button
                  key={cost}
                  type="button"
                  onClick={() => setMovementCostBrush(cost)}
                  className={`rounded px-2 py-1 ${
                    movementCostBrush === cost ? "bg-blue-600 text-white" : "bg-gray-800 text-gray-200"
                  }`}
                >
                  {cost}
                </button>
              ))}
              <span className="text-gray-500">· Eraser resets to {DEFAULT_MOVEMENT_COST}</span>
            </div>
          )}
          {activeLayer === "items" && (
            <div className="flex flex-wrap items-center gap-3 text-sm text-gray-300">
              <label className="flex items-center gap-2">
                TM
                <select
                  className="min-w-[14rem] max-w-md rounded bg-gray-800 px-2 py-1 text-white"
                  value={itemBrush ?? ""}
                  onChange={(e) =>
                    setItemBrush(e.target.value === "" ? null : Number(e.target.value))
                  }
                  disabled={tmItems.length === 0}
                >
                  {tmItems.length === 0 ? (
                    <option value="">Loading TMs…</option>
                  ) : (
                    <>
                      <option value={RANDOM_TM_ITEM_ID}>Random TM</option>
                      {tmItems.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name} — {item.moveName}
                        </option>
                      ))}
                    </>
                  )}
                </select>
              </label>
              {itemBrush === RANDOM_TM_ITEM_ID ? (
                <span
                  className="flex h-8 w-8 items-center justify-center rounded border border-yellow-400/70 bg-purple-900/80 text-sm font-bold text-yellow-200"
                  title="Random TM"
                >
                  ?
                </span>
              ) : (
                selectedTm && (
                  <img
                    src={getTmMachineUrl(selectedTm.moveType)}
                    alt={`${selectedTm.name} — ${selectedTm.moveName}`}
                    className="h-8 w-8"
                    style={{ imageRendering: "pixelated" }}
                  />
                )
              )}
              <span className="text-gray-500">· Eraser removes placed TMs</span>
            </div>
          )}

          <div className="overflow-auto rounded-lg border border-gray-700 bg-gray-950/50 p-4">
            <MapBuilderCanvas
              width={mapWidth}
              height={mapHeight}
              tileData={tileData}
              tilesetNames={tilesetNames}
              activeLayer={activeLayer}
              tool={drawingTool}
              selectedTile={selectedTile}
              spawnBrush={spawnBrush}
              specialBrush={specialBrush}
              flagBrush={flagBrush}
              movementCostBrush={movementCostBrush}
              itemBrush={itemBrush}
              itemMoveTypeById={itemMoveTypeById}
              warBrush={warBrush}
              showAllOverlays={showAllOverlays}
              onStrokeStart={handleStrokeStart}
              onStrokeEnd={handleStrokeEnd}
              onTileDataChange={handleTileDataChange}
            />
          </div>
        </section>

        <aside className="space-y-4">
          <section className="rounded-lg border border-gray-700 bg-gray-900/70 p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-300">Tilesets</h2>
            <label className="mb-3 flex flex-col gap-1 text-sm text-gray-300">
              Active palette
              <select
                className="rounded bg-gray-800 px-2 py-1 text-white"
                value={activeTileset}
                onChange={(e) => setActiveTileset(e.target.value)}
              >
                {tilesetNames.map((name) => (
                  <option key={name} value={name}>
                    {name}
                  </option>
                ))}
              </select>
            </label>
            <div className="mb-3 max-h-40 space-y-1 overflow-y-auto text-sm">
              {(availableTilesets.length > 0 ? availableTilesets : tilesetNames).map((name) => (
                <label key={name} className="flex items-center gap-2 text-gray-300">
                  <input
                    type="checkbox"
                    checked={tilesetNames.includes(name)}
                    onChange={() => toggleTileset(name)}
                  />
                  <span className="truncate">{name}</span>
                </label>
              ))}
            </div>
            {(activeLayer === "base" || activeLayer === "overlay" || activeLayer === "overlay2" || activeLayer === "overlay3") &&
              tilesetNames.includes(activeTileset) && (
              <TilePalette
                tilesetName={activeTileset}
                selectedTile={selectedTile}
                onSelectTile={setSelectedTile}
                tilesetIndex={activeTilesetIndex}
              />
            )}
          </section>

          <section className="rounded-lg border border-gray-700 bg-gray-900/70 p-4">
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-300">Player counts</h2>
            <p className="mb-3 text-xs text-gray-500">
              Maps export for Conquest and War. Each player up to the highest count selected needs at least one
              Conquest spawn point and exactly one master ball on the War layer.
            </p>
            <div className="space-y-2 text-sm">
              {PLAYER_COUNTS.map((count) => (
                <label key={count} className="flex items-center gap-2 text-gray-300">
                  <input
                    type="checkbox"
                    checked={allowedPlayerCounts.includes(count)}
                    onChange={() =>
                      setAllowedPlayerCounts((prev) =>
                        prev.includes(count) ? prev.filter((c) => c !== count) : [...prev, count]
                      )
                    }
                  />
                  {count} players
                </label>
              ))}
            </div>
            <label className="mt-4 flex items-center gap-2 border-t border-gray-700 pt-4 text-sm text-gray-300">
              <input
                type="checkbox"
                checked={showAllOverlays}
                onChange={(e) => setShowAllOverlays(e.target.checked)}
              />
              Show all overlay layers
            </label>
            <p className="mt-1 text-xs text-gray-500">
              When off, Conquest spawns, special tiles, War objectives, flags, and items are only visible on their
              active tab.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}
