import { useEffect } from 'react';

import { canDownloadLayer, decideDownloadOutcomeForLayer } from '../download';
import type { MapLayer } from '../layers';
import { isJobId, resultUrl } from '../processing';
import { layerProcessBlock, useProcessingStore, ZIP_LABEL } from '../processingStore';
import { MIN_REMAINING_MS, RESULT_ZIP } from '../resultLayer';
import { useAppStore } from '../store';
import Tip from './Tip';

export const EXPIRED_LAYER_TEXT = 'Expired: results are kept for 7 days. Start the job again.';
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

// An empty place of the grid, the size of the button that is missing: the others stay where they are.
function Slot({ col }: { col: string }) {
  return <span className="lm-slot" data-col={col} aria-hidden="true" />;
}

// "Download (ZIP)" of a result layer: the archive of the job, the same link as in its details. Once the
// results are gone there is nothing to download: the place stays empty and the ⚠ of the row says why.
function ResultDownload({ jobID, expired }: { jobID: string; expired: boolean }) {
  if (expired || !isJobId(jobID)) return <Slot col="download" />;
  return (
    <a className="lm-btn" data-col="download" href={resultUrl(jobID, RESULT_ZIP)} download rel="noopener noreferrer" title={ZIP_LABEL} aria-label={ZIP_LABEL}>
      ⇩
    </a>
  );
}

// One row, nine places in a fixed order: eye, name, opacity, up, down, process, download, note, remove.
function LayerRow({ layer: l, index, last }: { layer: MapLayer; index: number; last: boolean }) {
  const remove = useAppStore((s) => s.removeLayer);
  const toggleVis = useAppStore((s) => s.toggleLayerVisible);
  const setOpacity = useAppStore((s) => s.setLayerOpacity);
  const move = useAppStore((s) => s.moveLayer);
  const select = useAppStore((s) => s.selectLayer);
  const openDownload = useAppStore((s) => s.openDownloadDialog);
  const datasets = useAppStore((s) => s.datasets);
  const processLayer = useProcessingStore((s) => s.processLayer);
  const downloadOutcome = decideDownloadOutcomeForLayer(l, datasets);
  const processBlock = layerProcessBlock(l, datasets);
  const notes = [l.result?.expired ? EXPIRED_LAYER_TEXT : null, l.result?.resampled === true ? RESAMPLED_LAYER_TEXT : null].filter(
    (note): note is string => note !== null,
  );
  return (
    <li className="layer-row">
      <button
        type="button"
        className={`lm-eye${l.visible ? '' : ' off'}`}
        data-col="eye"
        title={l.visible ? 'Hide' : 'Show'}
        onClick={() => toggleVis(l.id)}
      >
        {l.visible ? '●' : '○'}
      </button>
      <button
        type="button"
        className="lm-name"
        data-col="name"
        title={`${l.name} — view this layer / continue working on it`}
        onClick={() => select(l.id)}
      >
        {l.name}
      </button>
      <input
        type="range"
        className="lm-opacity"
        data-col="opacity"
        min={0}
        max={1}
        step={0.05}
        value={l.opacity}
        title={`Opacity ${Math.round(l.opacity * 100)}%`}
        aria-label={`Opacity of ${l.name}`}
        onChange={(e) => setOpacity(l.id, Number(e.target.value))}
      />
      <button type="button" className="lm-btn" data-col="up" title="Move up" disabled={index === 0} onClick={() => move(l.id, 'up')}>
        ▲
      </button>
      <button type="button" className="lm-btn" data-col="down" title="Move down" disabled={last} onClick={() => move(l.id, 'down')}>
        ▼
      </button>
      {l.result ? (
        // A result is no scene: nothing can be processed on it yet, so the place stays empty (Otto, 26.10.2026).
        <Slot col="process" />
      ) : (
        <button
          type="button"
          className="lm-btn"
          data-col="process"
          disabled={processBlock !== null}
          title={processBlock ?? 'Process this layer'}
          onClick={() => void processLayer(l.id)}
        >
          ⚙
        </button>
      )}
      {l.result ? (
        <ResultDownload jobID={l.result.jobID} expired={l.result.expired} />
      ) : !l.derived && l.restore.itemIds.length > 0 ? (
        <button
          type="button"
          className="lm-btn"
          data-col="download"
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
      ) : (
        <Slot col="download" />
      )}
      {notes.length > 0 ? (
        <span className="lm-note" data-col="note">
          <Tip text={notes.join(' ')} symbol="⚠" tone="warn" />
        </span>
      ) : (
        <Slot col="note" />
      )}
      <button type="button" className="lm-btn danger" data-col="remove" title="Remove layer" onClick={() => remove(l.id)}>
        ✕
      </button>
    </li>
  );
}

export default function LayerManager() {
  const layers = useAppStore((s) => s.layers);
  useResultExpiry();

  // Docked beside the rail (UI-01 §6.9). It stays mounted when another panel is open: the timer of the
  // result layers above runs either way.
  return (
    <div className="layer-dock" role="region" aria-label="Layers">
      <div className="panel dock-panel layer-manager">
        <div className="results-head">
          <h2>Layers</h2>
          <div className="results-head-right">
            <span>{layers.length}</span>
          </div>
        </div>

        {layers.length === 0 ? (
          <p className="hint-text lm-empty">
            No layers yet — select an image and “Add to layers”.
          </p>
        ) : (
          <ul className="layer-list">
            {layers.map((l, i) => (
              <LayerRow key={l.id} layer={l} index={i} last={i === layers.length - 1} />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
