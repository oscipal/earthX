// The processing manager (UI-01 §6.10): the jobs of this browser, each with its title, progress and expiry,
// as rows; the jobs of one batch as one row that opens into its parts. A job is never deleted, only
// archived and put in a group. A click on a job opens its details in the processing window. R renames, G moves
// to a group and A archives the row that has the focus or else the one under the pointer, with no click first
// (never while a field has the keys); the arrow keys go from row to row.

import { useEffect, useMemo, useRef, useState, type DragEvent as ReactDragEvent, type KeyboardEvent as ReactKeyboardEvent, type PointerEvent as ReactPointerEvent, type RefObject } from 'react';

import { MAX_NAME_LENGTH, MAX_TITLE_LENGTH, type ShelfGroup } from '../jobShelf';
import { loadCollapsedGroups, loadJobFilter, saveCollapsedGroups, saveJobFilter, type JobFilter } from '../preferences';
import { isJobId } from '../processing';
import { MIN_REMAINING_MS } from '../resultLayer';
import { useProcessingStore, type BatchEntry, type JobEntry, type ManagerTarget } from '../processingStore';
import InlineRename from './InlineRename';
import { DownloadZip } from './JobRow';
import Popover from './Popover';
import { focusFirstItem } from '../popover';
import { batchSummary, countBatch, formatUntil, jobLabel, jobState, SHORTCUTS, useNowUntil, type JobState } from './jobView';
import Tip from './Tip';

export const KEPT_HERE_TIP = "Jobs are kept in this browser only: a private window or clearing the browser's data loses them.";
export const STORAGE_FULL_TIP = 'Browser storage is full: copies of the oldest orders were dropped.';
export const NOT_KEPT_TEXT = 'This browser does not keep your jobs. Download results before you close the tab.';
export const GROUP_NOT_EMPTY_TIP = 'Only an empty group can be removed.';

// How far the menu of a row is open: closed, the list of actions, or the list of groups to move to.
type MenuMode = 'closed' | 'menu' | 'move';

interface MenuProps {
  // What the menu offers; a missing action is not listed.
  onRename?: () => void;
  groups: ShelfGroup[];
  groupId: string | null;
  onMove?: (groupId: string | null) => void;
  archived?: boolean;
  onArchive?: (archived: boolean) => void;
  cancel?: { label: string; disabled: boolean; run: () => void };
  name: string;
  mode: MenuMode;
  onMode: (mode: MenuMode) => void;
  // The row the list hangs on: it is as wide as the row and lies over everything, outside the scrolling list.
  anchor: RefObject<HTMLElement | null>;
}

