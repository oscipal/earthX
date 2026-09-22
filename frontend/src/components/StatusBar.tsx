import { useEffect } from 'react';

import { zoomFloorHint } from '../datasets';
import { useAppStore } from '../store';

export default function StatusBar() {
  const error = useAppStore((s) => s.error);
  const notice = useAppStore((s) => s.notice);
  const searching = useAppStore((s) => s.searching);
  const downloading = useAppStore((s) => s.downloading);
  const setError = useAppStore((s) => s.setError);
  const setNotice = useAppStore((s) => s.setNotice);
  const datasets = useAppStore((s) => s.datasets);
  const datasetId = useAppStore((s) => s.datasetId);
  const mapZoom = useAppStore((s) => s.mapZoom);
  const hasResults = useAppStore((s) => s.groups.length > 0);

  // Why the map is empty below a dataset's lowest released level (M2-10). It
  // lives here, in the one overlay that is always on screen, because the control
  // panel it started in is slid away by `runSearch` — so it was never visible in
  // the situation it is for. Only once a search has results: before that the map
  // is empty for the ordinary reason, and a standing hint nobody needs is one
  // nobody reads.
  const zoomHint = hasResults
    ? zoomFloorHint(
        datasets.find((d) => d.id === datasetId),
        mapZoom,
      )
    : null;

  // Info notices fade out on their own after a few seconds (errors persist
  // until dismissed).
  useEffect(() => {
    if (!notice) return;
    const id = window.setTimeout(() => setNotice(null), 5000);
    return () => window.clearTimeout(id);
  }, [notice, setNotice]);

  const busy = searching
    ? 'Searching STAC catalog…'
    : downloading
      ? 'Processing on the server (crop / decomposition)…'
      : null;

  return (
    <div className="status-stack">
      {busy && (
        <div className="toast busy">
          <span className="spinner" aria-hidden="true" />
          {busy}
        </div>
      )}
      {error && (
        <div className="toast error" role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => setError(null)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}
      {notice && (
        <div className="toast notice fade" key={notice}>
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)} aria-label="Dismiss">
            ✕
          </button>
        </div>
      )}
      {/* A state, not an event: it stands as long as the zoom does, so it carries
          no dismiss button and does not fade like a notice. */}
      {zoomHint && (
        <div className="toast hint" role="status">
          <span>{zoomHint}</span>
        </div>
      )}
    </div>
  );
}
