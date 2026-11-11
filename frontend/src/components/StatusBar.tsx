import { useEffect } from 'react';

import { hasResultsPanel } from '../sections';
import { useAppStore } from '../store';
import CloseButton from './CloseButton';

export default function StatusBar() {
  const error = useAppStore((s) => s.error);
  const notice = useAppStore((s) => s.notice);
  const searching = useAppStore((s) => s.searching);
  const downloading = useAppStore((s) => s.downloading);
  const setError = useAppStore((s) => s.setError);
  const setNotice = useAppStore((s) => s.setNotice);
  // Info notices fade out on their own after a few seconds (errors persist
  // until dismissed).
  useEffect(() => {
    if (!notice) return;
    const id = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(id);
  }, [notice, setNotice]);

  // A search that checks the clouds inside the AOI walks on page by page (DS-03b). Its progress stands in the head of the
  // results; while there are none (nothing within the limit yet), it stands here, with "Stop".
  const checking = useAppStore((s) => s.aoiWalking && !hasResultsPanel(s.sections));
  const counts = useAppStore((s) => Object.values(s.searchContext?.answer?.aoiFilter ?? {})[0]);
  const stopSearch = useAppStore((s) => s.stopSearch);

  const busy = searching
    ? checking && counts
      ? `Checking scenes · ${counts.found} found / ${counts.checked} checked${counts.unreadable > 0 ? ` / ${counts.unreadable} skipped` : ''}`
      : 'Searching STAC catalog…'
    : downloading
      ? 'Processing on the server (crop / decomposition)…'
      : null;

  return (
    <div className="status-stack">
      {busy && (
        <div className="toast busy">
          <span className="spinner" aria-hidden="true" />
          {busy}
          {checking && (
            <button type="button" className="btn aoi-stop" data-tip-level="advanced" data-tip="Stop checking. What is found stays." onClick={stopSearch}>
              Stop
            </button>
          )}
        </div>
      )}
      {error && (
        <div className="toast error" role="alert">
          <span>{error}</span>
          <CloseButton onClick={() => setError(null)} />
        </div>
      )}
      {notice && (
        <div className="toast notice fade" key={notice}>
          <span>{notice}</span>
          <CloseButton onClick={() => setNotice(null)} />
        </div>
      )}
    </div>
  );
}
