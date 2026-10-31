import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from 'react';

import { canDownloadLayer, decideDownloadOutcomeForLayer } from '../download';
import { indexDownloadBlock, indexOfLayer } from '../indexDownload';
import { flipIdOf } from '../layerFlip';
import type { MapLayer } from '../layers';
import { isJobId, resultUrl } from '../processing';
import { RGB, RGB_LABEL } from '../processingBands';
import { EXPIRED_PROCESS_TEXT, layerProcessBlock, NO_COPY_TEXT, PROCESS_RESULT_TEXT, useProcessingStore, ZIP_LABEL } from '../processingStore';
import { MIN_REMAINING_MS, RESULT_ZIP } from '../resultLayer';
import { hasResultsPanel } from '../sections';
import { clampResultsAt } from '../resultsEntry';
import { useAppStore } from '../store';
import BandSelect from './BandSelect';
import Eye from './Eye';
import ResultsEye from './ResultsEye';
import Tip from './Tip';
import { useRowDrag, type RowDrag } from './useRowDrag';

export const EXPIRED_LAYER_TEXT = 'Expired: results are kept for 7 days. Start the job again.';
export const RESAMPLED_LAYER_TEXT = 'Resampled to a common grid';
export const DELETED_LAYER_TIP = 'Job deleted – restore to show';
export const HIDE_LAYER_TIP = 'Hide layer';
export const SHOW_LAYER_TIP = 'Show layer';
export const ADD_BAND_TIP = 'Add this band as a layer of its own';
export const FLIP_TIP = 'Flip through layers (↑/↓ or the mouse wheel over the list, Esc to stop)';
export const FLIP_ROW_TIP = 'Draw this layer on top of the others';
export const RESULTS_ENTRY_TIP = 'Search results, the view and the processing preview. Move to change what lies above.';

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

// What a row takes from the drag (NM4-65 part 1): the class that shows where it stands in it, and the handlers of its grip.
// `grip` is null while there is only one row: there is nothing to move it past.
export interface RowDnd {
  className: string;
  grip: ReturnType<ReturnType<typeof useRowDrag>['grip']> | null;
}

