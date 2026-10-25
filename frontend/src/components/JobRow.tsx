// A job as the dialogs of the download (M4-11b-2, M4-12b) show it: state, "Cancel", when it goes and, once
// finished, "Download (ZIP)" and nothing else (UI-01 §1 point 12). The manager has rows of its own
// (`ProcessingManager.tsx`); both read the state from `jobView.ts`.

import { useEffect } from 'react';

import { resultUrl } from '../processing';
import { MIN_REMAINING_MS } from '../resultLayer';
import { useProcessingStore, ZIP_LABEL, type JobEntry } from '../processingStore';
import { EXPIRED_TIP, formatUntil, jobState, useNowUntil } from './jobView';
import Tip from './Tip';

export const RESAMPLED_TIP = 'Resampled to a common grid';

// The archive of a finished job as a link; once it expired, the link is gone and the reason is the tooltip.
export function DownloadZip({ job, now, label, className = 'pm-icon' }: { job: JobEntry; now: number; label?: string; className?: string }) {
  const state = jobState(job, now);
  if (state.key === 'expired' && job.phase === 'successful') {
    return (
      <button type="button" className={className} disabled title={EXPIRED_TIP} aria-label={`${ZIP_LABEL}: ${EXPIRED_TIP}`}>
        {label ?? '⇩'}
      </button>
    );
  }
  if (state.key !== 'finished' || !job.archive) return <span className={className} aria-hidden="true" />;
  return (
    <a className={className} href={resultUrl(job.jobID, job.archive)} download rel="noopener noreferrer" title={ZIP_LABEL} aria-label={ZIP_LABEL}>
      {label ?? '⇩'}
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
            title="Cancel this job"
            onClick={() => void cancelJob(job.jobID)}
          >
            {job.cancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        )}
      </div>
      {active && <progress className="pp-progress" max={100} value={job.status?.progress ?? 0} aria-label="Progress" />}
      {job.phase === 'failed' && <span className="hint-text error">{job.failure ?? job.status?.message ?? 'The job failed'}</span>}
      {state.key !== 'expired' && state.key !== 'cancelled' && (
        <span className="pp-help" title={job.expires}>
          until {formatUntil(job.expires, now)}
        </span>
      )}
      {state.key === 'finished' && job.archive && (
        <span className="pp-links">
          <a href={resultUrl(job.jobID, job.archive)} download rel="noopener noreferrer">
            {ZIP_LABEL}
          </a>
          {job.resampled === true && <Tip text={RESAMPLED_TIP} symbol="⚠" tone="warn" />}
        </span>
      )}
      {job.error && <span className="hint-text error">{job.error}</span>}
    </li>
  );
}
