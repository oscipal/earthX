// DS-03b: the cloud share in the AOI as the server answers it and the list shows it (`aoiFilter.ts`). Pure functions only;
// the search and the screens that use them have tests of their own.

import { describe, expect, it } from 'vitest';

import {
  anyMeasuresAoi,
  aoiCountsOf,
  aoiMeasureOf,
  aoiNotes,
  AOI_CLOUD_PROPERTY,
  cloudText,
  cloudValueTip,
  countsFrom,
  groupCloudPercent,
  LOCK_NEEDS_AREA,
  LOCK_NEEDS_INPUT,
  LOCK_TOO_MANY,
  MAX_AOI_POSITIONS,
  measuresAoi,
  sortedGroupIndices,
  withinAoiLock,
  withinAoiTip,
} from './aoiFilter';
import { CLASSIFICATION } from './fixtures/searchFilters';
import { LOAD_MORE_NOTE, NO_SCENES_NOTE, type ResultSection } from './sections';
import type { StacItem, TimeStepGroup } from './types';

const item = (id: string, properties: Record<string, unknown> = {}): StacItem => ({ id, properties, assets: {} });

const measured = (id: string, cloud: number, data: number, percent?: number): StacItem =>
  item(id, {
    [AOI_CLOUD_PROPERTY]: percent ?? (data > 0 ? Math.round((cloud / data) * 1000) / 10 : 0),
    'earthx:aoi_measure': { data_percent: 80, cloud_pixels: cloud, data_pixels: data, resolution: 80 },
  });

const group = (label: string, items: StacItem[]): TimeStepGroup => ({ key: [label], label, items });

describe('the counts of an answer', () => {
  const counts = { checked: 180, found: 12, unreadable: 1, limit_reached: false };

  it('reads the four fields and nothing else', () => {
    expect(countsFrom(counts)).toEqual({ checked: 180, found: 12, unreadable: 1, limitReached: false });
  });

  it.each([
    ['text', 'x'],
    ['no object', null],
    ['a list', [1, 2, 3, 4]],
    ['a missing field', { checked: 1, found: 1, unreadable: 0 }],
    ['a negative number', { ...counts, found: -1 }],
    ['a fraction', { ...counts, checked: 1.5 }],
    ['a number as text', { ...counts, checked: '180' }],
    ['a flag that is no flag', { ...counts, limit_reached: 1 }],
  ])('takes %s for no counts rather than a wrong number', (_what, value) => {
    expect(countsFrom(value)).toBeNull();
  });

  it('puts the counts of a search over one dataset on the dataset that was asked with the filter', () => {
    const asked = { optical: { [AOI_CLOUD_PROPERTY]: { lte: 20 } }, radar: { 'test:track': { lte: 30 } } };
    expect(aoiCountsOf({ 'earthx:aoi_filter': counts }, asked)).toEqual({
      optical: { checked: 180, found: 12, unreadable: 1, limitReached: false },
    });
  });

  it('does not guess the dataset of counts when none, or several, were asked with the filter', () => {
    expect(aoiCountsOf({ 'earthx:aoi_filter': counts }, {})).toEqual({});
    expect(aoiCountsOf({ 'earthx:aoi_filter': counts }, undefined)).toEqual({});
    const two = { a: { [AOI_CLOUD_PROPERTY]: { lte: 1 } }, b: { [AOI_CLOUD_PROPERTY]: { lte: 1 } } };
    expect(aoiCountsOf({ 'earthx:aoi_filter': counts }, two)).toEqual({});
  });

  it('reads the counts of a mixed search by dataset and skips an entry that is not counts', () => {
    const read = aoiCountsOf({ 'earthx:aoi_filter_by_collection': { optical: counts, radar: { checked: 'many' } } }, {});
    expect(Object.keys(read)).toEqual(['optical']);
    expect(read.optical.found).toBe(12);
  });

  it('answers with nothing for a search without the filter', () => {
    expect(aoiCountsOf({}, undefined)).toEqual({});
    expect(aoiCountsOf({ 'earthx:aoi_filter_by_collection': 'x' }, {})).toEqual({});
  });
});