// "⋯" at the end of a row. The list is a `Popover`: in a portal over the whole window, so the scrolling list
// of jobs and the panel cannot cut it off or cover it.
function RowMenu({ onRename, groups, groupId, onMove, archived, onArchive, cancel, name, mode, onMode, anchor }: MenuProps) {
  const button = useRef<HTMLButtonElement>(null);
  const items = useRef<HTMLDivElement>(null);
  // The `Popover` focuses its first entry once per opening; the list of groups replaces the entry that has
  // the focus, so the focus goes to its first one again.
  useEffect(() => {
    if (mode === 'move') focusFirstItem(items.current);
  }, [mode]);
  const hasActions = onRename || onMove || onArchive || cancel;
  if (!hasActions) return <span className="pm-icon" aria-hidden="true" />;
  const done = (run: () => void, keepFocus = false) => () => {
    const row = anchor.current?.closest('.pm-row');
    onMode('closed');
    run();
    if (keepFocus) refocusAround(row);
  };
  const moving = mode === 'move';
  // With the menu open the letter is the item: no Enter after it.
  const onKey = (event: ReactKeyboardEvent<HTMLElement>) => {
    if (moving || event.ctrlKey || event.altKey || event.metaKey) return;
    const key = event.key.toUpperCase();
    const run =
      key === SHORTCUTS.rename ? onRename && done(onRename) : key === SHORTCUTS.move ? onMove && (() => onMode('move')) : key === SHORTCUTS.archive ? onArchive && done(() => onArchive(!archived), true) : undefined;
    if (!run) return;
    event.preventDefault();
    run();
  };
  return (
    <div className="pm-menu">
      <button
        type="button"
        ref={button}
        className="pm-icon"
        aria-haspopup="menu"
        aria-expanded={mode !== 'closed'}
        aria-label={`Actions for ${name}`}
        title="Actions"
        onClick={() => onMode(mode === 'closed' ? 'menu' : 'closed')}
      >
        ⋯
      </button>
      <Popover
        anchorRef={anchor}
        triggerRef={button}
        open={mode !== 'closed'}
        onClose={() => onMode('closed')}
        className="pm-menu-list"
        role="menu"
        ariaLabel={`Actions for ${name}`}
        focusOnOpen
      >
        <div className="pm-menu-items" ref={items} onKeyDown={onKey}>
          {!moving && onRename && (
            <button type="button" role="menuitem" aria-keyshortcuts={SHORTCUTS.rename} onClick={done(onRename)}>
              <span className="pm-menu-label">Rename</span>
              <span className="pm-key" aria-hidden="true">{SHORTCUTS.rename}</span>
            </button>
          )}
          {!moving && onMove && (
            <button type="button" role="menuitem" aria-keyshortcuts={SHORTCUTS.move} onClick={() => onMode('move')}>
              <span className="pm-menu-label">Move to group…</span>
              <span className="pm-key" aria-hidden="true">{SHORTCUTS.move}</span>
            </button>
          )}
          {moving && onMove && (
            <>
              <button type="button" role="menuitemradio" aria-checked={groupId === null} onClick={done(() => onMove(null), true)}>
                Ungrouped
              </button>
              {groups.map((g) => (
                <button key={g.id} type="button" role="menuitemradio" aria-checked={groupId === g.id} onClick={done(() => onMove(g.id), true)}>
                  {g.name}
                </button>
              ))}
            </>
          )}
          {!moving && onArchive && (
            <button type="button" role="menuitem" aria-keyshortcuts={SHORTCUTS.archive} onClick={done(() => onArchive(!archived), true)}>
              <span className="pm-menu-label">{archived ? 'Unarchive' : 'Archive'}</span>
              <span className="pm-key" aria-hidden="true">{SHORTCUTS.archive}</span>
            </button>
          )}
          {!moving && cancel && (
            <button type="button" role="menuitem" disabled={cancel.disabled} onClick={done(cancel.run)}>
              {cancel.label}
            </button>
          )}
        </div>
      </Popover>
    </div>
  );
}

// The keys R, G and A act on a row without a click first: the row the key was pressed on, the one that has the
// focus, or the one under the pointer. The row hears of it as an event; what it does is its own.
const ROW_ACTION = 'pm-row-action';
type RowAction = 'rename' | 'move' | 'archive';
const TOP_ROW = '.pm-rows > .pm-row';
// Where a key belongs to a field, a menu or a dialog, and not to the row.
const KEYS_ELSEWHERE = 'input, textarea, select, [contenteditable="true"], .popover';

// The row under the pointer, as far as the row says so itself: `:hover` is no help to a test, and a row that
// was taken out of the list never says it was left.
let hovered: HTMLElement | null = null;

function useRowActions(row: RefObject<HTMLElement | null>, actions: Record<RowAction, () => void>) {
  const latest = useRef(actions);
  latest.current = actions;
  useEffect(() => {
    const element = row.current;
    if (!element) return undefined;
    const run = (event: Event) => latest.current[(event as CustomEvent<RowAction>).detail]();
    const enter = () => {
      hovered = element;
    };
    const leave = () => {
      if (hovered === element) hovered = null;
    };
    element.addEventListener(ROW_ACTION, run);
    element.addEventListener('pointerenter', enter);
    element.addEventListener('pointerleave', leave);
    return () => {
      element.removeEventListener(ROW_ACTION, run);
      element.removeEventListener('pointerenter', enter);
      element.removeEventListener('pointerleave', leave);
      leave();
    };
  }, [row]);
}

