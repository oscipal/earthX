// The "confirm" step of "click, select, confirm" (ENTSCHEIDUNGEN §2) for
// switching from quicklook browsing into full-resolution viewing (M2-07b),
// plus a direct download of the selection's original data (V-4).
//
// UI-01g (Otto, 26.10.2026): every button here works at full resolution, so no
// label says so (the tooltips do); the buttons are one size; a button names what
// it does for one scene and what it does for several ("merged"); and there is no
// "Clear" (the list unticks scenes) and no "Add to layers". Scenes merge per group (Überflug), different
// groups stay separate files (P19).

import { DRAW_AOI_TO_CROP, isCogFormat, noOriginalsReason } from '../download';
import { processBlockReason } from '../processingOrder';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';

export default function ViewBar() {
  const selectedIds = useAppStore((s) => s.selectedIds);
  const aoi = useAppStore((s) => s.aoi);
  const focusLoading = useAppStore((s) => s.focusLoading);
  const enterFocus = useAppStore((s) => s.enterFocus);
  const openDownloadForSelection = useAppStore((s) => s.openDownloadForSelection);
  const dataset = useAppStore((s) => s.datasets.find((d) => d.id === s.datasetId));
  const openProcessing = useProcessingStore((s) => s.openProcessing);

  if (selectedIds.length === 0) return null;

  const plural = selectedIds.length > 1;
  // Two buttons whatever the AOI (Zusatz 1a, Otto 14.10.2026): the crop to the
  // AOI, and the whole original files, which an AOI does not change.
  const originalsAllowed = isCogFormat(dataset);
  // M4-13b K12: a job for the selection, next to the download buttons; the reason it
  // cannot start (licence tier) is the button's own title. No AOI needed (M4-13c K1).
  const processBlocked = processBlockReason(dataset, selectedIds.length);

  return (
    <div className="panel download-bar" role="group" aria-label="Selected scenes, full resolution">
      <span className="download-count">
        <strong>{selectedIds.length}</strong>
        <span>scene{plural ? 's' : ''} selected</span>
      </span>
      <button
        type="button"
        className="primary-btn"
        disabled={focusLoading || !aoi}
        title={
          aoi
            ? `View the selected scene${plural ? 's' : ''} at full resolution, cut to your AOI${plural ? ' and merged' : ''}`
            : 'Draw an AOI first to crop the full-resolution view to it'
        }
        onClick={() => enterFocus(true)}
      >
        {focusLoading ? 'Loading…' : plural ? 'Crop & merge to AOI' : 'Crop to AOI'}
      </button>
      <button
        type="button"
        className="ghost-btn"
        disabled={focusLoading}
        title={`View the whole selected scene${plural ? 's, merged,' : ''} at full resolution, tiled straight from the source`}
        onClick={() => enterFocus(false)}
      >
        {focusLoading ? 'Loading…' : plural ? 'View merged scenes' : 'View whole scene'}
      </button>
      <button
        type="button"
        className="ghost-btn"
        disabled={!aoi}
        title={aoi ? 'Download the selected scenes at full resolution as the AOI crop, one file per group' : DRAW_AOI_TO_CROP}
        onClick={() => openDownloadForSelection('crop')}
      >
        {plural ? '⇩ Download merged crop' : '⇩ Download crop'}
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
        {plural ? '⇩ Download full scenes' : '⇩ Download full scene'}
      </button>
      <button
        type="button"
        className="ghost-btn"
        disabled={processBlocked !== null}
        title={processBlocked ?? `Build a processing job for the selected scene${plural ? 's' : ''}`}
        onClick={() => openProcessing()}
      >
        ⚙ Process
      </button>
    </div>
  );
}
