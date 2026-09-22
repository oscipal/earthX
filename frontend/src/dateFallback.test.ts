import { describe, expect, it } from 'vitest';

import {
  fallbackNotice,
  fallbackWindows,
  findFallback,
  NO_FALLBACK_MESSAGE,
  pickNearest,
} from './dateFallback';
import type { StacItem } from './types';

function item(id: string, datetime?: string): StacItem {
  return { id, properties: datetime === undefined ? {} : { datetime }, assets: {} };
}

describe('fallbackWindows', () => {
  it('is null when neither bound is set — nothing to expand around', () => {
    expect(fallbackWindows('', '')).toBeNull();
  });

  it('the stage sequence is ±7, ±30, ±90 days around the chosen range', () => {
    const windows = fallbackWindows('2026-07-10', '2026-07-12');
    expect(windows).toEqual([
      { stageDays: 7, start: '2026-07-03', end: '2026-07-19' },
      { stageDays: 30, start: '2026-06-10', end: '2026-08-11' },
      { stageDays: 90, start: '2026-04-11', end: '2026-10-10' },
    ]);
  });

  it('a single bound is expanded around itself', () => {
    const windows = fallbackWindows('2026-07-10', '');
    expect(windows?.[0]).toEqual({ stageDays: 7, start: '2026-07-03', end: '2026-07-17' });
  });
});

describe('pickNearest', () => {
  const reference = Date.parse('2026-07-15T00:00:00Z');

  it('picks the item closest to the reference instant, on either side', () => {
    const before = item('before', '2026-07-10T00:00:00Z');
    const after = item('after', '2026-07-17T00:00:00Z');
    expect(pickNearest([before, after], reference)?.id).toBe('after');
  });

  it('a tie goes to the older item', () => {
    const older = item('older', '2026-07-13T00:00:00Z');
    const newer = item('newer', '2026-07-17T00:00:00Z');
    expect(pickNearest([older, newer], reference)?.id).toBe('older');
  });

  it('an item with a broken or missing datetime is skipped, not crashed on', () => {
    const broken = item('broken', 'not-a-date');
    const missing = item('missing');
    const ok = item('ok', '2026-07-16T00:00:00Z');
    expect(pickNearest([broken, missing, ok], reference)?.id).toBe('ok');
  });

  it('is null when nothing has a usable datetime', () => {
    expect(pickNearest([item('broken', 'nope')], reference)).toBeNull();
  });
});

describe('findFallback', () => {
  it('stops at the first stage with results', async () => {
    const calls: number[] = [];
    const probe = async (w: { stageDays: number }) => {
      calls.push(w.stageDays);
      if (w.stageDays === 7) return { features: [], numberMatched: 0, numberReturned: 0 };
      return {
        features: [item('found', '2026-07-05T00:00:00Z')],
        numberMatched: 1,
        numberReturned: 1,
      };
    };
    const result = await findFallback(probe, '2026-07-15', '2026-07-15');
    expect(calls).toEqual([7, 30]);
    expect(result?.item.id).toBe('found');
    expect(result?.stageDays).toBe(30);
    expect(result?.capped).toBe(false);
  });

  it('all three stages empty ⇒ no fallback', async () => {
    const probe = async () => ({ features: [], numberMatched: 0, numberReturned: 0 });
    expect(await findFallback(probe, '2026-07-15', '2026-07-15')).toBeNull();
  });

  it('no chosen time range ⇒ no fallback, the probe is never called', async () => {
    let called = false;
    const probe = async () => {
      called = true;
      return { features: [], numberMatched: 0, numberReturned: 0 };
    };
    expect(await findFallback(probe, '', '')).toBeNull();
    expect(called).toBe(false);
  });

  it('a capped probe is reported as capped, with the seen/matched counts', async () => {
    const probe = async () => ({
      features: [item('found', '2026-07-05T00:00:00Z')],
      numberMatched: 250,
      numberReturned: 100,
    });
    const result = await findFallback(probe, '2026-07-15', '2026-07-15');
    expect(result?.capped).toBe(true);
    expect(result?.seen).toBe(100);
    expect(result?.matched).toBe(250);
  });
});

describe('fallbackNotice', () => {
  it('the fully-seen case names the nearest date', () => {
    const result = {
      stageDays: 7,
      item: item('x', '2026-07-24T10:00:00Z'),
      capped: false,
      seen: 1,
      matched: 1,
    };
    expect(fallbackNotice(result)).toBe(
      'No results in the chosen time range — nearest scene: 2026-07-24',
    );
  });

  it('the capped case says "found" and names the sample size', () => {
    const result = {
      stageDays: 7,
      item: item('x', '2026-07-24T10:00:00Z'),
      capped: true,
      seen: 100,
      matched: 250,
    };
    expect(fallbackNotice(result)).toBe(
      'No results in the chosen time range — nearest scene found: 2026-07-24 ' +
        '(sample of 100 of 250 results within ±7 days)',
    );
  });
});

it('NO_FALLBACK_MESSAGE names all three stages', () => {
  expect(NO_FALLBACK_MESSAGE).toMatch(/90/);
});
