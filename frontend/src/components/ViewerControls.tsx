// The full-resolution view in the settings bar (`Inspector.tsx`): its head, the stretch and colormap controls (F18), the layer-manager
// hook and the way back to browsing. Unlike the BIOMASS prototype's ViewerControls, there is no polarization/decomposition UI here —
// that was product-specific (products.ts, removed with M2-07a).
//
// Otto, 27.10.2026 (zu #211): what does not fit the head is cut with "…" and given in full as the tooltip.
// "Change image" leaves the view, keeps the choice of scenes and shows the search results; the red x takes the view off the map and
// drops it, as "Clear" did (Otto, 2.11.2026: no "Clear" any more).

import { useMemo, useState } from 'react';

import { pageCount, pageSlice } from '../datasetPages';
import { DRAW_AOI_TO_CROP, hasOriginalFiles, noOriginalsReason } from '../download';
import { originalsTitle, scenesOf, summaryOf, summaryText } from '../originals';
import { processBlockReason } from '../processingOrder';
import { useProcessingStore } from '../processingStore';
import { defaultRenderOf, drawsClasses, showsColormap } from '../datasets';
import { isComposite, quickPresetsOf } from '../quickPresets';
import { trueColorOf } from '../processingOrder';
import { BAND_TIP, bandAssetsOf, ONE_BAND_TIP } from '../viewBand';
import { appliedRenderFrom, colourChannelsOf, lookChanged, NOTHING_TO_APPLY, NOTHING_TO_APPLY_TO_ALL_LAYER, NOTHING_TO_SAVE, NOTHING_TO_SAVE_IMAGES, NOTHING_TO_SAVE_ONE_IMAGE } from '../render';
import { histogramOf, type Histogram } from '../histogram';
import { colourView, datasetSavable, enhanceOn, shownImageOf, useAppStore, viewMeasure } from '../store';
import { datasetIdsOf, imagesOf, imagesOfDataset, satellitesOf, sectionsForView } from '../viewImages';
import { indexBlockOf, indexNote, indexNoteTip, viewIndexOf } from '../viewIndex';
import { computedNoteOf, overviewRasterOf } from '../overviewSubstitute';
import { layerShownName } from '../layerName';
import CopySceneNames from './CopySceneNames';
import EyeButton from './EyeButton';
import { fallbackReasonOf, MEASURED_ON_SCENE, measureView, type ViewMeasure } from '../viewMeasure';
import { isTemporaryImage, layerOfView, viewLayerOf } from '../viewLayer';
import AutoScaleButton from './AutoScaleButton';
import Badge from './Badge';
import Tip from './Tip';
import { useQuickRows } from '../inspectorFitContext';
import { QUICK_PER_ROW } from '../inspectorFit';
import { InspectorHead, InspectorSection, LayerStepper, Stepper } from './InspectorParts';
import Pager from './Pager';
import { ArrowLeftIcon, CogIcon, DownloadIcon, PlusIcon } from './icons';
import LayerActions from './LayerActions';
import OpacityRow from './OpacityRow';
import PresetParamControls from './PresetParamControls';
import type { BandOption } from './BandSelect';
import { viewKind } from '../viewKind';
import { classesOfBand } from '../bandClasses';
import RenderFields, { NO_COLORMAP } from './RenderFields';
import ScaleHistograms from './ScaleHistograms';
import ClassHistogram from './ClassHistogram';
import { useHistograms } from './useHistograms';

const INDEX_ONLY_TIP = 'This layer holds the index only';
const CLASS_COLOURS = 'Classes';
const CLASS_COLOURS_TIP = 'Each class in the colour of the source; a class map has no range and no other colormap';
const STEP_UNREADY = 'The range of this step is being measured';
const ENHANCE_RGB_TIP = 'Put the 2nd to the 98th percentile of red, green and blue in the fields, each channel on its own; Apply draws them. Only the look: Add to layers pins the whole view.';

// The histograms of the bands the statistics name, in their order; none where one band has none.
async function loadHistograms(measure: ViewMeasure): Promise<Histogram[] | null> {
  const read = Object.values((await measureView(measure, { histogram: true })).statistics).map((band) => histogramOf(band));
  return read.length > 0 && read.every((h) => h !== null) ? (read as Histogram[]) : null;
}

