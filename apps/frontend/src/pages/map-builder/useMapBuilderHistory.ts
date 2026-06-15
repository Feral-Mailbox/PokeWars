import { useCallback, useRef, useState } from "react";
import type { MapTileData } from "@/types/mapData";

const MAX_HISTORY = 50;

function cloneTileData(data: MapTileData): MapTileData {
  return structuredClone(data);
}

export function useMapBuilderHistory(initial: MapTileData) {
  const [tileData, setTileData] = useState<MapTileData>(initial);
  const pastRef = useRef<MapTileData[]>([]);
  const futureRef = useRef<MapTileData[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const syncHistoryButtons = useCallback(() => {
    setCanUndo(pastRef.current.length > 0);
    setCanRedo(futureRef.current.length > 0);
  }, []);

  const pushHistory = useCallback((snapshot: MapTileData) => {
    pastRef.current.push(cloneTileData(snapshot));
    if (pastRef.current.length > MAX_HISTORY) {
      pastRef.current.shift();
    }
    futureRef.current = [];
    syncHistoryButtons();
  }, [syncHistoryButtons]);

  const undo = useCallback(() => {
    const previous = pastRef.current.pop();
    if (!previous) return;
    setTileData((current) => {
      futureRef.current.push(cloneTileData(current));
      syncHistoryButtons();
      return previous;
    });
  }, [syncHistoryButtons]);

  const redo = useCallback(() => {
    const next = futureRef.current.pop();
    if (!next) return;
    setTileData((current) => {
      pastRef.current.push(cloneTileData(current));
      syncHistoryButtons();
      return next;
    });
  }, [syncHistoryButtons]);

  const resetHistory = useCallback(
    (next: MapTileData) => {
      pastRef.current = [];
      futureRef.current = [];
      setTileData(cloneTileData(next));
      syncHistoryButtons();
    },
    [syncHistoryButtons]
  );

  return {
    tileData,
    setTileData,
    pushHistory,
    undo,
    redo,
    resetHistory,
    canUndo,
    canRedo,
  };
}