describe('what a scene says about itself', () => {
  it('reads the share and the pixel counts', () => {
    expect(aoiMeasureOf(measured('a', 30, 100))).toEqual({ percent: 30, cloudPixels: 30, dataPixels: 100, dataPercent: 80 });
  });

  it('has no measure for a scene of a search without the filter', () => {
    expect(aoiMeasureOf(item('a', { 'eo:cloud': 12 }))).toBeNull();
  });

  it('keeps the share when the answer carries no pixel counts, and drops numbers that are not numbers', () => {
    expect(aoiMeasureOf(item('a', { [AOI_CLOUD_PROPERTY]: 7 }))).toEqual({ percent: 7, cloudPixels: null, dataPixels: null, dataPercent: null });
    expect(aoiMeasureOf(item('a', { [AOI_CLOUD_PROPERTY]: '7' }))).toBeNull();
    const odd = item('a', { [AOI_CLOUD_PROPERTY]: 7, 'earthx:aoi_measure': { cloud_pixels: -1, data_pixels: 'x', data_percent: NaN } });
    expect(aoiMeasureOf(odd)).toEqual({ percent: 7, cloudPixels: null, dataPixels: null, dataPercent: null });
  });
});

describe('the share of clouds of a time step', () => {
  it('is the cloud pixels over the valid pixels of its scenes, not the mean of their shares', () => {
    // 100 % of 10 valid pixels and 0 % of 990: the step is 1 % clouds, the mean of the shares would say 50 %.
    expect(groupCloudPercent([measured('a', 10, 10), measured('b', 0, 990)])).toBeCloseTo(1, 10);
  });

  it('leaves out a scene without pixel counts, and has no value when none has them', () => {
    expect(groupCloudPercent([measured('a', 50, 100), item('b', { [AOI_CLOUD_PROPERTY]: 99 })])).toBe(50);
    expect(groupCloudPercent([item('b', { [AOI_CLOUD_PROPERTY]: 99 }), item('c')])).toBeNull();
    expect(groupCloudPercent([])).toBeNull();
  });

  it('has no value when the valid pixels add up to nothing', () => {
    expect(groupCloudPercent([measured('a', 0, 0)])).toBeNull();
  });
});

describe('how a share is written', () => {
  it.each([
    [0, '0 %'],
    [0.04, '<1 %'],
    [0.99, '<1 %'],
    [1, '1 %'],
    [2.5, '3 %'],
    [3.4, '3 %'],
    [99.6, '100 %'],
    [100, '100 %'],
  ])('%s as %s', (percent, text) => {
    expect(cloudText(percent)).toBe(text);
  });
});

describe('the tooltips come from the registry', () => {
  it('names the classes of the registry and that shadows do not count, from the labels of its classes', () => {
    const tip = cloudValueTip(CLASSIFICATION, aoiMeasureOf(measured('a', 3, 100, 3)), 3);
    expect(tip).toContain("Clouds in AOI: 3 % of the AOI's valid pixels (classes 5, 6; cloud shadows do not count).");
  });

  it('says how much of the AOI was measured, only when that is not all of it', () => {
    const part = aoiMeasureOf(measured('a', 3, 100, 3));
    expect(cloudValueTip(CLASSIFICATION, part, 3)).toContain('Measured on 80 % of the AOI.');
    const whole = { ...part!, dataPercent: 100 };
    expect(cloudValueTip(CLASSIFICATION, whole, 3)).not.toContain('Measured on');
    expect(cloudValueTip(CLASSIFICATION, null, 3)).not.toContain('Measured on');
  });

  it('says nothing about shadows when the registry counts them, and names no classes when it names none', () => {
    const counted = { ...CLASSIFICATION, cloud_classes: [5, 6, 7] };
    expect(cloudValueTip(counted, null, 3)).not.toContain('shadow');
    expect(cloudValueTip(null, null, 3)).toBe("Clouds in AOI: 3 % of the AOI's valid pixels.");
    expect(cloudValueTip({ ...CLASSIFICATION, cloud_classes: [] }, null, 3)).not.toContain('classes');
  });

  it('puts the note of the registry into the tooltip of the switch, with the limit and the coverage map', () => {
    const tip = withinAoiTip(CLASSIFICATION);
    expect(tip).toContain('Limit applies to clouds inside the AOI (classes 5, 6; cloud shadows do not count)');
    expect(tip).toContain('checks up to 500 scenes');
    expect(tip).toContain(CLASSIFICATION.cloud_note);
    expect(tip).toContain('The coverage map shows the scene filter only.');
  });

  it('is still a tooltip for a dataset whose collection has no classification', () => {
    expect(withinAoiTip(undefined)).toBe(
      'Limit applies to clouds inside the AOI, measured on each scene. Slower: checks up to 500 scenes. The coverage map shows the scene filter only.',
    );
  });
});

