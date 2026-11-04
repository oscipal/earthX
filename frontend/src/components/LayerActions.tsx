// "Actions" of a layer in the settings bar (Otto, 2.11.2026): process it, download it, add a copy of it as it is drawn now, remove it.
// The same for a pinned view and a result layer, with the rules of the layer manager: the same "Process", the same download, the same
// removal (the settings close with the layer).

import { layerDownloadKind } from '../download';
import type { MapLayer } from '../layers';
import { EXPIRED_PROCESS_TEXT, layerProcessBlock, NO_COPY_TEXT, PROCESS_RESULT_TEXT, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import { CogIcon, PlusIcon, TrashIcon } from './icons';
import LayerDownload from './LayerDownload';

export const REMOVE_TIP = 'Remove layer';
export const COPY_LABEL = 'Add current view to layers';
const COPY_TIP = 'Add a copy of this layer, drawn as it is now, as a new layer; this layer stays as it was saved';

interface Props {
  layer: MapLayer;
  // Draws what the fields ask for, where that is not drawn yet, before the copy is made: resolves once it is drawn, `false` where it
  // cannot be (the fields say why).
  beforeCopy?: () => Promise<boolean>;
}

export default function LayerActions({ layer, beforeCopy }: Props) {
  const datasets = useAppStore((s) => s.datasets);
  const remove = useAppStore((s) => s.removeLayer);
  const copy = useAppStore((s) => s.copyLayerAsShown);
  const jobs = useProcessingStore((s) => s.jobs);
  const processLayer = useProcessingStore((s) => s.processLayer);
  const processBlock = layerProcessBlock(layer, datasets, jobs);
  const locked = layer.result?.deleted === true;
  return (
    <div className="vc-actions">
      <button
        type="button"
        className="btn"
        disabled={processBlock !== null}
        data-tip={processBlock === NO_COPY_TEXT ? NO_COPY_TEXT : (processBlock ?? (layer.result ? (layer.result.expired ? EXPIRED_PROCESS_TEXT : PROCESS_RESULT_TEXT) : 'Process this layer'))}
        onClick={() => void processLayer(layer.id)}
      >
        <CogIcon lead />Process
      </button>
      {layerDownloadKind(layer) !== null ? <LayerDownload layer={layer} className="btn" label="Download" /> : <span />}
      <button
        type="button"
        className="btn vc-copy"
        disabled={locked}
        data-tip={COPY_TIP}
        onClick={() => {
          void (beforeCopy ? beforeCopy() : Promise.resolve(true)).then((drawn) => drawn && copy(layer.id));
        }}
      >
        <PlusIcon lead />{COPY_LABEL}
      </button>
      <button type="button" className="btn danger vc-remove" data-tip={REMOVE_TIP} aria-label={REMOVE_TIP} onClick={() => remove(layer.id)}>
        <TrashIcon />
      </button>
    </div>
  );
}
