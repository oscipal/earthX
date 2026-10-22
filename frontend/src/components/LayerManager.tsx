import { useEffect } from 'react';

import { canDownloadLayer, decideDownloadOutcomeForLayer } from '../download';
import { layerProcessBlock, useProcessingStore } from '../processingStore';
import { MIN_REMAINING_MS } from '../resultLayer';
import { useAppStore } from '../store';
import Draggable from './Draggable';

export const EXPIRED_LAYER_TEXT = 'Expired: the results of this job are gone. Start the job again.';
export const RESAMPLED_LAYER_TEXT = 'Resampled to a common grid';

// Marks a result layer "Expired" when the time comes (M4-13c-5): one timer for the
// soonest of them, set again after every change to the list. The tiler's `410` is
// the lock behind it; this stops the map asking.
function useResultExpiry(): void {
  const layers = useAppStore((s) => s.layers);
  const expire = useAppStore((s) => s.expireResultLayers);
  useEffect(() => {
    const ends = layers.flatMap((l) => (l.result && !l.result.expired ? [Date.parse(l.result.expires)] : []));
    if (ends.length === 0) return undefined;
    const wait = Math.min(...ends) - MIN_REMAINING_MS - Date.now();
    if (!(wait > 0)) {
      expire(Date.now());
      return undefined;
    }
    // A timer holds 2^31 ms (about 25 days) at most, more than a result lives.
    const timer = setTimeout(() => expire(Date.now()), Math.min(wait + 50, 2 ** 31 - 1));
    return () => clearTimeout(timer);
  }, [layers, expire]);
}

export default function LayerManager() {
  const open = useAppStore((s) => s.layerManagerOpen);
  const panelCollapsed = useAppStore((s) => s.panelCollapsed);
  const layers = useAppStore((s) => s.layers);
  const toggle = useAppStore((s) => s.toggleLayerManager);
  const remove = useAppStore((s) => s.removeLayer);
  const toggleVis = useAppStore((s) => s.toggleLayerVisible);
  const setOpacity = useAppStore((s) => s.setLayerOpacity);
  const move = useAppStore((s) => s.moveLayer);
  const select = useAppStore((s) => s.selectLayer);
  const openDownload = useAppStore((s) => s.openDownloadDialog);
  const datasets = useAppStore((s) => s.datasets);
  const processLayer = useProcessingStore((s) => s.processLayer);
  useResultExpiry();

  // `Draggable` stays mounted regardless of `open` and is only hidden with
  // CSS: unmounting it (the previous `if (!open) return null`) threw away
  // its drag offset every time the panel closed, so a moved panel snapped
  // back to its original spot the next time it opened.
  return (
    <Draggable
      className={`layer-dock${open ? '' : ' layer-dock-hidden'}`}
      avoidSelector=".panel-dock"
      // Opening this panel (or the control dock collapsing/expanding) both
      // change whether the two actually overlap — force a fresh check
      // rather than relying only on `avoidSelector`'s own transition, which
      // this panel's `open` toggle doesn't fire (see Draggable.tsx).
      recalcTrigger={`${open}:${panelCollapsed}`}
    >
      <div className="panel layer-manager">
        <div className="results-head">
          <h2>Layers</h2>
          <div className="results-head-right">
            <span>{layers.length}</span>
            <button type="button" className="link-btn" title="Close" onClick={() => toggle()}>
              ✕
            </button>
          </div>
        </div>

        {layers.length === 0 ? (
          <p className="hint-text lm-empty">
            No layers yet — select an image and “Add to layers”.
          </p>
        ) : (
          <ul className="layer-list">
            {layers.map((l, i) => {
              const downloadOutcome = decideDownloadOutcomeForLayer(l, datasets);
              const processBlock = layerProcessBlock(l, datasets);
              return (
              <li key={l.id} className={`layer-row${l.result?.expired || l.result?.resampled || l.result?.unit ? ' layer-row-noted' : ''}`}>
                <button
                  type="button"
                  className={`lm-eye${l.visible ? '' : ' off'}`}
                  title={l.visible ? 'Hide' : 'Show'}
                  onClick={() => toggleVis(l.id)}
                >
                  {l.visible ? '●' : '○'}
                </button>
                <button
                  type="button"
                  className="lm-name"
                  title={`${l.name} — view this layer / continue working on it`}
                  onClick={() => select(l.id)}
                >
                  {l.name}
                </button>
                <input
                  type="range"
                  className="lm-opacity"
                  min={0}
                  max={1}
                  step={0.05}
                  value={l.opacity}
                  title={`Opacity ${Math.round(l.opacity * 100)}%`}
                  onChange={(e) => setOpacity(l.id, Number(e.target.value))}
                />
                <button
                  type="button"
                  className="lm-btn"
                  title="Move up"
                  disabled={i === 0}
                  onClick={() => move(l.id, 'up')}
                >
                  ▲
                </button>
                <button
                  type="button"
                  className="lm-btn"
                  title="Move down"
                  disabled={i === layers.length - 1}
                  onClick={() => move(l.id, 'down')}
                >
                  ▼
                </button>
                <button
                  type="button"
                  className="lm-btn"
                  disabled={processBlock !== null}
                  title={processBlock ?? 'Process this layer'}
                  onClick={() => void processLayer(l.id)}
                >
                  ⚙
                </button>
                {!l.derived && l.restore.itemIds.length > 0 && (
                  <button
                    type="button"
                    className="lm-btn"
                    disabled={downloadOutcome === 'disabled' || !canDownloadLayer(l, datasets)}
                    title={
                      downloadOutcome === 'disabled'
                        ? 'Draw an AOI to download this layer'
                        : downloadOutcome === 'originals'
                          ? 'Download the original files, straight from the source'
                          : 'Download the AOI crop, one file per group'
                    }
                    onClick={() => void openDownload(l.id)}
                  >
                    ⇩
                  </button>
                )}
                <button
                  type="button"
                  className="lm-btn danger"
                  title="Remove layer"
                  onClick={() => remove(l.id)}
                >
                  ✕
                </button>
                {l.result?.expired && <span className="lm-note hint-text warn">{EXPIRED_LAYER_TEXT}</span>}
                {l.result?.resampled === true && <span className="lm-note hint-text warn">{RESAMPLED_LAYER_TEXT}</span>}
                {l.result?.unit && <span className="lm-note hint-text">Values in {l.result.unit}</span>}
              </li>
              );
            })}
          </ul>
        )}
      </div>
    </Draggable>
  );
}
