// What a job is, as the list says it (UI-01 §6.10, NM4-27): its state, and what "Delete" and "Restore" may do with it.
// Pure, so the manager, its details and the store read one rule.

import type { JobEntry } from './processingStore';
import { isResultExpired } from './resultLayer';

export const UNAVAILABLE_TIP = 'The server does not know this job any more.';

export type JobStateKey =
  | 'checking'
  | 'waiting'
  | 'running'
  | 'finished'
  | 'failed'
  | 'cancelled'
  | 'expired'
  | 'unavailable'
  | 'deleted';

export interface JobState {
  key: JobStateKey;
  text: string;
  // 0–100 while the job waits or runs; `null` once it is over.
  progress: number | null;
}

// A finished job is "Expired" from a minute before `expires` (`MIN_REMAINING` of the job API: its links
// answer `410` from then on). A job the server no longer knows (`404`) is "Expired" if its time is up, else
// "No longer available" (cancelled, a reset database). A deleted job is "Deleted" whatever it was before, with
// "Restore" until `deletedUntil` (NM4-27); one the server forgot meanwhile says so.
export function jobState(job: JobEntry, now: number): JobState {
  if (job.deletedUntil !== null) {
    return { key: 'deleted', text: job.lost ? 'No longer available' : 'Deleted', progress: null };
  }
  switch (job.phase) {
    case 'gone':
      return job.expired || isResultExpired(job.expires, now)
        ? { key: 'expired', text: 'Expired', progress: null }
        : { key: 'unavailable', text: 'No longer available', progress: null };
    case 'dismissed':
      return { key: 'cancelled', text: 'Cancelled', progress: null };
    case 'failed':
      return { key: 'failed', text: 'Failed', progress: null };
    case 'successful':
      return job.expired || isResultExpired(job.expires, now)
        ? { key: 'expired', text: 'Expired', progress: null }
        : { key: 'finished', text: 'Finished', progress: null };
    default:
      if (!job.status) return { key: 'checking', text: 'Checking…', progress: null };
      return job.status.status === 'running'
        ? { key: 'running', text: `${job.status.progress}%`, progress: job.status.progress }
        : { key: 'waiting', text: 'Waiting', progress: 0 };
  }
}

// Whether "Restore" still works: the job is deleted and its day is not over.
export function canRestore(job: JobEntry, now: number): boolean {
  return job.deletedUntil !== null && Date.parse(job.deletedUntil) > now;
}

// What can be deleted: a job that is over, however it ended. One that waits or runs is cancelled (it has "Cancel").
const DELETABLE: readonly JobStateKey[] = ['finished', 'failed', 'cancelled', 'expired', 'unavailable'];

export function canDelete(job: JobEntry, now: number): boolean {
  return !job.deleting && DELETABLE.includes(jobState(job, now).key);
}

// The parts of a batch "Delete" acts on; none of them waits or runs, or the batch has "Cancel all" and no "Delete".
export function deletableParts(parts: readonly JobEntry[], now: number): JobEntry[] {
  if (parts.some((p) => ['checking', 'waiting', 'running'].includes(jobState(p, now).key))) return [];
  return parts.filter((p) => canDelete(p, now));
}

