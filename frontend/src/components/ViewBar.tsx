// The "confirm" step of "click, select, confirm" (ENTSCHEIDUNGEN §2) for
// switching from quicklook browsing into full-resolution viewing (M2-07b).
// It replaces the prototype's DownloadBar for this step — an actual file
// download is M2-06/M2-07d, plus (V-4) a direct download of the selection's
// original data over the existing crop route, without first viewing it at
// full resolution.
//
// M3-09 (Otto, 24.09.2026): the single "View full resolution" button became
// two, both entering the same full-resolution view — "Crop to AOI" clips it
// to the drawn AOI, "View full selection" shows the whole scene(s). Grouped
// under one label so it stays clear both are full resolution, not a preview.

import { useAppStore } from '../store';

export default function ViewBar() {
  const selectedIds = useAppStore((s) => s.selectedIds);
  const aoi = useAppStore((s) => s.aoi);
  const focusLoading = useAppStore((s) => s.focusLoading);
  const enterFocus = useAppStore((s) => s.enterFocus);
  const clearSelection = useAppStore((s) => s.clearSelection);
  const addCurrentToLayers = useAppStore((s) => s.addCurrentToLayers);
  const openDownloadForSelection = useAppStore((s) => s.openDownloadForSelection);

  if (selectedIds.length === 0) return null;

  const plural = selectedIds.length > 1;

  return (
    <div className="panel download-bar">
      <span className="download-count">
        {selectedIds.length} scene{plural ? 's' : ''} selected
      </span>
      <div className="view-full-group" role="group" aria-label="View full resolution">
        <span className="view-full-label">Full resolution</span>
        <button
          type="button"
          className="primary-btn"
          disabled={focusLoading || !aoi}
          title={
            aoi
              ? `View the selected scene${plural ? 's' : ''} at full resolution, cut to your AOI`
              : 'Draw an AOI first to crop the full-resolution view to it'
          }
          onClick={() => enterFocus(true)}
        >
          {focusLoading ? 'Loading…' : 'Crop to AOI'}
        </button>
        <button
          type="button"
          className="ghost-btn"
          disabled={focusLoading}
          title={`View the whole selected scene${plural ? 's' : ''} at full resolution, tiled straight from the source`}
          onClick={() => enterFocus(false)}
        >
          {focusLoading ? 'Loading…' : 'View full selection'}
        </button>
      </div>
      <button
        type="button"
        className="ghost-btn"
        title="Pin the selected scenes into the layer manager, at their current (preview) resolution"
        onClick={() => addCurrentToLayers()}
      >
        ＋ Add to layers
      </button>
      <button
        type="button"
        className="ghost-btn"
        title="Download the original data for the selected scenes over the AOI crop, not the preview image"
        onClick={() => openDownloadForSelection()}
      >
        ⇩ Download
      </button>
      <button type="button" className="ghost-btn" disabled={focusLoading} onClick={() => clearSelection()}>
        Clear
      </button>
    </div>
  );
}
