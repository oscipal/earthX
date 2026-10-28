// The details of one job, in the processing window instead of the order (UI-01 §6.8): its title (to be
// renamed), state and expiry, the steps of the order, the failure, and the actions. A finished job has one
// file to take, "Download (ZIP)"; it can also be drawn on the map.

import { useEffect, useState } from 'react';

import { viewOf } from '../permalink';
import { MAX_TITLE_LENGTH } from '../jobShelf';
import type { Order, OrderStep } from '../processing';
import { MIN_REMAINING_MS } from '../resultLayer';
import { useProcessingStore, type JobEntry } from '../processingStore';
import { useAppStore } from '../store';
import InlineRename from './InlineRename';
import { DownloadZip, RESAMPLED_TIP } from './JobRow';
import { canRestore, formatUntil, jobLabel, jobState, useNowUntil } from './jobView';
import Tip from './Tip';

export const NO_COPY_TIP = 'No copy of this order is kept: it was too large, or the browser ran out of room.';

const stepName = (op: string) => {
  const words = op.replaceAll('_', ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
};

// A value of a step as one short piece of text. An object (a geometry, say) is left out: the area of a job is
// not shown as coordinates.
function valueText(value: unknown): string | null {
  if (typeof value === 'string') return value.length > 120 ? `${value.slice(0, 120)}…` : value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value) && value.every((v) => typeof v === 'string' || typeof v === 'number')) return value.join(', ');
  return null;
}

function StepLine({ step }: { step: OrderStep }) {
  const values = Object.entries(step.params).flatMap(([name, value]) => {
    const text = valueText(value);
    return text === null ? [] : [`${name}: ${text}`];
  });
  return (
    <li className="pm-step">
      <strong>{stepName(step.op)}</strong>
      {values.length > 0 && <span className="pm-step-values">{values.join(' · ')}</span>}
    </li>
  );
}

function Steps({ order }: { order: Order }) {
  const datasets = useAppStore((s) => s.datasets);
  const input = order.inputs[0];
  const scenes = input ? input.groups.flat().length : 0;
  const dataset = input && (datasets.find((d) => d.id === input.dataset)?.title ?? input.dataset);
  return (
    <section className="pp-section" aria-label="Steps">
      <h3 className="pp-heading">Order</h3>
      <p className="pp-summary">
        {[dataset, `${scenes} scene${scenes === 1 ? '' : 's'}`, order.aoi ? 'AOI only' : 'Whole scenes'].filter(Boolean).join(' · ')}
      </p>
      <ol className="pm-steps">
        {order.steps.map((step, index) => (
          <StepLine key={index} step={step} />
        ))}
      </ol>
    </section>
  );
}

function Title({ job }: { job: JobEntry }) {
  const rename = useProcessingStore((s) => s.renameJob);
  const batch = useProcessingStore((s) => s.batches.find((b) => b.id === job.batchId));
  const [editing, setEditing] = useState(false);
  return (
    <div className="pm-detail-title">
      {editing ? (
        <InlineRename
          value={job.title ?? ''}
          label="Job title"
          maxLength={MAX_TITLE_LENGTH}
          onSave={(name) => {
            rename(job.jobID, name);
            setEditing(false);
          }}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          <h3 className="pm-title-text">{jobLabel(job)}</h3>
          <button type="button" className="link-btn" title="Rename this job" aria-label="Rename this job" onClick={() => setEditing(true)}>
            ✎
          </button>
        </>
      )}
      {batch && job.part && <span className="pp-help">{`${batch.title} · ${job.part}`}</span>}
    </div>
  );
}

function OpenInPanel({ job }: { job: JobEntry }) {
  const restoreOrder = useProcessingStore((s) => s.restoreOrder);
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const order = job.order;
  const open = async () => {
    if (!order) return;
    const app = useAppStore.getState();
    setBusy(true);
    setProblem(null);
    // The map stays where it is, basemap and projection included; the order brings its own area.
    const view = viewOf(app.viewportBbox ?? [-180, -90, 180, 90], app.mapZoom, job.range, { basemap: app.basemap, projection: app.projection });
    const result = await restoreOrder(order, view);
    setBusy(false);
    if (!result.ok) setProblem(result.reason);
  };
  return (
    <>
      <button
        type="button"
        className="ghost-btn has-tip"
        aria-disabled={!order || busy}
        data-tip={order ? 'Take the order of this job back into the panel' : NO_COPY_TIP}
        aria-label={order ? undefined : `Open in panel: ${NO_COPY_TIP}`}
        onClick={() => {
          if (order && !busy) void open();
        }}
      >
        Open in panel
      </button>
      {problem && (
        <p className="hint-text error" role="alert">
          {problem}
        </p>
      )}
    </>
  );
}

