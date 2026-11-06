// A job as the dialogs of the download (M4-11b-2, M4-12b) show it: state, "Cancel", when it goes and, once
// finished, "Download (ZIP)" and nothing else (UI-01 §1 point 12). The manager has rows of its own
// (`ProcessingManager.tsx`); both read the state from `jobView.ts`.

import { useEffect } from 'react';

import { resultUrl } from '../processing';
import { MIN_REMAINING_MS } from '../resultLayer';
import { useProcessingStore, ZIP_LABEL, type JobEntry } from '../processingStore';
import { DownloadIcon } from './icons';
import { formatMoment } from '../numberFormat';
import { EXPIRED_TIP, jobState, useNowUntil } from './jobView';


// The archive of a finished job as a link; once it expired, the link is gone and the reason is the tooltip.
export function DownloadZip({ job, now, label, className = 'icon-btn pm-icon' }: { job: JobEntry; now: number; label?: string; className?: string }) {
  const state = jobState(job, now);
  if (state.key === 'expired' && job.phase === 'successful') {
    return (
      <button type="button" className={`${className} has-tip`} aria-disabled="true" data-tip={EXPIRED_TIP} aria-label={`${ZIP_LABEL}: ${EXPIRED_TIP}`}>
        {label ? <><DownloadIcon lead />{label}</> : <DownloadIcon />}
      </button>
    );
  }
  if (state.key !== 'finished' || !job.archive) return <span className={className} aria-hidden="true" />;
  return (
    <a className={className} href={resultUrl(job.jobID, job.archive)} download rel="noopener noreferrer" data-tip-level="advanced" data-tip={ZIP_LABEL} aria-label={ZIP_LABEL}>
      {label ? <><DownloadIcon lead />{label}</> : <DownloadIcon />}
    </a>
  );
}

export function JobRow({ job }: { job: JobEntry }) {
  const cancelJob = useProcessingStore((s) => s.cancelJob);
  const followJob = useProcessingStore((s) => s.followJob);
  // A job from another tab is followed from the moment its row is shown.
  useEffect(() => {
    if (job.status === null) followJob(job.jobID);
  }, [job.jobID, job.status, followJob]);
  const now = useNowUntil(Date.parse(job.expires) - MIN_REMAINING_MS);
  const state = jobState(job, now);
  const active = job.phase === 'active';
  return (
    <li className="pp-job" aria-label={job.title ?? 'Job'}>
      {job.title && <span className="pp-job-title">{job.title}</span>}
      <div className="pp-job-head">
        <span className="pp-job-state">{state.progress !== null && state.key === 'running' ? `Running · ${state.text}` : state.text}</span>
        {active && (
          <button
            type="button"
            className="link-btn"
            disabled={job.cancelling || !job.status}
            data-tip-level="advanced" data-tip={job.cancelling ? 'The job is being cancelled' : !job.status ? 'Waiting for the state of the job' : 'Cancel this job'}
            onClick={() => void cancelJob(job.jobID)}
          >
            {job.cancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        )}
      </div>
      {active && <progress className="pp-progress" max={100} value={job.status?.progress ?? 0} aria-label="Progress" />}
      {job.phase === 'failed' && <span className="error">{job.failure ?? job.status?.message ?? 'The job failed'}</span>}
      {state.key !== 'cancelled' && state.key !== 'unavailable' && state.key !== 'deleted' && (
        <span className="hint" data-tip-level="advanced" data-tip={job.expires}>
          until {formatMoment(job.expires, now)}
        </span>
      )}
      {state.key === 'finished' && job.archive && (
        <span className="pp-links">
          <a href={resultUrl(job.jobID, job.archive)} download rel="noopener noreferrer">
            {ZIP_LABEL}
          </a>
        </span>
      )}
      {job.error && <span className="error">{job.error}</span>}
    </li>
  );
}
