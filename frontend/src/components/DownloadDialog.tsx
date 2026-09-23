import { useMemo } from 'react';

import {
  attributionText,
  canExportLicense,
  downloadRequestFor,
  downloadRequestForSelection,
  termsNoticeText,
} from '../download';
import { useAppStore } from '../store';

// Confirmation before a crop leaves the platform (M2-07d): attribution and the
// source's terms notice have to be visible before the download starts, not
// only inside the ZIP's ATTRIBUTION.txt (adr/0003 §11.2). English throughout,
// matching the rest of the interface since 2026-09-20 — the notice is
// requested from the backend with `language: 'en'` (`store.confirmDownload`).
//
// Two ways in (V-4): a pinned, full-resolution layer from the layer manager
// (`downloadDialogLayerId`), or the current selection straight from the
// results list (`downloadSelection`) — a selected quicklook's original data
// over the existing crop route, without first "View full resolution".
export default function DownloadDialog() {
  const layerId = useAppStore((s) => s.downloadDialogLayerId);
  const selectionMode = useAppStore((s) => s.downloadSelection);
  const layer = useAppStore((s) => s.layers.find((l) => l.id === s.downloadDialogLayerId));
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
  const activeGroup = useAppStore((s) => s.groups[s.activeGroupIndex]);
  const selectionItems = useMemo(
    () => (selectedIds.length ? items.filter((it) => selectedIds.includes(it.id)) : (activeGroup?.items ?? [])),
    [selectedIds, items, activeGroup],
  );
  const selectionAoi = useAppStore((s) => s.aoi);
  const activeGroupLabel = activeGroup?.label ?? '';
  const downloading = useAppStore((s) => s.downloading);
  const close = useAppStore((s) => s.closeDownloadDialog);
  const confirm = useAppStore((s) => s.confirmDownload);

  if (!layerId && !selectionMode) return null;

  const dataset = selectionMode ? selectionDataset : layerDataset;
  const req = selectionMode
    ? downloadRequestForSelection(selectionDataset, selectionItems, selectionAoi)
    : layer
      ? downloadRequestFor(layer)
      : null;
  const title = selectionMode
    ? [dataset?.title ?? selectionDataset?.id, activeGroupLabel].filter(Boolean).join(' · ')
    : (layer?.name ?? '');
  const flags = dataset?.collection['earthx:license_flags'];
  const attribution = attributionText(flags, new Date().getFullYear());
  const terms = termsNoticeText(flags, 'en');
  const exportAllowed = canExportLicense(flags);

  return (
    <div className="dialog-backdrop" onClick={close}>
      <div className="panel dialog-panel" onClick={(e) => e.stopPropagation()}>
        <div className="results-head">
          <h2>Download crop</h2>
          <button type="button" className="link-btn" title="Cancel" onClick={close}>
            ✕
          </button>
        </div>
        <div className="dialog-body">
          <p>
            <strong>{title}</strong>
            {req && (
              <>
                {' — '}
                {req.items.length} scene{req.items.length === 1 ? '' : 's'}, asset
                {req.assets.length === 1 ? '' : 's'} {req.assets.join(', ')}
              </>
            )}
          </p>

          {!exportAllowed && (
            <p className="hint-text">
              {dataset?.title ?? 'This dataset'}&rsquo;s licence does not permit a data export.
            </p>
          )}

          {attribution && <p className="dialog-attribution">{attribution}</p>}
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
        </div>
        <div className="dialog-actions">
          <button type="button" className="lm-btn" onClick={close} disabled={downloading}>
            Cancel
          </button>
          <button
            type="button"
            className="lm-btn primary"
            onClick={() => void confirm()}
            disabled={!req || !exportAllowed || downloading}
          >
            {downloading ? 'Downloading…' : 'Download'}
          </button>
        </div>
      </div>
    </div>
  );
}
