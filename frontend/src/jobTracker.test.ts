// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HttpError } from './api';
import {
  JOBS_STORAGE_KEY,
  loadStoredJobs,
  MAX_STREAM_ERRORS,
  POLL_MS,
  saveStoredJobs,
  trackJob,
  type TrackerOptions,
} from './jobTracker';
import type { StatusInfo } from './processing';

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const OTHER = 'ZZZZZZZZZZZZZZZZZZZZZZ';

function status(state: StatusInfo['status'], extra: Partial<StatusInfo> = {}): StatusInfo {
  return { jobID: JOB, status: state, message: '', progress: 0, expires: '2099-01-01T00:00:00Z', ...extra };
}

// An `EventSource` the test drives: `emit` sends a `status` event, `fail`
// raises `error` with the given `readyState`.
class FakeSource {
  static last: FakeSource | null = null;
  readonly url: string;
  readyState = 0;
  closed = false;
  onerror: (() => void) | null = null;
  onopen: (() => void) | null = null;
  private listeners: ((event: { data: string }) => void)[] = [];

  constructor(url: string) {
    this.url = url;
    FakeSource.last = this;
  }

  addEventListener(type: string, listener: (event: { data: string }) => void) {
    if (type === 'status') this.listeners.push(listener);
  }

  close() {
    this.closed = true;
    this.readyState = 2;
  }

  emit(data: unknown) {
    for (const listener of this.listeners) listener({ data: typeof data === 'string' ? data : JSON.stringify(data) });
  }

  fail(readyState: 0 | 2) {
    this.readyState = readyState;
    this.onerror?.();
  }
}

function options(fetchJob: TrackerOptions['fetchJob'], withSource = true): TrackerOptions {
  return { EventSource: withSource ? (FakeSource as unknown as TrackerOptions['EventSource']) : null, fetchJob };
}

beforeEach(() => {
  vi.useFakeTimers();
  FakeSource.last = null;
});

afterEach(() => {
  vi.useRealTimers();
});

describe('trackJob over server-sent events', () => {
  it('follows status events of its job until the final state, then closes the stream', () => {
    const seen: string[] = [];
    const fetchJob = vi.fn();
    trackJob(JOB, { onStatus: (s) => seen.push(`${s.status}:${s.progress}`), onGone: vi.fn() }, options(fetchJob));
    const source = FakeSource.last!;
    expect(source.url).toBe(`/processing/jobs/${JOB}/events`);
    source.emit(status('accepted'));
    source.emit(status('running', { progress: 50 }));
    source.emit(status('successful', { progress: 100 }));
    expect(seen).toEqual(['accepted:0', 'running:50', 'successful:100']);
    expect(source.closed).toBe(true);
    expect(fetchJob).not.toHaveBeenCalled();
  });

  it('drops an event with broken JSON or of another job', () => {
    const onStatus = vi.fn();
    trackJob(JOB, { onStatus, onGone: vi.fn() }, options(vi.fn()));
    FakeSource.last!.emit('{"jobID": ');
    FakeSource.last!.emit(status('running', { jobID: OTHER }));
    FakeSource.last!.emit({ ...status('running'), status: 'paused' });
    expect(onStatus).not.toHaveBeenCalled();
    expect(FakeSource.last!.closed).toBe(false);
  });

  it('polls at once when the server refuses the stream (CLOSED)', async () => {
    const fetchJob = vi.fn(async () => status('running', { progress: 10 }));
    const onStatus = vi.fn();
    trackJob(JOB, { onStatus, onGone: vi.fn() }, options(fetchJob));
    FakeSource.last!.fail(2);
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchJob).toHaveBeenCalledTimes(1);
    expect(onStatus).toHaveBeenCalledWith(status('running', { progress: 10 }));
    await vi.advanceTimersByTimeAsync(POLL_MS);
    expect(fetchJob).toHaveBeenCalledTimes(2);
  });

  it(`polls after ${MAX_STREAM_ERRORS} breaks in a row, not before`, async () => {
    const fetchJob = vi.fn(async () => status('running'));
    trackJob(JOB, { onStatus: vi.fn(), onGone: vi.fn() }, options(fetchJob));
    const source = FakeSource.last!;
    for (let i = 1; i < MAX_STREAM_ERRORS; i++) source.fail(0);
    await vi.advanceTimersByTimeAsync(POLL_MS * 3);
    expect(fetchJob).not.toHaveBeenCalled();
    source.fail(0);
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchJob).toHaveBeenCalledTimes(1);
    expect(source.closed).toBe(true);
  });

  it('counts breaks only in a row: an event in between starts the count again', async () => {
    const fetchJob = vi.fn(async () => status('running'));
    trackJob(JOB, { onStatus: vi.fn(), onGone: vi.fn() }, options(fetchJob));
    const source = FakeSource.last!;
    source.fail(0);
    source.fail(0);
    source.emit(status('running'));
    source.fail(0);
    source.fail(0);
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchJob).not.toHaveBeenCalled();
  });

  it('calls nothing after stop', () => {
    const onStatus = vi.fn();
    const stop = trackJob(JOB, { onStatus, onGone: vi.fn() }, options(vi.fn()));
    stop();
    FakeSource.last!.emit(status('running'));
    expect(onStatus).not.toHaveBeenCalled();
    expect(FakeSource.last!.closed).toBe(true);
  });
});

