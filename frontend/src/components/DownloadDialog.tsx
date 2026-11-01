import { useMemo } from 'react';

import { RESOLUTION_FACTORS } from '../api';
import {
  acquisitionYears,
  attributionText,
  canExportLicense,
  downloadRequestFor,
  downloadRequestForSelection,
  resolutionOptionLabel,
  termsNoticeText,
} from '../download';
import { groupItemIdsFor } from '../grouping';
import { indexOfferedFor } from '../indexDownload';
import { useAppStore } from '../store';
import ExportJobOffer from './ExportJobOffer';
import OriginalFiles from './OriginalFiles';
import CloseButton from './CloseButton';

// Confirmation before a download leaves the platform (M2-07d, M3-17):
// attribution and the source's terms notice have to be visible before it
// starts, not only inside the crop ZIP's ATTRIBUTION.txt (adr/0003 §11.2).
// English throughout, matching the rest of the interface since 2026-09-20 —
// the platform offers no language choice at all (Otto, 22.09.2026), so
// `termsNoticeText` below is never called with anything but its own English
// default. M3-12, K-16: the crop request used to carry a `language` field the
// backend's own `DownloadRequest` had already stopped declaring — pydantic
// silently dropped it, so removing it changed nothing the backend did.
//
// Two ways in (V-4): a pinned, full-resolution layer from the layer manager
// (`downloadDialogLayerId`), or the current selection straight from the
// results list (`downloadSelection`). Either can follow one of two outcomes
// (`store.downloadOutcome`, M3-17 plan §4): the AOI **crop**, confirmed here
// as one request the way M2-06 always did, or the **originals**, which start by
// themselves when the dialog opens, one ZIP per scene built in the browser
// from the files of the source (NM4-33, `OriginalFiles`); where a pass holds
// several scenes the dialog also offers them merged per pass as a job (M4-12b). A crop too
// large for a direct download is offered as an export job (`ExportJobOffer`,
// M4-11b-2) when the server's `413` says it fits one.
export default function DownloadDialog() {
  const layerId = useAppStore((s) => s.downloadDialogLayerId);
  const selectionMode = useAppStore((s) => s.downloadSelection);
  const layer = useAppStore((s) => s.layers.find((l) => l.id === s.downloadDialogLayerId));
  const datasets = useAppStore((s) => s.datasets);
  const layerDataset = useAppStore((s) =>
    s.datasets.find((d) => d.id === (layer?.restore.datasetId ?? s.datasetId)),
  );
  const selectionDataset = useAppStore((s) => s.datasets.find((d) => d.id === s.datasetId));
  // Selected via the raw, stable slices and combined here (not inside the
  // selector): a selector that returns a freshly filtered array or a `?? []`
  // literal is a new reference on every call, which zustand's `useSyncExternalStore`
  // then reads as "changed" forever — an infinite render loop once this dialog
  // is mounted (found via `AppTopBar.test.tsx`/`StatusBar.test.tsx`, both of
  // which mount the whole `App`).
  const selectedIds = useAppStore((s) => s.selectedIds);
  const items = useAppStore((s) => s.items);
  const groups = useAppStore((s) => s.groups);
  const activeGroup = useAppStore((s) => s.groups[s.activeGroupIndex]);
  const selectionItems = useMemo(
    () => {
      const picked = items.filter((it) => selectedIds.includes(it.id));
      return picked.length ? picked : (activeGroup?.items ?? []);
    },
    [selectedIds, items, activeGroup],
  );
  const selectionAoi = useAppStore((s) => s.aoi);
  const activeGroupLabel = activeGroup?.label ?? '';
  const downloading = useAppStore((s) => s.downloading);
  const close = useAppStore((s) => s.closeDownloadDialog);
  const confirm = useAppStore((s) => s.confirmDownload);
  const resolution = useAppStore((s) => s.downloadResolution);
  const setResolution = useAppStore((s) => s.setDownloadResolution);
  const outcome = useAppStore((s) => s.downloadOutcome);
  const originalLinks = useAppStore((s) => s.downloadOriginalLinks);
  const passes = useAppStore((s) => s.downloadPasses);
  const skippedGroupsNotice = useAppStore((s) => s.downloadSkippedGroupsNotice);
  const exportOffer = useAppStore((s) => s.downloadExportOffer);
  const downloadStatus = useAppStore((s) => s.downloadStatus);
  const indexNote = useAppStore((s) => s.downloadIndexNote);
  const downloadAs = useAppStore((s) => s.downloadAs);
  const setDownloadAs = useAppStore((s) => s.setDownloadAs);

  if (!layerId && !selectionMode) return null;

  const dataset = selectionMode ? selectionDataset : layerDataset;
  const title = selectionMode
    ? [dataset?.title ?? selectionDataset?.id, activeGroupLabel].filter(Boolean).join(' · ')
    : (layer?.name ?? '');
  const flags = dataset?.collection['earthx:license_flags'];

  if (outcome === 'originals') {
    // A whole scene's own files, unmodified, straight from the source (B11:
    // Katalogeintrag already permits a link — no licence-tier gate here,
    // unlike the crop below).
    const attribution = attributionText(flags, acquisitionYears((passes ?? []).flatMap((pass) => pass.items)), false);
    const terms = termsNoticeText(flags, 'en');
    const sceneTotal = new Set((passes ?? []).flatMap((pass) => pass.items.map((item) => item.id))).size;
    return (
      <div className="dialog-backdrop" onClick={close}>
        <div className="panel dialog-panel" onClick={(e) => e.stopPropagation()}>
          <div className="results-head">
            <h2>{sceneTotal === 1 ? 'Download full scene' : 'Download full scenes'}</h2>
            <CloseButton title="Close. This stops a download that is still running." onClick={close} />
          </div>
          <div className="dialog-body">
            <p>
              <strong>{title}</strong> — straight from the source, no crop applied.
            </p>
            {attribution && <p className="dialog-attribution">{attribution}</p>}
            {terms && <p className="dialog-terms">{terms}</p>}
            {flags?.terms_url && !terms?.includes(flags.terms_url) && (
              <p>
                <a href={flags.terms_url} target="_blank" rel="noreferrer">
                  {flags.terms_url}
                </a>
              </p>
            )}
            <OriginalFiles dataset={dataset} links={originalLinks} passes={passes} />
          </div>
          <div className="dialog-actions">
            <button type="button" className="lm-btn" onClick={close}>
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (skippedGroupsNotice) {
    // The download already happened (`store.confirmDownload`); this replaces
    // the confirmation UI rather than adding to it, so there is nothing left
    // here to confirm a second time — just the one thing still worth saying.
    return (
      <div className="dialog-backdrop" onClick={close}>
        <div className="panel dialog-panel" onClick={(e) => e.stopPropagation()}>
          <div className="results-head">
            <h2>Download crop</h2>
            <CloseButton onClick={close} />
          </div>
          <div className="dialog-body">
            <p>
              <strong>{title}</strong>
            </p>
            <p className="hint-text">{skippedGroupsNotice}</p>
          </div>
          <div className="dialog-actions">
            <button type="button" className="lm-btn primary" onClick={close}>
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  const req = selectionMode
    ? downloadRequestForSelection(
        selectionDataset,
        groupItemIdsFor(
          selectionItems.map((it) => it.id),
          groups,
        ),
        selectionAoi,
      )
    : layer
      ? downloadRequestFor(layer, datasets)
      : null;
  const sceneCount = req?.groups.flat().length ?? 0;
  // No attribution line: its year is that of the scenes' acquisition, which a pinned layer does not keep,
  // and ATTRIBUTION.txt in the ZIP carries the text (Otto, 25.10.2026, NM4-01).
  const terms = termsNoticeText(flags, 'en');
  const exportAllowed = canExportLicense(flags);
  // A layer that shows an index offers it besides its raw bands (NM4-14b, Otto, 1.11.2026): the file a Processing job would give,
  // with no job to see. The raw bands are what the dialog starts with, as for any layer.
  const offered = !selectionMode && layer ? indexOfferedFor(layer, datasets) : null;
  const index = offered && downloadAs === 'index' ? offered : null;

  return (
    <div className="dialog-backdrop" onClick={close}>
      <div className="panel dialog-panel" onClick={(e) => e.stopPropagation()}>
        <div className="results-head">
          <h2>Download crop</h2>
          <CloseButton onClick={close} />
        </div>
        <div className="dialog-body">
          <p>
            <strong>{title}</strong>
            {req && (
              <>
                {' — '}
                {sceneCount} scene{sceneCount === 1 ? '' : 's'}
                {req.groups.length > 1 ? ` in ${req.groups.length} groups` : ''},{' '}
                {index ? `${index.name} (${index.formula})` : `asset${req.assets.length === 1 ? '' : 's'} ${req.assets.join(', ')}`}
              </>
            )}
          </p>

          {offered && (
            <div className="dialog-as" role="radiogroup" aria-label="What to download">
              {(['raw', 'index'] as const).map((what) => (
                <label key={what} style={{ marginRight: '1em' }} title={what === 'raw' ? 'The bands of the scenes, cut to the AOI' : `The ${offered.name}, computed as a Processing job would give it`}>
                  <input type="radio" name="download-as" checked={downloadAs === what} onChange={() => setDownloadAs(what)} disabled={downloading} />{' '}
                  {what === 'raw' ? 'Raw bands' : offered.name}
                </label>
              ))}
            </div>
          )}

          {req && !index && (
            <div className="dialog-resolution">
              <span>Resolution: </span>
              {RESOLUTION_FACTORS.map((factor) => (
                <label key={factor} style={{ marginRight: '1em' }}>
                  <input
                    type="radio"
                    name="download-resolution"
                    checked={resolution === factor}
                    onChange={() => setResolution(factor)}
                    disabled={downloading}
                  />{' '}
                  {[
                    ...new Set(
                      req.assets.map((asset) =>
                        resolutionOptionLabel(selectionMode ? selectionItems : [], asset, factor),
                      ),
                    ),
                  ].join(', ')}
                </label>
              ))}
            </div>
          )}

          {!exportAllowed && (
            <p className="hint-text">
              {dataset?.title ?? 'This dataset'}&rsquo;s licence does not permit a data export.
            </p>
          )}

          {index && (
            <p
              className={`hint-text${!downloading && (indexNote?.state === 'blocked' || indexNote?.state === 'failed') ? ' warn' : ''}`}
              title={indexNote && indexNote.state !== 'estimating' ? indexNote.tip : 'The same result a Processing job would give for these scenes and this area'}
              role={indexNote?.state === 'blocked' || indexNote?.state === 'failed' ? 'alert' : undefined}
            >
              {downloading
                ? (downloadStatus ?? 'Computing…')
                : indexNote === null || indexNote.state === 'estimating'
                  ? 'Estimating…'
                  : indexNote.text}
            </p>
          )}

          {terms && <p className="dialog-terms">{terms}</p>}
          {flags?.terms_url && !terms?.includes(flags.terms_url) && (
            <p>
              <a href={flags.terms_url} target="_blank" rel="noreferrer">
                {flags.terms_url}
              </a>
            </p>
          )}

          {!req && (
            <p className="hint-text">
              {selectionMode ? 'Nothing left to crop.' : 'This layer has nothing left to crop.'}
            </p>
          )}

          {exportOffer && <ExportJobOffer key={exportOffer.id} offer={exportOffer} />}
        </div>
        <div className="dialog-actions">
          <button type="button" className="lm-btn" onClick={close} disabled={downloading}>
            Cancel
          </button>
          <button
            type="button"
            className="lm-btn primary"
            onClick={() => void confirm()}
            disabled={!req || !exportAllowed || downloading || (index !== null && indexNote?.state !== 'ready' && indexNote?.state !== 'failed')}
          >
            {downloading ? (index ? 'Computing…' : 'Downloading…') : 'Download'}
          </button>
        </div>
      </div>
    </div>
  );
}
