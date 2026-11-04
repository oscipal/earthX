// How the result of a job is drawn (UI-01 §6.11): range, colormap and opacity of a result layer, in the settings bar (`Inspector.tsx`)
// in the place of `ViewerControls` and with the same fields. The default is the one of the statistics (M4-32); "Apply"
// draws the result with what is typed, "Save" keeps that for the layer and the job, "auto" puts the default in the
// fields. What is applied and not saved goes when the settings are closed (Otto, 29.10.2026, zu #234). No unit shows
// here (Otto, 24.10.2026).

import { useMemo, useState } from 'react';

import { fetchResultStatistics } from '../api';
import { channelsAtPercent, channelsOf, rescaleOfChannels } from '../channels';
import { histogramOf, type Histogram } from '../histogram';

import { layerShownName } from '../layerName';
import CopySceneNames from './CopySceneNames';
import type { MapLayer } from '../layers';
import { checkPercent, DEFAULT_PERCENT, NO_RANGE_AT_PERCENT, percentOf, rescaleAtPercent, samePercent, type Percent, type RangeUnit } from '../percentRange';
import { rescaleOf, type PreviewRange } from '../processingPreview';
import { useProcessingStore } from '../processingStore';
import { NOTHING_TO_APPLY, NOTHING_TO_SAVE } from '../render';
import { RGB, RGB_LABEL } from '../processingBands';
import { bandPlacesOfTileUrl, defaultRange, rangeOfTileUrl, renderOfRange, resultPathOfTileUrl } from '../resultLayer';
import { useAppStore } from '../store';
import { sceneNamesOfOrder } from '../sceneNames';
import { ONE_BAND_TIP } from '../viewBand';
import AutoScaleButton from './AutoScaleButton';
import RenderFields, { NO_COLORMAP } from './RenderFields';
import ScaleHistograms from './ScaleHistograms';
import { useHistograms } from './useHistograms';
import Tip from './Tip';
import OpacityRow from './OpacityRow';
import { InspectorHead, InspectorSection, LayerStepper } from './InspectorParts';
import LayerActions from './LayerActions';

// The range as drawn: one pair, or one for each channel of a colour picture (UI-03d).
const scaleText = (range: PreviewRange) => (range.channels?.length ? (rescaleOfChannels(range.channels) ?? '') : `${range.vmin},${range.vmax}`);
const sameRange = (a: PreviewRange, b: PreviewRange) => scaleText(a) === scaleText(b) && a.colormap === b.colormap && samePercent(a.percent, b.percent);