describe('trackJob by polling', () => {
  it('polls from the start without EventSource, until the final state', async () => {
    const answers = [status('accepted'), status('running', { progress: 60 }), status('failed')];
    const fetchJob = vi.fn(async () => answers.shift()!);
    const onStatus = vi.fn();
    trackJob(JOB, { onStatus, onGone: vi.fn() }, options(fetchJob, false));
    await vi.advanceTimersByTimeAsync(POLL_MS * 5);
    expect(fetchJob).toHaveBeenCalledTimes(3);
    expect(onStatus.mock.calls.map(([s]) => (s as StatusInfo).status)).toEqual(['accepted', 'running', 'failed']);
  });

  it('waits as long as Retry-After says', async () => {
    const fetchJob = vi
      .fn<() => Promise<StatusInfo>>()
      .mockRejectedValueOnce(new HttpError(503, 'busy', 'busy', '7'))
      .mockResolvedValue(status('running'));
    trackJob(JOB, { onStatus: vi.fn(), onGone: vi.fn() }, options(fetchJob, false));
    await vi.advanceTimersByTimeAsync(0);
    expect(fetchJob).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(6900);
    expect(fetchJob).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(200);
    expect(fetchJob).toHaveBeenCalledTimes(2);
  });

  it('keeps the plain interval for a Retry-After that is a date or a network error', async () => {
    const fetchJob = vi
      .fn<() => Promise<StatusInfo>>()
      .mockRejectedValueOnce(new HttpError(503, 'busy', 'busy', 'Wed, 21 Oct 2026 07:28:00 GMT'))
      .mockRejectedValueOnce(new TypeError('Failed to fetch'))
      .mockResolvedValue(status('running'));
    trackJob(JOB, { onStatus: vi.fn(), onGone: vi.fn() }, options(fetchJob, false));
    await vi.advanceTimersByTimeAsync(POLL_MS * 2);
    expect(fetchJob).toHaveBeenCalledTimes(3);
  });

  it('ends with "gone" on a 404', async () => {
    const fetchJob = vi.fn(async () => {
      throw new HttpError(404, 'there is no such job', 'there is no such job');
    });
    const onGone = vi.fn();
    trackJob(JOB, { onStatus: vi.fn(), onGone }, options(fetchJob, false));
    await vi.advanceTimersByTimeAsync(POLL_MS * 3);
    expect(onGone).toHaveBeenCalledTimes(1);
    expect(fetchJob).toHaveBeenCalledTimes(1);
  });
});

describe('jobs in sessionStorage', () => {
  const now = Date.parse('2026-10-10T12:00:00Z');

  beforeEach(() => {
    sessionStorage.clear();
  });

  it('keeps only jobID and expires', () => {
    saveStoredJobs([{ jobID: JOB, expires: '2026-10-17T12:00:00Z', aoi: [1, 2], order: {} } as never]);
    expect(JSON.parse(sessionStorage.getItem(JOBS_STORAGE_KEY)!)).toEqual([
      { jobID: JOB, expires: '2026-10-17T12:00:00Z' },
    ]);
  });

  it('takes the jobs up again and drops expired, malformed and repeated ones', () => {
    sessionStorage.setItem(
      JOBS_STORAGE_KEY,
      JSON.stringify([
        { jobID: JOB, expires: '2026-10-17T12:00:00Z' },
        { jobID: OTHER, expires: '2026-10-10T11:59:59Z' },
        { jobID: '../x', expires: '2026-10-17T12:00:00Z' },
        { jobID: OTHER, expires: 'tomorrow' },
        'nonsense',
        { jobID: JOB, expires: '2026-10-18T12:00:00Z' },
      ]),
    );
    expect(loadStoredJobs(now)).toEqual([{ jobID: JOB, expires: '2026-10-17T12:00:00Z' }]);
  });

  it('reads nothing from a value that is no list or no JSON', () => {
    sessionStorage.setItem(JOBS_STORAGE_KEY, '{"jobID":"x"}');
    expect(loadStoredJobs(now)).toEqual([]);
    sessionStorage.setItem(JOBS_STORAGE_KEY, '[');
    expect(loadStoredJobs(now)).toEqual([]);
  });

  it('removes the key when no job is left', () => {
    saveStoredJobs([{ jobID: JOB, expires: '2026-10-17T12:00:00Z' }]);
    saveStoredJobs([]);
    expect(sessionStorage.getItem(JOBS_STORAGE_KEY)).toBeNull();
  });

  it('works on without resuming when the storage is blocked', () => {
    const blocked = vi.spyOn(globalThis, 'sessionStorage', 'get').mockImplementation(() => {
      throw new DOMException('blocked', 'SecurityError');
    });
    expect(() => saveStoredJobs([{ jobID: JOB, expires: '2026-10-17T12:00:00Z' }])).not.toThrow();
    expect(loadStoredJobs(now)).toEqual([]);
    blocked.mockRestore();
  });
});