export default function JobDetails() {
  const jobID = useProcessingStore((s) => s.detailJobID);
  const job = useProcessingStore((s) => s.jobs.find((j) => j.jobID === jobID));
  const back = useProcessingStore((s) => s.closeJobDetails);
  const close = useProcessingStore((s) => s.closeProcessing);
  const cancelJob = useProcessingStore((s) => s.cancelJob);
  const showOnMap = useProcessingStore((s) => s.showResultOnMap);
  const followJob = useProcessingStore((s) => s.followJob);
  // Narrow screens only: the sheet from below folds down to its head, as the order does.
  const [folded, setFolded] = useState(false);
  const now = useNowUntil(job ? (job.deletedUntil ? Date.parse(job.deletedUntil) : Date.parse(job.expires) - MIN_REMAINING_MS) : Number.POSITIVE_INFINITY);
  const unknownStatus = job?.status === null;
  useEffect(() => {
    if (unknownStatus && jobID) followJob(jobID);
  }, [unknownStatus, jobID, followJob]);
  const state = job ? jobState(job, now) : null;
  const active = job?.phase === 'active';
  const restorable = job ? canRestore(job, now) : false;

  return (
    <div className={`panel processing-panel${folded ? ' folded' : ''}`} role="dialog" aria-label="Job">
      <div className="pp-head">
        <button
          type="button"
          className="pp-grip"
          aria-expanded={!folded}
          aria-label={folded ? 'Show the panel' : 'Fold the panel down'}
          title={folded ? 'Show the panel' : 'Fold the panel down'}
          onClick={() => setFolded(!folded)}
        >
          {folded ? '▴' : '▾'}
        </button>
        <div className="vc-head">
          <button type="button" className="link-btn" title="Back to the order" onClick={back}>
            ‹ Order
          </button>
          <button type="button" className="link-btn" title="Close the panel" onClick={close}>
            ✕
          </button>
        </div>
      </div>
      <div className="pp-body">
        {!job || !state ? (
          <p className="hint-text">This job is not in the list.</p>
        ) : (
          <>
            <Title job={job} />
            <dl className="pm-facts">
              <dt>State</dt>
              <dd>
                {state.key === 'running' ? `Running · ${state.text}` : state.text}
                {job.resampled === true && state.key === 'finished' && <Tip text={RESAMPLED_TIP} symbol="⚠" tone="warn" />}
              </dd>
              {state.key === 'deleted' ? (
                restorable &&
                job.deletedUntil && (
                  <>
                    <dt>Restore until</dt>
                    <dd title={job.deletedUntil}>{formatUntil(job.deletedUntil, now)}</dd>
                  </>
                )
              ) : (
                state.key !== 'cancelled' &&
                state.key !== 'unavailable' && (
                  <>
                    <dt>Expires</dt>
                    <dd title={job.expires}>{formatUntil(job.expires, now)}</dd>
                  </>
                )
              )}
            </dl>
            {active && <progress className="pp-progress" max={100} value={job.status?.progress ?? 0} aria-label="Progress" />}
            {job.phase === 'failed' && (
              <p className="hint-text error" role="alert">
                {job.failure ?? job.status?.message ?? 'The job failed'}
              </p>
            )}
            {job.error && (
              <p className="hint-text error" role="alert">
                {job.error}
              </p>
            )}
            {job.order && <Steps order={job.order} />}
            <div className="vc-actions">
              {state.key === 'finished' && job.archive && <DownloadZip job={job} now={now} label="Download (ZIP)" className="ghost-btn" />}
              {state.key === 'finished' && job.tiles && (
                <button
                  type="button"
                  className="ghost-btn"
                  title="Draw the result on the map, cut to the area of the job, as a layer"
                  onClick={() => void showOnMap(job.jobID)}
                >
                  Show on map
                </button>
              )}
              {active && (
                <button
                  type="button"
                  className="ghost-btn"
                  disabled={job.cancelling || !job.status}
                  title="Cancel this job"
                  onClick={() => void cancelJob(job.jobID)}
                >
                  {job.cancelling ? 'Cancelling…' : 'Cancel'}
                </button>
              )}
              {(state.key === 'expired' || state.key === 'unavailable') && <OpenInPanel job={job} />}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
