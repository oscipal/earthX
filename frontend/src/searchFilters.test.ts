import { describe, expect, it } from 'vitest';

import { CLOUD_FILTER, ELEVATION, LEGACY, OPTICAL, ORBIT_FILTER, RADAR, SATELLITE_FILTER } from './fixtures/searchFilters';
import {
  filterError,
  filterQuery,
  groupsOf,
  hasFilterError,
  isEmptyQuery,
  isSet,
  searchFiltersOf,
  setFilters,
  type FilterInput,
} from './searchFilters';
import type { Collection } from './types';

const [cloud, , satellite] = searchFiltersOf(OPTICAL);
const [orbit] = searchFiltersOf(RADAR);
const range = (from: string, to: string): FilterInput => ({ kind: 'range', from, to });
const values = (...ticked: string[]): FilterInput => ({ kind: 'values', values: ticked });
const withFilters = (filters: unknown): Collection => ({ id: 'x', 'earthx:search_filters': filters as unknown[] });

describe('searchFiltersOf: what the registry offers', () => {
  it('reads a range and a choice in the order of the registry, each with its group', () => {
    expect(searchFiltersOf(OPTICAL).map((f) => [f.group, f.property, f.kind])).toEqual([
      ['Clouds', 'test:cloud', 'range'],
      ['Scene', 'test:nodata', 'range'],
      ['Acquisition', 'platform', 'values'],
    ]);
    expect(cloud).toEqual({
      property: 'test:cloud',
      kind: 'range',
      title: 'Cloud cover',
      group: 'Clouds',
      description: 'Share of the scene covered by clouds.',
      unit: '%',
      withinAoi: 'earthx:aoi_cloud_cover',
      minimum: 0,
      maximum: 100,
      integer: false,
      values: [],
    });
    expect(satellite).toEqual({
      property: 'platform',
      kind: 'values',
      title: 'Satellite',
      group: 'Acquisition',
      description: 'The satellite that took the scene.',
      unit: null,
      withinAoi: null,
      minimum: 0,
      maximum: 0,
      integer: false,
      values: [
        { value: 'sat-a', label: 'Satellite A' },
        { value: 'sat-b', label: 'Satellite B' },
      ],
    });
  });

  it('knows whole numbers from the type of the queryable', () => {
    expect(orbit).toMatchObject({ integer: true, minimum: 1, maximum: 175, unit: null });
  });

  it('gives a dataset without filters, and a collection of an older backend, none', () => {
    expect(searchFiltersOf(ELEVATION)).toEqual([]);
    expect(searchFiltersOf(LEGACY)).toEqual([]);
    expect(searchFiltersOf(withFilters('cloud'))).toEqual([]);
    expect(searchFiltersOf(withFilters(null))).toEqual([]);
  });

  it.each([
    ['no property', { ...CLOUD_FILTER, property: '' }],
    ['no title', { ...CLOUD_FILTER, title: '' }],
    ['no group', { ...CLOUD_FILTER, group: undefined }],
    ['an empty group', { ...CLOUD_FILTER, group: '' }],
    ['a group that is no text', { ...CLOUD_FILTER, group: 3 }],
    ['no tooltip', { ...CLOUD_FILTER, description: undefined }],
    ['a unit that is no text', { ...CLOUD_FILTER, unit: 5 }],
    ['an unknown kind', { ...CLOUD_FILTER, kind: 'slider' }],
    ['a bound that is no number', { ...CLOUD_FILTER, maximum: '100' }],
    ['a bound that is not finite', { ...CLOUD_FILTER, maximum: Infinity }],
    ['a missing bound', { ...CLOUD_FILTER, minimum: undefined }],
    ['a range that is empty', { ...CLOUD_FILTER, minimum: 100, maximum: 100 }],
    ['a range that runs backwards', { ...CLOUD_FILTER, minimum: 100, maximum: 0 }],
    ['a choice without a list', { ...SATELLITE_FILTER, oneOf: undefined }],
    ['a choice of one value', { ...SATELLITE_FILTER, oneOf: [{ const: 'sat-a', title: 'A' }] }],
    ['a value without a label', { ...SATELLITE_FILTER, oneOf: [{ const: 'sat-a', title: 'A' }, { const: 'sat-b' }] }],
    ['a value twice', { ...SATELLITE_FILTER, oneOf: [{ const: 'a', title: 'A' }, { const: 'a', title: 'B' }] }],
    ['an entry that is no object', 'test:cloud'],
    ['an entry that is null', null],
  ])('leaves out an entry with %s instead of guessing', (_name, entry) => {
    // Next to a good one, which stays.
    expect(searchFiltersOf(withFilters([entry, ORBIT_FILTER])).map((f) => f.property)).toEqual(['test:track']);
  });

  it('keeps the first of two entries for one property', () => {
    const second = { ...CLOUD_FILTER, title: 'Clouds again' };
    expect(searchFiltersOf(withFilters([CLOUD_FILTER, second])).map((f) => f.title)).toEqual(['Cloud cover']);
  });
});

