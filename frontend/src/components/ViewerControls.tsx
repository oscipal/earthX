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
import { COLORMAPS, lookChanged, NOTHING_TO_APPLY, NOTHING_TO_SAVE } from '../render';
import { shownImageOf, useAppStore } from '../store';
import { datasetIdsOf, imagesOf, imagesOfDataset, satellitesOf, sectionsForView } from '../viewImages';
import { viewKind } from '../viewKind';
import { layerOfView } from '../viewLayer';
import AutoScaleButton from './AutoScaleButton';
import Eye from './Eye';

export default function ViewerControls() {
  const pendingColormapName = useAppStore((s) => s.pendingColormapName);
  const pendingVmin = useAppStore((s) => s.pendingVmin);
  const pendingVmax = useAppStore((s) => s.pendingVmax);
  const setPendingColormapName = useAppStore((s) => s.setPendingColormapName);
  const setPendingVmin = useAppStore((s) => s.setPendingVmin);
  const setPendingVmax = useAppStore((s) => s.setPendingVmax);
  const applyRender = useAppStore((s) => s.applyRender);
  // Whether "Apply" would draw anything else than the map shows.
  const changed = useAppStore((s) => lookChanged(s.appliedRender, s));
  const autoStretch = useAppStore((s) => s.autoStretch);
  // The pinned layer this view was opened from: its settings are these, and "Save" keeps the look for it (NM4-50).
  const layer = useAppStore((s) => layerOfView(s.layers, { ...s, aoi: s.viewAoi }));
  const saveViewLook = useAppStore((s) => s.saveViewLook);
  const savable = useAppStore((s) => {
    const own = layerOfView(s.layers, { ...s, aoi: s.viewAoi });
    return own !== null && lookChanged(own.restore.appliedRender, s);
  });
  const focusLoading = useAppStore((s) => s.focusLoading);
  const cropToAoi = useAppStore((s) => s.cropToAoi);
  const exitFocus = useAppStore((s) => s.exitFocus);
  const changeImage = useAppStore((s) => s.changeImage);
  const addCurrentToLayers = useAppStore((s) => s.addCurrentToLayers);
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
  const images = useMemo(
    () => imagesOf(downloaded, sectionsForView({ sections, openSectionId, datasetId, items, groups }), datasets),
    [downloaded, sections, openSectionId, datasetId, items, groups, datasets],
  );
  const shown = shownImageOf(images, shownKey);
  const datasetTitleOf = (id: string) => datasets.find((d) => d.id === id)?.title ?? id;
  const datasetTitle = shown ? datasetTitleOf(shown.datasetId) : '';
  const date = shown?.date ?? null;
  const count = shown?.ids.length ?? Object.keys(downloaded).length;
  // What the head cuts short, in full.
  const title = [datasetTitle, date, cropToAoi ? 'cropped to the AOI' : 'whole scene'].filter(Boolean).join(' · ') + (count > 1 ? ` · ${count} scenes merged` : '');
  const here = shown ? imagesOfDataset(images, shown.datasetId) : [];
  const at = shown ? here.indexOf(shown) : -1;
  const datasetIds = datasetIdsOf(images);
  const stepText = shown ? [shown.date ?? shown.groupLabel, satellitesOf(shown)].filter(Boolean).join(' · ') : '';
  const onKeys = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    e.preventDefault();
    stepImage(e.key === 'ArrowLeft' ? -1 : 1);
  };

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

      {images.length > 1 && shown && (
        <div className="vc-steps">
          {datasetIds.length > 1 && (
            <select
              className="vc-dataset"
              aria-label="Dataset"
              title={`Dataset whose images the arrows step through: ${datasetTitle}`}
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
          <div className="vc-stepper" role="group" aria-label="Time step" onKeyDown={onKeys}>
            {here.length > 1 && (
              <button
                type="button"
                className="ghost-btn vc-step"
                aria-label="Previous image"
                aria-disabled={at <= 0 || undefined}
                title={at <= 0 ? 'This is the first image' : 'Previous image'}
                onClick={() => stepImage(-1)}
              >
                ‹
              </button>
            )}
            <span className="vc-step-text" title={`Step ${at + 1} of ${here.length}${shown.groupLabel ? ` · ${shown.groupLabel}` : ''}`}>
              {stepText}
            </span>
            {here.length > 1 && (
              <button
                type="button"
                className="ghost-btn vc-step"
                aria-label="Next image"
                aria-disabled={at >= here.length - 1 || undefined}
                title={at >= here.length - 1 ? 'This is the last image' : 'Next image'}
                onClick={() => stepImage(1)}
              >
                ›
              </button>
            )}
          </div>
        </div>
      )}

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
        <div className="vc-buttons">
          <AutoScaleButton
            title={focusLoading ? 'Measuring the range…' : 'Measure the 2nd/98th percentile stretch from the source again'}
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
          {layer && (
            <button
              type="button"
              className="primary-btn vc-save"
              aria-disabled={!savable || undefined}
              title={savable ? 'Keep these values for this layer' : NOTHING_TO_SAVE}
              onClick={() => {
                if (savable) saveViewLook();
              }}
            >
              Save
            </button>
          )}
        </div>
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
