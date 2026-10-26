// Jobs as the manager holds them, for the tests of the manager and the details (UI-01 §6.10). Synthetic:
// ids and times are made up.

import type { StatusInfo } from '../processing';
import type { BatchEntry, JobEntry } from '../processingStore';

export const NOW = Date.parse('2026-10-20T12:00:00Z');
const DAY = 86_400_000;

// A valid `jobID` for the number `n`.
export const jobId = (n: number): string => `Job${String(n).padStart(19, '0')}`;

export function status(over: Partial<StatusInfo> = {}): StatusInfo {
  return {
    jobID: jobId(1),
    status: 'running',
    message: '',
    progress: 40,
    expires: new Date(NOW + 7 * DAY).toISOString(),
    ...over,
  };
}

export function jobEntry(n: number, over: Partial<JobEntry> = {}): JobEntry {
  const expires = new Date(NOW + 7 * DAY).toISOString();
  return {
    jobID: jobId(n),
    expires,
    title: `Band math · Sentinel-2 L2A · ${n} Oct`,
    titleDefault: `Band math · Sentinel-2 L2A · ${n} Oct`,
    createdAt: new Date(NOW - n * 60_000).toISOString(),
    archived: false,
    groupId: null,
    batchId: null,
    part: null,
    range: null,
    order: null,
    status: status({ jobID: jobId(n), expires }),
    phase: 'active',
    archive: null,
    bytes: null,
    resampled: null,
    failure: null,
    error: null,
    cancelling: false,
    expired: false,
    tiles: null,
    statistics: null,
    ...over,
  };
}

export const finished = (n: number, over: Partial<JobEntry> = {}): JobEntry =>
  jobEntry(n, { phase: 'successful', archive: 'result.zip', status: status({ jobID: jobId(n), status: 'successful', progress: 100 }), ...over });

export function batchEntry(id: string, over: Partial<BatchEntry> = {}): BatchEntry {
  return {
    id,
    title: 'Band math · Sentinel-2 L2A · 12 Oct',
    titleDefault: 'Band math · Sentinel-2 L2A · 12 Oct',
    createdAt: new Date(NOW - 60_000).toISOString(),
    archived: false,
    groupId: null,
    refused: [],
    ...over,
  };
}
