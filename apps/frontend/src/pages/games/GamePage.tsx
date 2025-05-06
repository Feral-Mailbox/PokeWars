import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";

const TILE_SIZE = 16;
const TILE_SCALE = 2;

export default function GamePage() {
  const { gameId } = useParams();
  const [gameData, setGameData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchGame = async () => {
      try {
        // Hash the game ID to obscure raw DB IDs
        const res = await secureFetch(`/api/games/${gameId}`); // optionally use hashedId
        if (!res.ok) throw new Error("Game not found");

        const data = await res.json();
        setGameData(data);
      } catch (err: any) {
        setError(err.message);
      }
    };
    fetchGame();
  }, [gameId]);

  useEffect(() => {
    if (!gameData || !gameData.map || !gameData.map.tile_data) return;
  
    const canvas = document.getElementById("mapCanvas") as HTMLCanvasElement;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
  
    const tileset = new Image();
    tileset.src = `/tilesets/${gameData.map.tileset_name}`;

    console.log(tileset.src)
  
    tileset.onload = () => {
      const { base, overlay } = gameData.map.tile_data;
      const tilesPerRow = Math.floor(tileset.width / TILE_SIZE);
  
      for (let y = 0; y < gameData.map.height; y++) {
        for (let x = 0; x < gameData.map.width; x++) {
          const drawTile = (tileIndex: number | null) => {
            if (tileIndex == null || tileIndex < 0) return;
            const sx = (tileIndex % tilesPerRow) * TILE_SIZE;
            const sy = Math.floor(tileIndex / tilesPerRow) * TILE_SIZE;
            ctx.drawImage(
              tileset,
              sx, sy,
              TILE_SIZE, TILE_SIZE,
              x * TILE_SIZE * TILE_SCALE, y * TILE_SIZE * TILE_SCALE,
              TILE_SIZE * TILE_SCALE, TILE_SIZE * TILE_SCALE
            );
          };
  
          drawTile(base[y][x]);    // Draw base layer first
          drawTile(overlay[y][x]); // Draw overlay second
        }
      }
    };
  }, [gameData]);  

  if (error) {
    return <div className="p-8 text-red-500">Error: {error}</div>;
  }

  if (!gameData) {
    return <div className="p-8 text-white">Loading game...</div>;
  }

  const mapWidth = gameData?.map?.width * TILE_SIZE * TILE_SCALE;
  const mapHeight = gameData?.map?.height * TILE_SIZE * TILE_SCALE;

  return (
    <div className="p-8 text-white">
      <canvas id="mapCanvas" width={mapWidth} height={mapHeight}></canvas>
      <h1 className="text-3xl font-bold mb-4">{gameData.game_name || "Untitled Game"}</h1>
      <p className="mb-2"><strong>Map:</strong> {gameData.map_name}</p>
      <p className="mb-2"><strong>Host:</strong> {gameData.host.username}</p>
      <p className="mb-2"><strong>Players:</strong> {gameData.players.length}/{gameData.max_players}</p>

      {/* Future implementation: round viewer or current game board goes here */}
      <div className="mt-6">
        <p className="text-sm italic">Game viewer placeholder — implement board state or rollback here.</p>
      </div>
    </div>
  );
}
