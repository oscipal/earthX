// The symbol "Download all (ZIP)" at the end of the row of a batch (UI-01 §6.12); `useBundleDownload.ts` does the work.

import { BUNDLE_LABEL, type BundleOffer } from './jobView';

export default function DownloadAll({ offer, busy, onRun }: { offer: BundleOffer; busy: boolean; onRun: () => void }) {
  if (offer.kind === 'hidden') return <span className="pm-icon" aria-hidden="true" />;
  if (offer.kind === 'locked' || busy) {
    const reason = offer.kind === 'locked' ? offer.reason : 'Preparing the ZIP…';
    return (
      <button type="button" className="pm-icon has-tip" aria-disabled="true" data-tip={reason} aria-label={`${BUNDLE_LABEL}: ${reason}`}>
        ⇊
      </button>
    );
  }
  const note = offer.leftOut > 0 ? ` ${offer.leftOut} of ${offer.jobIds.length} parts are left out; MISSING.txt in the ZIP says why.` : '';
  return (
    <button type="button" className="pm-icon has-tip" data-tip={`${BUNDLE_LABEL}.${note}`} aria-label={`${BUNDLE_LABEL}.${note}`} onClick={onRun}>
      ⇊
    </button>
  );
}
