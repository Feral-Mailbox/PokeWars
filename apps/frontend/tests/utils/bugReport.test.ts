import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  buildBugReportPageUrl,
  buildBugReportTemplate,
  openBugReportWindow,
  parseBugReportSearchParams,
} from '@/utils/bugReport';

describe('bugReport utils', () => {
  beforeEach(() => {
    vi.stubGlobal('window', {
      ...window,
      location: { origin: 'https://poketactics.net' },
      open: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds a report template with game context', () => {
    const template = buildBugReportTemplate({
      gameLink: 'abc123',
      gameName: 'Test Game',
      gameMode: 'Conquest',
      gameStatus: 'in_progress',
      username: 'player1',
      pageUrl: 'https://poketactics.net/games/abc123',
    });

    expect(template).toContain('Game link: abc123');
    expect(template).toContain('Game name: Test Game');
    expect(template).toContain('Username: player1');
  });

  it('builds a report page URL with query params', () => {
    const url = buildBugReportPageUrl({
      gameLink: 'abc123',
      gameName: 'Test Game',
    });

    expect(url).toBe('https://poketactics.net/report-bug?gameLink=abc123&gameName=Test+Game');
  });

  it('opens the report page in a new window', () => {
    openBugReportWindow({ gameLink: 'abc123' });

    expect(window.open).toHaveBeenCalledWith(
      'https://poketactics.net/report-bug?gameLink=abc123',
      '_blank',
      'noopener,noreferrer',
    );
  });

  it('parses search params into report context', () => {
    const params = new URLSearchParams('gameLink=abc123&username=player1');
    expect(parseBugReportSearchParams(params)).toEqual({
      gameLink: 'abc123',
      gameName: undefined,
      gameMode: undefined,
      gameStatus: undefined,
      username: 'player1',
      pageUrl: undefined,
    });
  });
});
