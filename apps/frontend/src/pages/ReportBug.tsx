import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import {
  buildBugReportTemplate,
  getExternalBugReportUrl,
  parseBugReportSearchParams,
} from '../utils/bugReport';

export default function ReportBug() {
  const [searchParams] = useSearchParams();
  const [copyStatus, setCopyStatus] = useState<'idle' | 'copied' | 'failed'>('idle');

  const context = useMemo(
    () => parseBugReportSearchParams(searchParams),
    [searchParams],
  );
  const reportTemplate = useMemo(() => buildBugReportTemplate(context), [context]);
  const externalUrl = getExternalBugReportUrl();

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(reportTemplate);
      setCopyStatus('copied');
      setTimeout(() => setCopyStatus('idle'), 2000);
    } catch {
      setCopyStatus('failed');
      setTimeout(() => setCopyStatus('idle'), 2000);
    }
  };

  return (
    <div className="mx-auto max-w-2xl px-4 pt-20 pb-12 text-left text-white">
      <h1 className="text-3xl font-bold">Report a bug</h1>
      <p className="mt-2 text-gray-300">
        Fill in what went wrong, then copy the report or submit it through your host&apos;s tracker.
      </p>

      {context.gameLink && (
        <dl className="mt-6 grid gap-2 rounded-lg border border-gray-700 bg-gray-800/80 p-4 text-sm">
          <div className="flex gap-2">
            <dt className="text-gray-400">Game link:</dt>
            <dd>{context.gameLink}</dd>
          </div>
          {context.gameName && (
            <div className="flex gap-2">
              <dt className="text-gray-400">Game:</dt>
              <dd>{context.gameName}</dd>
            </div>
          )}
          {context.gameStatus && (
            <div className="flex gap-2">
              <dt className="text-gray-400">Status:</dt>
              <dd>{context.gameStatus}</dd>
            </div>
          )}
        </dl>
      )}

      <label htmlFor="bug-report-body" className="mt-6 block text-sm font-medium text-gray-200">
        Bug report
      </label>
      <textarea
        id="bug-report-body"
        value={reportTemplate}
        readOnly
        rows={18}
        className="mt-2 w-full rounded border border-gray-600 bg-gray-900 px-3 py-2 font-mono text-sm text-gray-100"
      />

      <div className="mt-4 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={handleCopy}
          className="rounded bg-indigo-600 px-4 py-2 font-medium text-white hover:bg-indigo-700"
        >
          {copyStatus === 'copied'
            ? 'Copied!'
            : copyStatus === 'failed'
              ? 'Copy failed'
              : 'Copy report'}
        </button>
        {externalUrl && (
          <a
            href={externalUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded border border-gray-600 px-4 py-2 font-medium text-white hover:border-gray-500 hover:bg-gray-800"
          >
            Open bug tracker
          </a>
        )}
      </div>

      {!externalUrl && (
        <p className="mt-4 text-sm text-gray-500">
          Paste the copied report into Discord, GitHub Issues, or the channel your host provided.
        </p>
      )}
    </div>
  );
}
