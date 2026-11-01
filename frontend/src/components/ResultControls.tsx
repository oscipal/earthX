// How the result of a job is drawn (UI-01 §6.11): range, colormap and opacity of a result layer, in the place
// of `ViewerControls` and with the same fields. The default is the one of the statistics (M4-32); "Apply"
// draws the result with what is typed, "Save" keeps that for the layer and the job, "auto" puts the default in the
// fields. What is applied and not saved goes when the settings are closed (Otto, 29.10.2026, zu #234). No unit shows
// here (Otto, 24.10.2026).

import { useState } from 'react';

import { fetchResultStatistics } from '../api';

import { layerShownName } from '../layerName';
import type { MapLayer } from '../layers';
import { checkPercent, DEFAULT_PERCENT, NO_RANGE_AT_PERCENT, percentOf, rescaleAtPercent, samePercent, type Percent, type RangeUnit } from '../percentRange';
import { rescaleOf, type PreviewRange } from '../processingPreview';
import { useProcessingStore } from '../processingStore';
import { NOTHING_TO_APPLY, NOTHING_TO_SAVE } from '../render';
import { RGB, RGB_LABEL } from '../processingBands';
import { bandPlacesOfTileUrl, defaultRange, rangeOfTileUrl, renderOfRange, resultPathOfTileUrl } from '../resultLayer';
import { useAppStore } from '../store';
import AutoScaleButton from './AutoScaleButton';
import RenderFields from './RenderFields';
import Tip from './Tip';
import OpacityRow from './OpacityRow';
import CloseButton from './CloseButton';

