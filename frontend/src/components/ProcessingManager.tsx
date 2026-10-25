// The processing manager (UI-01 §6.10): the jobs of this browser, each with its title, progress and expiry,
// as rows; the jobs of one batch as one row that opens into its parts. A job is never deleted, only
// archived and put in a group. A click on a job opens its details in the processing window.

import { useEffect, useMemo, useRef, useState } from 'react';

import { MAX_NAME_LENGTH, MAX_TITLE_LENGTH, type ShelfGroup } from '../jobShelf';
import { loadJobFilter, saveJobFilter, type JobFilter } from '../preferences';
import { MIN_REMAINING_MS } from '../resultLayer';
import { useProcessingStore, type BatchEntry, type JobEntry, type ManagerTarget } from '../processingStore';
import InlineRename from './InlineRename';
import { DownloadZip } from './JobRow';
import { batchSummary, countBatch, formatUntil, jobLabel, jobState, useNowUntil, type JobState } from './jobView';
import Tip from './Tip';

export const KEPT_HERE_TIP = "Jobs are kept in this browser only: a private window or clearing the browser's data loses them.";
export const STORAGE_FULL_TIP = 'Browser storage is full: copies of the oldest orders were dropped.';
export const NOT_KEPT_TEXT = 'This browser does not keep your jobs. Download results before you close the tab.';
export const GROUP_NOT_EMPTY_TIP = 'Only an empty group can be removed.';

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
}

