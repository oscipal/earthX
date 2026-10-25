import { describe, expect, it } from 'vitest';

import type { EstimateDocument } from './processing';
import {
  batchPass,
  effectiveRunAs,
  foreignReason,
  foreignScenes,
  jobTitle,
  titleDay,
  MAX_BATCH_JOBS,
  runChoices,
  runPool,
  secondsOf,
  totalOf,
  TOO_MANY_JOBS,
  unitsOf,
} from './processingBatch';
import type { Pass } from './processingOrder';
import type { StacItem } from './types';

function item(id: string, collection?: string): StacItem {
  return { id, ...(collection ? { collection } : {}), properties: {}, assets: {} } as unknown as StacItem;
}

function pass(key: string, ids: string[]): Pass {
  return { key, label: `pass ${key}`, items: ids.map((id) => item(id)) };
}

function many(n: number): StacItem[] {
  return Array.from({ length: n }, (_, i) => item(`S${i}`));
}

describe('the choices of "Run as"', () => {
  it('leaves out a choice that would make one job', () => {
    const one = pass('a', ['S1']);
    expect(runChoices([one], one.items).map((c) => c.value)).toEqual(['one']);
  });

  it('offers a job per pass only for several passes, a job per scene only for several scenes', () => {
    const a = pass('a', ['S1', 'S2']);
    expect(runChoices([a], a.items).map((c) => c.label)).toEqual(['One job', 'One job per scene (2)']);
    const b = pass('b', ['S3']);
    expect(runChoices([a, b], [...a.items, ...b.items]).map((c) => c.label)).toEqual([
      'One job',
      'One job per pass (2)',
      'One job per scene (3)',
    ]);
  });

  it('offers nothing for no scenes', () => {
    expect(runChoices([], []).map((c) => c.value)).toEqual(['one']);
  });

  it(`greys out a choice over ${MAX_BATCH_JOBS} jobs and gives the reason`, () => {
    const scenes = many(MAX_BATCH_JOBS + 1);
    const choices = runChoices([pass('a', scenes.map((s) => s.id))], scenes);
    expect(choices.find((c) => c.value === 'scene')?.disabled).toBe('At most 25 jobs at once');
    expect(TOO_MANY_JOBS).toBe('At most 25 jobs at once');
  });

  it('takes exactly 25 jobs', () => {
    const scenes = many(MAX_BATCH_JOBS);
    const choices = runChoices([pass('a', scenes.map((s) => s.id))], scenes);
    expect(choices.find((c) => c.value === 'scene')?.disabled).toBeNull();
  });

  it('falls back to one job when the wanted choice is gone or not allowed', () => {
    const scenes = many(MAX_BATCH_JOBS + 1);
    const over = runChoices([pass('a', scenes.map((s) => s.id))], scenes);
    expect(effectiveRunAs('scene', over)).toBe('one');
    expect(effectiveRunAs('pass', over)).toBe('one');
    const ok = runChoices([pass('a', ['S1', 'S2'])], many(2));
    expect(effectiveRunAs('scene', ok)).toBe('scene');
    expect(effectiveRunAs('pass', ok)).toBe('one');
  });
});

describe('the jobs of a batch', () => {
  const a = pass('a', ['S1', 'S2']);
  const b = pass('b', ['S3']);
  const scenes = [...a.items, ...b.items];

  it('is the picked pass for one job, and none while no pass is picked', () => {
    expect(unitsOf('one', a, [a, b], scenes).map((u) => u.items.map((i) => i.id))).toEqual([['S1', 'S2']]);
    expect(unitsOf('one', null, [a, b], scenes)).toEqual([]);
  });

  it('is one job per pass, in the order of the passes', () => {
    const units = unitsOf('pass', null, [a, b], scenes);
    expect(units.map((u) => [u.label, u.items.map((i) => i.id)])).toEqual([
      ['pass a', ['S1', 'S2']],
      ['pass b', ['S3']],
    ]);
  });

  it('is one job per scene, in the order of the scenes', () => {
    expect(unitsOf('scene', null, [a, b], scenes).map((u) => [u.key, u.items.length])).toEqual([
      ['S1', 1],
      ['S2', 1],
      ['S3', 1],
    ]);
  });

  it('is read as one piece of all the scenes of the batch', () => {
    const units = unitsOf('pass', null, [a, b], scenes);
    expect(batchPass('pass', units)).toMatchObject({ label: '2 passes', items: scenes });
    expect(batchPass('scene', unitsOf('scene', null, [a, b], scenes))?.label).toBe('');
    expect(batchPass('scene', [])).toBeNull();
  });
});

describe('scenes of another dataset', () => {
  const sections: Record<string, string> = { S1: 'sentinel-2-c1-l2a', S2: 'cop-dem-glo-30' };
  const foundUnder = (i: StacItem) => sections[i.id] ?? null;

  it('finds the scenes that were found under another dataset', () => {
    const items = [item('S1'), item('S2'), item('S3')];
    expect(foreignScenes('sentinel-2-c1-l2a', items, foundUnder).map((i) => i.id)).toEqual(['S2']);
  });

  it('goes by where the scene was found, not by its collection', () => {
    // a federated source names its collection otherwise than the platform names the dataset
    const upstream = item('S1', 'upstream-collection-name');
    expect(foreignScenes('sentinel-2-c1-l2a', [upstream], foundUnder)).toEqual([]);
    const other = item('S2', 'sentinel-2-c1-l2a');
    expect(foreignScenes('sentinel-2-c1-l2a', [other], foundUnder).map((i) => i.id)).toEqual(['S2']);
  });

  it('lets a scene pass whose context is not known, and an empty selection', () => {
    expect(foreignScenes('x', [item('S3')], foundUnder)).toEqual([]);
    expect(foreignScenes('x', [], foundUnder)).toEqual([]);
  });

  it('names the scenes in the reason', () => {
    expect(foreignReason([item('S2'), item('S4')])).toContain('S2, S4');
  });
});

