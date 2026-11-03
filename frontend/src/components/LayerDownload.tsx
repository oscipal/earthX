// The ⇩ of a layer: the ZIP of a result, or the dialog of the AOI crop and the original files for a layer of scenes. One block for the
// row of the layer manager and for the settings bar, so that they look and answer alike (UI-03a, Otto, 2.11.2026).

import type { ReactNode } from 'react';

import { canDownloadLayer, decideDownloadOutcomeForLayer, layerDownloadKind } from '../download';
import { indexDownloadBlock, indexOfferedFor } from '../indexDownload';
import type { MapLayer } from '../layers';
import { resultUrl } from '../processing';
import { ZIP_LABEL } from '../processingStore';
import { RESULT_ZIP } from '../resultLayer';
import { useAppStore } from '../store';

interface Props {
  layer: MapLayer;
  // The class of the button or link; the manager's `lm-btn` by default.
  className?: string;
  // A word after the ⇩ (the manager shows the symbol only).
  label?: string;
  // The column of the manager's grid; with it, a layer without a download leaves an empty place (`empty`), without it nothing.
  col?: string;
  empty?: ReactNode;
}

export default function LayerDownload({ layer, className = 'lm-btn', label, col, empty = null }: Props) {
  const openDownload = useAppStore((s) => s.openDownloadDialog);
  const datasets = useAppStore((s) => s.datasets);
  const kind = layerDownloadKind(layer);
  const text = label ? `⇩ ${label}` : '⇩';
  if (kind === 'zip' && layer.result) {
    return (
      <a className={className} data-col={col} href={resultUrl(layer.result.jobID, RESULT_ZIP)} download rel="noopener noreferrer" title={ZIP_LABEL} aria-label={ZIP_LABEL}>
        {text}
      </a>
    );
  }
  if (kind !== 'dialog') return <>{empty}</>;
  const outcome = decideDownloadOutcomeForLayer(layer, datasets);
  const index = indexOfferedFor(layer, datasets);
  // A layer of an index alone downloads the index and nothing else (UI-03d): where it cannot, the button says why.
  const indexBlock = layer.restore.indexOnly ? indexDownloadBlock(layer, datasets) : null;
  return (
    <button
      type="button"
      className={className}
      data-col={col}
      disabled={outcome === 'disabled' || indexBlock !== null || !canDownloadLayer(layer, datasets)}
      title={
        outcome === 'disabled'
          ? 'Draw an AOI to download this layer'
          : indexBlock
            ? indexBlock
            : index && layer.restore.indexOnly
              ? `Download the ${index.name} of the AOI crop, computed as a Processing job would`
              : index
                ? `Download the AOI crop, one file per group; the ${index.name} too, computed as a Processing job would`
                : outcome === 'originals'
                  ? 'Download the original files, straight from the source'
                  : 'Download the AOI crop, one file per group'
      }
      onClick={() => void openDownload(layer.id)}
    >
      {text}
    </button>
  );
}
