import { describe, expect, it } from 'vitest';

import { batchEntry, finished, jobEntry, NOW, status } from '../fixtures/jobEntries';
import { MIN_REMAINING_MS } from '../resultLayer';
import { batchSummary, countBatch, formatUntil, jobLabel, jobState } from './jobView';

describe('jobState', () => {
  it('names the state of a job that waits, runs or has not been asked yet', () => {
    expect(jobState(jobEntry(1, { status: status({ status: 'accepted', progress: 0 }) }), NOW)).toEqual({ key: 'waiting', text: 'Waiting', progress: 0 });
    expect(jobState(jobEntry(1, { status: status({ progress: 70 }) }), NOW)).toEqual({ key: 'running', text: '70%', progress: 70 });
    expect(jobState(jobEntry(1, { status: null }), NOW)).toEqual({ key: 'checking', text: 'Checking…', progress: null });
  });

  it('names the end of a job: finished, failed, cancelled', () => {
    expect(jobState(finished(1), NOW).key).toBe('finished');
    expect(jobState(jobEntry(1, { phase: 'failed' }), NOW).key).toBe('failed');
    expect(jobState(jobEntry(1, { phase: 'dismissed' }), NOW).key).toBe('cancelled');
  });

  it('calls a job the server no longer knows, and one past its expiry, expired', () => {
    expect(jobState(jobEntry(1, { phase: 'gone' }), NOW).key).toBe('expired');
    expect(jobState(finished(1, { expired: true }), NOW).key).toBe('expired');
  });

  it('turns a finished job expired a minute before its time, the minute its links stop working', () => {
    const job = finished(1, { expires: new Date(NOW + MIN_REMAINING_MS + 1000).toISOString() });
    expect(jobState(job, NOW).key).toBe('finished');
    expect(jobState(job, NOW + 1001).key).toBe('expired');
  });

  it('leaves a failed job failed after its expiry: the reason is what the user needs', () => {
    expect(jobState(jobEntry(1, { phase: 'failed', expires: new Date(NOW - 1000).toISOString() }), NOW).key).toBe('failed');
  });
});

describe('formatUntil', () => {
  it('is day, month, hour and minute, without a year in this year', () => {
    expect(formatUntil('2026-10-31T14:02:00Z', NOW)).toMatch(/^31 Oct, \d{2}:\d{2}$/u);
  });

  it('names the year when it is not this one', () => {
    expect(formatUntil('2027-01-05T14:02:00Z', NOW)).toMatch(/^5 Jan 2027, \d{2}:\d{2}$/u);
  });

  it('shows what it cannot read as it is', () => {
    expect(formatUntil('soon', NOW)).toBe('soon');
  });
});

describe('countBatch', () => {
  const batch = batchEntry('b'.repeat(32), { refused: [{ label: 'S9', message: 'no' }] });
  const parts = [
    finished(1, { batchId: batch.id }),
    finished(2, { batchId: batch.id }),
    jobEntry(3, { batchId: batch.id, status: status({ progress: 50 }) }),
    jobEntry(4, { batchId: batch.id, phase: 'failed' }),
    jobEntry(5, { batchId: batch.id, phase: 'gone' }),
  ];

  it('counts the parts by state, the refused ones too', () => {
    expect(countBatch(batch, parts, NOW)).toMatchObject({ done: 2, running: 1, refused: 1, failed: 1, expired: 1, cancelled: 0, total: 6 });
  });

  it('adds the progress up: a part that is over counts whole, a refused one too', () => {
    // 100 + 100 + 50 + 100 + 100 + 100 (refused), over six parts
    expect(countBatch(batch, parts, NOW).progress).toBe(92);
  });

  it('takes the earliest expiry of the parts that still stand', () => {
    const early = new Date(NOW + 2 * 86_400_000).toISOString();
    const late = new Date(NOW + 5 * 86_400_000).toISOString();
    const stood = [finished(1, { batchId: batch.id, expires: late }), finished(2, { batchId: batch.id, expires: early }), jobEntry(3, { batchId: batch.id, phase: 'gone', expires: new Date(NOW - 1000).toISOString() })];
    expect(countBatch(batch, stood, NOW).expires).toBe(early);
  });

  it('takes the earliest of all where none stands, and none where there is no part', () => {
    const gone = [jobEntry(1, { batchId: batch.id, phase: 'gone', expires: '2026-10-01T00:00:00.000Z' }), jobEntry(2, { batchId: batch.id, phase: 'gone', expires: '2026-10-02T00:00:00.000Z' })];
    expect(countBatch(batch, gone, NOW).expires).toBe('2026-10-01T00:00:00.000Z');
    expect(countBatch(batchEntry('c'.repeat(32)), [], NOW)).toMatchObject({ total: 0, progress: 0, expires: null });
  });

  it('counts a part whose state is not known yet as running, not as done', () => {
    expect(countBatch(batch, [jobEntry(1, { batchId: batch.id, status: null })], NOW)).toMatchObject({ running: 1, done: 0 });
  });
});

describe('batchSummary', () => {
  it('reads "12 done · 3 running · 1 refused · 1 failed" and leaves out what is zero', () => {
    const count = { done: 12, running: 3, refused: 1, failed: 1, expired: 0, cancelled: 0, total: 17, progress: 0, expires: null };
    expect(batchSummary(count)).toBe('12 done · 3 running · 1 refused · 1 failed');
    expect(batchSummary({ ...count, done: 0, running: 0, refused: 0, failed: 0, expired: 2 })).toBe('2 expired');
  });
});

describe('jobLabel', () => {
  it('is the title, or a plain name for a job that has none', () => {
    expect(jobLabel({ title: 'NDVI' })).toBe('NDVI');
    expect(jobLabel({ title: null })).toBe('Untitled job');
  });
});