// "⋯" at the end of a row. The list opens under the row, not over the map: nothing to place.
function RowMenu({ onRename, groups, groupId, onMove, archived, onArchive, cancel, name }: MenuProps) {
  const [open, setOpen] = useState(false);
  const [moving, setMoving] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);
  // The focus goes into the list when it opens and when it turns into the list of groups: the item that
  // was focused is gone by then.
  useEffect(() => {
    if (open) list.current?.querySelector<HTMLElement>('button:not(:disabled)')?.focus();
  }, [open, moving]);
  useEffect(() => {
    if (!open) return undefined;
    const away = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('pointerdown', away);
    return () => document.removeEventListener('pointerdown', away);
  }, [open]);
  const hasActions = onRename || onMove || onArchive || cancel;
  if (!hasActions) return <span className="pm-icon" aria-hidden="true" />;
  const done = (run: () => void) => () => {
    setOpen(false);
    setMoving(false);
    run();
  };
  return (
    <div
      className="pm-menu"
      ref={root}
      onKeyDown={(e) => {
        if (!open) return;
        if (e.key === 'Escape') {
          // The menu closes; the panel around it stays.
          e.stopPropagation();
          setOpen(false);
          setMoving(false);
          button.current?.focus();
          return;
        }
        const items = [...(list.current?.querySelectorAll<HTMLElement>('button:not(:disabled)') ?? [])];
        const at = items.indexOf(document.activeElement as HTMLElement);
        if (items.length === 0 || at < 0) return;
        const go = (index: number) => {
          e.preventDefault();
          items[(index + items.length) % items.length].focus();
        };
        if (e.key === 'ArrowDown') go(at + 1);
        else if (e.key === 'ArrowUp') go(at - 1);
        else if (e.key === 'Home') go(0);
        else if (e.key === 'End') go(items.length - 1);
      }}
    >
      <button
        type="button"
        ref={button}
        className="pm-icon"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Actions for ${name}`}
        title="Actions"
        onClick={() => {
          setOpen(!open);
          setMoving(false);
        }}
      >
        ⋯
      </button>
      {open && (
        <div className="pm-menu-list" role="menu" aria-label={`Actions for ${name}`} ref={list}>
          {!moving && onRename && (
            <button type="button" role="menuitem" onClick={done(onRename)}>
              Rename
            </button>
          )}
          {!moving && onMove && (
            <button type="button" role="menuitem" onClick={() => setMoving(true)}>
              Move to group…
            </button>
          )}
          {moving && onMove && (
            <>
              <button type="button" role="menuitemradio" aria-checked={groupId === null} onClick={done(() => onMove(null))}>
                Ungrouped
              </button>
              {groups.map((g) => (
                <button key={g.id} type="button" role="menuitemradio" aria-checked={groupId === g.id} onClick={done(() => onMove(g.id))}>
                  {g.name}
                </button>
              ))}
            </>
          )}
          {!moving && onArchive && (
            <button type="button" role="menuitem" onClick={done(() => onArchive(!archived))}>
              {archived ? 'Unarchive' : 'Archive'}
            </button>
          )}
          {!moving && cancel && (
            <button type="button" role="menuitem" disabled={cancel.disabled} onClick={done(cancel.run)}>
              {cancel.label}
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function Meter({ state, progress }: { state: JobState; progress?: number }) {
  const value = progress ?? state.progress;
  return value === null ? null : <progress className="pm-progress" max={100} value={value} aria-label="Progress" />;
}

function JobItem({ job, now, part, groups }: { job: JobEntry; now: number; part?: boolean; groups: ShelfGroup[] }) {
  const open = useProcessingStore((s) => s.openJobDetails);
  const cancelJob = useProcessingStore((s) => s.cancelJob);
  const followJob = useProcessingStore((s) => s.followJob);
  const rename = useProcessingStore((s) => s.renameJob);
  const setArchived = useProcessingStore((s) => s.setArchived);
  const moveToGroup = useProcessingStore((s) => s.moveToGroup);
  const [renaming, setRenaming] = useState(false);
  // The job of another tab, or an archived one, is followed from the moment its row is shown.
  useEffect(() => {
    if (job.status === null) followJob(job.jobID);
  }, [job.jobID, job.status, followJob]);
  const state = jobState(job, now);
  const title = part ? (job.part ?? jobLabel(job)) : jobLabel(job);
  const target: ManagerTarget = { jobID: job.jobID };
  return (
    <li className={`pm-row${part ? ' part' : ''}${job.archived ? ' archived' : ''}`}>
      <div className="pm-line">
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
          <button type="button" className="pm-open" title={title} onClick={() => open(job.jobID)}>
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

function BatchItem({ batch, parts, now, groups }: { batch: BatchEntry; parts: JobEntry[]; now: number; groups: ShelfGroup[] }) {
  const [expanded, setExpanded] = useState(false);
  const [renaming, setRenaming] = useState(false);
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
  return (
    <li className={`pm-row batch${batch.archived ? ' archived' : ''}`}>
      <div className="pm-line">
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
          <button type="button" className="pm-open" title={batch.title} onClick={() => setExpanded(!expanded)}>
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

function GroupHeading({ group, empty }: { group: ShelfGroup; empty: boolean }) {
  const renameGroup = useProcessingStore((s) => s.renameGroup);
  const removeGroup = useProcessingStore((s) => s.removeGroup);
  const [renaming, setRenaming] = useState(false);
  return (
    <header className="pm-group-head">
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
        <h3 className="pm-group-name">{group.name}</h3>
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

export default function ProcessingManager() {
  const jobs = useProcessingStore((s) => s.jobs);
  const batches = useProcessingStore((s) => s.batches);
  const groups = useProcessingStore((s) => s.groups);
  const shelf = useProcessingStore((s) => s.shelf);
  const createGroup = useProcessingStore((s) => s.createGroup);
  const [filter, setFilter] = useState<JobFilter>(loadJobFilter);
  const [naming, setNaming] = useState(false);
  const choose = (next: JobFilter) => {
    setFilter(next);
    saveJobFilter(next);
  };

  // A finished job turns "Expired" a minute before `expires`: the clock runs to the soonest of them.
  const deadline = Math.min(
    ...jobs.filter((j) => j.phase === 'successful' && !j.expired).map((j) => Date.parse(j.expires) - MIN_REMAINING_MS),
    Number.POSITIVE_INFINITY,
  );
  const now = useNowUntil(deadline);

  const all = useMemo(() => entriesOf(jobs, batches), [jobs, batches]);
  const shown = filter === 'all' ? all : all.filter((e) => !e.archived);
  const groupOf = (e: Entry) => (e.groupId && groups.some((g) => g.id === e.groupId) ? e.groupId : null);
  const sections: { group: ShelfGroup | null; entries: Entry[]; empty: boolean }[] = [
    { group: null, entries: shown.filter((e) => groupOf(e) === null), empty: false },
    ...groups.map((group) => ({
      group,
      entries: shown.filter((e) => groupOf(e) === group.id),
      empty: !all.some((e) => groupOf(e) === group.id),
    })),
  ].filter((section) => section.group !== null || section.entries.length > 0);

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
          {(['active', 'all'] as const).map((value) => (
            <button key={value} type="button" className={`pp-seg${filter === value ? ' on' : ''}`} aria-pressed={filter === value} onClick={() => choose(value)}>
              {value === 'active' ? 'Active' : 'All'}
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
        {shown.length === 0 && groups.length === 0 && <p className="hint-text pm-empty">{all.length === 0 ? 'No jobs yet.' : 'No active jobs.'}</p>}
        {sections.map(({ group, entries, empty }) => (
          <section key={group?.id ?? 'ungrouped'} className="pm-group" aria-label={group?.name ?? 'Ungrouped'}>
            {group ? <GroupHeading group={group} empty={empty} /> : groups.length > 0 && <h3 className="pm-group-name">Ungrouped</h3>}
            <ul className="pm-rows">
              {entries.map((entry) =>
                entry.kind === 'job' ? (
                  <JobItem key={entry.job.jobID} job={entry.job} now={now} groups={groups} />
                ) : (
                  <BatchItem key={entry.batch.id} batch={entry.batch} parts={entry.parts} now={now} groups={groups} />
                ),
              )}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
}
