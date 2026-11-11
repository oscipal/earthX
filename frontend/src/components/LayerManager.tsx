import { useEffect, useRef, useState, type KeyboardEvent as ReactKeyboardEvent, type RefObject } from 'react';

import { zoomFloorHint } from '../datasets';
import { flipIdOf } from '../layerFlip';
import { layerShownName } from '../layerName';
import { EXPIRED_LAYER_TIP, LOCKED_LAYER_TIP, type MapLayer } from '../layers';
import { RGB, RGB_LABEL } from '../processingBands';
import { EXPIRED_PROCESS_TEXT, layerProcessBlock, NO_COPY_TEXT, PROCESS_LAYER_TEXT, useProcessingStore } from '../processingStore';
import { MIN_REMAINING_MS } from '../resultLayer';
import { hasResultsPanel } from '../sections';
import { clampResultsAt } from '../resultsEntry';
import { useAppStore } from '../store';
import { zoomReasonOf } from '../zoomHint';
import BandSelect from './BandSelect';
import EyeButton from './EyeButton';
import { ArrowDownIcon, ArrowUpDownIcon, ArrowUpIcon, CogIcon, GripVerticalIcon, PencilIcon, PlusIcon, TrashIcon } from './icons';
import InlineRename from './InlineRename';
import { RENAME_TIP } from './InspectorParts';
import { REMOVE_TIP } from './LayerActions';
import LayerDownload from './LayerDownload';
import ResultsEye from './ResultsEye';
import Tip from './Tip';
import { useRowDrag, type RowDrag } from './useRowDrag';

export const EXPIRED_LAYER_TEXT = 'Expired: results are kept for 7 days. Start the job again.';
export const TOP_TIP = 'Already at the top';
export const BOTTOM_TIP = 'Already at the bottom';
const moveTip = (direction: 'up' | 'down', blocked: boolean) => (blocked ? (direction === 'up' ? TOP_TIP : BOTTOM_TIP) : direction === 'up' ? 'Move up' : 'Move down');
export const HIDE_LAYER_TIP = 'Hide layer';
export const SHOW_LAYER_TIP = 'Show layer';
export const ADD_BAND_TIP = 'Add this band as a layer of its own';
export const FLIP_TIP = 'Flip through layers (Up and Down or the mouse wheel over the list, Esc to stop)';
export const RESULTS_ENTRY_TIP = 'The search results, the view and the processing preview. Move to change what lies above.';

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

// The grip at the left of a row to take the row with the mouse or a finger. The arrows stay for the keyboard, so the
// grip is no tab stop and no screen reader's business.
function Grip({ dnd }: { dnd: RowDnd }) {
  if (!dnd.grip) return <Slot col="grip" />;
  return (
    <span className="lm-grip" data-col="grip" data-tip-level="advanced" data-tip="Drag to move" aria-hidden="true" {...dnd.grip}>
      <GripVerticalIcon size={14} />
    </span>
  );
}

