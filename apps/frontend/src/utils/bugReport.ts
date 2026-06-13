export type BugReportContext = {
  gameLink?: string;
  gameName?: string;
  gameMode?: string;
  gameStatus?: string;
  username?: string;
  pageUrl?: string;
};

function browserSummary(): string {
  if (typeof navigator === 'undefined') return 'Unknown';
  return navigator.userAgent;
}

export function buildBugReportTemplate(context: BugReportContext): string {
  const lines = [
    '**What I was trying to do:**',
    '',
    '**What happened instead:**',
    '',
    '**Steps to reproduce:**',
    '1.',
    '',
    '---',
    `Game link: ${context.gameLink ?? 'N/A'}`,
    `Game name: ${context.gameName ?? 'N/A'}`,
    `Game mode: ${context.gameMode ?? 'N/A'}`,
    `Game status: ${context.gameStatus ?? 'N/A'}`,
    `Username: ${context.username ?? 'N/A'}`,
    `Page URL: ${context.pageUrl ?? 'N/A'}`,
    `Browser: ${browserSummary()}`,
    `Reported at: ${new Date().toISOString()}`,
  ];
  return lines.join('\n');
}

export function buildBugReportPageUrl(context: BugReportContext): string {
  const params = new URLSearchParams();
  if (context.gameLink) params.set('gameLink', context.gameLink);
  if (context.gameName) params.set('gameName', context.gameName);
  if (context.gameMode) params.set('gameMode', context.gameMode);
  if (context.gameStatus) params.set('gameStatus', context.gameStatus);
  if (context.username) params.set('username', context.username);
  if (context.pageUrl) params.set('pageUrl', context.pageUrl);

  const query = params.toString();
  return `${window.location.origin}/report-bug${query ? `?${query}` : ''}`;
}

export function openBugReportWindow(context: BugReportContext): void {
  const url = buildBugReportPageUrl(context);
  window.open(url, '_blank', 'noopener,noreferrer');
}

export function getExternalBugReportUrl(): string | null {
  const url = import.meta.env.VITE_BUG_REPORT_URL?.trim();
  return url || null;
}

export function parseBugReportSearchParams(searchParams: URLSearchParams): BugReportContext {
  return {
    gameLink: searchParams.get('gameLink') ?? undefined,
    gameName: searchParams.get('gameName') ?? undefined,
    gameMode: searchParams.get('gameMode') ?? undefined,
    gameStatus: searchParams.get('gameStatus') ?? undefined,
    username: searchParams.get('username') ?? undefined,
    pageUrl: searchParams.get('pageUrl') ?? undefined,
  };
}