function doc(seconds: string, pixels: number, size: number, units: number): EstimateDocument {
  return {
    estimate: { size, duration: seconds, outputPixels: pixels, inputPixels: 0, inputBytes: 0, assets: 1, units },
    skippedItems: [],
  };
}

describe('the estimate as a sum', () => {
  it('adds pixels, bytes, units and the work', () => {
    const total = totalOf([doc('PT3.4S', 1_000_000, 4_000_000, 1), doc('PT10S', 2_000_000, 8_000_000, 1.5)]);
    expect(total).toEqual({ jobs: 2, outputPixels: 3_000_000, size: 12_000_000, units: 2.5, duration: 'PT13.4S' });
  });

  it('is nothing for no job', () => {
    expect(totalOf([])).toEqual({ jobs: 0, outputPixels: 0, size: 0, units: 0, duration: 'PT0S' });
  });

  it('names no sum of work when a duration has a form it does not know', () => {
    expect(totalOf([doc('PT1M30S', 1, 1, 1), doc('PT2S', 1, 1, 1)]).duration).toBeNull();
    expect(secondsOf('P1D')).toBeNull();
    expect(secondsOf('PT12.5S')).toBe(12.5);
  });
});

describe('the title of a job (K5, UI-01 §6.5)', () => {
  it('is the operators, the dataset and the day', () => {
    expect(jobTitle({ operators: ['Band math'], dataset: 'Sentinel-2 L2A', day: '12 Oct' })).toBe(
      'Band math · Sentinel-2 L2A · 12 Oct',
    );
    expect(jobTitle({ operators: ['Band math'], dataset: 'Sentinel-2 L2A' })).toBe('Band math · Sentinel-2 L2A');
  });

  it('names an operator once and lists several', () => {
    expect(jobTitle({ operators: ['Reproject', 'Band math', 'Reproject'], dataset: 'DEM' })).toBe(
      'Reproject, Band math · DEM',
    );
  });

  it('leaves out what is empty', () => {
    expect(jobTitle({ operators: [], dataset: 'DEM' })).toBe('DEM');
  });

  it('never grows past the length the shelf keeps', () => {
    expect(jobTitle({ operators: ['x'.repeat(300)], dataset: 'DEM', day: '1 Jan' })).toHaveLength(200);
  });
});

describe('the day of a title', () => {
  const now = new Date(2026, 9, 25, 10);
  const scene = (datetime: unknown) => ({ id: 's', properties: { datetime } }) as unknown as StacItem;
  const key = ['datetime', 's2:datatake_id'];

  it('is the day the scenes were acquired, where they share one', () => {
    expect(titleDay([scene('2026-10-12T10:20:30Z'), scene('2026-10-12T10:20:55Z')], key, now)).toBe('12 Oct');
  });

  it('counts the day in UTC, as the name of a download does', () => {
    expect(titleDay([scene('2026-10-12T23:59:59-03:00')], key, now)).toBe('13 Oct');
  });

  it('adds the year when it is not the current one', () => {
    expect(titleDay([scene('2025-03-02T10:00:00Z')], key, now)).toBe('2 Mar 2025');
  });

  it('is the day the job is started where the scenes were acquired on several days', () => {
    expect(titleDay([scene('2026-10-12T10:00:00Z'), scene('2026-10-13T10:00:00Z')], key, now)).toBe('25 Oct');
  });

  it('is the day the job is started where a scene has no instant, or the dataset has no day of acquisition', () => {
    expect(titleDay([scene('2026-10-12T10:00:00Z'), scene(null)], key, now)).toBe('25 Oct');
    expect(titleDay([scene('nonsense')], key, now)).toBe('25 Oct');
    expect(titleDay([scene('2026-10-12T10:00:00Z')], ['start_datetime'], now)).toBe('25 Oct');
    expect(titleDay([scene('2026-10-12T10:00:00Z')], null, now)).toBe('25 Oct');
    expect(titleDay([], key, now)).toBe('25 Oct');
  });
});

describe('a few at a time', () => {
  it('never runs more than the limit at once, and returns the results in order', async () => {
    let running = 0;
    let peak = 0;
    const results = await runPool([1, 2, 3, 4, 5, 6, 7, 8, 9], 4, new AbortController().signal, async (n) => {
      running += 1;
      peak = Math.max(peak, running);
      await new Promise((resolve) => setTimeout(resolve, 5));
      running -= 1;
      return n * 10;
    });
    expect(peak).toBe(4);
    expect(results).toEqual([10, 20, 30, 40, 50, 60, 70, 80, 90]);
  });

  it('hands out nothing more once aborted', async () => {
    const controller = new AbortController();
    const started: number[] = [];
    const results = await runPool([1, 2, 3, 4, 5, 6], 2, controller.signal, async (n) => {
      started.push(n);
      if (n === 2) controller.abort();
      await new Promise((resolve) => setTimeout(resolve, 5));
      return n;
    });
    expect(started).toEqual([1, 2]);
    expect(results.slice(2)).toEqual([undefined, undefined, undefined, undefined]);
  });

  it('does nothing for no item', async () => {
    expect(await runPool([], 4, new AbortController().signal, async () => 1)).toEqual([]);
  });
});
