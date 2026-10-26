import { useEffect, useState } from 'react';

import { HttpError } from '../api';
import { resultsGroupByOfOption } from '../datasets';
import type { ExportOffer } from '../download';
import { estimateOrder, type EstimateDocument } from '../processing';
import { jobTitle, titleDay } from '../processingBatch';
import { aoiProvenanceOf, buildExportOrder, formatBytes, formatDuration } from '../processingOrder';
import { orderStands, refusalMessage, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import { JobRow } from './JobRow';

// "Export as job" in the download dialog (M4-11b-2, plan §3.2): the crop was
// refused as too large for a direct download, and its `413` said the same
// selection fits an export job. The estimate is asked once when the offer
// appears (K6); the job is followed by the row of the processing panel and
// stays in the panel's list when the dialog closes (K7). The dialog mounts one
// per offer (`key` is `ExportOffer.id`), so a new refusal starts afresh.

export const TOO_LARGE_FOR_A_JOB = 'An export job may write at most 5 GB. Draw a smaller area or choose fewer assets.';

type Estimate =
  | { state: 'estimating' }
  | { state: 'ready'; doc: EstimateDocument }
  | { state: 'too-large' }
  | { state: 'error'; message: string };

type Started = { state: 'starting' } | { state: 'placed'; jobID: string } | { state: 'refused'; message: string };

// "Export · <dataset> · <day>"; the day is the one the scenes share, where the app holds them.
function titleOfExport({ request }: ExportOffer): string {
  const app = useAppStore.getState();
  const dataset = app.datasets.find((d) => d.id === request.datasetId);
  const ids = new Set(request.groups.flat());
  const scenes = app.items.filter((item) => ids.has(item.id));
  const known = scenes.length === ids.size ? scenes : [];
  return jobTitle({
    operators: ['Export'],
    dataset: dataset?.title ?? '',
    day: titleDay(known, dataset ? resultsGroupByOfOption(dataset) : null),
  });
}

export default function ExportJobOffer({ offer }: { offer: ExportOffer }) {
  const placeOrder = useProcessingStore((s) => s.placeOrder);
  const jobs = useProcessingStore((s) => s.jobs);
  const tooLarge = offer.exportJob === 'too-large';
  const [estimate, setEstimate] = useState<Estimate>(tooLarge ? { state: 'too-large' } : { state: 'estimating' });
  const [attempt, setAttempt] = useState(0);
  const [started, setStarted] = useState<Started | null>(null);

  useEffect(() => {
    if (tooLarge) return undefined;
    const controller = new AbortController();
    estimateOrder(buildExportOrder(offer.request), controller.signal)
      .then((doc) => {
        if (!controller.signal.aborted) setEstimate({ state: 'ready', doc });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof HttpError && error.status === 413) setEstimate({ state: 'too-large' });
        else setEstimate({ state: 'error', message: refusalMessage(error) });
      });
    return () => controller.abort();
  }, [offer, tooLarge, attempt]);

  const job = started?.state === 'placed' ? jobs.find((j) => j.jobID === started.jobID) : undefined;
  const blocked = estimate.state !== 'ready' || started?.state === 'starting' || orderStands(job);

  const start = async () => {
    if (blocked) return;
    setStarted({ state: 'starting' });
    const answer = await placeOrder(buildExportOrder(offer.request), {
      aoiProvenance: aoiProvenanceOf(offer.request.aoi),
      title: titleOfExport(offer),
    });
    setStarted('jobID' in answer ? { state: 'placed', jobID: answer.jobID } : { state: 'refused', message: answer.message });
  };

  const retry = () => {
    setEstimate({ state: 'estimating' });
    setAttempt((n) => n + 1);
  };

  return (
    <section className="dialog-export-job" aria-label="Export as job">
      <h3>Too large for a direct download</h3>
      <p className="hint-text">{offer.message}</p>
      {estimate.state === 'estimating' && <p className="hint-text">Estimating the export…</p>}
      {estimate.state === 'ready' && (
        <p>
          About {formatBytes(estimate.doc.estimate.size)} · {formatDuration(estimate.doc.estimate.duration)}
        </p>
      )}
      {estimate.state === 'too-large' && <p className="hint-text warn">{TOO_LARGE_FOR_A_JOB}</p>}
      {estimate.state === 'error' && (
        <p className="hint-text error" role="alert">
          {estimate.message}{' '}
          <button type="button" className="link-btn" onClick={retry}>
            Try again
          </button>
        </p>
      )}
      <button
        type="button"
        className="lm-btn primary"
        disabled={blocked}
        title={estimate.state === 'too-large' ? TOO_LARGE_FOR_A_JOB : 'Compute the crop on the platform, as a job'}
        onClick={() => void start()}
      >
        {started?.state === 'starting' ? 'Starting…' : 'Export as job'}
      </button>
      {started?.state === 'refused' && (
        <p className="hint-text error" role="alert">
          {started.message}
        </p>
      )}
      {job && (
        <ul className="pp-jobs">
          <JobRow job={job} />
        </ul>
      )}
    </section>
  );
}