describe('groupsOf: the headings of the pop-up', () => {
  it('keeps the order of the registry and puts each filter under its heading', () => {
    expect(groupsOf(searchFiltersOf(OPTICAL)).map((g) => [g.name, g.filters.map((f) => f.title)])).toEqual([
      ['Clouds', ['Cloud cover']],
      ['Scene', ['No data']],
      ['Acquisition', ['Satellite']],
    ]);
  });

  it('gathers the filters of a group, and has none for no filters', () => {
    const more = { ...CLOUD_FILTER, property: 'test:cirrus', title: 'Thin cirrus' };
    expect(groupsOf(searchFiltersOf(withFilters([CLOUD_FILTER, more, SATELLITE_FILTER]))).map((g) => g.filters.length)).toEqual([2, 1]);
    expect(groupsOf([])).toEqual([]);
  });
});

describe('isSet and setFilters', () => {
  it('a filter is set once a field has something in it', () => {
    expect(isSet(undefined)).toBe(false);
    expect(isSet(range(' ', ''))).toBe(false);
    expect(isSet(range('', '20'))).toBe(true);
    expect(isSet(range('5', ''))).toBe(true);
    expect(isSet(values())).toBe(false);
    expect(isSet(values('sat-a'))).toBe(true);
  });

  it('lists the filters with something in them, wrong or not', () => {
    const filters = [cloud, satellite];
    expect(setFilters(filters, undefined)).toEqual([]);
    expect(setFilters(filters, { 'test:cloud': range('abc', '') })).toEqual([cloud]);
    expect(setFilters(filters, { platform: values('sat-b') })).toEqual([satellite]);
  });
});

describe('filterError: what is wrong with the fields', () => {
  it('has nothing to say about empty fields, one bound, or both bounds in order', () => {
    expect(filterError(cloud, undefined)).toBeNull();
    expect(filterError(cloud, range('', ''))).toBeNull();
    expect(filterError(cloud, range('', '20'))).toBeNull();
    expect(filterError(cloud, range('5', ''))).toBeNull();
    expect(filterError(cloud, range('0', '100'))).toBeNull();
    expect(filterError(cloud, range('20', '20'))).toBeNull();
    expect(filterError(cloud, range(' 12.5 ', '5e1'))).toBeNull();
  });

  it('marks the field that is no number', () => {
    for (const text of ['abc', '1,5', '--3', 'NaN', 'Infinity', '0x10', '1e999', '.', '5 5']) {
      expect(filterError(cloud, range(text, '')), text).toEqual({ field: 'from', message: 'Enter a number' });
      expect(filterError(cloud, range('', text)), text).toEqual({ field: 'to', message: 'Enter a number' });
    }
  });

  it('marks a bound outside the range, and names the range', () => {
    expect(filterError(cloud, range('-1', ''))).toEqual({ field: 'from', message: 'Between 0 and 100' });
    expect(filterError(cloud, range('', '100.5'))).toEqual({ field: 'to', message: 'Between 0 and 100' });
    expect(filterError(orbit, range('0', ''))).toEqual({ field: 'from', message: 'Between 1 and 175' });
  });

  it('marks a fraction where only whole numbers are asked for', () => {
    expect(filterError(orbit, range('2.5', ''))).toEqual({ field: 'from', message: 'Whole numbers only' });
    expect(filterError(orbit, range('', '7.0'))).toBeNull();
    expect(filterError(cloud, range('2.5', ''))).toBeNull();
  });

  it('marks both fields when the start is above the end', () => {
    expect(filterError(cloud, range('50', '20'))).toEqual({ field: 'both', message: 'From is above to' });
  });

  it('reports the wrong field first, then the order', () => {
    expect(filterError(cloud, range('200', '20'))?.field).toBe('from');
    expect(filterError(cloud, range('50', '300'))?.field).toBe('to');
  });

  it('has nothing to say about a choice, whatever is ticked', () => {
    expect(filterError(satellite, values('sat-a', 'not-offered'))).toBeNull();
    expect(hasFilterError([cloud, satellite], { 'test:cloud': range('', '20'), platform: values('sat-a') })).toBe(false);
    expect(hasFilterError([cloud, satellite], { 'test:cloud': range('', 'x') })).toBe(true);
  });
});