// For a part of a batch, which listens to nothing.
const noRow: RefObject<HTMLElement | null> = { current: null };

const topRowOf = (element: Element | null | undefined) => element?.closest<HTMLElement>(TOP_ROW) ?? null;

function rowKey(event: KeyboardEvent) {
  if (event.defaultPrevented || event.ctrlKey || event.altKey || event.metaKey) return;
  const target = event.target as HTMLElement;
  if (target.closest(KEYS_ELSEWHERE) || document.querySelector('.dialog-backdrop')) return;
  const key = event.key.toUpperCase();
  const action: RowAction | null = key === SHORTCUTS.rename ? 'rename' : key === SHORTCUTS.move ? 'move' : key === SHORTCUTS.archive ? 'archive' : null;
  const arrow = event.key === 'ArrowDown' ? 1 : event.key === 'ArrowUp' ? -1 : 0;
  if (!action && !arrow) return;
  if (arrow) {
    // From row to row, once the focus is in the manager; from its other controls to the first or the last.
    if (!target.closest('.processing-manager')) return;
    const rows = [...document.querySelectorAll<HTMLElement>(`.pm-list ${TOP_ROW}`)];
    const at = rows.indexOf(topRowOf(target) as HTMLElement);
    const next = at < 0 ? (arrow > 0 ? rows[0] : rows.at(-1)) : rows[at + arrow];
    if (!next) return;
    event.preventDefault();
    next.querySelector<HTMLElement>(':scope > .pm-line .pm-open')?.focus();
    return;
  }
  const row = topRowOf(target) ?? topRowOf(document.activeElement) ?? (hovered?.isConnected ? hovered : null);
  if (!row || !action) return;
  event.preventDefault();
  row.dispatchEvent(new CustomEvent<RowAction>(ROW_ACTION, { detail: action }));
  if (action === 'archive') refocusAround(row);
}

// An action can take the row out of the list (archived under "Active", moved to a folded group) or put it
// somewhere else, and the focus would fall to the page, so that the next key does nothing. It goes back to the
// row, or else to the row beside it, once the list has been drawn again.
let refocusTimer: ReturnType<typeof setTimeout> | undefined;

function refocusAround(row: Element | null | undefined) {
  if (!(row instanceof HTMLElement)) return;
  const id = row.dataset.rowId;
  const beside = (row.nextElementSibling ?? row.previousElementSibling) as HTMLElement | null;
  clearTimeout(refocusTimer);
  refocusTimer = setTimeout(() => {
    const held = document.activeElement;
    // Something else took the focus meanwhile (a field, the menu): leave it there.
    if (held && held !== document.body && held.isConnected) return;
    const open = (rowId?: string) =>
      rowId ? document.querySelector<HTMLElement>(`.pm-list [data-row-id="${rowId}"] > .pm-line .pm-open`) : null;
    (open(id) ?? open(beside?.dataset.rowId))?.focus();
  }, 0);
}

// A click on the row, not only on its button, puts the focus on the row: some browsers do not focus a
// button that is clicked, and then the keys of the row would have nothing to act on.
function focusOnPress(event: ReactPointerEvent<HTMLElement>) {
  const target = event.target as HTMLElement;
  if (target.closest('button, a, input, .tip')) return;
  event.currentTarget.querySelector<HTMLElement>(':scope > .pm-line .pm-open')?.focus();
}

// The focus returns to the row's own button when a rename ends, or the keyboard user would be left on nothing.
function useRefocusAfter(editing: boolean, row: RefObject<HTMLElement | null>) {
  const was = useRef(editing);
  useEffect(() => {
    if (was.current && !editing) row.current?.querySelector<HTMLElement>('.pm-open')?.focus();
    was.current = editing;
  }, [editing, row]);
}