describe('when "Within AOI" is locked', () => {
  const ready = {
    aoi: { type: 'Polygon', coordinates: [] } as GeoJSON.Polygon,
    aoiPoint: null,
    dateFrom: '2026-07-01',
    dateTo: '2026-07-31',
  };

  it('is free with an area and a date range with both ends', () => {
    expect(withinAoiLock(ready)).toBeNull();
  });

  it.each([
    ['no area', { aoi: null }],
    ['no start', { dateFrom: '' }],
    ['no end', { dateTo: '' }],
    ['no dates', { dateFrom: '', dateTo: '' }],
  ])('is locked with %s, and says what to do', (_what, change) => {
    expect(withinAoiLock({ ...ready, ...change })).toBe(LOCK_NEEDS_INPUT);
  });

  it('is locked for a point, which is no area', () => {
    expect(withinAoiLock({ ...ready, aoiPoint: { type: 'Point', coordinates: [1, 2] } })).toBe(LOCK_NEEDS_AREA);
  });

  const ring = (positions: number): GeoJSON.Polygon => ({
    type: 'Polygon',
    coordinates: [Array.from({ length: positions }, (_, i) => [Math.cos(i), Math.sin(i)])],
  });

  it('is free up to the most positions the server measures in, and locked above, with the reason', () => {
    expect(MAX_AOI_POSITIONS).toBe(20_000);
    expect(withinAoiLock({ ...ready, aoi: ring(20_000) })).toBeNull();
    expect(withinAoiLock({ ...ready, aoi: ring(20_001) })).toBe(LOCK_TOO_MANY);
    expect(LOCK_TOO_MANY).toBe('The area has too many points for this filter');
  });

  it('counts the positions of all parts of a MultiPolygon', () => {
    const multi: GeoJSON.MultiPolygon = { type: 'MultiPolygon', coordinates: [ring(12_000).coordinates, ring(12_000).coordinates] };
    expect(withinAoiLock({ ...ready, aoi: multi })).toBe(LOCK_TOO_MANY);
  });

  it('asks for the area and the dates first when a point has no dates either', () => {
    expect(withinAoiLock({ ...ready, aoiPoint: { type: 'Point', coordinates: [1, 2] }, dateTo: '' })).toBe(LOCK_NEEDS_INPUT);
  });
});

describe('what the search asked', () => {
  const query = { queryByCollection: { optical: { [AOI_CLOUD_PROPERTY]: { lte: 20 } }, radar: { 'test:track': { lte: 3 } } } };

  it('is the filter under the dataset, and nowhere else', () => {
    expect(measuresAoi(query, 'optical')).toBe(true);
    expect(measuresAoi(query, 'radar')).toBe(false);
    expect(measuresAoi(query, 'elevation')).toBe(false);
    expect(anyMeasuresAoi(query)).toBe(true);
  });

  it('is nothing for a search without filters, and for no search', () => {
    expect(anyMeasuresAoi({})).toBe(false);
    expect(anyMeasuresAoi(undefined)).toBe(false);
    expect(measuresAoi(undefined, 'optical')).toBe(false);
  });
});

