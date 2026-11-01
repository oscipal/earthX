// The full-resolution view: its head, the stretch and colormap controls (F18), the layer-manager hook and the way
// back to browsing. Unlike the BIOMASS prototype's ViewerControls, there is no polarization/decomposition UI here —
// that was product-specific (products.ts, removed with M2-07a).
//
// Otto, 27.10.2026 (zu #211): the head is one line and never wider than the two rows of buttons below it, which share
// one grid and decide the width of the whole view; what does not fit is cut with "…" and given in full as the tooltip.
// "Change image" leaves the view and keeps the choice of scenes; "Clear" takes the view off the map and drops the
// choice. Neither touches "Hide results".

import { useMemo } from 'react';

import { processBlockReason } from '../processingOrder';
import { useProcessingStore } from '../processingStore';
import { showsColormap } from '../datasets';
import { indexPresetsOf, presetTip } from '../indexPresets';
import { trueColorOf } from '../processingOrder';
import { BAND_TIP, bandAssetsOf } from '../viewBand';
import { lookChanged, NOTHING_TO_APPLY, NOTHING_TO_APPLY_TO_ALL_LAYER, NOTHING_TO_SAVE_IMAGES, NOTHING_TO_SAVE_ONE_IMAGE } from '../render';
import { datasetSavable, shownImageOf, useAppStore } from '../store';
import { datasetIdsOf, imagesOf, imagesOfDataset, satellitesOf, sectionsForView } from '../viewImages';
import { indexBlockOf, indexNote, indexNoteTip, viewIndexOf } from '../viewIndex';
import { viewKind } from '../viewKind';
import { layerShownName } from '../layerName';
import { layerOfView } from '../viewLayer';
import AutoScaleButton from './AutoScaleButton';
import Chevron from './Chevron';
import CloseButton from './CloseButton';
import Eye from './Eye';
import type { BandOption } from './BandSelect';
import RenderFields from './RenderFields';

