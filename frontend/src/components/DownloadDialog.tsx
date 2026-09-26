import { useMemo } from 'react';

import { RESOLUTION_FACTORS } from '../api';
import {
  attributionText,
  canExportLicense,
  downloadRequestFor,
  downloadRequestForSelection,
  resolutionOptionLabel,
  termsNoticeText,
} from '../download';
import { groupItemIdsFor } from '../grouping';
import { useAppStore } from '../store';

// Confirmation before a download leaves the platform (M2-07d, M3-17):
// attribution and the source's terms notice have to be visible before it
// starts, not only inside the crop ZIP's ATTRIBUTION.txt (adr/0003 §11.2).
// English throughout, matching the rest of the interface since 2026-09-20 —
// the crop's notice is requested from the backend with `language: 'en'`
// (`store.confirmDownload`).
//
// Two ways in (V-4): a pinned, full-resolution layer from the layer manager
// (`downloadDialogLayerId`), or the current selection straight from the
// results list (`downloadSelection`). Either can follow one of two outcomes
// (`store.downloadOutcome`, M3-17 plan §4): the AOI **crop**, confirmed here
// as one request the way M2-06 always did, or the **originals**, a plain
// list of links to click — no confirm step, no CORS, no big in-browser
// download (plan §6, F2 option 1).
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
    () => (selectedIds.length ? items.filter((it) => selectedIds.includes(it.id)) : (activeGroup?.items ?? [])),
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
    const attribution = attributionText(flags, new Date().getFullYear(), false);
    const terms = termsNoticeText(flags, 'en');
    const byGroup = new Map<string, typeof originalLinks>();
    for (const link of originalLinks ?? []) {
      byGroup.set(link.groupLabel, [...(byGroup.get(link.groupLabel) ?? []), link]);
    }
    return (
      <div className="dialog-backdrop" onClick={close}>
        <div className="panel dialog-panel" onClick={(e) => e.stopPropagation()}>
          <div className="results-head">
            <h2>Download original files</h2>
            <button type="button" className="link-btn" title="Close" onClick={close}>
              ✕
            </button>
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
            {originalLinks === null && <p className="hint-text">Loading the original files…</p>}
            {originalLinks !== null && originalLinks.length === 0 && (
              <p className="hint-text">
                No original file of this selection could be linked directly from the source.
              </p>
            )}
            {originalLinks !== null && originalLinks.length > 0 && (
              <ul className="dialog-original-links">
                {[...byGroup.entries()].map(([groupLabel, links]) => (
                  <li key={groupLabel}>
                    <span className="dialog-original-group">{groupLabel}</span>
                    <ul>
                      {(links ?? []).map((link) => (
                        <li key={`${link.itemId}:${link.asset}`}>
                          <a href={link.href} download rel="noopener noreferrer" target="_blank">
                            {link.itemId} · {link.asset}
                          </a>
                        </li>
                      ))}
                    </ul>
                  </li>
                ))}
              </ul>
            )}
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
                {sceneCount} scene{sceneCount === 1 ? '' : 's'}
                {req.groups.length > 1 ? ` in ${req.groups.length} groups` : ''}, asset
                {req.assets.length === 1 ? '' : 's'} {req.assets.join(', ')}
              </>
            )}
          </p>

          {req && (
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
