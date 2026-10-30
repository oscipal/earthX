import { useEffect } from 'react';

import { canDownloadLayer, decideDownloadOutcomeForLayer } from '../download';
import type { MapLayer } from '../layers';
import { isJobId, resultUrl } from '../processing';
import { layerProcessBlock, useProcessingStore, ZIP_LABEL } from '../processingStore';
import { MIN_REMAINING_MS, RESULT_ZIP } from '../resultLayer';
import { useAppStore } from '../store';
import Eye from './Eye';
import Tip from './Tip';

export const EXPIRED_LAYER_TEXT = 'Expired: results are kept for 7 days. Start the job again.';
export const RESAMPLED_LAYER_TEXT = 'Resampled to a common grid';
export const DELETED_LAYER_TIP = 'Job deleted – restore to show';
export const HIDE_LAYER_TIP = 'Hide layer';
export const SHOW_LAYER_TIP = 'Show layer';

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

// Locks the result layers of deleted jobs for the day they can be restored, and takes them out when it is over
// (NM4-27). One timer for the soonest end; the list of deletions is read as one text, so that only a change of it
// runs the effect.
function useDeletedResults(): void {
  const deletions = useProcessingStore((s) =>
    s.jobs.flatMap((j) => (j.deletedUntil !== null ? [`${j.jobID}|${Date.parse(j.deletedUntil)}`] : [])).join(','),
  );
  const sync = useAppStore((s) => s.syncDeletedResults);
  useEffect(() => {
    const until = new Map(deletions === '' ? [] : deletions.split(',').map((entry): [string, number] => {
      const [jobID, end] = entry.split('|');
      return [jobID, Number(end)];
    }));
    sync(until, Date.now());
    const ahead = [...until.values()].filter((end) => end > Date.now());
    if (ahead.length === 0) return undefined;
    const wait = Math.min(...ahead) - Date.now();
    const timer = setTimeout(() => sync(until, Date.now()), Math.min(wait + 50, 2 ** 31 - 1));
    return () => clearTimeout(timer);
  }, [deletions, sync]);
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
  const locked = l.result?.deleted === true;
  const shown = l.visible && !locked;
  const notes = [l.result?.expired && !locked ? EXPIRED_LAYER_TEXT : null, l.result?.resampled === true ? RESAMPLED_LAYER_TEXT : null].filter(
    (note): note is string => note !== null,
  );
  return (
    <li className={`layer-row${locked ? ' locked' : ''}`}>
      <button
        type="button"
        className={`lm-eye${shown ? '' : ' off'}`}
        data-col="eye"
        title={locked ? DELETED_LAYER_TIP : shown ? HIDE_LAYER_TIP : SHOW_LAYER_TIP}
        aria-label={locked ? DELETED_LAYER_TIP : shown ? HIDE_LAYER_TIP : SHOW_LAYER_TIP}
        aria-pressed={locked ? undefined : shown}
        aria-disabled={locked || undefined}
        onClick={() => {
          if (!locked) toggleVis(l.id);
        }}
      >
        <Eye off={!shown} />
      </button>
      <button
        type="button"
        className="lm-name"
        data-col="name"
        title={
          (locked ? `${l.name} — ${DELETED_LAYER_TIP}` : `${l.name} — view this layer / continue working on it`) +
          (l.note ? `\n${l.note}` : '')
        }
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
        disabled={locked}
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
        <ResultDownload jobID={l.result.jobID} expired={l.result.expired || locked} />
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
  useDeletedResults();

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
