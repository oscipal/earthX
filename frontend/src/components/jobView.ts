// What the manager and the job details say of a job (UI-01 §6.10): its state, when it goes, and the
// count of a batch. Pure, so the rows and the details read one rule.

import { useEffect, useState } from 'react';

import { isResultExpired } from '../resultLayer';
import type { BatchEntry, JobEntry } from '../processingStore';

export const EXPIRED_TIP = 'Expired: results are kept for 7 days.';

export type JobStateKey = 'checking' | 'waiting' | 'running' | 'finished' | 'failed' | 'cancelled' | 'expired';

export interface JobState {
  key: JobStateKey;
  text: string;
  // 0–100 while the job waits or runs; `null` once it is over.
  progress: number | null;
}

// The current time, refreshed when `deadline` passes: a finished job turns "Expired" on the spot.
export function useNowUntil(deadline: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const wait = deadline - Date.now();
    if (!Number.isFinite(wait) || wait <= 0) return undefined;
    const timer = setTimeout(() => setNow(Date.now()), Math.min(wait + 50, 2 ** 31 - 1));
    return () => clearTimeout(timer);
  }, [deadline, now]);
  return now;
}

// A finished job is "Expired" from a minute before `expires` (`MIN_REMAINING` of the job API: its links
// answer `410` from then on); a job the server no longer knows (`404`) is expired or cancelled.
export function jobState(job: JobEntry, now: number): JobState {
  switch (job.phase) {
    case 'gone':
      return { key: 'expired', text: 'Expired', progress: null };
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

const MONTH_DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' });
const HOUR_MINUTE = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
const YEAR = new Intl.DateTimeFormat('en-GB', { year: 'numeric' });

// "31 Oct, 14:02"; the year only when it is not this one.
export function formatUntil(iso: string, now: number = Date.now()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const year = YEAR.format(date) === YEAR.format(now) ? '' : ` ${YEAR.format(date)}`;
  return `${MONTH_DAY.format(date)}${year}, ${HOUR_MINUTE.format(date)}`;
}

export interface BatchCount {
  done: number;
  running: number;
  refused: number;
  failed: number;
  expired: number;
  cancelled: number;
  total: number;
  // 0–100: a part that is over counts whole.
  progress: number;
  // The earliest `expires` of the parts that still stand; of all of them once none does.
  expires: string | null;
}

export function countBatch(batch: BatchEntry, parts: readonly JobEntry[], now: number): BatchCount {
  const states = parts.map((part) => jobState(part, now));
  const count = (key: JobStateKey) => states.filter((s) => s.key === key).length;
  const total = parts.length + batch.refused.length;
  const sum = states.reduce((all, s) => all + (s.progress ?? (s.key === 'checking' ? 0 : 100)), 0) + 100 * batch.refused.length;
  const standing = parts.filter((_, i) => states[i].key !== 'expired' && states[i].key !== 'cancelled');
  const ends = (standing.length > 0 ? standing : parts).map((part) => part.expires).sort((a, b) => Date.parse(a) - Date.parse(b));
  return {
    done: count('finished'),
    running: count('running') + count('waiting') + count('checking'),
    refused: batch.refused.length,
    failed: count('failed'),
    expired: count('expired'),
    cancelled: count('cancelled'),
    total,
    progress: total === 0 ? 0 : Math.round(sum / total),
    expires: ends[0] ?? null,
  };
}

// "12 done · 3 running · 1 refused · 1 failed"; what is zero is left out.
export function batchSummary(count: BatchCount): string {
  const parts: [number, string][] = [
    [count.done, 'done'],
    [count.running, 'running'],
    [count.refused, 'refused'],
    [count.failed, 'failed'],
    [count.expired, 'expired'],
    [count.cancelled, 'cancelled'],
  ];
  return parts.filter(([n]) => n > 0).map(([n, word]) => `${n} ${word}`).join(' · ');
}

export const jobLabel = (job: { title: string | null }): string => job.title ?? 'Untitled job';
