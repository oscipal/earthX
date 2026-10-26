// How the result of a job is drawn (UI-01 §6.11): range, colormap and opacity of a result layer, in the place
// of `ViewerControls` and with the same fields. The default is the one of the statistics (M4-32); "Apply"
// draws the result with what is typed and keeps it for the job, "Auto" goes back to the default. No unit
// shows here (Otto, 24.10.2026).

import { useState } from 'react';

import type { MapLayer } from '../layers';
import { rescaleOf, type PreviewRange } from '../processingPreview';
import { useProcessingStore } from '../processingStore';
import { COLORMAPS } from '../render';
import { defaultRange, rangeOfTileUrl, renderOfRange } from '../resultLayer';
import { useAppStore } from '../store';
import Tip from './Tip';

const WHOLE_NUMBERS_TIP = 'A result of whole numbers is drawn as it is: it has no range or colormap to set.';

function Controls({ layer }: { layer: MapLayer }) {
  const info = layer.result;
  const tileUrl = layer.overlays.find((o) => o.kind === 'raster')?.tileUrl ?? '';
  const setOpacity = useAppStore((s) => s.setLayerOpacity);
  const restyle = useAppStore((s) => s.restyleResultLayer);
  const close = useAppStore((s) => s.closeResultView);
  const setJobRange = useProcessingStore((s) => s.setJobRange);
  // What the typed fields hold, from what the layer draws now; a layer drawn another way starts over.
  const [draft, setDraft] = useState<PreviewRange>(() => rangeOfTileUrl(tileUrl));
  const [problem, setProblem] = useState<string | null>(null);
  if (!info) return null;
  const adjustable = info.dataType !== null && /^float/.test(info.dataType);
  // What cannot be set at all is not shown: a result of whole numbers is drawn as it is, an expired one not at all.
  const settable = adjustable && !info.expired;
  const edit = (patch: Partial<PreviewRange>) => {
    setDraft((d) => ({ ...d, ...patch }));
    setProblem(null);
  };

  const apply = () => {
    const render = renderOfRange(draft);
    if (!render) {
      const checked = rescaleOf(draft);
      setProblem('problem' in checked ? checked.problem : null);
      return;
    }
    setJobRange(info.jobID, draft);
    restyle(layer.id, render);
  };
  const auto = () => {
    const fallback = defaultRange(info, useProcessingStore.getState().range);
    setJobRange(info.jobID, null);
    restyle(layer.id, fallback ? (renderOfRange(fallback) ?? {}) : {});
    setDraft(fallback ?? { vmin: '', vmax: '', colormap: '' });
    setProblem(null);
  };

  return (
    <div className="panel viewer-controls result-controls">
      <div className="vc-head">
        <span className="vc-title">{layer.name.toUpperCase()}</span>
        <div className="results-head-right">
          <button type="button" className="link-btn" title="Close this view and show the search results again" onClick={() => close()}>
            ‹ Close
          </button>
          {!adjustable && !info.expired && <Tip text={WHOLE_NUMBERS_TIP} />}
        </div>
      </div>

      <div className="vc-render">
        {settable && (
          <>
            <label className="vc-field">
              <span>Colormap</span>
              <select value={draft.colormap} onChange={(e) => edit({ colormap: e.target.value })}>
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
              <input type="number" value={draft.vmin} onChange={(e) => edit({ vmin: e.target.value })} />
            </label>
            <label className="vc-field vc-num">
              <span>vmax</span>
              <input type="number" value={draft.vmax} onChange={(e) => edit({ vmax: e.target.value })} />
            </label>
            <button type="button" className="link-btn" title="Back to the range of the statistics of this result" onClick={auto}>
              auto
            </button>
          </>
        )}
        <label className="vc-field">
          <span>Opacity</span>
          <input
            type="range"
            className="lm-opacity"
            min={0}
            max={1}
            step={0.05}
            value={layer.opacity}
            title={`Opacity ${Math.round(layer.opacity * 100)}%`}
            onChange={(e) => setOpacity(layer.id, Number(e.target.value))}
          />
        </label>
        {settable && (
          <button type="button" className="primary-btn vc-apply" onClick={apply}>
            Apply
          </button>
        )}
      </div>
      {settable && problem && (
        <p className="hint-text warn" role="alert">
          {problem}
        </p>
      )}
    </div>
  );
}

export default function ResultControls() {
  const layer = useAppStore((s) => s.layers.find((l) => l.id === s.resultViewLayerId && l.derived === 'result'));
  if (!layer) return null;
  // The key follows what the layer draws: another picture starts the fields over.
  return <Controls key={`${layer.id}|${layer.overlays.find((o) => o.kind === 'raster')?.tileUrl}`} layer={layer} />;
}
