import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { secureFetch } from "@/utils/secureFetch";
import sha256 from "crypto-js/sha256";

export default function GamePage() {
  const { gameId } = useParams();
  const [gameData, setGameData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchGame = async () => {
      try {
        // Hash the game ID to obscure raw DB IDs
        const hashedId = sha256(gameId).toString();
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

  if (error) {
    return <div className="p-8 text-red-500">Error: {error}</div>;
  }

  if (!gameData) {
    return <div className="p-8 text-white">Loading game...</div>;
  }

  return (
    <div className="p-8 text-white">
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
