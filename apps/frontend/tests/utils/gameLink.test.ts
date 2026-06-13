import { describe, it, expect, vi, beforeEach } from 'vitest';
import { gameExists, parseGameLink } from '@/utils/gameLink';
import { secureFetch } from '@/utils/secureFetch';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn(),
}));

describe('gameLink utils', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('parses plain slugs and full URLs', () => {
    expect(parseGameLink('forest123')).toBe('forest123');
    expect(parseGameLink('https://poketactics.net/games/forest123')).toBe('forest123');
    expect(parseGameLink('/games/forest123')).toBe('forest123');
  });

  it('returns null for invalid formats', () => {
    expect(parseGameLink('not valid!!!')).toBeNull();
    expect(parseGameLink('')).toBeNull();
  });

  it('checks game existence via the backend', async () => {
    vi.mocked(secureFetch).mockResolvedValue({ ok: true } as Response);
    await expect(gameExists('abc123')).resolves.toBe(true);
    expect(secureFetch).toHaveBeenCalledWith('/api/games/abc123');

    vi.mocked(secureFetch).mockResolvedValue({ ok: false } as Response);
    await expect(gameExists('missing')).resolves.toBe(false);
  });
});
