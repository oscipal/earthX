// Following a job (M4-13 §3.6, K5): server-sent events from
// `/processing/jobs/{jobID}/events`, with a fallback to asking
// `GET /processing/jobs/{jobID}` every 2 s.
//
// - A `status` event whose data is not a status document of *this* job is
//   dropped, never shown.
// - On a final state the stream is closed; otherwise `EventSource` would
//   connect again on its own.
// - A refusal before the stream (`404`, `503` with too many followers) leaves
//   `EventSource` `CLOSED`: polling starts at once. A stream that breaks off
//   reconnects by itself (`CONNECTING`); after three such errors with no valid
//   event in between the tracker polls instead — also when each reconnect
//   opens and then breaks without an event (a buffering proxy). Without
//   `EventSource` it polls from the start.
// - Polling honours `Retry-After`; a `404` means the job is gone (expired or
//   dismissed) and ends the tracking.
//
// Jobs survive a reload in `sessionStorage` (F5 (1)): only `jobID` and
// `expires`, never the order or the AOI (Q8).

import { HttpError } from './api';
import { eventsUrl, fetchJob, isJobId, parseStatusInfo, TERMINAL_STATES, type StatusInfo } from './processing';

export const POLL_MS = 2000;
export const MAX_STREAM_ERRORS = 3;
// A `Retry-After` the server sends is honoured up to this; a larger value (or
// an HTTP date) falls back to the plain interval rather than stall the row.
const MAX_RETRY_AFTER_MS = 60_000;

export interface TrackerHandlers {
  onStatus: (status: StatusInfo) => void;
  onGone: () => void;
}

type EventSourceLike = Pick<EventSource, 'addEventListener' | 'close' | 'readyState'> & {
  onerror: ((this: EventSource, ev: Event) => unknown) | null;
};

export interface TrackerOptions {
  // Injected by tests; the browser's own by default.
  EventSource?: (new (url: string) => EventSourceLike) | null;
  fetchJob?: (jobId: string) => Promise<StatusInfo>;
  pollMs?: number;
}

function retryDelay(error: unknown, fallback: number): number {
  if (error instanceof HttpError && error.retryAfter && /^\d+$/u.test(error.retryAfter.trim())) {
    return Math.min(Number(error.retryAfter) * 1000, MAX_RETRY_AFTER_MS);
  }
  return fallback;
}

// Starts following `jobId`; the returned function stops it (no further
// callback after that).
export function trackJob(jobId: string, handlers: TrackerHandlers, options: TrackerOptions = {}): () => void {
  const Source = options.EventSource === undefined ? globalThis.EventSource : options.EventSource;
  const ask = options.fetchJob ?? fetchJob;
  const pollMs = options.pollMs ?? POLL_MS;
  let stopped = false;
  let source: EventSourceLike | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;

  const stop = () => {
    stopped = true;
    source?.close();
    source = null;
    if (timer !== null) clearTimeout(timer);
    timer = null;
  };

  const deliver = (status: StatusInfo) => {
    if (stopped) return;
    handlers.onStatus(status);
    if (TERMINAL_STATES.includes(status.status)) stop();
  };

  const poll = async () => {
    timer = null;
    if (stopped) return;
    let delay = pollMs;
    try {
      deliver(await ask(jobId));
    } catch (error) {
      if (stopped) return;
      if (error instanceof HttpError && error.status === 404) {
        stop();
        handlers.onGone();
        return;
      }
      delay = retryDelay(error, pollMs);
    }
    if (!stopped) timer = setTimeout(poll, delay);
  };

  const fallBack = () => {
    source?.close();
    source = null;
    if (!stopped && timer === null) void poll();
  };

  if (!Source) {
    void poll();
    return stop;
  }

  let errors = 0;
  const stream = new Source(eventsUrl(jobId));
  source = stream;
  stream.addEventListener('status', (event) => {
    let data: unknown;
    try {
      data = JSON.parse((event as MessageEvent).data as string);
    } catch {
      return;
    }
    const status = parseStatusInfo(data, jobId);
    if (!status) return;
    errors = 0;
    deliver(status);
  });
  stream.onerror = () => {
    if (stopped || source !== stream) return;
    // `EventSource.CLOSED` is 2; read off the number so a stub needs no constants.
    if (stream.readyState === 2) {
      fallBack();
      return;
    }
    errors += 1;
    if (errors >= MAX_STREAM_ERRORS) fallBack();
  };
  return stop;
}

// --- sessionStorage (F5 (1)) ---------------------------------------------------

export const JOBS_STORAGE_KEY = 'earthx.processing.jobs';

export interface StoredJob {
  jobID: string;
  expires: string;
}

function storage(): Storage | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null; // blocked storage throws on access
  }
}

// The jobs of this tab that have not expired; anything malformed is dropped.
export function loadStoredJobs(now: number = Date.now()): StoredJob[] {
  try {
    const raw = storage()?.getItem(JOBS_STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    const jobs: StoredJob[] = [];
    for (const entry of parsed) {
      if (!entry || typeof entry !== 'object') continue;
      const { jobID, expires } = entry as Record<string, unknown>;
      if (!isJobId(jobID) || typeof expires !== 'string') continue;
      const end = Date.parse(expires);
      if (Number.isNaN(end) || end <= now) continue;
      if (!jobs.some((j) => j.jobID === jobID)) jobs.push({ jobID, expires });
    }
    return jobs;
  } catch {
    return [];
  }
}

export function saveStoredJobs(jobs: readonly StoredJob[]): void {
  try {
    const target = storage();
    if (!target) return;
    if (jobs.length === 0) target.removeItem(JOBS_STORAGE_KEY);
    else target.setItem(JOBS_STORAGE_KEY, JSON.stringify(jobs.map(({ jobID, expires }) => ({ jobID, expires }))));
  } catch {
    /* blocked or full: the panel works on without resuming after a reload */
  }
}