// The grip at the left of a row: 2 × 3 small dots to take the row with the mouse or a finger. ▲/▼ stay for the keyboard, so the
// grip is no tab stop and no screen reader's business.
function Grip({ dnd }: { dnd: RowDnd }) {
  if (!dnd.grip) return <Slot col="grip" />;
  return (
    <span className="lm-grip" data-col="grip" title="Drag to move" aria-hidden="true" {...dnd.grip}>
      <svg viewBox="0 0 8 12" width="8" height="12" focusable="false">
        {[1, 4].flatMap((x) => [1.5, 6, 10.5].map((y) => <circle key={`${x}-${y}`} cx={x} cy={y} r="1.1" fill="currentColor" />))}
      </svg>
    </span>
  );
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

// One row, ten places in a fixed order: grip, eye, name, opacity, up, down, process, download, note, remove.
function LayerRow({ layer: l, index, last, dnd, flipped, flipping }: { layer: MapLayer; index: number; last: boolean; dnd: RowDnd; flipped: boolean; flipping: boolean }) {
  const remove = useAppStore((s) => s.removeLayer);
  const toggleVis = useAppStore((s) => s.toggleLayerVisible);
  const setOpacity = useAppStore((s) => s.setLayerOpacity);
  const move = useAppStore((s) => s.moveLayer);
  const select = useAppStore((s) => s.selectLayer);
  const flipTo = useAppStore((s) => s.flipTo);
  const openDownload = useAppStore((s) => s.openDownloadDialog);
  const datasets = useAppStore((s) => s.datasets);
  const processLayer = useProcessingStore((s) => s.processLayer);
  const chooseBand = useProcessingStore((s) => s.chooseResultBand);
  const addBand = useAppStore((s) => s.addBandAsLayer);
  const downloadOutcome = decideDownloadOutcomeForLayer(l, datasets);
  const jobs = useProcessingStore((s) => s.jobs);
  const processBlock = layerProcessBlock(l, datasets, jobs);
  const locked = l.result?.deleted === true;
  // A result of several bands draws one of them (NM4-43e PR 2).
  const bands = l.result?.bands;
  const shown = l.visible && !locked;
  const notes = [l.result?.expired && !locked ? EXPIRED_LAYER_TEXT : null, l.result?.resampled === true ? RESAMPLED_LAYER_TEXT : null].filter(
    (note): note is string => note !== null,
  );
  return (
    <li className={`layer-row${locked ? ' locked' : ''}${flipped ? ' flip' : ''}${dnd.className}`} aria-current={flipped || undefined}>
      <Grip dnd={dnd} />
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
          (locked ? `${l.name} — ${DELETED_LAYER_TIP}` : `${l.name} — ${flipping ? FLIP_ROW_TIP : 'view this layer / continue working on it'}`) +
          (l.note ? `\n${l.note}` : '')
        }
        onClick={() => (flipping ? flipTo(l.id) : select(l.id))}
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
      {l.result && processBlock === NO_COPY_TEXT ? (
        // Without the order of its job a result cannot be processed further, and nothing the person does brings it back: the place
        // stays empty (Otto, 31.10.2026).
        <Slot col="process" />
      ) : (
        <button
          type="button"
          className="lm-btn"
          data-col="process"
          disabled={processBlock !== null}
          title={processBlock ?? (l.result ? (l.result.expired ? EXPIRED_PROCESS_TEXT : PROCESS_RESULT_TEXT) : 'Process this layer')}
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
              ? (indexDownloadBlock(l, datasets) ?? 'Draw an AOI to download this layer')
              : indexOfLayer(l, datasets)
                ? `Download the ${indexOfLayer(l, datasets)!.name} of the AOI crop, computed as a Processing job would`
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
      {l.date && (
        <span className="lm-date" title="Acquisition date (UTC)">
          {l.date}
        </span>
      )}
      {bands && bands.length > 1 && (
        <BandSelect
          label="Band"
          className="lm-band"
          title="The band of the result this layer draws"
          value={String(l.result?.band ?? 0)}
          options={[
            ...(l.result?.colour ? [{ value: RGB, label: RGB_LABEL }] : []),
            ...bands.map((b, place) => ({ value: String(place), label: b.name || `Band ${place + 1}` })),
          ]}
          disabled={locked || l.result?.expired === true}
          onChange={(place) => chooseBand(l.id, place === RGB ? RGB : Number(place))}
        />
      )}
      {bands && bands.length > 1 && !locked && l.result?.expired !== true && (
        <button type="button" className="lm-btn lm-add-band" title={ADD_BAND_TIP} aria-label={ADD_BAND_TIP} onClick={() => addBand(l.id)}>
          ＋
        </button>
      )}
    </li>
  );
}

// The entry "Results" (NM4-59): the search results, the view and the live preview, moved among the layers as one. It has
// a grip, an eye and ▲/▼ only; the other places stay empty.
function ResultsRow({ first, last, dnd }: { first: boolean; last: boolean; dnd: RowDnd }) {
  const move = useAppStore((s) => s.moveResults);
  return (
    <li className={`layer-row results-row${dnd.className}`}>
      <Grip dnd={dnd} />
      <ResultsEye />
      <span className="lm-name results-name" data-col="name" title={RESULTS_ENTRY_TIP}>
        Results
      </span>
      <Slot col="opacity" />
      <button type="button" className="lm-btn" data-col="up" title="Move up" disabled={first} onClick={() => move('up')}>
        ▲
      </button>
      <button type="button" className="lm-btn" data-col="down" title="Move down" disabled={last} onClick={() => move('down')}>
        ▼
      </button>
      <Slot col="process" />
      <Slot col="download" />
      <Slot col="note" />
      <Slot col="remove" />
    </li>
  );
}

// The toggle of "Flip through layers" in the head of the manager (NM4-65 part 9): up and down arrows around a layer.
function FlipToggle() {
  const on = useAppStore((s) => s.flipThrough);
  const set = useAppStore((s) => s.setFlipThrough);
  return (
    <button type="button" className="lm-btn lm-flip" aria-pressed={on} title={FLIP_TIP} aria-label="Flip through layers" onClick={() => set(!on)}>
      <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
        <path d="M8 1.5 11.5 5h-7z" fill="currentColor" />
        <path d="M8 14.5 4.5 11h7z" fill="currentColor" />
        <rect x="3" y="7" width="10" height="2" rx="1" fill="currentColor" />
      </svg>
    </button>
  );
}

// What flipping answers to while it is on: the mouse wheel over the list steps (a native listener, so that the list does not
// scroll along), Escape ends it unless another part of the page took the key (a pop-up, a tooltip), and it ends of itself when
// fewer than two layers are left. The row that is flipped to is kept in sight.
function useFlipping(listRef: RefObject<HTMLUListElement | null>) {
  const flipping = useAppStore((s) => s.flipThrough);
  const flipId = useAppStore((s) => s.flipLayerId);
  const count = useAppStore((s) => s.layers.length);
  const step = useAppStore((s) => s.flipStep);
  const setFlip = useAppStore((s) => s.setFlipThrough);

  useEffect(() => {
    if (flipping && count < 2) setFlip(false);
  }, [flipping, count, setFlip]);

  useEffect(() => {
    if (!flipping) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !event.defaultPrevented) setFlip(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [flipping, setFlip]);

  useEffect(() => {
    const list = listRef.current;
    if (!flipping || !list) return undefined;
    let travelled = 0;
    let last = 0;
    const onWheel = (event: WheelEvent) => {
      event.preventDefault();
      // A pause starts a new turn of the wheel; a turn of about one notch (or a flick of a touchpad) is one step.
      if (event.timeStamp - last > WHEEL_PAUSE_MS) travelled = 0;
      last = event.timeStamp;
      travelled += event.deltaY;
      if (Math.abs(travelled) < WHEEL_NOTCH) return;
      step(travelled > 0 ? 1 : -1);
      travelled = 0;
    };
    list.addEventListener('wheel', onWheel, { passive: false });
    return () => list.removeEventListener('wheel', onWheel);
  }, [flipping, listRef, step]);

  useEffect(() => {
    if (flipping) listRef.current?.querySelector('.layer-row.flip')?.scrollIntoView?.({ block: 'nearest' });
  }, [flipping, flipId, listRef]);
  return flipping;
}

const WHEEL_NOTCH = 40;
const WHEEL_PAUSE_MS = 180;

// Keys in the manager while flipping. Esc ends it and, taken here, does not close the panel as well (`App.tsx` leaves a key
// that was taken alone). ↑/↓ step, but not in a field, where the arrows are the field's (the opacity slider, a dropdown).
function onFlipKeys(event: ReactKeyboardEvent<HTMLElement>, step: (dir: 1 | -1) => void, end: () => void) {
  if (event.key === 'Escape' && !event.defaultPrevented && !(event.target as HTMLElement).closest('input, textarea, select, .popover, [role="menu"]')) {
    event.preventDefault();
    end();
    return;
  }
  if (event.key !== 'ArrowUp' && event.key !== 'ArrowDown') return;
  if ((event.target as HTMLElement).closest('input, select, textarea')) return;
  event.preventDefault();
  step(event.key === 'ArrowDown' ? 1 : -1);
}

// How the row at `index` stands in the drag: held, or the place it would take (a line above the row where the row held comes
// from below, under it where it comes from above).
function dndClass(drag: RowDrag | null, index: number): string {
  if (!drag) return '';
  if (index === drag.from) return ' dragging';
  if (index !== drag.over) return '';
  return drag.over > drag.from ? ' drop-below' : ' drop-above';
}

export default function LayerManager() {
  const layers = useAppStore((s) => s.layers);
  const moveRowTo = useAppStore((s) => s.moveRowTo);
  // The entry "Results" is there while the search has results (NM4-59); without them the view and the preview lie at its
  // place all the same.
  const hasResults = useAppStore((s) => hasResultsPanel(s.sections));
  const resultsAt = useAppStore((s) => clampResultsAt(s.resultsAt, s.layers));
  useResultExpiry();
  useDeletedResults();
  const rows = layers.length + (hasResults ? 1 : 0);
  // The rows as they are drawn: a layer by its id, "Results" as `null`.
  const order: (string | null)[] = [...layers.slice(0, resultsAt).map((l) => l.id), ...(hasResults ? [null] : []), ...layers.slice(resultsAt).map((l) => l.id)];
  const listRef = useRef<HTMLUListElement>(null);
  const { drag, grip } = useRowDrag(listRef, (from, to) => moveRowTo(order[from] ?? null, to));
  const flipping = useFlipping(listRef);
  const flipId = useAppStore(flipIdOf);
  const flipStep = useAppStore((s) => s.flipStep);
  const setFlip = useAppStore((s) => s.setFlipThrough);
  const dndOf = (row: number): RowDnd => ({ className: dndClass(drag, row), grip: rows > 1 ? grip(row) : null });
  const rowOf = (l: MapLayer, i: number) => {
    const row = hasResults && i >= resultsAt ? i + 1 : i;
    return <LayerRow key={l.id} layer={l} index={row} last={row === rows - 1} dnd={dndOf(row)} flipped={flipId === l.id} flipping={flipping} />;
  };

  // Docked beside the rail (UI-01 §6.9). It stays mounted when another panel is open: the timer of the
  // result layers above runs either way.
  return (
    <div className="layer-dock" role="region" aria-label="Layers" onKeyDown={flipping ? (event) => onFlipKeys(event, flipStep, () => setFlip(false)) : undefined}>
      <div className="panel dock-panel layer-manager">
        <div className="results-head">
          <h2>Layers</h2>
          <div className="results-head-right">
            {(layers.length > 1 || flipping) && <FlipToggle />}
            <span>{layers.length}</span>
          </div>
        </div>

        {rows === 0 ? (
          <p className="hint-text lm-empty">
            No layers yet — select an image and “Add to layers”.
          </p>
        ) : (
          <ul className={`layer-list${drag ? ' is-dragging' : ''}`} ref={listRef}>
            {layers.slice(0, resultsAt).map(rowOf)}
            {hasResults && <ResultsRow first={resultsAt === 0} last={resultsAt === layers.length} dnd={dndOf(resultsAt)} />}
            {layers.slice(resultsAt).map((l, i) => rowOf(l, i + resultsAt))}
          </ul>
        )}
      </div>
    </div>
  );
}
