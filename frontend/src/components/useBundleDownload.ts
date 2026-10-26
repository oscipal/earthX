// "Download all (ZIP)" of a batch (UI-01 §6.12): one request keeps the list of parts on the server, then the
// browser downloads the ZIP from the address it got, which a download manager can resume.

import { useState } from 'react';

import { createBundle } from '../processing';
import { bundleFault, type BundleOffer } from './jobView';

// A plain link to the ZIP, so that the browser's own download (and its resuming) does the rest.
function startDownload(href: string): void {
  const link = document.createElement('a');
  link.href = href;
  link.download = '';
  link.rel = 'noopener noreferrer';
  document.body.append(link);
  link.click();
  link.remove();
}

export function useBundleDownload(offer: BundleOffer) {
  const [busy, setBusy] = useState(false);
  const [fault, setFault] = useState<string | null>(null);
  const run = async () => {
    if (busy || offer.kind !== 'ready') return;
    setBusy(true);
    setFault(null);
    try {
      startDownload((await createBundle(offer.jobIds)).href);
    } catch (error) {
      setFault(bundleFault(error));
    } finally {
      setBusy(false);
    }
  };
  return { busy, fault, run };
}