// The attributes of a row that can be dragged to a group.
function dragSource(target: ManagerTarget, id: string, onDrag?: (id: string | null) => void) {
  return {
    draggable: true,
    onDragStart: (event: ReactDragEvent<HTMLElement>) => {
      event.dataTransfer.setData(DRAG_TYPE, JSON.stringify(target));
      event.dataTransfer.effectAllowed = 'move';
      onDrag?.(id);
    },
    onDragEnd: () => onDrag?.(null),
  };
}

function Meter({ state, progress }: { state: JobState; progress?: number }) {
  const value = progress ?? state.progress;
  return value === null ? null : <progress className="pm-progress" max={100} value={value} aria-label="Progress" />;
}

function JobItem({ job, now, part, groups, onDrag, dragging }: { job: JobEntry; now: number; part?: boolean; groups: ShelfGroup[] } & DragProps) {
  const open = useProcessingStore((s) => s.openJobDetails);
  const cancelJob = useProcessingStore((s) => s.cancelJob);
  const followJob = useProcessingStore((s) => s.followJob);
  const rename = useProcessingStore((s) => s.renameJob);
  const setArchived = useProcessingStore((s) => s.setArchived);
  const moveToGroup = useProcessingStore((s) => s.moveToGroup);
  const [renaming, setRenaming] = useState(false);
  const [menu, setMenu] = useState<MenuMode>('closed');
  const line = useRef<HTMLDivElement>(null);
  const row = useRef<HTMLLIElement>(null);
  useRefocusAfter(renaming, row);
  // The job of another tab, or an archived one, is followed from the moment its row is shown.
  useEffect(() => {
    if (job.status === null) followJob(job.jobID);
  }, [job.jobID, job.status, followJob]);
  const state = jobState(job, now);
  const title = part ? (job.part ?? jobLabel(job)) : jobLabel(job);
  const target: ManagerTarget = { jobID: job.jobID };
  // The parts of a batch have no keys of their own: the batch's row hears them.
  useRowActions(part ? noRow : row, {
    rename: () => setRenaming(true),
    move: () => setMenu('move'),
    archive: () => setArchived(target, !job.archived),
  });
  return (
    <li
      ref={row}
      data-row-id={job.jobID}
      className={`pm-row${part ? ' part' : ''}${job.archived ? ' archived' : ''}${dragging ? ' dragging' : ''}`}
      aria-keyshortcuts={part ? undefined : 'R G A'}
      onPointerDown={part ? undefined : focusOnPress}
      {...(part || renaming ? {} : dragSource({ jobID: job.jobID }, job.jobID, onDrag))}
    >
      <div className="pm-line" ref={line}>
        {renaming ? (
          <InlineRename
            value={job.title ?? ''}
            label="Job title"
            maxLength={MAX_TITLE_LENGTH}
            onSave={(name) => {
              rename(job.jobID, name);
              setRenaming(false);
            }}
            onCancel={() => setRenaming(false)}
          />
        ) : (
          <button
            type="button"
            className="pm-open"
            title={title}
            onClick={(e) => {
              e.currentTarget.focus();
              open(job.jobID);
            }}
          >
            <span className="pm-title">{title}</span>
            <span className={`pm-meta ${state.key}`}>
              <span className="pm-state">{state.text}</span>
              {state.key !== 'cancelled' && (
                <span className="pm-until" title={job.expires}>
                  until {formatUntil(job.expires, now)}
                </span>
              )}
              {job.archived && <span className="pm-tag">Archived</span>}
            </span>
          </button>
        )}
        <DownloadZip job={job} now={now} />
        <RowMenu
          name={title}
          mode={menu}
          onMode={setMenu}
          anchor={line}
          groups={groups}
          groupId={job.groupId}
          onRename={part ? undefined : () => setRenaming(true)}
          onMove={part ? undefined : (groupId) => moveToGroup(target, groupId)}
          archived={job.archived}
          onArchive={part ? undefined : (archived) => setArchived(target, archived)}
          cancel={
            job.phase === 'active'
              ? { label: 'Cancel', disabled: job.cancelling || !job.status, run: () => void cancelJob(job.jobID) }
              : undefined
          }
        />
      </div>
      <Meter state={state} />
      {job.phase === 'failed' && <span className="pm-fault">{job.failure ?? job.status?.message ?? 'The job failed'}</span>}
    </li>
  );
}

