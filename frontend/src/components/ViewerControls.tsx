// Stretch and colormap controls for the full-resolution view (F18), plus the
// layer-manager hook and the way back to browsing. Unlike the BIOMASS
// prototype's ViewerControls, there is no polarization/decomposition UI here —
// that was product-specific (products.ts, removed with M2-07a).

import { useAppStore } from '../store';

// Named colormaps rio-tiler/matplotlib ship — generic, not tied to any dataset.
const COLORMAPS = [
  'viridis',
  'plasma',
  'inferno',
  'magma',
  'cividis',
  'turbo',
  'greens',
  'ylgn',
  'rdylgn',
  'spectral',
  'terrain',
  'gist_earth',
  'greys',
];

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
  const clearAll = useAppStore((s) => s.clearAll);
  const addCurrentToLayers = useAppStore((s) => s.addCurrentToLayers);
  const count = useAppStore((s) => Object.keys(s.downloaded).length);
  const showDownloaded = useAppStore((s) => s.showDownloaded);
  const toggleDownloaded = useAppStore((s) => s.toggleDownloaded);
  const datasetTitle = useAppStore(
    (s) => s.datasets.find((d) => d.id === s.datasetId)?.title ?? s.datasetId ?? '',
  );

  return (
    <div className="panel viewer-controls">
      <div className="vc-head">
        <span className="vc-title">
          FULL-RESOLUTION VIEW · {datasetTitle} · {cropToAoi ? 'cropped to AOI' : 'whole selection'}
        </span>
        <div className="results-head-right">
          <span className="vc-sub">
            {count} image{count === 1 ? '' : 's'}
          </span>
          <button
            type="button"
            className={`link-btn${showDownloaded ? '' : ' off'}`}
            title="Show or hide the full-resolution image on the map"
            aria-pressed={showDownloaded}
            onClick={() => toggleDownloaded()}
          >
            {showDownloaded ? '● Hide image' : '○ Show image'}
          </button>
        </div>
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
          className="link-btn"
          disabled={focusLoading}
          title="Measure the 2nd/98th percentile stretch from the source again"
          onClick={() => autoStretch()}
        >
          {focusLoading ? 'measuring…' : 'auto'}
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
          onClick={() => addCurrentToLayers()}
        >
          ＋ Add to layers
        </button>
        <button type="button" className="ghost-btn" onClick={() => exitFocus()}>
          ‹ Choose a different image
        </button>
        <button type="button" className="ghost-btn danger" onClick={() => clearAll()}>
          Clear all
        </button>
      </div>
    </div>
  );
}