export default function ViewerControls() {
  const quickRows = useQuickRows();
  const [quickPageWanted, setQuickPage] = useState(0);
  const pendingColormapName = useAppStore((s) => s.pendingColormapName);
  const pendingVmin = useAppStore((s) => s.pendingVmin);
  const pendingVmax = useAppStore((s) => s.pendingVmax);
  const setPendingColormapName = useAppStore((s) => s.setPendingColormapName);
  const setPendingVmin = useAppStore((s) => s.setPendingVmin);
  const setPendingVmax = useAppStore((s) => s.setPendingVmax);
  const pendingUnit = useAppStore((s) => s.pendingUnit);
  const pendingPercentLow = useAppStore((s) => s.pendingPercentLow);
  const pendingPercentHigh = useAppStore((s) => s.pendingPercentHigh);
  const setPendingUnit = useAppStore((s) => s.setPendingUnit);
  const setPendingPercent = useAppStore((s) => s.setPendingPercent);
  const applyRender = useAppStore((s) => s.applyRender);
  // Whether "Apply" would draw anything else than the map shows.
  const changed = useAppStore((s) => lookChanged(s.appliedRender, s));
  const autoStretch = useAppStore((s) => s.autoStretch);
  // The pinned layer this view was opened from: its settings are these, and "Save" keeps the look for it (NM4-50).
  const layer = useAppStore((s) => layerOfView(s.layers, { ...s, aoi: s.viewAoi }));
  // The pinned layer that draws the view as it is now, in the view's place: its opacity is the one the slider sets.
  const drawnBy = useAppStore((s) => viewLayerOf(s.layers, { ...s, aoi: s.viewAoi }));
  const saveViewLook = useAppStore((s) => s.saveViewLook);
  // "Save" keeps the look for the layer the view is the picture of and for every image of the dataset (NM4-53).
  const savable = useAppStore((s) => {
    const own = layerOfView(s.layers, { ...s, aoi: s.viewAoi });
    // The settings of a layer: there is something to keep where the layer was changed (applied, its opacity) or the fields ask for more.
    if (s.viewOfLayer && own) return own.saved !== undefined || lookChanged(own.restore.appliedRender, s);
    return (own !== null && lookChanged(own.restore.appliedRender, s)) || datasetSavable(s);
  });
  const focusLoading = useAppStore((s) => s.focusLoading);
  const cropToAoi = useAppStore((s) => s.cropToAoi);
  const aoi = useAppStore((s) => s.aoi);
  const openDownloadForView = useAppStore((s) => s.openDownloadForView);
  const viewAoi = useAppStore((s) => s.viewAoi);
  const layers = useAppStore((s) => s.layers);
  const exitFocus = useAppStore((s) => s.exitFocus);
  const changeImage = useAppStore((s) => s.changeImage);
  const addCurrentToLayers = useAppStore((s) => s.addCurrentToLayers);
  const addAllToLayers = useAppStore((s) => s.addAllToLayers);
  const pinLoading = useAppStore((s) => s.pinLoading);
  const showDownloaded = useAppStore((s) => s.showDownloaded);
  const toggleDownloaded = useAppStore((s) => s.toggleDownloaded);
  const processBlock = useAppStore((s) =>
    processBlockReason(
      s.datasets.find((d) => d.id === s.datasetId),
      Object.keys(s.downloaded).length,
    ),
  );
  const processFocusView = useProcessingStore((s) => s.processFocusView);
  // The images of the view (NM4-53): the head, the row of steps and the buttons speak of the one that is shown.
  const downloaded = useAppStore((s) => s.downloaded);
  const sections = useAppStore((s) => s.sections);
  const openSectionId = useAppStore((s) => s.openSectionId);
  const datasetId = useAppStore((s) => s.datasetId);
  const items = useAppStore((s) => s.items);
  const groups = useAppStore((s) => s.groups);
  const datasets = useAppStore((s) => s.datasets);
  const shownKey = useAppStore((s) => s.shownImage);
  const stepImage = useAppStore((s) => s.stepImage);
  const chooseViewDataset = useAppStore((s) => s.chooseViewDataset);
  const chooseViewIndex = useAppStore((s) => s.chooseViewIndex);
  const chooseViewBand = useAppStore((s) => s.chooseViewBand);
  const pendingBand = useAppStore((s) => s.pendingBand);
  const appliedRender = useAppStore((s) => s.appliedRender);
  const viewOfLayer = useAppStore((s) => s.viewOfLayer);
  const pendingIndex = useAppStore((s) => s.pendingIndex);
  const pendingPresetParams = useAppStore((s) => s.pendingPresetParams);
  const setPresetParam = useAppStore((s) => s.setPresetParam);
  const pendingChannels = useAppStore((s) => s.pendingChannels);
  const renameLayer = useAppStore((s) => s.renameLayer);
  const setPendingChannel = useAppStore((s) => s.setPendingChannel);
  const setPendingChannelUnit = useAppStore((s) => s.setPendingChannelUnit);
  const setPendingChannelPercent = useAppStore((s) => s.setPendingChannelPercent);
  const quickIndex = useAppStore((s) => s.quickIndex);
  const enhanceContrast = useAppStore((s) => s.enhanceContrast);
  const enhanced = useAppStore(enhanceOn);
  // The colour picture in the fields: a range for each channel (UI-03d).
  const colour = useAppStore(colourView);
  // A unit for each channel (UI-03e): the rows of the three channels, each in values or in percentiles.
  const colourChannels = colour
    ? {
        values: colourChannelsOf({ pendingColormapName, pendingVmin, pendingVmax, pendingChannels, pendingUnit, pendingPercentLow, pendingPercentHigh }),
        onChange: setPendingChannel,
        onPercent: setPendingChannelPercent,
        onUnit: setPendingChannelUnit,
      }
    : undefined;
  const measure = useAppStore(viewMeasure);
  const mosaics = useAppStore((s) => s.mosaics);
  const mapZoom = useAppStore((s) => s.mapZoom);
  const images = useMemo(
    () => imagesOf(downloaded, sectionsForView({ sections, openSectionId, datasetId, items, groups }), datasets),
    [downloaded, sections, openSectionId, datasetId, items, groups, datasets],
  );
  const shown = shownImageOf(images, shownKey);
  const datasetTitleOf = (id: string) => datasets.find((d) => d.id === id)?.title ?? id;
  const datasetTitle = shown ? datasetTitleOf(shown.datasetId) : '';
  const count = shown?.ids.length ?? Object.keys(downloaded).length;
  // What the head cuts short, in full.
  const here = shown ? imagesOfDataset(images, shown.datasetId) : [];
  // What "Download full scene" will load, told in its tooltip.
  const originalsSummary = useMemo(() => {
    const dataset = shown ? datasets.find((d) => d.id === shown.datasetId) : undefined;
    if (!shown || !dataset) return '';
    const wanted = sectionsForView({ sections, openSectionId, datasetId, items, groups })
      .filter((section) => section.datasetId === shown.datasetId)
      .flatMap((section) => section.items)
      .filter((it) => shown.ids.includes(it.id));
    return summaryText(summaryOf(dataset.collection, scenesOf(dataset.collection, [{ label: '', items: wanted }])));
  }, [shown, datasets, sections, openSectionId, datasetId, items, groups]);
  const shownDataset = shown ? datasets.find((d) => d.id === shown.datasetId) : undefined;
  const originalsAllowed = hasOriginalFiles(shownDataset);
  // What "Quick processing" offers for the dataset the image shows (NM4-14b, M5-14): its indices, composites and steps.
  const presets = quickPresetsOf(shownDataset?.collection);
  // What the fields hold (chosen, drawn after "Apply") and what the map draws now.
  const chosen = viewIndexOf({ index: pendingIndex, presetParams: pendingPresetParams }, shownDataset?.collection);
  const index = viewIndexOf(appliedRender, shownDataset?.collection);
  // The same step with other values of its parameters is one picture: its histograms stay until the new ones come, and are asked once the
  // values rest (M5-14, Otto, 17.11.2026), so the panel does not jump while a dial turns.
  const family = chosen && chosen.adjustable.length > 0 && shown ? `${shown.key}|${chosen.name}|${cropToAoi}` : null;
  const histograms = useHistograms(measure && measure.key, () => loadHistograms(measure!), family);
  // Read after the histograms: their measure is the first of a picture, and a refusal of the tiler is known once it is in.
  const measuredOnScene = measure ? fallbackReasonOf(measure) : null;
  // Opened from the layer manager: the box of every layer, not the view with its row of buttons (NM4-65, Otto, 1.11.2026). A view that
  // is still open from the search keeps all of it, also once its image is pinned.
  const compact = viewOfLayer && layer !== null;
  // A layer pinned with an index of "Quick processing" is that index alone (UI-03d).
  const indexOnly = compact && layer.restore.indexOnly === true;
  // One dropdown "Band" (NM4-45, Otto, 31.10.2026): the standard picture first ("RGB" where the dataset has a true-colour one) and the
  // single bands of the data; the indices are in "Quick processing" (UI-03d, Otto, 2.11.2026). The index drawn stands in it, not to
  // be picked, so that the field says what the map shows; a band picked puts it away.
  // The first scene of the image shown: with `first_present` its band is the standard picture (DS-04c).
  const shownItem = shown ? sectionsForView({ sections, openSectionId, datasetId, items, groups }).flatMap((section) => section.items).find((it) => it.id === shown.ids[0]) : undefined;
  const standardAsset = shownDataset ? (defaultRenderOf(shownDataset.collection, shownItem)?.assets[0] ?? null) : null;
  const bandAssets = shownDataset && shown ? bandAssetsOf(shownItem, shownDataset.collection) : [];
  const trueColour = shownDataset ? trueColorOf(shownDataset.collection) !== null : false;
  const chosenOption: BandOption[] = chosen ? [{ value: `index:${chosen.name}`, label: chosen.label, title: chosen.tip, disabled: true }] : [];
  const bandOptions: BandOption[] = indexOnly
    ? chosenOption
    : [
        { value: '', label: trueColour ? 'RGB' : (standardAsset ?? 'Standard') },
        ...bandAssets.filter((asset) => asset !== standardAsset).map((asset) => ({ value: `band:${asset}`, label: asset })),
        ...chosenOption,
      ];
  // A dropdown with one entry offers no choice: it stays, locked, and says so. The view of a layer of the layer manager has it free, as
  // the view the layer came from (Otto, 1.11.2026).
  const showBand = bandOptions.filter((option) => !option.disabled).length > 1;
  const bandValue = chosen ? `index:${chosen.name}` : pendingBand ? `band:${pendingBand}` : '';
  const chooseView = (value: string) => {
    if (value.startsWith('index:')) chooseViewIndex(value.slice('index:'.length));
    else if (value.startsWith('band:')) chooseViewBand(value.slice('band:'.length));
    else chooseViewIndex(null);
  };
  // "Quick processing" offers the presets of a dataset that has any, not at a layer of one, and "Enhance contrast" for RGB.
  const quickIndices = presets.length > 0 && !indexOnly;
  // The parameters of the step chosen that a person may change (Otto, 17.11.2026), also at a layer of it.
  const params = chosen?.kind === 'step' && chosen.adjustable.length > 0 && shownDataset ? chosen : null;
  const quick = quickIndices || colour || params !== null;
  // The buttons of "Quick processing" in pages (UI-12 (4), Otto 17.11.2026): three a row, as many rows a page as the bar holds without
  // scrolling (`inspectorFit.ts`), the order of the registry; "Enhance contrast" last.
  const quickItems = [
    ...(quickIndices
      ? presets.map((preset) => {
          const on = chosen?.name === preset.name;
          return (
            <button
              key={preset.name}
              type="button"
              className={`btn${on ? ' on' : ''}`}
              aria-pressed={on}
              disabled={pinLoading}
              data-tip-level="advanced" data-tip={`${preset.tip} ${on ? 'Click again for the standard image of the dataset, then Apply.' : 'Apply draws it, no job.'}`}
              onClick={() => void quickIndex(preset.name)}
            >
              {preset.label}
            </button>
          );
        })
      : []),
    ...(colour
      ? [
          <button
            key="enhance-contrast"
            type="button"
            className={`btn${enhanced ? ' on' : ''}`}
            aria-pressed={enhanced}
            disabled={focusLoading}
            data-tip-level="advanced" data-tip={enhanced ? 'Click again for the fields as they were before' : ENHANCE_RGB_TIP}
            onClick={() => void enhanceContrast()}
          >
            Enhance contrast
          </button>,
        ]
      : []),
  ];
  const quickPageSize = Number.isFinite(quickRows) ? Math.max(1, quickRows) * QUICK_PER_ROW : Math.max(1, quickItems.length);
  const quickPages = pageCount(quickItems.length, quickPageSize);
  const quickPage = Math.min(quickPageWanted, quickPages - 1);
  const indexBlock =
    index && shown
      ? indexBlockOf({
          datasetId: shown.datasetId,
          entries: shown.ids.flatMap((id) => (downloaded[id] ? [[id, downloaded[id]] as [string, (typeof downloaded)[string]]] : [])),
          groups: sectionsForView({ sections, openSectionId, datasetId, items, groups }).flatMap((section) => section.groups),
          mosaics,
          preset: index,
          mapZoom,
          overview: overviewRasterOf(shownDataset, datasets) !== null,
        })
      : null;
  const note = index && indexBlock && (
    <p className="hint warn" role="status" data-tip-level="advanced" data-tip={indexNoteTip(indexBlock)}>
      {indexNote(indexBlock, index.label)}
    </p>
  );
  // A step of "Quick processing" is drawn once its look and range are in (adr/0035), never with a range made up.
  const stepUnready = chosen?.kind === 'step' && (pendingVmin.trim() === '' || pendingVmax.trim() === '' || pendingColormapName === '');
  // An index or a step is drawn with a colormap whatever the dataset's own picture is; a composite is a colour picture.
  const colormap = chosen ? !isComposite(chosen) : pendingBand || !shownDataset ? true : showsColormap(shownDataset.collection);
  // A layer of classes keeps the colours of its source: no range, no other colormap (M5-07 plan F4).
  const classes = !chosen && shownDataset ? drawsClasses(shownDataset.collection) : false;
  // Its histogram in the colours of its classes (M5-60 F9), without sliders.
  const classList = classes && shownDataset ? classesOfBand(shownDataset.collection, standardAsset ?? undefined) : null;
  const at = shown ? here.indexOf(shown) : -1;
  // Temporary where no layer holds the image as it is drawn now (Otto, 1.11.2026). What is only typed in the fields does not count: the
  // measured range that stands in them when the view opens is no change; "Apply" is.
  const standardLook = useMemo(() => {
    const render = shownDataset ? defaultRenderOf(shownDataset.collection, shownItem) : null;
    return render ? appliedRenderFrom(render) : {};
  }, [shownDataset, shownItem]);
  const temporary = shown ? isTemporaryImage(layers, shown, appliedRender, { cropToAoi: cropToAoi && viewAoi !== null, aoi: viewAoi }, standardLook) : false;
  const datasetIds = datasetIdsOf(images);
  // Only the date is read in the switcher (Otto, 1.11.2026); the satellite, the step and the group are its tooltip.
  const stepText = shown ? (shown.date ?? shown.groupLabel) : '';
  const stepTitle = shown
    ? [stepText, satellitesOf(shown), `step ${at + 1} of ${here.length}`, shown.groupLabel !== stepText ? shown.groupLabel : ''].filter(Boolean).join(' · ')
    : '';
  const onKeys = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    stepImage(e.key === 'ArrowLeft' ? -1 : 1);
  };

  return (
    <div className="viewer-controls scene-view">
      {/* A pinned view has the head of every layer (NM4-65): its name and date, no eye, no dataset. The view of the search is a temporary
          picture, not a layer (Otto, 1.11.2026): "Temporary", the badge of "Preview", beside the title. */}
      <InspectorHead
        title={compact ? layerShownName(layer) : [datasetTitle, viewKind(cropToAoi, count)].filter(Boolean).join(' · ')}
        // The scenes of the image shown, which is the layer's own where the settings of a layer are open.
        copy={<CopySceneNames names={shown?.ids ?? []} />}
        mark={
          !compact &&
          temporary && <Badge tip="This image is not a layer: add it to the layers to keep it">Temporary</Badge>
        }
        eye={
          !compact && (
            <EyeButton shown={showDownloaded} tip={showDownloaded ? 'Hide image' : 'Show image'} onToggle={() => toggleDownloaded()} />
          )
        }
        onClose={() => exitFocus()}
        closeTitle={compact ? undefined : 'Close and drop this view'}
        rename={compact ? { name: layer.name, onRename: (name) => renameLayer(layer.id, name) } : undefined}
      >
        {compact ? (
          <LayerStepper date={layer.date} />
        ) : (
          <>
            {datasetIds.length > 1 && shown && (
              <select
                className="vc-dataset"
                aria-label="Dataset"
                value={shown.datasetId}
                onChange={(e) => chooseViewDataset(e.target.value)}
              >
                {datasetIds.map((id) => (
                  <option key={id} value={id}>
                    {datasetTitleOf(id)}
                  </option>
                ))}
              </select>
            )}
            {shown && (
              <Stepper
                text={stepText}
                tip={stepTitle}
                single={here.length <= 1}
                onKeyDown={onKeys}
                previous={{ disabled: at <= 0, title: here.length <= 1 ? 'There is only one image' : at <= 0 ? 'This is the first image' : 'Previous image', onClick: () => stepImage(-1) }}
                next={{ disabled: at >= here.length - 1, title: here.length <= 1 ? 'There is only one image' : at >= here.length - 1 ? 'This is the last image' : 'Next image', onClick: () => stepImage(1) }}
              />
            )}
          </>
        )}
      </InspectorHead>

      <div className="insp-body">
        <InspectorSection title="Display">
          <div className="vc-render">
            <RenderFields
              // One band is no choice: the field stays, locked, and says so.
              band={{
                value: bandValue,
                options: bandOptions,
                onChange: chooseView,
                title: indexOnly
                  ? INDEX_ONLY_TIP
                  : !showBand
                    ? ONE_BAND_TIP
                    : chosen
                      ? [chosen.tip, computedNoteOf(shownDataset, datasets)].filter(Boolean).join('\n')
                      : BAND_TIP,
                disabled: !showBand,
              }}
              channels={colourChannels}
              histograms={
                histograms && (
                  <ScaleHistograms
                    histograms={histograms}
                    unit={colour ? 'value' : pendingUnit}
                    vmin={pendingUnit === 'percent' ? pendingPercentLow : pendingVmin}
                    vmax={pendingUnit === 'percent' ? pendingPercentHigh : pendingVmax}
                    onVmin={pendingUnit === 'percent' ? (text) => setPendingPercent('low', text) : setPendingVmin}
                    onVmax={pendingUnit === 'percent' ? (text) => setPendingPercent('high', text) : setPendingVmax}
                    colormap={colour ? undefined : pendingColormapName}
                    channels={colourChannels}
                  />
                )
              }
              vmin={pendingUnit === 'percent' ? { value: pendingPercentLow, onChange: (text) => setPendingPercent('low', text) } : { value: pendingVmin, onChange: setPendingVmin }}
              vmax={pendingUnit === 'percent' ? { value: pendingPercentHigh, onChange: (text) => setPendingPercent('high', text) } : { value: pendingVmax, onChange: setPendingVmax }}
              unit={colour ? undefined : { value: pendingUnit, onChange: setPendingUnit }}
              // The bar stays as it is for every dataset; an image of three bands offers RGB and nothing else (Otto, 1.11.2026).
              colormap={
                classes
                  ? { fixed: CLASS_COLOURS, title: CLASS_COLOURS_TIP }
                  : colormap
                    ? { value: pendingColormapName, onChange: setPendingColormapName }
                    : { fixed: NO_COLORMAP, title: 'True colour: three bands, no colormap' }
              }
              placeholder="auto"
              scale
              noRange={classes}
            />
            {/* The view of the search has an opacity of its own; a layer that draws it has its own (Otto, 2.11.2026). */}
            {classList && histograms?.length === 1 && <ClassHistogram histogram={histograms[0]} classes={classList} />}
            <OpacityRow layer={compact ? layer : (drawnBy ?? undefined)} />
            <div className="vc-buttons">
              {!classes && <AutoScaleButton
                title={focusLoading ? 'Measuring the range…' : pendingUnit === 'percent' ? 'Put the usual stretch in the fields: the 2nd to the 98th percentile' : 'Measure the 2nd/98th percentile stretch from the source again'}
                busy={focusLoading}
                onClick={() => void autoStretch()}
              />}
              <button
                type="button"
                className="btn vc-apply"
                aria-disabled={!changed || stepUnready || undefined}
                data-tip-level="advanced" data-tip={stepUnready ? STEP_UNREADY : changed ? 'Draw the view with these values' : NOTHING_TO_APPLY}
                onClick={() => {
                  if (changed && !stepUnready) applyRender();
                }}
              >
                Apply
              </button>
              <button
                type="button"
                className="btn primary vc-save"
                aria-disabled={!savable || undefined}
                data-tip-level="advanced" data-tip={
                  savable
                    ? compact
                      ? 'Keep this image, these values and this opacity for the layer; closing the settings without it puts the saved layer back'
                      : layer
                        ? 'Draw every image of this dataset with these values and keep them for this layer'
                        : 'Draw every image of this dataset with these values'
                    : compact
                      ? NOTHING_TO_SAVE
                      : layer
                        ? NOTHING_TO_APPLY_TO_ALL_LAYER
                        : here.length > 1
                          ? NOTHING_TO_SAVE_IMAGES
                          : NOTHING_TO_SAVE_ONE_IMAGE
                }
                onClick={() => {
                  if (savable) saveViewLook();
                }}
              >
                {compact ? 'Save' : 'Apply to all'}
              </button>
            </div>
          </div>
          {measuredOnScene && (
            <p className="hint" role="status">
              {MEASURED_ON_SCENE} <Tip text={measuredOnScene} />
            </p>
          )}
          {/* Without "Quick processing" (a layer of an index) the note of the index stands under the fields. */}
          {!quick && note}
        </InspectorSection>

        {/* Only what applies (Otto, 3.11.2026): the presets of the dataset, and "Enhance contrast" for RGB; a layer of a preset has none of
            it but the parameters of its step. Three in a row (Otto, 2.11.2026), each says whether it is on; a second click, or a band picked,
            puts it away. */}
        {quick ? (
          <InspectorSection title="Quick processing" extra={quickItems.length > 0 ? <Pager label="Pages of quick processing" className="quick-pages" page={quickPage} pages={quickPages} onPage={setQuickPage} /> : null}>
            {quickItems.length > 0 && (
              <div className="vc-quick" data-rows={Math.ceil(quickItems.length / QUICK_PER_ROW)}>
                {pageSlice(quickItems, quickPage, quickPageSize)}
              </div>
            )}
            {params && shownDataset && <PresetParamControls datasetId={shownDataset.id} preset={params} onChange={setPresetParam} />}
            {note}
          </InspectorSection>
        ) : null}

        {compact ? (
          <InspectorSection title="Actions">
            <LayerActions
              layer={layer}
              beforeCopy={async () => {
                if (changed) await applyRender();
                return true;
              }}
            />
          </InspectorSection>
        ) : (
          <InspectorSection title="Actions">
            {/* In pairs (Otto, 2.11.2026): what to look at next, what to keep, what to download. */}
            <div className="vc-actions">
              <button type="button" className="btn" data-tip-level="advanced" data-tip="Remove this view, show the search results and choose another scene" onClick={() => changeImage()}>
                <ArrowLeftIcon lead />Change image
              </button>
              <button
                type="button"
                className="btn"
                disabled={processBlock !== null}
                data-tip-level="advanced" data-tip={processBlock ?? 'Build a processing job for the scenes of this view'}
                onClick={() => void processFocusView()}
              >
                <CogIcon lead />Process
              </button>
              <button
                type="button"
                className="btn"
                data-tip-level="advanced" data-tip={images.length > 1 ? 'Add the image that is shown to the layers' : 'Add this image to the layers'}
                disabled={pinLoading}
                onClick={() => addCurrentToLayers()}
              >
                {pinLoading ? 'Loading…' : (<><PlusIcon lead />Add to layers</>)}
              </button>
              <button
                type="button"
                className="btn"
                data-tip-level="advanced" data-tip={images.length > 1 ? `Add all ${images.length} images of the view to the layers, one layer each` : 'There is only one image'}
                disabled={pinLoading || images.length <= 1}
                onClick={() => addAllToLayers()}
              >
                {pinLoading ? 'Loading…' : (<><PlusIcon lead />Add all to layers</>)}
              </button>
              <button
                type="button"
                className="btn"
                disabled={!aoi}
                data-tip-level="advanced" data-tip={aoi ? 'Download the image shown at full resolution as the AOI crop, one file per group' : DRAW_AOI_TO_CROP}
                onClick={() => openDownloadForView('crop')}
              >
                <DownloadIcon lead />Download crop
              </button>
              <button
                type="button"
                className="btn"
                disabled={!originalsAllowed}
                data-tip-level="advanced" data-tip={originalsAllowed ? originalsTitle(count > 1, shownDataset?.collection['earthx:access']?.cors === true, originalsSummary) : noOriginalsReason(shownDataset)}
                onClick={() => openDownloadForView('originals')}
              >
                <DownloadIcon lead />Download full scene
              </button>
            </div>
          </InspectorSection>
        )}
      </div>
    </div>
  );
}
