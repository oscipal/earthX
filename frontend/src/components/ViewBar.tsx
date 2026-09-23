// The "confirm" step of "click, select, confirm" (ENTSCHEIDUNGEN §2) for
// switching from quicklook browsing into full-resolution viewing (M2-07b).
// It replaces the prototype's DownloadBar for this step — an actual file
// download is M2-06/M2-07d, not this.

import { useAppStore } from '../store';

export default function ViewBar() {
  const selectedIds = useAppStore((s) => s.selectedIds);
  const focusLoading = useAppStore((s) => s.focusLoading);
  const enterFocus = useAppStore((s) => s.enterFocus);
  const clearSelection = useAppStore((s) => s.clearSelection);
  const addCurrentToLayers = useAppStore((s) => s.addCurrentToLayers);

  if (selectedIds.length === 0) return null;

  return (
    <div className="panel download-bar">
      <span className="download-count">
        {selectedIds.length} scene{selectedIds.length > 1 ? 's' : ''} selected
      </span>
      <button
        type="button"
        className="primary-btn"
        disabled={focusLoading}
        title={
          selectedIds.length > 1
            ? 'Show the selected scenes at full resolution, tiled straight from the source'
            : 'Show the scene at full resolution, tiled straight from the source'
        }
        onClick={() => enterFocus()}
      >
        {focusLoading ? 'Loading…' : 'View full resolution'}
      </button>
      <button
        type="button"
        className="ghost-btn"
        title="Pin the selected scenes into the layer manager, at their current (preview) resolution"
        onClick={() => addCurrentToLayers()}
      >
        ＋ Add to layers
      </button>
      <button type="button" className="ghost-btn" disabled={focusLoading} onClick={() => clearSelection()}>
        Clear
      </button>
    </div>
  );
}
