import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { clampDay, dateBounds, prefilledDays, todayUtc, utcDay } from './dateBounds';
import type { Collection } from './types';

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};
const VIEWER = {
  group_by: ['datetime'],
  min_zoom: 0,
  max_zoom: 14,
  browse: 'quicklook' as const,
  quicklook_nodata_max: null,
  results_group_by: ['datetime'],
};

function dataset(id: string, interval: unknown, timeAxis = true): Collection {
  return {
    id,
    title: id,
    extent: { temporal: { interval: [interval as [string | null, string | null]] } },
    'earthx:capabilities': { ...CAPABILITIES, time_range: timeAxis },
    'earthx:viewer': VIEWER,
  };
}

const TODAY = '2026-11-06';
const OPTICAL = dataset('optical', ['2015-06-27T10:25:31.456Z', null]);
const RADAR = dataset('radar', ['2014-10-03T00:00:00Z', '2025-12-31T23:59:59Z']);
const DEM = dataset('dem', ['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z'], false);
const ALL = datasetsFrom([OPTICAL, RADAR, DEM]);
const bounds = (...ids: string[]) => dateBounds(ALL, ids, TODAY);

describe('utcDay', () => {
  it('is the day of the instant in UTC, whatever the offset written', () => {
    expect(utcDay('2015-06-27T10:25:31.456Z')).toBe('2015-06-27');
    expect(utcDay('2015-06-27T23:30:00-02:00')).toBe('2015-06-28');
  });

  it('is null for what is not an instant', () => {
    expect(utcDay('soon')).toBeNull();
    expect(utcDay('')).toBeNull();
  });
});

describe('dateBounds', () => {
  it('is the extent of one dataset, an open end being today', () => {
    expect(bounds('optical')).toEqual({ min: '2015-06-27', max: TODAY });
    expect(bounds('radar')).toEqual({ min: '2014-10-03', max: '2025-12-31' });
  });

  it('spans the chosen datasets with a time axis, earliest start to latest end', () => {
    expect(bounds('optical', 'radar')).toEqual({ min: '2014-10-03', max: TODAY });
  });

  it('leaves out a dataset without a time axis, and is null when none of the chosen has one', () => {
    expect(bounds('optical', 'dem')).toEqual({ min: '2015-06-27', max: TODAY });
    expect(bounds('dem')).toBeNull();
    expect(bounds()).toBeNull();
  });

  it('leaves out a dataset that is not chosen or cannot be viewed', () => {
    const broken = datasetsFrom([{ id: 'broken', extent: { temporal: { interval: [['1990-01-01T00:00:00Z', null]] } } }]);
    expect(dateBounds([...ALL, ...broken], ['optical', 'broken'], TODAY)).toEqual({ min: '2015-06-27', max: TODAY });
  });

  it.each([
    ['no interval', undefined],
    ['an interval that is no list', 'always'],
    ['a start that is no instant', ['soon', '2020-01-01T00:00:00Z']],
    ['an open start', [null, '2020-01-01T00:00:00Z']],
  ])('leaves the side open where the extent says nothing it can read: %s', (_name, interval) => {
    const odd = datasetsFrom([dataset('odd', interval)]);
    const result = dateBounds(odd, ['odd'], TODAY)!;
    expect(result.min).toBeNull();
  });

  it('says nothing for an extent that ends before it starts', () => {
    const odd = datasetsFrom([dataset('odd', ['2020-01-01T00:00:00Z', '2019-01-01T00:00:00Z'])]);
    expect(dateBounds(odd, ['odd'], TODAY)).toEqual({ min: null, max: null });
  });

  it('opens a side for all when one chosen dataset leaves it open', () => {
    const odd = datasetsFrom([dataset('odd', [null, '2020-01-01T00:00:00Z'])]);
    expect(dateBounds([...ALL, ...odd], ['radar', 'odd'], TODAY)).toEqual({ min: null, max: '2025-12-31' });
  });

  it('takes today from the UTC clock', () => {
    expect(todayUtc()).toMatch(/^\d{4}-\d{2}-\d{2}$/u);
  });
});

describe('clampDay', () => {
  const limits = { min: '2015-06-27', max: TODAY };

  it('moves a day outside the bounds onto the nearest one', () => {
    expect(clampDay('2001-01-01', limits)).toBe('2015-06-27');
    expect(clampDay('2030-01-01', limits)).toBe(TODAY);
  });

  it('leaves a day within the bounds, an empty field and what is no day as they are', () => {
    expect(clampDay('2020-05-05', limits)).toBe('2020-05-05');
    expect(clampDay('', limits)).toBe('');
    expect(clampDay('2020-5-5', limits)).toBe('2020-5-5');
  });

  it('moves nothing without bounds or on an open side', () => {
    expect(clampDay('2001-01-01', null)).toBe('2001-01-01');
    expect(clampDay('2001-01-01', { min: null, max: TODAY })).toBe('2001-01-01');
    expect(clampDay('2030-01-01', { min: '2015-06-27', max: null })).toBe('2030-01-01');
  });
});

describe('prefilledDays', () => {
  const days = (...ids: string[]) => prefilledDays(ALL, ids, TODAY);

  it('is the first and the last day of a chosen dataset, an open end being today', () => {
    expect(days('optical')).toEqual({ from: '2015-06-27', to: TODAY });
    expect(days('radar')).toEqual({ from: '2014-10-03', to: '2025-12-31' });
  });

  it('spans all chosen datasets with a time axis, leaving out one without', () => {
    expect(days('optical', 'radar')).toEqual({ from: '2014-10-03', to: TODAY });
    expect(days('optical', 'dem')).toEqual({ from: '2015-06-27', to: TODAY });
  });

  it('is the acquisition period where no chosen dataset has a time axis', () => {
    expect(days('dem')).toEqual({ from: '2010-12-01', to: '2015-01-31' });
  });

  it('is empty with nothing chosen, or only what cannot be viewed', () => {
    expect(days()).toEqual({ from: '', to: '' });
    const broken = datasetsFrom([{ id: 'broken', extent: { temporal: { interval: [['1990-01-01T00:00:00Z', null]] } } }]);
    expect(prefilledDays(broken, ['broken'], TODAY)).toEqual({ from: '', to: '' });
  });

  it('leaves a side empty that the extent does not name', () => {
    const odd = datasetsFrom([dataset('odd', [null, '2020-01-01T00:00:00Z'])]);
    expect(prefilledDays(odd, ['odd'], TODAY)).toEqual({ from: '', to: '2020-01-01' });
  });
});
