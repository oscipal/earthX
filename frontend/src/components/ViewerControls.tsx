// The full-resolution view in the settings bar (`Inspector.tsx`): its head, the stretch and colormap controls (F18), the layer-manager
// hook and the way back to browsing. Unlike the BIOMASS prototype's ViewerControls, there is no polarization/decomposition UI here —
// that was product-specific (products.ts, removed with M2-07a).
//
// Otto, 27.10.2026 (zu #211): what does not fit the head is cut with "…" and given in full as the tooltip.
// "Change image" leaves the view, keeps the choice of scenes and shows the search results; the red x takes the view off the map and
// drops it, as "Clear" did (Otto, 2.11.2026: no "Clear" any more).

import { useMemo } from 'react';

import { DRAW_AOI_TO_CROP, isCogFormat, layerDownloadKind, noOriginalsReason } from '../download';
import { originalsTitle, scenesOf, summaryOf, summaryText } from '../originals';
import { processBlockReason } from '../processingOrder';
import { useProcessingStore } from '../processingStore';
import { defaultRenderOf, showsColormap } from '../datasets';
import { indexPresetsOf, presetTip } from '../indexPresets';
import { trueColorOf } from '../processingOrder';
import { BAND_TIP, bandAssetsOf, ONE_BAND_TIP } from '../viewBand';
import { appliedRenderFrom, lookChanged, NOTHING_TO_APPLY, NOTHING_TO_APPLY_TO_ALL_LAYER, NOTHING_TO_SAVE, NOTHING_TO_SAVE_IMAGES, NOTHING_TO_SAVE_ONE_IMAGE } from '../render';
import { datasetSavable, shownImageOf, useAppStore } from '../store';
import { datasetIdsOf, imagesOf, imagesOfDataset, satellitesOf, sectionsForView } from '../viewImages';
import { indexBlockOf, indexNote, indexNoteTip, viewIndexOf } from '../viewIndex';
import { layerShownName } from '../layerName';
import { isTemporaryImage, layerOfView, viewLayerOf } from '../viewLayer';
import AutoScaleButton from './AutoScaleButton';
import Eye from './Eye';
import { InspectorHead, InspectorSection, LayerStepper, Stepper } from './InspectorParts';
import LayerDownload from './LayerDownload';
import OpacityRow from './OpacityRow';
import type { BandOption } from './BandSelect';
import { viewKind } from '../viewKind';
import RenderFields, { NO_COLORMAP } from './RenderFields';

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
  const originalsAllowed = isCogFormat(shownDataset);
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
  // A dropdown with one entry offers no choice: it stays, locked, and says so. The view of a layer of the layer manager has it free, as
  // the view the layer came from (Otto, 1.11.2026).
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
  // Temporary where no layer holds the image as it is drawn now (Otto, 1.11.2026). What is only typed in the fields does not count: the
  // measured range that stands in them when the view opens is no change; "Apply" is.
  const standardLook = useMemo(() => {
    const render = shownDataset ? defaultRenderOf(shownDataset.collection) : null;
    return render ? appliedRenderFrom(render) : {};
  }, [shownDataset]);
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
        tip={compact ? layerShownName(layer) : title}
        mark={
          !compact &&
          temporary && (
            <span className="pp-badge vc-temporary" title="This picture is not a layer: add it to the layers to keep it">
              Temporary
            </span>
          )
        }
        eye={
          !compact && (
            <button
              type="button"
              className={`vc-eye${showDownloaded ? '' : ' off'}`}
              title={showDownloaded ? 'Hide image' : 'Show image'}
              aria-label={showDownloaded ? 'Hide image' : 'Show image'}
              onClick={() => toggleDownloaded()}
            >
              <Eye off={!showDownloaded} />
            </button>
          )
        }
        onClose={() => exitFocus()}
        closeTitle={compact ? undefined : 'Close and drop this view'}
      >
        {compact ? (
          <LayerStepper date={layer.date} />
        ) : (
          <>
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
              <Stepper
                text={stepText}
                tip={stepTitle}
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
                title: !showBand ? ONE_BAND_TIP : chosen ? presetTip(chosen) : BAND_TIP,
                disabled: !showBand,
              }}
              vmin={pendingUnit === 'percent' ? { value: pendingPercentLow, onChange: (text) => setPendingPercent('low', text) } : { value: pendingVmin, onChange: setPendingVmin }}
              vmax={pendingUnit === 'percent' ? { value: pendingPercentHigh, onChange: (text) => setPendingPercent('high', text) } : { value: pendingVmax, onChange: setPendingVmax }}
              unit={{ value: pendingUnit, onChange: setPendingUnit }}
              // The bar stays as it is for every dataset; an image of three bands offers RGB and nothing else (Otto, 1.11.2026).
              colormap={colormap ? { value: pendingColormapName, onChange: setPendingColormapName } : { fixed: NO_COLORMAP, title: 'True colour: three bands, no colormap' }}
              placeholder="auto"
              scale
            />
            {/* The view of the search has an opacity of its own; a layer that draws it has its own (Otto, 2.11.2026). */}
            <OpacityRow layer={compact ? layer : (drawnBy ?? undefined)} />
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
                    ? compact
                      ? 'Keep this picture, these values and this opacity for the layer; closing the settings without it puts the saved layer back'
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
          {index && indexBlock && (
            <p className="vc-note hint-text warn" role="status" title={indexNoteTip(indexBlock)}>
              {indexNote(indexBlock, index.name)}
            </p>
          )}
        </InspectorSection>

        {compact ? (
          layerDownloadKind(layer) !== null && (
            <InspectorSection title="Actions">
              <div className="vc-actions">
                <LayerDownload layer={layer} className="ghost-btn" label="Download" />
              </div>
            </InspectorSection>
          )
        ) : (
          <InspectorSection title="Actions">
            {/* In pairs (Otto, 2.11.2026): what to look at next, what to keep, what to download. */}
            <div className="vc-actions">
              <button type="button" className="ghost-btn" title="Remove this view, show the search results and choose another scene" onClick={() => changeImage()}>
                ‹ Change image
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
              <button
                type="button"
                className="ghost-btn"
                title={images.length > 1 ? 'Pin the image that is shown into the layer manager' : 'Pin this image into the layer manager'}
                disabled={pinLoading}
                onClick={() => addCurrentToLayers()}
              >
                {pinLoading ? 'Loading…' : '＋ Add to layers'}
              </button>
              <button
                type="button"
                className="ghost-btn"
                title={images.length > 1 ? `Pin all ${images.length} images of the view into the layer manager, one layer each` : 'There is only one image'}
                disabled={pinLoading || images.length <= 1}
                onClick={() => addAllToLayers()}
              >
                {pinLoading ? 'Loading…' : '＋ Add all to layers'}
              </button>
              <button
                type="button"
                className="ghost-btn"
                disabled={!aoi}
                title={aoi ? 'Download the image shown at full resolution as the AOI crop, one file per group' : DRAW_AOI_TO_CROP}
                onClick={() => openDownloadForView('crop')}
              >
                ⇩ Download crop
              </button>
              <button
                type="button"
                className="ghost-btn"
                disabled={!originalsAllowed}
                title={originalsAllowed ? originalsTitle(count > 1, shownDataset?.collection['earthx:access']?.cors === true, originalsSummary) : noOriginalsReason(shownDataset)}
                onClick={() => openDownloadForView('originals')}
              >
                ⇩ Download full scene
              </button>
            </div>
          </InspectorSection>
        )}
      </div>
    </div>
  );
}
