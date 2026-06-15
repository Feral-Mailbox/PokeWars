import { useEffect, useMemo, useRef, useState } from "react";
import { MAP_TILE_SIZE } from "@/utils/pixelCanvas";
import { getTilesetUrl } from "@/utils/gameAssets";

const PREVIEW_SIZE = MAP_TILE_SIZE * 2;

type TilePaletteProps = {
  tilesetName: string;
  selectedTile: [number, number] | null;
  onSelectTile: (tile: [number, number]) => void;
  tilesetIndex: number;
};

function TileButton({
  image,
  tileIndex,
  tilesPerRow,
  isSelected,
  onSelect,
}: {
  image: HTMLImageElement;
  tileIndex: number;
  tilesPerRow: number;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sx = (tileIndex % tilesPerRow) * MAP_TILE_SIZE;
  const sy = Math.floor(tileIndex / tilesPerRow) * MAP_TILE_SIZE;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !image.naturalWidth) return;

    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    canvas.width = PREVIEW_SIZE;
    canvas.height = PREVIEW_SIZE;

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, PREVIEW_SIZE, PREVIEW_SIZE);
    ctx.drawImage(
      image,
      sx,
      sy,
      MAP_TILE_SIZE,
      MAP_TILE_SIZE,
      0,
      0,
      PREVIEW_SIZE,
      PREVIEW_SIZE
    );
  }, [image, sx, sy]);

  return (
    <button
      type="button"
      title={`Tile ${tileIndex}`}
      onClick={onSelect}
      className={`flex shrink-0 items-center justify-center overflow-hidden rounded border p-0 ${
        isSelected ? "border-yellow-400 ring-2 ring-yellow-400/60" : "border-gray-600 hover:border-gray-400"
      }`}
      style={{ width: PREVIEW_SIZE, height: PREVIEW_SIZE }}
    >
      <canvas
        ref={canvasRef}
        width={PREVIEW_SIZE}
        height={PREVIEW_SIZE}
        className="block"
        style={{
          width: PREVIEW_SIZE,
          height: PREVIEW_SIZE,
          imageRendering: "pixelated",
        }}
      />
    </button>
  );
}

export default function TilePalette({
  tilesetName,
  selectedTile,
  onSelectTile,
  tilesetIndex,
}: TilePaletteProps) {
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    setLoadError(false);
    setImage(null);

    const img = new Image();
    img.onload = () => setImage(img);
    img.onerror = () => setLoadError(true);
    img.src = getTilesetUrl(tilesetName);

    return () => {
      img.onload = null;
      img.onerror = null;
    };
  }, [tilesetName]);

  const tilesPerRow = image ? Math.floor(image.naturalWidth / MAP_TILE_SIZE) : 0;
  const tileCount = image
    ? Math.floor((image.naturalWidth / MAP_TILE_SIZE) * (image.naturalHeight / MAP_TILE_SIZE))
    : 0;

  const tileButtons = useMemo(() => {
    if (!image || tilesPerRow <= 0) return [];
    return Array.from({ length: tileCount }, (_, tileIndex) => (
      <TileButton
        key={tileIndex}
        image={image}
        tileIndex={tileIndex}
        tilesPerRow={tilesPerRow}
        isSelected={selectedTile?.[0] === tileIndex && selectedTile?.[1] === tilesetIndex}
        onSelect={() => onSelectTile([tileIndex, tilesetIndex])}
      />
    ));
  }, [image, tileCount, tilesPerRow, selectedTile, tilesetIndex, onSelectTile]);

  if (loadError) {
    return <p className="text-sm text-red-400">Failed to load tileset: {tilesetName}</p>;
  }

  if (!image) {
    return <p className="text-sm text-gray-400">Loading tileset…</p>;
  }

  return (
    <div className="max-h-[420px] overflow-y-auto rounded border border-gray-700 bg-gray-900/80 p-2">
      <p className="mb-2 text-xs text-gray-400">
        {tilesetName} · {tileCount} tiles
      </p>
      <div className="flex flex-wrap gap-1">{tileButtons}</div>
    </div>
  );
}