// One row, eleven places in a fixed order: grip, name and its pencil, then eye, opacity, up, down, process, download, note, remove.
function LayerRow({ layer: l, index, last, dnd, flipped, flipping }: { layer: MapLayer; index: number; last: boolean; dnd: RowDnd; flipped: boolean; flipping: boolean }) {
  const remove = useAppStore((s) => s.removeLayer);
  const rename = useAppStore((s) => s.renameLayer);
  const [renaming, setRenaming] = useState(false);
  const toggleVis = useAppStore((s) => s.toggleLayerVisible);
  const setOpacity = useAppStore((s) => s.setLayerOpacity);
  const move = useAppStore((s) => s.moveLayer);
  const select = useAppStore((s) => s.selectLayer);
  const flipTo = useAppStore((s) => s.flipTo);
  const datasets = useAppStore((s) => s.datasets);
  const mapZoom = useAppStore((s) => s.mapZoom);
  const processLayer = useProcessingStore((s) => s.processLayer);
  const chooseBand = useProcessingStore((s) => s.chooseResultBand);
  const addBand = useAppStore((s) => s.addBandAsLayer);
  const jobs = useProcessingStore((s) => s.jobs);
  const processBlock = layerProcessBlock(l, datasets, jobs);
  const locked = l.result?.deleted === true;
  // A result of several bands draws one of them (NM4-43e PR 2).
  const bands = l.result?.bands;
  const shown = l.visible && !locked;
  // What locks the band of a result: a deleted job, or an expired result.
  const bandLock = locked ? LOCKED_LAYER_TIP : l.result?.expired ? EXPIRED_LAYER_TIP : null;
  // A result that was resampled says nothing here any more: the warning came before the job (NM4-65 part 7).
  const notes = [l.result?.expired && !locked ? EXPIRED_LAYER_TEXT : null].filter(
    (note): note is string => note !== null,
  );
  // A layer that shows nothing at this zoom says why, in either step of the tooltips: nothing over the map does (Otto, 10.11.2026).
  const zoomReason = shown ? zoomReasonOf(l.overlays, mapZoom) : null;
  return (
    <li className={`layer-row${locked ? ' locked' : ''}${flipped ? ' flip' : ''}${dnd.className}`} aria-current={flipped || undefined}>
      <Grip dnd={dnd} />
      <EyeButton row col="eye" shown={shown} locked={locked} tip={locked ? LOCKED_LAYER_TIP : shown ? HIDE_LAYER_TIP : SHOW_LAYER_TIP} onToggle={() => toggleVis(l.id)} />
      {renaming ? (
        <span className="lm-name lm-renaming" data-col="name" data-tip-level="advanced" data-tip="A layer needs a name: an empty one keeps the name it had">
          <InlineRename
            value={l.name}
            label="Layer name"
            maxLength={120}
            onSave={(name) => {
              rename(l.id, name);
              setRenaming(false);
            }}
            onCancel={() => setRenaming(false)}
          />
        </span>
      ) : (
        <button
          type="button"
          className="lm-name"
          data-col="name"
          data-tip-level={zoomReason ? undefined : 'advanced'}
          data-tip={[zoomReason, l.note].filter(Boolean).join(' ') || undefined}
          onClick={() => (flipping ? flipTo(l.id) : select(l.id))}
        >
          {layerShownName(l)}
        </button>
      )}
      {/* The name is renamed here as in the head of the settings (Otto, 3.11.2026). */}
      <button type="button" className="icon-btn sm quiet" data-col="rename" data-tip-level="advanced" data-tip={locked ? LOCKED_LAYER_TIP : RENAME_TIP} aria-label={RENAME_TIP} disabled={locked} onClick={() => setRenaming(true)}>
        <PencilIcon size={14} />
      </button>
      <input
        type="range"
        className="lm-opacity"
        data-col="opacity"
        min={0}
        max={1}
        step={0.05}
        value={l.opacity}
        data-tip-level="advanced" data-tip={locked ? LOCKED_LAYER_TIP : `Opacity ${Math.round(l.opacity * 100)}%`}
        aria-label={`Opacity of ${l.name}`}
        disabled={locked}
        onChange={(e) => setOpacity(l.id, Number(e.target.value))}
      />
      <button type="button" className="icon-btn sm" data-col="up" data-tip-level="advanced" data-tip={moveTip('up', index === 0)} aria-label="Move up" disabled={index === 0} onClick={() => move(l.id, 'up')}>
        <ArrowUpIcon size={14} />
      </button>
      <button type="button" className="icon-btn sm" data-col="down" data-tip-level="advanced" data-tip={moveTip('down', last)} aria-label="Move down" disabled={last} onClick={() => move(l.id, 'down')}>
        <ArrowDownIcon size={14} />
      </button>
      {l.result && processBlock === NO_COPY_TEXT ? (
        // Without the order of its job a result cannot be processed further, and nothing the person does brings it back: the place
        // stays empty (Otto, 31.10.2026).
        <Slot col="process" />
      ) : (
        <button
          type="button"
          className="icon-btn sm"
          data-col="process"
          disabled={processBlock !== null}
          data-tip={processBlock ?? (l.result?.expired ? EXPIRED_PROCESS_TEXT : PROCESS_LAYER_TEXT)}
          aria-label={PROCESS_LAYER_TEXT}
          onClick={() => void processLayer(l.id)}
        >
          <CogIcon size={14} />
        </button>
      )}
      <LayerDownload layer={l} col="download" empty={<Slot col="download" />} />
      {notes.length > 0 ? (
        <span className="lm-note" data-col="note">
          <Tip text={notes.join(' ')} tone="warn" />
        </span>
      ) : (
        <Slot col="note" />
      )}
      <button type="button" className="icon-btn sm danger" data-col="remove" data-tip-level="advanced" data-tip={REMOVE_TIP} aria-label={REMOVE_TIP} onClick={() => remove(l.id)}>
        <TrashIcon size={14} />
      </button>
      {bands && bands.length > 1 && (
        <BandSelect
          label="Band"
          className="lm-band"
          title={bandLock ?? 'The band of the result this layer draws'}
          value={String(l.result?.band ?? 0)}
          options={[
            ...(l.result?.colour ? [{ value: RGB, label: RGB_LABEL }] : []),
            ...bands.map((b, place) => ({ value: String(place), label: b.name || `Band ${place + 1}` })),
          ]}
          disabled={bandLock !== null}
          onChange={(place) => chooseBand(l.id, place === RGB ? RGB : Number(place))}
        />
      )}
      {/* Locked with its reason while the job is deleted and can come back; gone with an expired result (Otto, 26.10.2026). */}
      {bands && bands.length > 1 && l.result?.expired !== true && (
        <button
          type="button"
          className="icon-btn sm lm-add-band"
          disabled={locked}
          data-tip-level="advanced"
          data-tip={locked ? LOCKED_LAYER_TIP : ADD_BAND_TIP}
          aria-label={ADD_BAND_TIP}
          onClick={() => addBand(l.id)}
        >
          <PlusIcon size={14} />
        </button>
      )}
    </li>
  );
}

