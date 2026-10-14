// The "confirm" step of "click, select, confirm" (ENTSCHEIDUNGEN §2) for
// switching from quicklook browsing into full-resolution viewing (M2-07b).
// It replaces the prototype's DownloadBar for this step — an actual file
// download is M2-06/M2-07d, plus (V-4) a direct download of the selection's
// original data over the existing crop route, without first viewing it at
// full resolution.
//
// M3-09 (Otto, 24.09.2026): the single "View full resolution" button became
// two, both entering the same full-resolution view — "Crop & merge to AOI"
// clips it to the drawn AOI, "View full selection" shows the whole scene(s).
// Grouped under one label so it stays clear both are full resolution, not a
// preview. "Crop & merge" (renamed from "Crop to AOI", Otto's addendum) names
// what the download of a cropped selection already does: scenes merge per
// group (Überflug), different groups stay separate files (P19) — the view
// itself does not merge anything yet (see the M3-09 plan's proposal for the
// per-group outline and layer split, held for approval).

import { DRAW_AOI_TO_CROP, isCogFormat, noOriginalsReason } from '../download';
import { processBlockReason } from '../processingOrder';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';

export default function ViewBar() {
  const selectedIds = useAppStore((s) => s.selectedIds);
  const aoi = useAppStore((s) => s.aoi);
  const focusLoading = useAppStore((s) => s.focusLoading);
  const enterFocus = useAppStore((s) => s.enterFocus);
  const clearSelection = useAppStore((s) => s.clearSelection);
  const addCurrentToLayers = useAppStore((s) => s.addCurrentToLayers);
  const openDownloadForSelection = useAppStore((s) => s.openDownloadForSelection);
  const dataset = useAppStore((s) => s.datasets.find((d) => d.id === s.datasetId));
  const openProcessing = useProcessingStore((s) => s.openProcessing);

  if (selectedIds.length === 0) return null;

  const plural = selectedIds.length > 1;
  // Two buttons whatever the AOI (Zusatz 1a, Otto 14.10.2026): the crop to the
  // AOI, and the whole original files, which an AOI does not change.
  const originalsAllowed = isCogFormat(dataset);
  // M4-13b K12: a job for the selection, next to the download buttons; the reason it
  // cannot start (licence tier, no area) is the button's own title.
  const processBlocked = processBlockReason(dataset, aoi, selectedIds.length);

  return (
    <div className="panel download-bar">
      <span className="download-count">
        {selectedIds.length} scene{plural ? 's' : ''} selected
      </span>
      <div className="view-full-group" role="group" aria-label="View full resolution">
        <span className="view-full-label">Full resolution</span>
        <button
          type="button"
          className="primary-btn"
          disabled={focusLoading || !aoi}
          title={
            aoi
              ? `View the selected scene${plural ? 's' : ''} at full resolution, cut to your AOI`
              : 'Draw an AOI first to crop the full-resolution view to it'
          }
          onClick={() => enterFocus(true)}
        >
          {focusLoading ? 'Loading…' : 'Crop & merge to AOI'}
        </button>
        <button
          type="button"
          className="ghost-btn"
          disabled={focusLoading}
          title={`View the whole selected scene${plural ? 's' : ''} at full resolution, tiled straight from the source`}
          onClick={() => enterFocus(false)}
        >
          {focusLoading ? 'Loading…' : 'View full selection'}
        </button>
      </div>
      <button
        type="button"
        className="ghost-btn"
        title="Pin the selected scenes into the layer manager, at their current (preview) resolution"
        onClick={() => addCurrentToLayers()}
      >
        ＋ Add to layers
      </button>
      <button
        type="button"
        className="ghost-btn"
        disabled={!aoi}
        title={aoi ? 'Download the selected scenes as the AOI crop, one file per group' : DRAW_AOI_TO_CROP}
        onClick={() => openDownloadForSelection('crop')}
      >
        ⇩ Download crop
      </button>
      <button
        type="button"
        className="ghost-btn"
        disabled={!originalsAllowed}
        title={
          originalsAllowed
            ? 'Download the whole original files of the selected scenes, straight from the source'
            : noOriginalsReason(dataset)
        }
        onClick={() => openDownloadForSelection('originals')}
      >
        ⇩ Download originals
      </button>
      <button
        type="button"
        className="ghost-btn"
        disabled={processBlocked !== null}
        title={processBlocked ?? 'Build a processing job for the selected scene, cut to your AOI'}
        onClick={() => openProcessing()}
      >
        ⚙ Process
      </button>
      <button type="button" className="ghost-btn" disabled={focusLoading} onClick={() => clearSelection()}>
        Clear
      </button>
    </div>
  );
}
