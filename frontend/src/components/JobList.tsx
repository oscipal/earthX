// The jobs of this tab (M4-13 §3.5 point 7, K6): state, progress, "Cancel",
// when it expires; once finished, links to the files, and whether the result
// was resampled to a common grid (Prinzip 2.9). M4-11b shows its export job
// with the same row.

import { useEffect, useState } from 'react';

import { resultUrl } from '../processing';
import { useProcessingStore, type JobEntry } from '../processingStore';

// `MIN_REMAINING` of the job API (`objectstore/results.py`): from a minute
// before `expires`, a result link answers `410`, which a plain link could only
// show as a JSON page — the row says "Expired" instead.
export const MIN_REMAINING_MS = 60_000;

// The current time, refreshed when `deadline` passes.
function useNowUntil(deadline: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const wait = deadline - Date.now();
    if (!Number.isFinite(wait) || wait <= 0) return undefined;
    const timer = setTimeout(() => setNow(Date.now()), Math.min(wait + 50, 2 ** 31 - 1));
    return () => clearTimeout(timer);
  }, [deadline, now]);
  return now;
}

function stateText(job: JobEntry): string {
  switch (job.phase) {
    case 'gone':
      return 'Gone (expired or dismissed)';
    case 'dismissed':
      return 'Cancelled';
    case 'failed':
      return `Failed: ${job.failure ?? job.status?.message ?? 'the job failed'}`;
    case 'successful':
      return 'Finished';
    default:
      if (!job.status) return 'Checking…';
      return job.status.status === 'running' ? `Running · ${job.status.progress}%` : 'Waiting for a worker';
  }
}

function formatTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function JobRow({ job }: { job: JobEntry }) {
  const cancelJob = useProcessingStore((s) => s.cancelJob);
  const removeJob = useProcessingStore((s) => s.removeJob);
  const linksUntil = Date.parse(job.expires) - MIN_REMAINING_MS;
  const now = useNowUntil(linksUntil);
  const expired = !(now < linksUntil);
  const active = job.phase === 'active';
  return (
    <li className="pp-job" aria-label={`Job ${job.jobID.slice(0, 8)}`}>
      <div className="pp-job-head">
        <span className="pp-job-state">{stateText(job)}</span>
        {active ? (
          <button
            type="button"
            className="link-btn"
            disabled={job.cancelling}
            title="Cancel this job"
            onClick={() => void cancelJob(job.jobID)}
          >
            {job.cancelling ? 'Cancelling…' : 'Cancel'}
          </button>
        ) : (
          <button type="button" className="link-btn" title="Remove this row" onClick={() => removeJob(job.jobID)}>
            ✕
          </button>
        )}
      </div>
      {active && (
        <progress className="pp-progress" max={100} value={job.status?.progress ?? 0} aria-label="Progress" />
      )}
      {job.phase !== 'gone' && job.phase !== 'dismissed' && (
        <span className="pp-help">Kept until {formatTime(job.expires)}</span>
      )}
      {job.phase === 'successful' && expired && <span className="hint-text warn">Expired</span>}
      {job.phase === 'successful' && !expired && job.files && (
        <span className="pp-links">
          {job.files.map((f) => (
            <a key={f.file} href={resultUrl(job.jobID, f.file)} download rel="noopener noreferrer">
              {f.label}
            </a>
          ))}
        </span>
      )}
      {job.phase === 'successful' && job.resampled === true && (
        <span className="hint-text warn">Resampled to a common grid</span>
      )}
      {job.error && <span className="hint-text error">{job.error}</span>}
    </li>
  );
}

export default function JobList() {
  const jobs = useProcessingStore((s) => s.jobs);
  if (jobs.length === 0) return null;
  return (
    <section className="pp-section" aria-label="Jobs">
      <h3 className="pp-heading">Jobs</h3>
      <ul className="pp-jobs">
        {jobs.map((job) => (
          <JobRow key={job.jobID} job={job} />
        ))}
      </ul>
    </section>
  );
}