// The entry "Results" (NM4-59): the search results, the view and the live preview, moved among the layers as one. It has
// a grip, an eye and the two arrows only; the other places stay empty.
function ResultsRow({ first, last, dnd }: { first: boolean; last: boolean; dnd: RowDnd }) {
  const move = useAppStore((s) => s.moveResults);
  // The results of a dataset drawn from a zoom above this one show nothing (M2-10): the row says why, in either step.
  const zoomReason = useAppStore((s) =>
    s.resultsOnMap && !s.focusMode && hasResultsPanel(s.sections) ? zoomFloorHint(s.datasets.find((d) => d.id === s.datasetId), s.mapZoom) : null,
  );
  return (
    <li className={`layer-row results-row${dnd.className}`}>
      <Grip dnd={dnd} />
      <ResultsEye />
      <span className="lm-name results-name" data-col="name" data-tip-level={zoomReason ? undefined : 'advanced'} data-tip={zoomReason ? `${zoomReason} ${RESULTS_ENTRY_TIP}` : RESULTS_ENTRY_TIP}>
        Search results
      </span>
      <Slot col="rename" />
      <Slot col="opacity" />
      <button type="button" className="icon-btn sm" data-col="up" data-tip-level="advanced" data-tip={moveTip('up', first)} aria-label="Move up" disabled={first} onClick={() => move('up')}>
        <ArrowUpIcon size={14} />
      </button>
      <button type="button" className="icon-btn sm" data-col="down" data-tip-level="advanced" data-tip={moveTip('down', last)} aria-label="Move down" disabled={last} onClick={() => move('down')}>
        <ArrowDownIcon size={14} />
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
    <button type="button" className="icon-btn sm lm-flip" aria-pressed={on} data-tip={FLIP_TIP} aria-label="Flip through layers" onClick={() => set(!on)}>
      <ArrowUpDownIcon size={14} />
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

// Keys in the manager while flipping. Esc ends it, the one thing Esc does besides "Cancel" in a dialog (Otto, 2.11.2026). Up and Down step,
// but not in a field, where the arrows are the field's (the opacity slider, a dropdown).
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
          <div>
            {(layers.length > 1 || flipping) && <FlipToggle />}
            <span>{layers.length}</span>
          </div>
        </div>

        {rows === 0 ? (
          <p className="hint lm-empty">
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