describe('the notes of a section searched with the limit', () => {
  const section = (change: Partial<ResultSection> = {}): ResultSection => ({
    datasetId: 'optical',
    items: [],
    groups: [],
    notes: [NO_SCENES_NOTE],
    groupingError: null,
    origin: 'search',
    incomplete: false,
    ...change,
  });
  const counts = (change: Partial<{ checked: number; found: number; unreadable: number; limitReached: boolean }> = {}) => ({
    checked: 120,
    found: 0,
    unreadable: 0,
    limitReached: false,
    ...change,
  });

  it('says that nothing is within the limit, in place of "no scenes for this area", once the search is done', () => {
    expect(aoiNotes(section(), counts(), false)).toEqual(['No scenes within the AOI limit in this date range']);
  });

  it('says nothing about it while the search still goes on', () => {
    expect(aoiNotes(section(), counts(), true)).toEqual([]);
  });

  it('does not ask for "Load more" while the search goes on by itself, and keeps the note once it stopped', () => {
    const waiting = section({ notes: [LOAD_MORE_NOTE] });
    expect(aoiNotes(waiting, counts(), true)).toEqual([]);
    expect(aoiNotes(waiting, counts(), false)).toEqual([LOAD_MORE_NOTE]);
  });

  it('names the scenes it checked when the limit is reached, and those it could not read', () => {
    const notes = aoiNotes(section(), counts({ checked: 500, limitReached: true, unreadable: 2 }), false);
    expect(notes).toEqual([
      'No scenes within the AOI limit in this date range',
      'Checked 500 scenes. Narrow the date range to search further.',
      '2 scenes could not be checked',
    ]);
  });

  it('says "1 scene" for one', () => {
    expect(aoiNotes(section({ items: [item('a')] }), counts({ unreadable: 1 }), false)).toEqual(['1 scene could not be checked']);
  });

  it('keeps the other notes of the section, and does not claim "nothing within" over an answer that is incomplete', () => {
    const failed = section({ notes: ['Results incomplete: the source timed out.'], incomplete: true });
    expect(aoiNotes(failed, counts(), false)).toEqual(['Results incomplete: the source timed out.']);
    const broken = section({ notes: ['Grouping failed: x'], groupingError: 'x' });
    expect(aoiNotes(broken, counts(), false)).toEqual(['Grouping failed: x']);
  });

  it('adds nothing to a section that has scenes and counts nothing wrong', () => {
    expect(aoiNotes(section({ items: [item('a')], notes: [] }), counts({ found: 1 }), false)).toEqual([]);
  });
});

describe('the order of the time steps', () => {
  const groups = [
    group('c', [measured('1', 50, 100)]),
    group('b', [measured('2', 5, 100)]),
    group('none', [item('3')]),
    group('a', [measured('4', 5, 100)]),
    group('clear', [measured('5', 0, 100)]),
  ];

  it('stays as the search gives it by date', () => {
    expect(sortedGroupIndices(groups, 'date')).toEqual([0, 1, 2, 3, 4]);
  });

  it('puts the least clouds first, a step without a value last, and keeps the order by date between equal values', () => {
    expect(sortedGroupIndices(groups, 'clouds')).toEqual([4, 1, 3, 0, 2]);
  });

  it('does not move the groups themselves', () => {
    const before = groups.map((g) => g.label);
    sortedGroupIndices(groups, 'clouds');
    expect(groups.map((g) => g.label)).toEqual(before);
  });

  it('orders several steps without a value as they came, and no steps as none', () => {
    expect(sortedGroupIndices([group('x', [item('1')]), group('y', [item('2')])], 'clouds')).toEqual([0, 1]);
    expect(sortedGroupIndices([], 'clouds')).toEqual([]);
  });
});
