import { attributionText, canExportLicense, downloadRequestFor, termsNoticeText } from '../download';
import { useAppStore } from '../store';

// Confirmation before a crop leaves the platform (M2-07d): attribution and the
// source's terms notice have to be visible before the download starts, not
// only inside the ZIP's ATTRIBUTION.txt (adr/0003 §11.2). English throughout,
// matching the rest of the interface since 2026-09-20 — the notice is
// requested from the backend with `language: 'en'` (`store.confirmDownload`).
export default function DownloadDialog() {
  const layerId = useAppStore((s) => s.downloadDialogLayerId);
  const layer = useAppStore((s) => s.layers.find((l) => l.id === s.downloadDialogLayerId));
  const dataset = useAppStore((s) =>
    s.datasets.find((d) => d.id === (layer?.restore.datasetId ?? s.datasetId)),
  );
  const downloading = useAppStore((s) => s.downloading);
  const close = useAppStore((s) => s.closeDownloadDialog);
  const confirm = useAppStore((s) => s.confirmDownload);

  if (!layerId || !layer) return null;

  const req = downloadRequestFor(layer);
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
            <strong>{layer.name}</strong>
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
          {flags?.terms_url && (
            <p>
              <a href={flags.terms_url} target="_blank" rel="noreferrer">
                {flags.terms_url}
              </a>
            </p>
          )}

          {!req && <p className="hint-text">This layer has nothing left to crop.</p>}
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
