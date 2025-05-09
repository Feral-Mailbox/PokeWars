import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useWebSocket } from '@/state/WebSocketContext';
import { secureFetch } from "@/utils/secureFetch";

const TILE_SIZE = 16;
const TILE_SCALE = 2;

export default function GamePage() {
  const { gameId } = useParams();
  const [userId, setUserId] = useState<number | null>(null);
  const [gameData, setGameData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [gameSocket, setGameSocket] = useState<WebSocket | null>(null);

  // Fetch game data
  useEffect(() => {
    const fetchGame = async () => {
      try {
        const res = await secureFetch(`/api/games/${gameId}`);
        if (!res.ok) throw new Error("Game not found");
        const data = await res.json();
        setGameData(data);
      } catch (err: any) {
        setError(err.message);
      }
    };
    fetchGame();
  }, [gameId]);

  // Fetch user ID
  useEffect(() => {
    const fetchUser = async () => {
      try {
        const res = await secureFetch("/api/me");
        const data = await res.json();
        setUserId(data.id);
      } catch (err) {
        console.error("Failed to fetch user:", err);
      }
    };
    fetchUser();
  }, []);

  // WebSocket subscription and listener
  useEffect(() => {
    if (!gameData?.link) return;

    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    const hostname = window.location.hostname;
    const ws = new WebSocket(`${protocol}://${hostname}/api/ws/game/${gameData.link}`);

    console.log("[Game WS] Connecting to", ws.url);

    ws.onopen = () => console.log("[Game WS] Connected");
    ws.onclose = () => console.log("[Game WS] Disconnected");
    ws.onerror = (e) => console.error("[Game WS] Error", e);

    ws.onmessage = (event) => {
      console.log("[Game WS] Message received:", event.data);
      if (["player_joined", "game_started"].includes(event.data)) {
        secureFetch(`/api/games/${gameData.link}`).then(async (res) => {
          if (res.ok) {
            const updatedData = await res.json();
            console.log("[Game WS] New game status:", updatedData.status);
            setGameData(updatedData);
          }          
        });
      }
    };

    setGameSocket(ws);

    return () => {
      console.log("[Game WS] Closing connection");
      ws.close();
    };
  }, [gameData?.link]);

  // Map rendering
  useEffect(() => {
    if (!gameData?.map?.tile_data) return;

    const canvas = document.getElementById("mapCanvas") as HTMLCanvasElement;
    const ctx = canvas?.getContext("2d");
    if (!ctx) return;

    const tileset = new Image();
    tileset.src = `/tilesets/${gameData.map.tileset_name}`;

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

          drawTile(base[y][x]);
          drawTile(overlay[y][x]);
        }
      }
    };
  }, [gameData]);

  if (error) return <div className="p-8 text-red-500">Error: {error}</div>;
  if (!gameData) return <div className="p-8 text-white">Loading game...</div>;

  const mapWidth = gameData.map.width * TILE_SIZE * TILE_SCALE;
  const mapHeight = gameData.map.height * TILE_SIZE * TILE_SCALE;
  const isHost = gameData.host.id === userId;
  const isFull = gameData.players.length >= gameData.max_players;

  let statusMessage = "";
  if (gameData.status === "in_progress") {
    statusMessage = "Game in progress...";
  } else if (!isFull) {
    statusMessage = "Waiting for players...";
  } else if (isHost) {
    statusMessage = "Players have been found!";
  } else {
    statusMessage = "Waiting for host to start the match...";
  }

  return (
    <div className="p-8 text-white">
      <h1 className="text-3xl font-bold mb-4">{gameData.game_name || "Untitled Game"}</h1>
      <p className="text-lg font-semibold mb-2 text-yellow-400">{statusMessage}</p>
      {isHost && gameData.status !== "in_progress" && (
        <button
          className="mt-2 bg-green-600 text-white px-4 py-2 rounded disabled:opacity-50"
          disabled={!isFull}
          onClick={async () => {
            const res = await secureFetch(`/api/games/start/${gameData.id}`, { method: "POST" });
            if (res.ok) {
              const updated = await secureFetch(`/api/games/${gameData.link}`);
              setGameData(await updated.json());
            } else {
              alert("Unable to start game");
            }
          }}
        >
          Start Game
        </button>
      )}
      <canvas id="mapCanvas" width={mapWidth} height={mapHeight}></canvas>
      <p className="mb-2"><strong>Map:</strong> {gameData.map_name}</p>
      <p className="mb-2"><strong>Host:</strong> {gameData.host.username}</p>
      <p className="mb-2"><strong>Players:</strong> {gameData.players.length}/{gameData.max_players}</p>

      <div className="mt-6">
        <p className="text-sm italic">Game viewer placeholder — implement board state or rollback here.</p>
      </div>
    </div>
  );
}