const sameRange = (a: PreviewRange, b: PreviewRange) => a.vmin === b.vmin && a.vmax === b.vmax && a.colormap === b.colormap && samePercent(a.percent, b.percent);

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
  const restyle = useAppStore((s) => s.restyleResultLayer);
  const save = useAppStore((s) => s.saveResultLayer);
  const close = useAppStore((s) => s.closeResultView);
  const setJobRange = useProcessingStore((s) => s.setJobRange);
  const chooseBand = useProcessingStore((s) => s.chooseResultBand);
  // What the typed fields hold, from what the layer draws now; a layer drawn another way starts over.
  const [draft, setDraft] = useState<PreviewRange>(() => ({ ...rangeOfTileUrl(tileUrl), ...(layer.result?.percent ? { percent: layer.result.percent } : {}) }));
  const [problem, setProblem] = useState<string | null>(null);
  // "vmin"/"vmax" as values or as percentiles (NM4-65 part 4): in percentiles the fields hold what was typed, and `draft` the
  // values of the last "Apply".
  const [unit, setUnit] = useState<RangeUnit>(() => (layer.result?.percent ? 'percent' : 'value'));
  const [typed, setTyped] = useState<Percent>(() => layer.result?.percent ?? DEFAULT_PERCENT);
  const [measuring, setMeasuring] = useState(false);
  if (!info) return null;
  const adjustable = info.dataType !== null && /^float/.test(info.dataType);
  // What cannot be set at all is not shown: a result of whole numbers is drawn as it is, an expired one not at all.
  const settable = adjustable && !info.expired && !info.deleted;
  // The dropdown "Band" is there for a result of several bands, as the box of every layer has it where there is a choice.
  const bands = info.bands ?? [];
  const hasBand = bands.length > 1;
  const edit = (patch: Partial<PreviewRange>) => {
    setDraft((d) => ({ ...d, ...patch }));
    setProblem(null);
  };

  // What the layer draws now and what it is saved with: "Apply" is for the first to change, "Save" for the second.
  const withPercent = (range: PreviewRange, percent: Percent | undefined): PreviewRange => ({ colormap: range.colormap, vmin: range.vmin, vmax: range.vmax, ...(percent ? { percent } : {}) });
  const drawn = withPercent(rangeOfTileUrl(tileUrl), info.percent);
  const saved = withPercent(rangeOfTileUrl(info.savedTileUrl ?? tileUrl), info.savedTileUrl === undefined ? info.percent : (info.savedPercent ?? undefined));
  const typedPair = unit === 'percent' ? percentOf(typed) : null;
  // The look the fields ask for: in percentiles with the pair typed (a pair that is none counts as another look, so that "Apply"
  // is open and says why it cannot).
  const asked = withPercent(draft, unit === 'percent' ? (typedPair ?? { low: typed.low, high: typed.high }) : undefined);
  const canApply = !sameRange(asked, drawn);
  const canSave = !sameRange(asked, saved);
  const render = (range: PreviewRange) => {
    const made = renderOfRange(range);
    if (!made) {
      const checked = rescaleOf(range);
      setProblem('problem' in checked ? checked.problem : null);
    }
    return made;
  };
  // The values the percentiles typed give: the statistics of the result over its mask, for the bands this layer draws. `null`,
  // with the reason said, where there are none.
  const resolve = async (): Promise<PreviewRange | null> => {
    const checked = checkPercent(typed);
    if ('problem' in checked) {
      setProblem(checked.problem);
      return null;
    }
    const path = resultPathOfTileUrl(tileUrl);
    if (!path) return null;
    setMeasuring(true);
    try {
      const bands = await fetchResultStatistics(path);
      const wanted = bandPlacesOfTileUrl(tileUrl).flatMap((place) => (bands[place]?.statistics ? [bands[place].statistics] : []));
      const range = rescaleAtPercent(wanted, checked);
      if (!range) {
        setProblem(NO_RANGE_AT_PERCENT);
        return null;
      }
      const made: PreviewRange = { ...draft, vmin: String(range[0]), vmax: String(range[1]), percent: { low: String(checked.low), high: String(checked.high) } };
      setDraft(made);
      setProblem(null);
      return made;
    } catch (error) {
      setProblem(`Could not measure the percentiles: ${error instanceof Error ? error.message : String(error)}`);
      return null;
    } finally {
      setMeasuring(false);
    }
  };
  // What the fields ask for as a look with values, where that needs no statistics: values as typed, percentiles that are the
  // ones drawn. Anything else is read first (`resolve`), so that "Apply" and "Save" of values stay done when the click returns.
  const known = (): PreviewRange | null => (unit === 'value' ? withPercent(draft, undefined) : typedPair && samePercent(typedPair, drawn.percent) ? withPercent(draft, typedPair) : null);
  const draw = (range: PreviewRange) => {
    const made = render(range);
    if (made) restyle(layer.id, made, range.percent ?? null);
    return made !== null;
  };
  const apply = () => {
    if (!canApply) return;
    const range = known();
    if (range) draw(range);
    else void resolve().then((read) => read && draw(read));
  };
  // Draws what is typed, if it is not drawn yet, and keeps it for the layer and for the job; the default of the statistics
  // is no range set by hand.
  const keepRange = (range: PreviewRange) => {
    const made = render(range);
    if (!made) return;
    if (!sameRange(range, drawn)) restyle(layer.id, made, range.percent ?? null);
    save(layer.id);
    // A layer of its own band keeps its look for itself: the job and the layer it came from stay as they are.
    if (info.own) return;
    const fallback = defaultRange(info, useProcessingStore.getState().range);
    // A result of several bands keeps the range of the band it draws, by the band's name ("RGB" for the colour picture).
    const named = info.bands && info.bands.length > 1 ? (info.band === RGB ? RGB : (info.bands[info.band ?? 0]?.name ?? '')) : undefined;
    setJobRange(info.jobID, fallback && sameRange(range, fallback) ? null : range, named);
  };
  const keep = () => {
    if (!canSave) return;
    const range = known();
    if (range) keepRange(range);
    else void resolve().then((read) => read && keepRange(read));
  };
  const auto = () => {
    // In percentiles the usual stretch is the 2nd to the 98th.
    if (unit === 'percent') setTyped(DEFAULT_PERCENT);
    else setDraft(defaultRange(info, useProcessingStore.getState().range) ?? { vmin: '', vmax: '', colormap: '' });
    setProblem(null);
  };

  return (
    <div className="panel viewer-controls scene-view result-controls">
      <div className="vc-head">
        <span className="vc-title" title={layerShownName(layer)}>{layerShownName(layer).toUpperCase()}</span>
        <div className="results-head-right">
          <CloseButton title="Close" onClick={() => close()} />
          {!adjustable && !info.expired && <Tip text={WHOLE_NUMBERS_TIP} />}
        </div>
      </div>

      <div className={`vc-render${hasBand ? ' has-index' : ''}`}>
        {settable && (
          <>
            <RenderFields
              band={
                hasBand
                  ? {
                      value: String(info.band ?? 0),
                      options: [
                        ...(info.colour ? [{ value: RGB, label: RGB_LABEL }] : []),
                        ...bands.map((b, place) => ({ value: String(place), label: b.name || `Band ${place + 1}` })),
                      ],
                      title: 'The band of the result this layer draws',
                      onChange: (place) => chooseBand(layer.id, place === RGB ? RGB : Number(place)),
                    }
                  : undefined
              }
              vmin={unit === 'percent' ? { value: typed.low, onChange: (low) => { setTyped((t) => ({ ...t, low })); setProblem(null); } } : { value: draft.vmin, onChange: (vmin) => edit({ vmin }) }}
              vmax={unit === 'percent' ? { value: typed.high, onChange: (high) => { setTyped((t) => ({ ...t, high })); setProblem(null); } } : { value: draft.vmax, onChange: (vmax) => edit({ vmax }) }}
              unit={{ value: unit, onChange: setUnit }}
              colormap={info.band === RGB ? { fixed: RGB_LABEL, title: 'True colour: three bands, no colormap' } : { value: draft.colormap, onChange: (colormap) => edit({ colormap }) }}
            />
            <div className="vc-buttons">
              <AutoScaleButton title={unit === 'percent' ? 'Put the usual stretch in the fields: the 2nd to the 98th percentile' : 'Put the range of the statistics of this result in the fields'} busy={measuring} onClick={auto} />
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
      </div>
      <OpacityRow layer={layer} />
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
