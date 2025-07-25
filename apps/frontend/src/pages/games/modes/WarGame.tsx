import { useMapRenderer } from "@/hooks/useMapRenderer";

export default function WarGame({ gameData, userId }: { gameData: any, userId: number }) {
  // War mode currently has no additional overlay requirements
  useMapRenderer("mapCanvas", gameData);

  return (
    <div className="mt-4 text-white">
      <p className="italic text-sm text-blue-300">War Mode: Eliminate all enemies to win.</p>
    </div>
  );
}
