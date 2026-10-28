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


export const RETRY_TIP = 'Run again';
export const RETRY_PARTS_TIP = 'Retry failed parts';

// The kinds of failure (`processing.failure_kind`, the end of the `type` of the result) that run again the way they ran
// before would end the same: the recipe is wrong or does not fit, the source refuses it, or the job is too big for
// the worker. There "Open in panel" is the way, to change the order. Any other kind, and one the platform adds later,
// may be gone on a second try (the source was down, the worker lost, memory short for a moment).
const FAILS_AGAIN: ReadonlySet<string> = new Set([
  'recipe_invalid',
  'unsupported_recipe',
  'scaling_mismatch',
  'grid_mismatch',
  'aoi_outside_inputs',
  'rejected',
  'source_4xx',
  'runtime_exceeded',
  'disk_space',
]);

export const failsAgain = (kind: string | null): boolean => kind !== null && FAILS_AGAIN.has(kind);

// The states "Run again" starts from: the job failed, was cancelled, or its result is gone with its time.
const RETRYABLE: readonly JobStateKey[] = ['failed', 'cancelled', 'expired'];

// Whether "Run again" is offered: the order is kept, the job is in one of those states for a reason that may not
// repeat, it is not already replaced, and the platform still carries the dataset (`retiredDataset`, or a `410`).
export function canRetry(job: JobEntry, now: number, retiredDataset = false): boolean {
  if (!job.order || job.superseded || job.retryRefused || retiredDataset) return false;
  const state = jobState(job, now).key;
  if (!RETRYABLE.includes(state)) return false;
  return state !== 'failed' || !failsAgain(job.failureKind);
}

// The parts of a batch "Run the failed parts again" starts: those that failed or were cancelled, not those that expired.
export function retryableParts(parts: readonly JobEntry[], now: number, retired: (job: JobEntry) => boolean = () => false): JobEntry[] {
  return parts.filter((part) => ['failed', 'cancelled'].includes(jobState(part, now).key) && canRetry(part, now, retired(part)));
}