// The histograms of the bands a result layer draws, from the statistics of the result over its mask.
async function resultHistograms(path: string, places: readonly number[]): Promise<Histogram[] | null> {
  const bands = await fetchResultStatistics(path);
  const read = places.map((place) => histogramOf(bands[place]?.statistics));
  return read.length > 0 && read.every((h) => h !== null) ? (read as Histogram[]) : null;
}

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
  const renameLayer = useAppStore((s) => s.renameLayer);
  const setJobRange = useProcessingStore((s) => s.setJobRange);
  // A string, so that a job list that is rebuilt without this order does not change what the selector returns.
  const orderedScenes = useProcessingStore((s) => JSON.stringify(sceneNamesOfOrder(s.jobs.find((j) => j.jobID === layer.result?.jobID)?.order)));
  const sceneNames = useMemo(() => JSON.parse(orderedScenes) as string[], [orderedScenes]);
  const chooseBand = useProcessingStore((s) => s.chooseResultBand);
  // What the typed fields hold, from what the layer draws now; a layer drawn another way starts over.
  const [draft, setDraft] = useState<PreviewRange>(() => ({ ...rangeOfTileUrl(tileUrl), ...(layer.result?.percent ? { percent: layer.result.percent } : {}) }));
  const [problem, setProblem] = useState<string | null>(null);
  // "vmin"/"vmax" as values or as percentiles (NM4-65 part 4): in percentiles the fields hold what was typed, and `draft` the
  // values of the last "Apply".
  const [unit, setUnit] = useState<RangeUnit>(() => (layer.result?.percent ? 'percent' : 'value'));
  const [typed, setTyped] = useState<Percent>(() => layer.result?.percent ?? DEFAULT_PERCENT);
  const [measuring, setMeasuring] = useState(false);
  const path = resultPathOfTileUrl(tileUrl);
  const places = bandPlacesOfTileUrl(tileUrl);
  const histograms = useHistograms(path && info && !info.expired && !info.deleted ? `${path}|${places.join(',')}` : null, () => resultHistograms(path!, places));
  if (!info) return null;
  const colour = info.band === RGB;
  // A colour picture in values: the range of each channel, the one range three times until one is changed.
  const channelValues = draft.channels?.length ? draft.channels : channelsOf(draft.vmin, draft.vmax);
  const editChannel = (channel: number, end: 'vmin' | 'vmax', text: string) =>
    edit({ channels: channelValues.map((range, index) => (index === channel ? { ...range, [end]: text } : range)), ...(channel === 0 ? { [end]: text } : {}) });
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
  const withPercent = (range: PreviewRange, percent: Percent | undefined): PreviewRange => ({
    colormap: range.colormap,
    vmin: range.vmin,
    vmax: range.vmax,
    ...(range.channels?.length ? { channels: range.channels } : {}),
    ...(percent ? { percent } : {}),
  });
  const drawn = withPercent(rangeOfTileUrl(tileUrl), info.percent);
  const saved = withPercent(rangeOfTileUrl(info.savedTileUrl ?? tileUrl), info.savedTileUrl === undefined ? info.percent : (info.savedPercent ?? undefined));
  const typedPair = unit === 'percent' ? percentOf(typed) : null;
  // The look the fields ask for: in percentiles with the pair typed (a pair that is none counts as another look, so that "Apply"
  // is open and says why it cannot).
  const asked = withPercent(draft, unit === 'percent' ? (typedPair ?? { low: typed.low, high: typed.high }) : undefined);
  const canApply = !sameRange(asked, drawn);
  // Also where only the opacity was changed: it is kept with "Save" too (NM4-54, Otto, 1.11.2026).
  const canSave = !sameRange(asked, saved) || layer.saved !== undefined;
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
      // A colour picture takes each channel at the percentiles of its own values (UI-03d).
      const channels = colour ? channelsAtPercent(wanted, checked) : null;
      const { channels: _drop, ...rest } = draft;
      const made: PreviewRange = {
        ...rest,
        ...(channels ? { vmin: channels[0].vmin, vmax: channels[0].vmax, channels } : { vmin: String(range[0]), vmax: String(range[1]) }),
        percent: { low: String(checked.low), high: String(checked.high) },
      };
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
    <div className="viewer-controls scene-view result-controls">
      <InspectorHead
        title={layerShownName(layer)}
        tip={layerShownName(layer)}
        mark={!adjustable && !info.expired && <Tip text={WHOLE_NUMBERS_TIP} />}
        onClose={() => close()}
        rename={{ name: layer.name, onRename: (name) => renameLayer(layer.id, name) }}
        // The scenes of the job the layer was made by, from its copy of the order; none where that is gone, and then no line.
        copy={<CopySceneNames names={sceneNames} />}
      >
        <LayerStepper date={layer.date} />
      </InspectorHead>

      <div className="insp-body">
        <InspectorSection title="Display">
          <div className="vc-render">
            {settable && (
              <RenderFields
                // One band is no choice: the field stays, locked, and says so.
                band={{
                  value: String(info.band ?? 0),
                  options: [
                    ...(info.colour ? [{ value: RGB, label: RGB_LABEL }] : []),
                    ...(bands.length > 0 ? bands : [{ name: '' }]).map((b, place) => ({ value: String(place), label: b.name || `Band ${place + 1}` })),
                  ],
                  title: hasBand ? 'The band of the result this layer draws' : ONE_BAND_TIP,
                  disabled: !hasBand,
                  onChange: (place) => chooseBand(layer.id, place === RGB ? RGB : Number(place)),
                }}
                vmin={unit === 'percent' ? { value: typed.low, onChange: (low) => { setTyped((t) => ({ ...t, low })); setProblem(null); } } : { value: draft.vmin, onChange: (vmin) => edit({ vmin }) }}
                vmax={unit === 'percent' ? { value: typed.high, onChange: (high) => { setTyped((t) => ({ ...t, high })); setProblem(null); } } : { value: draft.vmax, onChange: (vmax) => edit({ vmax }) }}
                unit={{ value: unit, onChange: setUnit }}
                channels={colour ? { values: channelValues, onChange: editChannel } : undefined}
                histograms={
                  histograms && (
                    <ScaleHistograms
                      histograms={histograms}
                      unit={unit}
                      vmin={unit === 'percent' ? typed.low : draft.vmin}
                      vmax={unit === 'percent' ? typed.high : draft.vmax}
                      onVmin={unit === 'percent' ? (low) => { setTyped((t) => ({ ...t, low })); setProblem(null); } : (vmin) => edit({ vmin })}
                      onVmax={unit === 'percent' ? (high) => { setTyped((t) => ({ ...t, high })); setProblem(null); } : (vmax) => edit({ vmax })}
                      channels={colour ? { values: channelValues, onChange: editChannel } : undefined}
                    />
                  )
                }
                colormap={info.band === RGB ? { fixed: NO_COLORMAP, title: 'True colour: three bands, no colormap' } : { value: draft.colormap, onChange: (colormap) => edit({ colormap }) }}
                scale
              />
            )}
            <OpacityRow layer={layer} />
            {settable && (
              <div className="vc-buttons">
                <AutoScaleButton title={unit === 'percent' ? 'Put the usual stretch in the fields: the 2nd to the 98th percentile' : 'Put the range of the statistics of this result in the fields'} busy={measuring} onClick={auto} />
                <button
                  type="button"
                  className="btn vc-apply"
                  aria-disabled={!canApply || undefined}
                  title={canApply ? 'Draw the result with these values; not kept until you save' : NOTHING_TO_APPLY}
                  onClick={apply}
                >
                  Apply
                </button>
                <button
                  type="button"
                  className="btn primary vc-save"
                  aria-disabled={!canSave || undefined}
                  title={canSave ? SAVE_TIP[info.own ? 'own' : info.bands && info.bands.length > 1 ? 'band' : 'job'] : NOTHING_TO_SAVE}
                  onClick={keep}
                >
                  Save
                </button>
              </div>
            )}
          </div>
          {settable && problem && (
            <p className="hint-text warn" role="alert">
              {problem}
            </p>
          )}
        </InspectorSection>

        <InspectorSection title="Actions">
          <LayerActions
            layer={layer}
            beforeCopy={async () => {
              if (!settable || !canApply) return true;
              const range = known() ?? (await resolve());
              return range !== null && draw(range);
            }}
          />
        </InspectorSection>
      </div>
    </div>
  );
}

export default function ResultControls() {
  const layer = useAppStore((s) => s.layers.find((l) => l.id === s.resultViewLayerId && l.derived === 'result'));
  if (!layer) return null;
  // The key follows what the layer draws: another picture starts the fields over.
  return <Controls key={`${layer.id}|${layer.overlays.find((o) => o.kind === 'raster')?.tileUrl}`} layer={layer} />;
}
