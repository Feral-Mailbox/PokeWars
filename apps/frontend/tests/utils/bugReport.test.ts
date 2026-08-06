import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  buildBugReportPageUrl,
  buildBugReportTemplate,
  getExternalBugReportUrl,
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

  it('includes every populated context value and supports no query', () => {
    const context = {
      gameLink: 'abc',
      gameName: 'Arena',
      gameMode: 'War',
      gameStatus: 'complete',
      username: 'ash',
      pageUrl: 'https://example.test/game',
    };
    const url = buildBugReportPageUrl(context);

    expect(url).toContain('gameMode=War');
    expect(url).toContain('gameStatus=complete');
    expect(url).toContain('username=ash');
    expect(url).toContain('pageUrl=https%3A%2F%2Fexample.test%2Fgame');
    expect(buildBugReportPageUrl({})).toBe('https://poketactics.net/report-bug');
    expect(buildBugReportTemplate({})).toContain('Game link: N/A');
  });

  it('reads an optional external report URL', () => {
    vi.stubEnv('VITE_BUG_REPORT_URL', '  https://reports.example.test  ');
    expect(getExternalBugReportUrl()).toBe('https://reports.example.test');
    vi.stubEnv('VITE_BUG_REPORT_URL', '');
    expect(getExternalBugReportUrl()).toBeNull();
    vi.unstubAllEnvs();
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

  it('parses every supported search parameter', () => {
    const params = new URLSearchParams(
      'gameLink=id&gameName=Arena&gameMode=War&gameStatus=done&username=ash&pageUrl=https%3A%2F%2Fexample.test'
    );
    expect(parseBugReportSearchParams(params)).toEqual({
      gameLink: 'id',
      gameName: 'Arena',
      gameMode: 'War',
      gameStatus: 'done',
      username: 'ash',
      pageUrl: 'https://example.test',
    });
  });

  it('uses an unknown browser summary outside a browser', () => {
    vi.stubGlobal('navigator', undefined);
    expect(buildBugReportTemplate({})).toContain('Browser: Unknown');
  });
});
