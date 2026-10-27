import { describe, expect, it } from 'vitest';

import { batchEntry, finished, jobEntry, NOW, status } from '../fixtures/jobEntries';
import { MIN_REMAINING_MS } from '../resultLayer';
import { batchSummary, canDelete, canRestore, countBatch, deletableParts, formatUntil, jobLabel, jobState } from './jobView';

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

  it('calls a job past its expiry expired, and one the server no longer knows "No longer available"', () => {
    expect(jobState(jobEntry(1, { phase: 'gone' }), NOW)).toMatchObject({ key: 'unavailable', text: 'No longer available' });
    expect(jobState(jobEntry(1, { phase: 'gone', expired: true }), NOW).key).toBe('expired');
    expect(jobState(jobEntry(1, { phase: 'gone', expires: new Date(NOW - 1000).toISOString() }), NOW).key).toBe('expired');
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
    expect(countBatch(batch, parts, NOW)).toMatchObject({ done: 2, running: 1, refused: 1, failed: 1, expired: 0, cancelled: 0, unavailable: 1, deleted: 0, total: 6 });
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
    const count = { done: 12, running: 3, refused: 1, failed: 1, expired: 0, cancelled: 0, unavailable: 0, deleted: 0, total: 17, progress: 0, expires: null };
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

describe('a deleted job (NM4-27)', () => {
  const day = (ms: number) => new Date(NOW + ms).toISOString();

  it('is "Deleted" whatever it was before, and says so when the server forgot it', () => {
    for (const make of [() => finished(1), () => jobEntry(1, { phase: 'failed' }), () => jobEntry(1, { phase: 'gone' }), () => jobEntry(1, { phase: 'dismissed' })]) {
      expect(jobState({ ...make(), deletedUntil: day(1000) }, NOW)).toEqual({ key: 'deleted', text: 'Deleted', progress: null });
    }
    expect(jobState({ ...finished(1), deletedUntil: day(1000), lost: true }, NOW).text).toBe('No longer available');
  });

  it('is "Deleted" after its day too: it does not come back as anything else', () => {
    expect(jobState({ ...finished(1), deletedUntil: day(-1000) }, NOW).key).toBe('deleted');
  });

  it('can be restored until the end of its day, not at it and not after', () => {
    expect(canRestore({ ...finished(1), deletedUntil: day(1) }, NOW)).toBe(true);
    expect(canRestore({ ...finished(1), deletedUntil: day(0) }, NOW)).toBe(false);
    expect(canRestore({ ...finished(1), deletedUntil: day(-1) }, NOW)).toBe(false);
    expect(canRestore(finished(1), NOW)).toBe(false);
  });
});

describe('what Delete acts on (NM4-27)', () => {
  it('is a job that is over, however it ended', () => {
    const over = [finished(1), jobEntry(2, { phase: 'failed' }), jobEntry(3, { phase: 'dismissed' }), finished(4, { expired: true }), jobEntry(5, { phase: 'gone' })];
    expect(over.map((job) => canDelete(job, NOW))).toEqual([true, true, true, true, true]);
  });

  it('is not a job that waits, runs or is not known yet: those have "Cancel"', () => {
    const live = [jobEntry(1), jobEntry(2, { status: status({ status: 'accepted', progress: 0 }) }), jobEntry(3, { status: null })];
    expect(live.map((job) => canDelete(job, NOW))).toEqual([false, false, false]);
  });

  it('is not a job that is deleted already, nor one whose deletion is under way', () => {
    expect(canDelete({ ...finished(1), deletedUntil: new Date(NOW + 1000).toISOString() }, NOW)).toBe(false);
    expect(canDelete({ ...finished(1), deleting: true }, NOW)).toBe(false);
  });

  it('is every part of a batch that is over and none while one part waits or runs', () => {
    const parts = [finished(1), jobEntry(2, { phase: 'failed' }), { ...finished(3), deletedUntil: new Date(NOW + 1000).toISOString() }];
    expect(deletableParts(parts, NOW).map((p) => p.jobID)).toEqual([parts[0].jobID, parts[1].jobID]);
    expect(deletableParts([...parts, jobEntry(4)], NOW)).toEqual([]);
    expect(deletableParts([], NOW)).toEqual([]);
  });
});

describe('the count of a batch with deleted and forgotten parts', () => {
  const batch = batchEntry('b'.repeat(32));
  const until = new Date(NOW + 1000).toISOString();
  const parts = [
    finished(1, { batchId: batch.id }),
    finished(2, { batchId: batch.id, deletedUntil: until }),
    jobEntry(3, { batchId: batch.id, phase: 'gone' }),
  ];

  it('counts them apart and says so in the summary', () => {
    const count = countBatch(batch, parts, NOW);
    expect(count).toMatchObject({ done: 1, deleted: 1, unavailable: 1, expired: 0 });
    expect(batchSummary(count)).toBe('1 done · 1 unavailable · 1 deleted');
  });

  it('names the end of the parts that still stand and not of those that are deleted or forgotten', () => {
    expect(countBatch(batch, parts, NOW).expires).toBe(parts[0].expires);
  });
});