export default function ViewerControls() {
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
  const saveViewLook = useAppStore((s) => s.saveViewLook);
  // "Save" keeps the look for the layer the view is the picture of and for every image of the dataset (NM4-53).
  const savable = useAppStore((s) => {
    const own = layerOfView(s.layers, { ...s, aoi: s.viewAoi });
    return (own !== null && lookChanged(own.restore.appliedRender, s)) || datasetSavable(s);
  });
  const focusLoading = useAppStore((s) => s.focusLoading);
  const cropToAoi = useAppStore((s) => s.cropToAoi);
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
  const title = [datasetTitle, cropToAoi ? 'cropped to the AOI' : 'whole scene'].filter(Boolean).join(' · ') + (count > 1 ? ` · ${count} scenes merged` : '');
  const here = shown ? imagesOfDataset(images, shown.datasetId) : [];
  // An image of three bands has no colormap field.
  const shownDataset = shown ? datasets.find((d) => d.id === shown.datasetId) : undefined;
  // The index of the dataset the image shows in place of a band (NM4-14b): a dataset without presets has no dropdown.
  const presets = indexPresetsOf(shownDataset?.collection);
  // What the fields hold (chosen, drawn after "Apply") and what the map draws now.
  const chosen = viewIndexOf({ index: pendingIndex }, shownDataset?.collection);
  const index = viewIndexOf(appliedRender, shownDataset?.collection);
  // One dropdown "Band" (NM4-45, Otto, 31.10.2026): the standard picture first ("RGB" where the dataset has a true-colour one), the
  // single bands of the data, and after a line the index presets of the dataset (the quick calculation of NM4-14b).
  const standardAsset = shownDataset?.collection['earthx:default_render']?.assets[0] ?? null;
  const bandAssets = shownDataset && shown ? bandAssetsOf(sectionsForView({ sections, openSectionId, datasetId, items, groups }).flatMap((section) => section.items).find((it) => it.id === shown.ids[0]), shownDataset.collection) : [];
  const trueColour = shownDataset ? trueColorOf(shownDataset.collection) !== null : false;
  const bandOptions: BandOption[] = [
    { value: '', label: trueColour ? 'RGB' : (standardAsset ?? 'Standard') },
    ...bandAssets.filter((asset) => asset !== standardAsset).map((asset) => ({ value: `band:${asset}`, label: asset })),
    ...(presets.length > 0 ? [{ value: '|', label: '', separator: true }, ...presets.map((preset) => ({ value: `index:${preset.name}`, label: preset.name, title: presetTip(preset) }))] : []),
  ];
  // A dropdown with one entry offers no choice and is not shown. The view of a layer of the layer manager keeps what the layer was added with
  // (Otto, 1.11.2026): its dropdown stays in its place, locked.
  const showBand = bandOptions.filter((option) => !option.separator).length > 1;
  const bandValue = chosen ? `index:${chosen.name}` : pendingBand ? `band:${pendingBand}` : '';
  const chooseView = (value: string) => {
    if (value.startsWith('index:')) chooseViewIndex(value.slice('index:'.length));
    else if (value.startsWith('band:')) chooseViewBand(value.slice('band:'.length));
    else chooseViewIndex(null);
  };
  // Opened from the layer manager: the box of every layer, not the view with its row of buttons (NM4-65, Otto, 1.11.2026). A view that
  // is still open from the search keeps all of it, also once its image is pinned.
  const compact = viewOfLayer && layer !== null;
  const indexBlock =
    index && shown
      ? indexBlockOf({
          datasetId: shown.datasetId,
          entries: shown.ids.flatMap((id) => (downloaded[id] ? [[id, downloaded[id]] as [string, (typeof downloaded)[string]]] : [])),
          groups: sectionsForView({ sections, openSectionId, datasetId, items, groups }).flatMap((section) => section.groups),
          mosaics,
          preset: index,
          mapZoom,
        })
      : null;
  // An index is drawn with a colormap whatever the dataset's own picture is.
  const colormap = chosen || pendingBand || !shownDataset ? true : showsColormap(shownDataset.collection);
  const at = shown ? here.indexOf(shown) : -1;
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
    <div className="panel viewer-controls scene-view">
      {compact ? (
        // The view of a layer opened from the layer manager has the box of every layer: its name, the way to close it, the fields
        // and nothing under them: one row, as before, with no row of buttons for pinning, processing or changing the image (NM4-65, Otto,
        // 1.11.2026).
        <div className="vc-head">
          <span className="vc-title" title={layerShownName(layer)}>
            {layerShownName(layer).toUpperCase()}
          </span>
          <div className="results-head-right">
            <CloseButton onClick={() => exitFocus()} />
          </div>
        </div>
      ) : (
      <div className="vc-head">
        <span className="vc-title" title={title}>
          {[datasetTitle, viewKind(cropToAoi, count)].filter(Boolean).join(' · ')}
        </span>
        {datasetIds.length > 1 && shown && (
          <select
            className="vc-dataset"
            aria-label="Dataset"
            title={`Dataset of the image shown: ${datasetTitle}`}
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
          <div className="vc-stepper" role="group" aria-label="Time step" onKeyDown={onKeys}>
            <button
              type="button"
              className="vc-step"
              aria-label="Previous image"
              aria-disabled={at <= 0 || undefined}
              title={here.length <= 1 ? 'There is only one image' : at <= 0 ? 'This is the first image' : 'Previous image'}
              onClick={() => stepImage(-1)}
            >
              <Chevron direction="left" />
            </button>
            <span className="vc-step-text" title={stepTitle}>
              {stepText}
            </span>
            <button
              type="button"
              className="vc-step"
              aria-label="Next image"
              aria-disabled={at >= here.length - 1 || undefined}
              title={here.length <= 1 ? 'There is only one image' : at >= here.length - 1 ? 'This is the last image' : 'Next image'}
              onClick={() => stepImage(1)}
            >
              <Chevron direction="right" />
            </button>
          </div>
        )}
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
      )}

      <div className={`vc-render${showBand ? ' has-index' : ''}`}>
        <RenderFields
          band={
            showBand
              ? {
                  value: bandValue,
                  options: bandOptions,
                  onChange: chooseView,
                  disabled: viewOfLayer,
                  title: viewOfLayer ? 'A layer keeps the picture it was added with' : chosen ? presetTip(chosen) : BAND_TIP,
                }
              : undefined
          }
          vmin={pendingUnit === 'percent' ? { value: pendingPercentLow, onChange: (text) => setPendingPercent('low', text) } : { value: pendingVmin, onChange: setPendingVmin }}
          vmax={pendingUnit === 'percent' ? { value: pendingPercentHigh, onChange: (text) => setPendingPercent('high', text) } : { value: pendingVmax, onChange: setPendingVmax }}
          unit={{ value: pendingUnit, onChange: setPendingUnit }}
          // The box stays where it is for every dataset; an image of three bands offers RGB and nothing else (Otto, 1.11.2026).
          colormap={colormap ? { value: pendingColormapName, onChange: setPendingColormapName } : { fixed: 'RGB', title: 'True colour: three bands, no colormap' }}
          placeholder="auto"
        />
        <div className="vc-buttons">
          <AutoScaleButton
            title={focusLoading ? 'Measuring the range…' : pendingUnit === 'percent' ? 'Put the usual stretch in the fields: the 2nd to the 98th percentile' : 'Measure the 2nd/98th percentile stretch from the source again'}
            busy={focusLoading}
            onClick={() => void autoStretch()}
          />
          <button
            type="button"
            className="ghost-btn vc-apply"
            aria-disabled={!changed || undefined}
            title={changed ? 'Draw the view with these values' : NOTHING_TO_APPLY}
            onClick={() => {
              if (changed) applyRender();
            }}
          >
            Apply
          </button>
          <button
            type="button"
            className="primary-btn vc-save"
            aria-disabled={!savable || undefined}
            title={
              savable
                ? layer
                  ? 'Draw every image of this dataset with these values and keep them for this layer'
                  : 'Draw every image of this dataset with these values'
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
            Apply to all
          </button>
        </div>
      </div>

      {index && indexBlock && (
        <p className="vc-note hint-text warn" role="status" title={indexNoteTip(indexBlock)}>
          {indexNote(indexBlock, index.name)}
        </p>
      )}

      {!compact && (
        <div className={`vc-actions${images.length > 1 ? ' has-all' : ''}`}>
          <button
            type="button"
            className="ghost-btn"
            title={images.length > 1 ? 'Pin the image that is shown into the layer manager' : 'Pin this image into the layer manager'}
            disabled={pinLoading}
            onClick={() => addCurrentToLayers()}
          >
            {pinLoading ? 'Loading…' : '＋ Add to layers'}
          </button>
          {images.length > 1 && (
            <button
              type="button"
              className="ghost-btn"
              title={`Pin all ${images.length} images of the view into the layer manager, one layer each`}
              disabled={pinLoading}
              onClick={() => addAllToLayers()}
            >
              {pinLoading ? 'Loading…' : '＋ Add all to layers'}
            </button>
          )}
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
      )}
    </div>
  );
}
