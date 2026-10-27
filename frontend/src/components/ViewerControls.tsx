// The full-resolution view: its head, the stretch and colormap controls (F18), the layer-manager hook and the way
// back to browsing. Unlike the BIOMASS prototype's ViewerControls, there is no polarization/decomposition UI here —
// that was product-specific (products.ts, removed with M2-07a).
//
// Otto, 27.10.2026 (zu #211): the head is one line and never wider than the two rows of buttons below it, which share
// one grid and decide the width of the whole view; what does not fit is cut with "…" and given in full as the tooltip.
// "Change image" leaves the view and keeps the choice of scenes; "Clear" takes the view off the map and drops the
// choice. Neither touches "Hide results".

import { processBlockReason } from '../processingOrder';
import { useProcessingStore } from '../processingStore';
import { COLORMAPS } from '../render';
import { useAppStore } from '../store';
import { viewDates, viewKind } from '../viewKind';

function Eye({ off }: { off: boolean }) {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3.6-6.5 10-6.5S22 12 22 12s-3.6 6.5-10 6.5S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
      {off && <path d="M4 4l16 16" />}
    </svg>
  );
}

export default function ViewerControls() {
  const pendingColormapName = useAppStore((s) => s.pendingColormapName);
  const pendingVmin = useAppStore((s) => s.pendingVmin);
  const pendingVmax = useAppStore((s) => s.pendingVmax);
  const setPendingColormapName = useAppStore((s) => s.setPendingColormapName);
  const setPendingVmin = useAppStore((s) => s.setPendingVmin);
  const setPendingVmax = useAppStore((s) => s.setPendingVmax);
  const applyRender = useAppStore((s) => s.applyRender);
  const autoStretch = useAppStore((s) => s.autoStretch);
  const focusLoading = useAppStore((s) => s.focusLoading);
  const cropToAoi = useAppStore((s) => s.cropToAoi);
  const exitFocus = useAppStore((s) => s.exitFocus);
  const changeImage = useAppStore((s) => s.changeImage);
  const addCurrentToLayers = useAppStore((s) => s.addCurrentToLayers);
  const pinLoading = useAppStore((s) => s.pinLoading);
  const count = useAppStore((s) => Object.keys(s.downloaded).length);
  const showDownloaded = useAppStore((s) => s.showDownloaded);
  const toggleDownloaded = useAppStore((s) => s.toggleDownloaded);
  const processBlock = useAppStore((s) =>
    processBlockReason(
      s.datasets.find((d) => d.id === s.datasetId),
      Object.keys(s.downloaded).length,
    ),
  );
  const processFocusView = useProcessingStore((s) => s.processFocusView);
  const datasetTitle = useAppStore(
    (s) => s.datasets.find((d) => d.id === s.datasetId)?.title ?? s.datasetId ?? '',
  );
  // The scenes of the view, for the date in its head.
  const date = useAppStore((s) => viewDates(s.groups.flatMap((g) => g.items).filter((it) => it.id in s.downloaded)));
  // What the head cuts short, in full.
  const title = [datasetTitle, date, cropToAoi ? 'cropped to the AOI' : 'whole scene'].filter(Boolean).join(' · ') + (count > 1 ? ` · ${count} scenes merged` : '');

  return (
    <div className="panel viewer-controls scene-view">
      <div className="vc-head">
        <span className="vc-title" title={title}>
          {[datasetTitle, date, viewKind(cropToAoi, count)].filter(Boolean).join(' · ')}
        </span>
        <button
          type="button"
          className={`vc-eye${showDownloaded ? '' : ' off'}`}
          title={showDownloaded ? 'Hide image' : 'Show image'}
          aria-label={showDownloaded ? 'Hide image' : 'Show image'}
          onClick={() => toggleDownloaded()}
        >
          <Eye off={!showDownloaded} />
        </button>
      </div>

      <div className="vc-render">
        <label className="vc-field">
          <span>Colormap</span>
          <select value={pendingColormapName} onChange={(e) => setPendingColormapName(e.target.value)}>
            <option value="">— none —</option>
            {COLORMAPS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="vc-field vc-num">
          <span>vmin</span>
          <input
            type="number"
            value={pendingVmin}
            placeholder="auto"
            onChange={(e) => setPendingVmin(e.target.value)}
          />
        </label>
        <label className="vc-field vc-num">
          <span>vmax</span>
          <input
            type="number"
            value={pendingVmax}
            placeholder="auto"
            onChange={(e) => setPendingVmax(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="ghost-btn vc-auto"
          disabled={focusLoading}
          title="Measure the 2nd/98th percentile stretch from the source again"
          onClick={() => autoStretch()}
        >
          {focusLoading ? 'measuring…' : 'auto-scale'}
        </button>
        <button type="button" className="primary-btn vc-apply" onClick={() => applyRender()}>
          Apply
        </button>
      </div>

      <div className="vc-actions">
        <button
          type="button"
          className="ghost-btn"
          title="Pin this image into the layer manager"
          disabled={pinLoading}
          onClick={() => addCurrentToLayers()}
        >
          {pinLoading ? 'Loading…' : '＋ Add to layers'}
        </button>
        <button
          type="button"
          className="ghost-btn"
          disabled={processBlock !== null}
          title={processBlock ?? 'Build a processing job for the scenes of this view'}
          onClick={() => void processFocusView()}
        >
          ⚙ Process
        </button>
        <button type="button" className="ghost-btn" title="Remove this view and choose another scene from the results" onClick={() => changeImage()}>
          ‹ Change image
        </button>
        <button type="button" className="ghost-btn" title="Remove this view from the map" onClick={() => exitFocus()}>
          ✕ Clear
        </button>
      </div>
    </div>
  );
}
