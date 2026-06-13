import { secureFetch } from '@/utils/secureFetch';

export const INVALID_GAME_LINK_MESSAGE = 'Enter a valid game link or ID.';
export const GAME_NOT_FOUND_MESSAGE = 'Game not found. Check the link and try again.';

export function parseGameLink(input: string): string | null {
  const trimmed = input.trim();
  if (!trimmed) return null;

  if (trimmed.includes('://')) {
    try {
      const url = new URL(trimmed);
      const match = url.pathname.match(/\/games\/([^/]+)/);
      if (match?.[1]) return match[1];
    } catch {
      return null;
    }
  }

  const pathMatch = trimmed.match(/\/games\/([^/]+)/);
  if (pathMatch?.[1]) return pathMatch[1];

  if (/^[a-zA-Z0-9_-]+$/.test(trimmed)) return trimmed;

  return null;
}

export async function gameExists(link: string): Promise<boolean> {
  const res = await secureFetch(`/api/games/${encodeURIComponent(link)}`);
  return res.ok;
}
