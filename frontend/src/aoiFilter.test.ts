// DS-03b: the cloud share in the AOI as the server answers it and the list shows it (`aoiFilter.ts`). Pure functions only;
// the search and the screens that use them have tests of their own.

import { describe, expect, it } from 'vitest';

import {
  anyMeasuresAoi,
  aoiCountsOf,
  aoiNotes,
  countsFrom,
  LOCK_NEEDS_AREA,
  LOCK_NEEDS_INPUT,
  LOCK_TOO_MANY,
  MAX_AOI_POSITIONS,
  measuresAoi,
  withinAoiLock,
  withinAoiTip,
  withinFilters,
} from './aoiFilter';
import { CLASSIFICATION, OPTICAL } from './fixtures/searchFilters';
import { searchFiltersOf } from './searchFilters';
import { LOAD_MORE_NOTE, NO_SCENES_NOTE, type ResultSection } from './sections';
import type { StacItem } from './types';

const item = (id: string, properties: Record<string, unknown> = {}): StacItem => ({ id, properties, assets: {} });
const AOI_CLOUD = 'earthx:aoi_cloud_cover';
const AOI_NODATA = 'earthx:aoi_nodata';

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
    const asked = { optical: { [AOI_CLOUD]: { lte: 20 } }, radar: { 'test:track': { lte: 30 } } };
    expect(aoiCountsOf({ 'earthx:aoi_filter': counts }, asked)).toEqual({
      optical: { checked: 180, found: 12, unreadable: 1, limitReached: false },
    });
  });

  it('does not guess the dataset of counts when none, or several, were asked with the filter', () => {
    expect(aoiCountsOf({ 'earthx:aoi_filter': counts }, {})).toEqual({});
    expect(aoiCountsOf({ 'earthx:aoi_filter': counts }, undefined)).toEqual({});
    const two = { a: { [AOI_CLOUD]: { lte: 1 } }, b: { [AOI_CLOUD]: { lte: 1 } } };
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
  const query = { queryByCollection: { optical: { [AOI_CLOUD]: { lte: 20 } }, radar: { 'test:track': { lte: 3 } } } };

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

describe('the tooltip of the switch comes from the registry', () => {
  const filters = searchFiltersOf(OPTICAL);

  it('names the filters it changes and not the others, with the classes of the registry for the share of clouds', () => {
    const tip = withinAoiTip(filters, CLASSIFICATION);
    expect(tip).toContain(
      'Measure these filters inside the AOI instead of the whole scene: Cloud cover (classes 5, 6; cloud shadows do not count), No data. Others are unchanged.',
    );
    expect(tip).not.toContain('Satellite');
    expect(tip).toContain('Slower: checks up to 500 scenes.');
    expect(tip).toContain(CLASSIFICATION.cloud_note);
    expect(tip).toContain('The coverage map shows the scene filter only.');
  });

  it('says nothing about shadows when the registry counts them, and names no classes when it names none', () => {
    expect(withinAoiTip(filters, { ...CLASSIFICATION, cloud_classes: [5, 6, 7] })).not.toContain('shadow');
    expect(withinAoiTip(filters, null)).toContain('Cloud cover, No data.');
    expect(withinAoiTip(filters, { ...CLASSIFICATION, cloud_classes: [] })).not.toContain('classes');
  });

  it('names only what the registry marks', () => {
    expect(withinFilters(filters).map((f) => f.withinAoi)).toEqual([AOI_CLOUD, AOI_NODATA]);
    expect(withinFilters(filters.filter((f) => f.withinAoi === null))).toEqual([]);
  });
});

describe('what a search asked, by any platform property', () => {
  it('counts the share of no data in the AOI as well as the share of clouds', () => {
    const query = { queryByCollection: { optical: { [AOI_NODATA]: { lte: 5 } }, radar: { 'test:track': { lte: 3 } } } };
    expect(measuresAoi(query, 'optical')).toBe(true);
    expect(measuresAoi(query, 'radar')).toBe(false);
    expect(anyMeasuresAoi(query)).toBe(true);
  });
});