describe('filterQuery: the query extension for the fields', () => {
  it('is empty when nothing is set', () => {
    expect(filterQuery([cloud, satellite], undefined)).toEqual({});
    expect(filterQuery([cloud, satellite], { 'test:cloud': range('', ''), platform: values() })).toEqual({});
    expect(isEmptyQuery(filterQuery([cloud], undefined))).toBe(true);
  });

  it('sends gte and lte for the bounds that are set, as numbers', () => {
    expect(filterQuery([cloud], { 'test:cloud': range('5', '20') })).toEqual({ 'test:cloud': { gte: 5, lte: 20 } });
    expect(filterQuery([cloud], { 'test:cloud': range('', '20') })).toEqual({ 'test:cloud': { lte: 20 } });
    expect(filterQuery([cloud], { 'test:cloud': range(' 7.5', '') })).toEqual({ 'test:cloud': { gte: 7.5 } });
    expect(filterQuery([cloud], { 'test:cloud': range('0', '100') })).toEqual({ 'test:cloud': { gte: 0, lte: 100 } });
  });

  it('sends the ticked values in the order of the registry', () => {
    expect(filterQuery([satellite], { platform: values('sat-b', 'sat-a') })).toEqual({ platform: { in: ['sat-a', 'sat-b'] } });
    expect(filterQuery([satellite], { platform: values('sat-b') })).toEqual({ platform: { in: ['sat-b'] } });
  });

  it('leaves out a filter with a wrong field, and keeps the others', () => {
    const inputs = { 'test:cloud': range('50', '20'), platform: values('sat-a') };
    expect(filterQuery([cloud, satellite], inputs)).toEqual({ platform: { in: ['sat-a'] } });
  });

  it('sends nothing for a property the dataset does not offer, nor a value it does not know', () => {
    expect(filterQuery([cloud], { 'test:track': range('1', '5') })).toEqual({});
    expect(filterQuery([satellite], { platform: values('not-offered') })).toEqual({});
    expect(filterQuery([satellite], { platform: values('sat-a', 'not-offered') })).toEqual({ platform: { in: ['sat-a'] } });
  });

  it('sends nothing when the fields belong to the other kind of filter', () => {
    expect(filterQuery([cloud], { 'test:cloud': values('sat-a') })).toEqual({});
    expect(filterQuery([satellite], { platform: range('1', '2') })).toEqual({});
  });
});

// DS-03b (Otto, 31.10.2026): the registry names, for each filter that depends on the area, the property the server measures it
// under inside the AOI (`within_aoi`); "Filter within AOI only" moves those ranges there and nothing else.
describe('within_aoi: the filters that depend on the area', () => {
  const [cloudFilter, nodata] = searchFiltersOf(OPTICAL);

  it('reads the property of the registry, and null where a filter has none', () => {
    expect(cloudFilter.withinAoi).toBe('earthx:aoi_cloud_cover');
    expect(nodata.withinAoi).toBe('earthx:aoi_nodata');
    expect(satellite.withinAoi).toBeNull();
    expect(orbit.withinAoi).toBeNull();
  });

  it.each([
    ['a flag of the first version', true],
    ['false', false],
    ['text that is no platform property', 'eo:cloud_cover'],
    ['the bare namespace', 'earthx:'],
    ['a number', 3],
  ])('takes %s for no property rather than send the server a name it does not know', (_what, value) => {
    const [filter] = searchFiltersOf(withFilters([{ ...CLOUD_FILTER, within_aoi: value }]));
    expect(filter.withinAoi).toBeNull();
  });

  const inputs = { 'test:cloud': range('', '20'), 'test:nodata': range('5', ''), platform: values('sat-a') };
  const filters = searchFiltersOf(OPTICAL);

  it('keeps every range under the property of the scene while the switch is not looked at', () => {
    expect(filterQuery(filters, inputs)).toEqual({ 'test:cloud': { lte: 20 }, 'test:nodata': { gte: 5 }, platform: { in: ['sat-a'] } });
  });

  it('moves every filter that depends on the area to its own property, and nothing else, with "aoi"', () => {
    expect(filterQuery(filters, inputs, 'aoi')).toEqual({
      'earthx:aoi_cloud_cover': { lte: 20 },
      'earthx:aoi_nodata': { gte: 5 },
      platform: { in: ['sat-a'] },
    });
  });

  it('leaves them out and nothing else, with "skip" (the coverage map)', () => {
    expect(filterQuery(filters, inputs, 'skip')).toEqual({ platform: { in: ['sat-a'] } });
  });

  it('does not send a range that is wrong, under either name', () => {
    expect(filterQuery(filters, { 'test:cloud': range('', '500') }, 'aoi')).toEqual({});
  });
});