function BatchItem({ batch, parts, now, groups, onDrag, dragging }: { batch: BatchEntry; parts: JobEntry[]; now: number; groups: ShelfGroup[] } & DragProps) {
  const [expanded, setExpanded] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [menu, setMenu] = useState<MenuMode>('closed');
  const line = useRef<HTMLDivElement>(null);
  const row = useRef<HTMLLIElement>(null);
  useRefocusAfter(renaming, row);
  const renameBatch = useProcessingStore((s) => s.renameBatch);
  const setArchived = useProcessingStore((s) => s.setArchived);
  const moveToGroup = useProcessingStore((s) => s.moveToGroup);
  const cancelBatch = useProcessingStore((s) => s.cancelBatch);
  const followJob = useProcessingStore((s) => s.followJob);
  // The total needs every part; a part of another tab is followed while its batch is listed.
  useEffect(() => {
    for (const part of parts) if (part.status === null) followJob(part.jobID);
  }, [parts, followJob]);
  const count = countBatch(batch, parts, now);
  const running = parts.some((p) => p.phase === 'active');
  const target: ManagerTarget = { batchId: batch.id };
  const listId = `pm-batch-${batch.id}`;
  useRowActions(row, {
    rename: () => setRenaming(true),
    move: () => setMenu('move'),
    archive: () => setArchived(target, !batch.archived),
  });
  return (
    <li
      ref={row}
      data-row-id={batch.id}
      className={`pm-row batch${batch.archived ? ' archived' : ''}${dragging ? ' dragging' : ''}`}
      aria-keyshortcuts="R G A"
      onPointerDown={focusOnPress}
      {...(renaming ? {} : dragSource({ batchId: batch.id }, batch.id, onDrag))}
    >
      <div className="pm-line" ref={line}>
        <button
          type="button"
          className="pm-icon pm-chevron"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-label={expanded ? `Fold up ${batch.title}` : `Show the parts of ${batch.title}`}
          title={expanded ? 'Fold up' : 'Show the parts'}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? '▾' : '▸'}
        </button>
        {renaming ? (
          <InlineRename
            value={batch.title}
            label="Batch title"
            maxLength={MAX_TITLE_LENGTH}
            onSave={(name) => {
              renameBatch(batch.id, name);
              setRenaming(false);
            }}
            onCancel={() => setRenaming(false)}
          />
        ) : (
          <button
            type="button"
            className="pm-open"
            title={batch.title}
            onClick={(e) => {
              e.currentTarget.focus();
              setExpanded(!expanded);
            }}
          >
            <span className="pm-title">{batch.title}</span>
            <span className="pm-meta">
              <span className="pm-state">{batchSummary(count)}</span>
              {count.expires && (
                <span className="pm-until" title={count.expires}>
                  until {formatUntil(count.expires, now)}
                </span>
              )}
              {batch.archived && <span className="pm-tag">Archived</span>}
            </span>
          </button>
        )}
        <RowMenu
          name={batch.title}
          mode={menu}
          onMode={setMenu}
          anchor={line}
          groups={groups}
          groupId={batch.groupId}
          onRename={() => setRenaming(true)}
          onMove={(groupId) => moveToGroup(target, groupId)}
          archived={batch.archived}
          onArchive={(archived) => setArchived(target, archived)}
          cancel={
            running
              ? { label: 'Cancel all', disabled: parts.some((p) => p.cancelling), run: () => void cancelBatch(batch.id) }
              : undefined
          }
        />
      </div>
      {running && <progress className="pm-progress" max={100} value={count.progress} aria-label="Progress" />}
      {expanded && (
        <ul className="pm-parts" id={listId}>
          {parts.map((part) => (
            <JobItem key={part.jobID} job={part} now={now} part groups={groups} />
          ))}
          {batch.refused.map((refused) => (
            <li key={refused.label} className="pm-row part refused">
              <div className="pm-line">
                <span className="pm-open">
                  <span className="pm-title">{refused.label}</span>
                  <span className="pm-meta">
                    <span className="pm-state">Refused</span>
                  </span>
                </span>
                <Tip text={refused.message} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

type Entry =
  | { kind: 'job'; job: JobEntry; at: number; groupId: string | null; archived: boolean }
  | { kind: 'batch'; batch: BatchEntry; parts: JobEntry[]; at: number; groupId: string | null; archived: boolean };

// Batches with their parts, and the jobs that belong to none; the newest first.
function entriesOf(jobs: readonly JobEntry[], batches: readonly BatchEntry[]): Entry[] {
  const known = new Set(batches.map((b) => b.id));
  const entries: Entry[] = [
    ...batches.map((batch): Entry => ({
      kind: 'batch',
      batch,
      parts: jobs.filter((j) => j.batchId === batch.id),
      at: Date.parse(batch.createdAt),
      groupId: batch.groupId,
      archived: batch.archived,
    })),
    ...jobs
      .filter((j) => !j.batchId || !known.has(j.batchId))
      .map((job): Entry => ({ kind: 'job', job, at: Date.parse(job.createdAt), groupId: job.groupId, archived: job.archived })),
  ];
  return entries.sort((a, b) => b.at - a.at);
}

// The arrow that folds a group up, with the number of rows it holds under the current filter.
function FoldButton({ name, listId, collapsed, onToggle, count }: { name: string; listId: string; collapsed: boolean; onToggle: () => void; count: number }) {
  return (
    <button
      type="button"
      className="pm-icon pm-fold"
      aria-expanded={!collapsed}
      aria-controls={listId}
      aria-label={collapsed ? `Show ${name}, ${count}` : `Fold up ${name}`}
      title={collapsed ? 'Show the group' : 'Fold up the group'}
      onClick={onToggle}
    >
      {collapsed ? '▸' : '▾'}
    </button>
  );
}

function GroupHeading({
  group,
  empty,
  collapsed,
  count,
  onToggle,
}: {
  group: ShelfGroup;
  empty: boolean;
  collapsed: boolean;
  count: number;
  onToggle: () => void;
}) {
  const renameGroup = useProcessingStore((s) => s.renameGroup);
  const removeGroup = useProcessingStore((s) => s.removeGroup);
  const [renaming, setRenaming] = useState(false);
  return (
    <header className="pm-group-head">
      <FoldButton name={group.name} listId={`pm-group-${group.id}`} collapsed={collapsed} onToggle={onToggle} count={count} />
      {renaming ? (
        <InlineRename
          value={group.name}
          label="Group name"
          maxLength={MAX_NAME_LENGTH}
          onSave={(name) => {
            renameGroup(group.id, name);
            setRenaming(false);
          }}
          onCancel={() => setRenaming(false)}
        />
      ) : (
        <h3 className="pm-group-name">
          {group.name}
          {collapsed && <span className="pm-count"> ({count})</span>}
        </h3>
      )}
      <button type="button" className="pm-icon" title="Rename this group" aria-label={`Rename ${group.name}`} onClick={() => setRenaming(true)}>
        ✎
      </button>
      {/* `aria-disabled`, not `disabled`: the symbol stays reachable by keyboard, and so does the reason. */}
      <button
        type="button"
        className="pm-icon has-tip"
        aria-disabled={!empty}
        data-tip={empty ? 'Remove this group' : GROUP_NOT_EMPTY_TIP}
        aria-label={empty ? `Remove ${group.name}` : `Remove ${group.name}: ${GROUP_NOT_EMPTY_TIP}`}
        onClick={() => {
          if (empty) removeGroup(group.id);
        }}
      >
        ✕
      </button>
    </header>
  );
}

const UNGROUPED = 'ungrouped';

// What a dragged row carries: the job or the batch, never more than its own id, and never leaving the page.
const DRAG_TYPE = 'application/x-earthx-job-row';

// What a drop carries, read again: only a job id or a batch id of the right form is taken.
function parseDragged(raw: string): ManagerTarget | null {
  try {
    const value: unknown = JSON.parse(raw);
    if (typeof value !== 'object' || value === null) return null;
    const { jobID, batchId } = value as { jobID?: unknown; batchId?: unknown };
    if (isJobId(jobID)) return { jobID };
    if (typeof batchId === 'string' && /^[0-9a-f]{32}$/u.test(batchId)) return { batchId };
  } catch {
    /* not ours */
  }
  return null;
}

interface DragProps {
  // Reports the row that is dragged, and `null` when it is dropped or the drag ends.
  onDrag?: (id: string | null) => void;
  dragging?: boolean;
}

const FILTERS: [JobFilter, string][] = [
  ['active', 'Active'],
  ['expired', 'Expired'],
  ['all', 'All'],
];

// A batch is expired when every one of its parts is.
function isExpired(entry: Entry, now: number): boolean {
  return entry.kind === 'job' ? jobState(entry.job, now).key === 'expired' : entry.parts.length > 0 && entry.parts.every((p) => jobState(p, now).key === 'expired');
}

// "Active": not archived and not expired. "Expired": expired ones, archived or not. "All": everything.
function listed(filter: JobFilter, entry: Entry, now: number): boolean {
  if (filter === 'all') return true;
  return filter === 'expired' ? isExpired(entry, now) : !entry.archived && !isExpired(entry, now);
}

const emptyText = (filter: JobFilter, total: number): string =>
  total === 0 ? 'No jobs yet.' : filter === 'expired' ? 'No expired jobs.' : 'No active jobs.';

export default function ProcessingManager() {
  // A focus still due when the manager closes is not wanted any more.
  useEffect(() => () => clearTimeout(refocusTimer), []);
  useEffect(() => {
    document.addEventListener('keydown', rowKey);
    return () => document.removeEventListener('keydown', rowKey);
  }, []);
  const jobs = useProcessingStore((s) => s.jobs);
  const batches = useProcessingStore((s) => s.batches);
  const groups = useProcessingStore((s) => s.groups);
  const shelf = useProcessingStore((s) => s.shelf);
  const createGroup = useProcessingStore((s) => s.createGroup);
  const [filter, setFilter] = useState<JobFilter>(loadJobFilter);
  const [naming, setNaming] = useState(false);
  // The groups that are folded up; what is kept for a group that is gone is dropped at the next change.
  const [collapsed, setCollapsed] = useState<string[]>(loadCollapsedGroups);
  // The row that is being dragged, and the section it is over.
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const moveToGroup = useProcessingStore((s) => s.moveToGroup);
  const choose = (next: JobFilter) => {
    setFilter(next);
    saveJobFilter(next);
  };
  const toggle = (id: string) => {
    const next = collapsed.includes(id) ? collapsed.filter((c) => c !== id) : [...collapsed, id];
    const kept = next.filter((c) => c === UNGROUPED || groups.some((g) => g.id === c));
    setCollapsed(kept);
    saveCollapsedGroups(kept);
  };

  // A finished job turns "Expired" a minute before `expires`: the clock runs to the soonest of them.
  const deadline = Math.min(
    ...jobs.filter((j) => j.phase === 'successful' && !j.expired).map((j) => Date.parse(j.expires) - MIN_REMAINING_MS),
    Number.POSITIVE_INFINITY,
  );
  const now = useNowUntil(deadline);

  const all = useMemo(() => entriesOf(jobs, batches), [jobs, batches]);
  const shown = all.filter((e) => listed(filter, e, now));
  const groupOf = (e: Entry) => (e.groupId && groups.some((g) => g.id === e.groupId) ? e.groupId : null);
  const sections: { group: ShelfGroup | null; entries: Entry[]; empty: boolean }[] = [
    { group: null, entries: shown.filter((e) => groupOf(e) === null), empty: false },
    ...groups.map((group) => ({
      group,
      entries: shown.filter((e) => groupOf(e) === group.id),
      empty: !all.some((e) => groupOf(e) === group.id),
    })),
    // With groups there is always a place to drop a job out of one: "Ungrouped", also when it holds none.
  ].filter((section) => section.group !== null || section.entries.length > 0 || groups.length > 0);

  return (
    <div className="panel dock-panel processing-manager" role="region" aria-label="Processing jobs">
      <div className="results-head pm-head">
        <h2>Jobs</h2>
        <div className="results-head-right">
          <Tip text={KEPT_HERE_TIP} />
          {shelf === 'trimmed' && <Tip text={STORAGE_FULL_TIP} symbol="⚠" tone="warn" />}
        </div>
      </div>
      <div className="pm-tools">
        <div className="pm-filter" role="group" aria-label="Show">
          {FILTERS.map(([value, label]) => (
            <button key={value} type="button" className={`pp-seg${filter === value ? ' on' : ''}`} aria-pressed={filter === value} onClick={() => choose(value)}>
              {label}
            </button>
          ))}
        </div>
        <button type="button" className="ghost-btn" title="Make a group to put jobs in" onClick={() => setNaming(true)}>
          ＋ New group
        </button>
      </div>
      {shelf === 'memory' && (
        <p className="hint-text warn pm-note" role="status">
          {NOT_KEPT_TEXT}
        </p>
      )}
      {naming && (
        <div className="pm-new-group">
          <InlineRename
            value=""
            label="New group name"
            maxLength={MAX_NAME_LENGTH}
            onSave={(name) => {
              createGroup(name);
              setNaming(false);
            }}
            onCancel={() => setNaming(false)}
          />
        </div>
      )}
      <div className="pm-list">
        {shown.length === 0 && groups.length === 0 && <p className="hint-text pm-empty">{emptyText(filter, all.length)}</p>}
        {sections.map(({ group, entries, empty }) => {
          const id = group?.id ?? UNGROUPED;
          const folded = collapsed.includes(id);
          const listId = `pm-group-${id}`;
          const target = group?.id ?? null;
          return (
            <section
              key={id}
              className={`pm-group${over === id ? ' drop' : ''}`}
              aria-label={group?.name ?? 'Ungrouped'}
              onDragOver={(e) => {
                if (!e.dataTransfer.types.includes(DRAG_TYPE)) return;
                // Dropping is allowed here.
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                setOver(id);
              }}
              onDragLeave={(e) => {
                if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver((now) => (now === id ? null : now));
              }}
              onDrop={(e) => {
                const raw = e.dataTransfer.getData(DRAG_TYPE);
                setOver(null);
                setDragging(null);
                const moved = parseDragged(raw);
                if (!moved) return;
                e.preventDefault();
                moveToGroup(moved, target);
              }}
            >
              {group ? (
                <GroupHeading group={group} empty={empty} collapsed={folded} count={entries.length} onToggle={() => toggle(id)} />
              ) : (
                groups.length > 0 && (
                  <header className="pm-group-head">
                    <FoldButton name="Ungrouped" listId={listId} collapsed={folded} onToggle={() => toggle(id)} count={entries.length} />
                    <h3 className="pm-group-name">
                      Ungrouped
                      {folded && <span className="pm-count"> ({entries.length})</span>}
                    </h3>
                  </header>
                )
              )}
              {/* With no group there is no heading to fold under: the jobs are all there is. */}
              {(!folded || (!group && groups.length === 0)) && (
                <ul className="pm-rows" id={listId}>
                  {entries.map((entry) =>
                    entry.kind === 'job' ? (
                      <JobItem key={entry.job.jobID} job={entry.job} now={now} groups={groups} onDrag={setDragging} dragging={dragging === entry.job.jobID} />
                    ) : (
                      <BatchItem
                        key={entry.batch.id}
                        batch={entry.batch}
                        parts={entry.parts}
                        now={now}
                        groups={groups}
                        onDrag={setDragging}
                        dragging={dragging === entry.batch.id}
                      />
                    ),
                  )}
                </ul>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
