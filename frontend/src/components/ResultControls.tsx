// How the result of a job is drawn (UI-01 §6.11): range, colormap and opacity of a result layer, in the place
// of `ViewerControls` and with the same fields. The default is the one of the statistics (M4-32); "Apply"
// draws the result with what is typed, "Save" keeps that for the layer and the job, "auto" puts the default in the
// fields. What is applied and not saved goes when the settings are closed (Otto, 29.10.2026, zu #234). No unit shows
// here (Otto, 24.10.2026).

import { useState } from 'react';

import type { MapLayer } from '../layers';
import { rescaleOf, type PreviewRange } from '../processingPreview';
import { useProcessingStore } from '../processingStore';
import { NOTHING_TO_APPLY, NOTHING_TO_SAVE } from '../render';
import { RGB, RGB_LABEL } from '../processingBands';
import { defaultRange, rangeOfTileUrl, renderOfRange } from '../resultLayer';
import { useAppStore } from '../store';
import AutoScaleButton from './AutoScaleButton';
import RenderFields from './RenderFields';
import Tip from './Tip';
import CloseButton from './CloseButton';

const sameRange = (a: PreviewRange, b: PreviewRange) => a.vmin === b.vmin && a.vmax === b.vmax && a.colormap === b.colormap;

const SAVE_TIP = {
  job: 'Keep these values for this layer and for every layer of this job',
  band: 'Keep these values for this band, in this layer and in every layer of this job',
  // A layer made from one band of another keeps its look for itself (NM4-65 part 2).
  own: 'Keep these values for this layer only',
};

const WHOLE_NUMBERS_TIP = 'A result of whole numbers is drawn as it is: it has no range or colormap to set.';

function Controls({ layer }: { layer: MapLayer }) {
  const info = layer.result;
  const tileUrl = layer.overlays.find((o) => o.kind === 'raster')?.tileUrl ?? '';
  const setOpacity = useAppStore((s) => s.setLayerOpacity);
  const restyle = useAppStore((s) => s.restyleResultLayer);
  const save = useAppStore((s) => s.saveResultLayer);
  const close = useAppStore((s) => s.closeResultView);
  const setJobRange = useProcessingStore((s) => s.setJobRange);
  const chooseBand = useProcessingStore((s) => s.chooseResultBand);
  // What the typed fields hold, from what the layer draws now; a layer drawn another way starts over.
  const [draft, setDraft] = useState<PreviewRange>(() => rangeOfTileUrl(tileUrl));
  const [problem, setProblem] = useState<string | null>(null);
  if (!info) return null;
  const adjustable = info.dataType !== null && /^float/.test(info.dataType);
  // What cannot be set at all is not shown: a result of whole numbers is drawn as it is, an expired one not at all.
  const settable = adjustable && !info.expired && !info.deleted;
  const edit = (patch: Partial<PreviewRange>) => {
    setDraft((d) => ({ ...d, ...patch }));
    setProblem(null);
  };

  // What the layer draws now and what it is saved with: "Apply" is for the first to change, "Save" for the second.
  const drawn = rangeOfTileUrl(tileUrl);
  const saved = rangeOfTileUrl(info.savedTileUrl ?? tileUrl);
  const canApply = !sameRange(draft, drawn);
  const canSave = !sameRange(draft, saved);
  const render = () => {
    const made = renderOfRange(draft);
    if (!made) {
      const checked = rescaleOf(draft);
      setProblem('problem' in checked ? checked.problem : null);
    }
    return made;
  };
  const apply = () => {
    if (!canApply) return;
    const made = render();
    if (made) restyle(layer.id, made);
  };
  // Draws what is typed, if it is not drawn yet, and keeps it for the layer and for the job; the default of the statistics
  // is no range set by hand.
  const keep = () => {
    if (!canSave) return;
    const made = render();
    if (!made) return;
    if (canApply) restyle(layer.id, made);
    save(layer.id);
    // A layer of its own band keeps its look for itself: the job and the layer it came from stay as they are.
    if (info.own) return;
    const fallback = defaultRange(info, useProcessingStore.getState().range);
    // A result of several bands keeps the range of the band it draws, by the band's name ("RGB" for the colour picture).
    const named = info.bands && info.bands.length > 1 ? (info.band === RGB ? RGB : (info.bands[info.band ?? 0]?.name ?? '')) : undefined;
    setJobRange(info.jobID, fallback && sameRange(draft, fallback) ? null : draft, named);
  };
  const auto = () => {
    setDraft(defaultRange(info, useProcessingStore.getState().range) ?? { vmin: '', vmax: '', colormap: '' });
    setProblem(null);
  };

  return (
    <div className="panel viewer-controls result-controls">
      <div className="vc-head">
        <span className="vc-title">{layer.name.toUpperCase()}</span>
        <div className="results-head-right">
          <CloseButton title="Close" onClick={() => close()} />
          {!adjustable && !info.expired && <Tip text={WHOLE_NUMBERS_TIP} />}
        </div>
      </div>

      <div className="vc-render">
        {settable && (
          <>
            <RenderFields
              band={
                info.bands && info.bands.length > 1
                  ? {
                      value: String(info.band ?? 0),
                      options: [
                        ...(info.colour ? [{ value: RGB, label: RGB_LABEL }] : []),
                        ...info.bands.map((b, place) => ({ value: String(place), label: b.name || `Band ${place + 1}` })),
                      ],
                      title: 'The band of the result this layer draws',
                      onChange: (place) => chooseBand(layer.id, place === RGB ? RGB : Number(place)),
                    }
                  : undefined
              }
              vmin={{ value: draft.vmin, onChange: (vmin) => edit({ vmin }) }}
              vmax={{ value: draft.vmax, onChange: (vmax) => edit({ vmax }) }}
              colormap={info.band === RGB ? null : { value: draft.colormap, onChange: (colormap) => edit({ colormap }) }}
            />
            <div className="vc-buttons">
              <AutoScaleButton title="Put the range of the statistics of this result in the fields" onClick={auto} />
              <button
                type="button"
                className="ghost-btn vc-apply"
                aria-disabled={!canApply || undefined}
                title={canApply ? 'Draw the result with these values; not kept until you save' : NOTHING_TO_APPLY}
                onClick={apply}
              >
                Apply
              </button>
              <button
                type="button"
                className="primary-btn vc-save"
                aria-disabled={!canSave || undefined}
                title={canSave ? SAVE_TIP[info.own ? 'own' : info.bands && info.bands.length > 1 ? 'band' : 'job'] : NOTHING_TO_SAVE}
                onClick={keep}
              >
                Save
              </button>
            </div>
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
