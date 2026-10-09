import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import {
  buildSections,
  combineAnswers,
  firstSectionWithItems,
  hasResultsPanel,
  incompleteNote,
  needsFallback,
  totalItems,
  withSourceState,
} from './sections';
import type { Collection, StacItem } from './types';

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};

function collection(id: string, title: string, overrides: Partial<Collection> = {}): Collection {
  return {
    id,
    title,
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': {
      group_by: ['datetime'],
      min_zoom: 0,
      max_zoom: 14,
      browse: 'quicklook',
      quicklook_nodata_max: null,
      results_group_by: ['datetime'],
    },
    ...overrides,
  };
}

const NO_TIME_AXIS = collection('dem', 'Elevation', {
  extent: { temporal: { interval: [['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z']] } },
  'earthx:capabilities': { ...CAPABILITIES, time_range: false },
  'earthx:viewer': {
    group_by: ['start_datetime'],
    min_zoom: 0,
    max_zoom: 14,
    browse: 'full_resolution',
    quicklook_nodata_max: null,
    results_group_by: ['start_datetime'],
  },
});

const [optical, opticalZarr, dem] = datasetsFrom([
  collection('optical', 'Optical'),
  collection('optical-zarr', 'Optical (Zarr)'),
  NO_TIME_AXIS,
]);
if (!optical.viewable || !opticalZarr.viewable || !dem.viewable) throw new Error('fixtures must be viewable');

function item(id: string, collectionId: string | null | undefined, properties: Record<string, unknown>): StacItem {
  return { id, collection: collectionId, bbox: [0, 0, 1, 1], properties, assets: {} };
}

const NOTHING = { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] };

describe('buildSections', () => {
  it('splits a mixed page into one section per dataset, in the order given', () => {
    const { sections, stray } = buildSections(
      [
        item('d1', 'dem', { start_datetime: '2011-01-01T00:00:00Z' }),
        item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' }),
        item('o2', 'optical', { datetime: '2026-07-25T10:00:00Z' }),
      ],
      [optical, opticalZarr, dem],
      NOTHING,
    );
    expect(sections.map((s) => [s.datasetId, s.items.length])).toEqual([
      ['optical', 2],
      ['optical-zarr', 0],
      ['dem', 1],
    ]);
    expect(stray).toBe(0);
  });

  it("groups each section by its own dataset's results key", () => {
    const { sections } = buildSections(
      [
        item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' }),
        item('o2', 'optical', { datetime: '2026-07-25T10:00:00Z' }),
        item('d1', 'dem', { start_datetime: '2011-01-01T00:00:00Z' }),
        item('d2', 'dem', { start_datetime: '2011-01-01T00:00:00Z' }),
      ],
      [optical, dem],
      NOTHING,
    );
    expect(sections[0].groups).toHaveLength(2);
    expect(sections[1].groups).toHaveLength(1);
    expect(sections[1].groups[0].items).toHaveLength(2);
  });

  it('counts an item of an unsearched dataset, or without a collection, as stray — in no section', () => {
    const { sections, stray } = buildSections(
      [
        item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' }),
        item('x1', 'unknown', { datetime: '2026-07-24T10:00:00Z' }),
        item('x2', null, { datetime: '2026-07-24T10:00:00Z' }),
        item('x3', undefined, { datetime: '2026-07-24T10:00:00Z' }),
      ],
      [optical, dem],
      NOTHING,
    );
    expect(stray).toBe(3);
    expect(totalItems(sections)).toBe(1);
  });

  it('gives every item to the one dataset of a single-dataset search, even without a collection', () => {
    const { sections, stray } = buildSections(
      [item('o1', undefined, { datetime: '2026-07-24T10:00:00Z' })],
      [optical],
      NOTHING,
    );
    expect(stray).toBe(0);
    expect(sections[0].items).toHaveLength(1);
  });

  it('says "No scenes for this area." for an empty section, and only then', () => {
    const { sections } = buildSections([item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' })], [optical, opticalZarr], NOTHING);
    expect(sections[0].notes).toEqual([]);
    expect(sections[1].notes).toEqual(['No scenes for this area.']);
  });

  it('puts the dropped datetime into the head of the section it belongs to, with the acquisition period', () => {
    const { sections } = buildSections(
      [item('d1', 'dem', { start_datetime: '2011-01-01T00:00:00Z' }), item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' })],
      [optical, dem],
      { ignoredFilters: ['datetime'], ignoredFiltersByCollection: { dem: ['datetime'] }, incompleteCollections: [] },
    );
    expect(sections[0].notes).toEqual([]);
    expect(sections[1].notes).toEqual(['No time axis – acquired Dec 2010 to Jan 2015']);
  });

  it('names any other dropped filter as it came', () => {
    const { sections } = buildSections([item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' })], [optical, dem], {
      ignoredFilters: ['ids'],
      ignoredFiltersByCollection: { optical: ['ids'] },
      incompleteCollections: [],
    });
    expect(sections[0].notes).toEqual(['Filter not applied: ids']);
  });

  it('falls back to a plain sentence when the acquisition period cannot be formatted', () => {
    const openInterval = datasetsFrom([
      { ...NO_TIME_AXIS, id: 'open', extent: { temporal: { interval: [[null, null]] } } },
    ])[0];
    if (!openInterval.viewable) throw new Error('fixture');
    const { sections } = buildSections([], [openInterval], {
      ...NOTHING,
      ignoredFiltersByCollection: { open: ['datetime'] },
    });
    expect(sections[0].notes[0]).toBe('No time axis – the date range does not apply.');
  });

  it('with one dataset and no per-collection breakdown, reads the flat list as that dataset\'s', () => {
    const { sections } = buildSections([item('d1', 'dem', { start_datetime: '2011-01-01T00:00:00Z' })], [dem], {
      ...NOTHING,
      ignoredFilters: ['datetime'],
    });
    expect(sections[0].notes).toEqual(['No time axis – acquired Dec 2010 to Jan 2015']);
  });

  it('with several datasets and no breakdown, attributes the flat list to none of them', () => {
    const { sections } = buildSections([], [optical, dem], { ...NOTHING, ignoredFilters: ['datetime'] });
    expect(sections.flatMap((s) => s.notes)).toEqual(['No scenes for this area.', 'No scenes for this area.']);
  });

  it('notes an unreachable source in its section, keeping the scenes it did return', () => {
    const { sections } = buildSections([item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' })], [optical, opticalZarr], {
      ...NOTHING,
      incompleteCollections: [{ collection: 'optical-zarr', reason: 'timeout' }],
    });
    expect(sections[1].notes).toEqual(['Results incomplete: the source timed out.']);
    expect(sections[0].notes).toEqual([]);
  });

  it('a grouping failure empties only that section and carries the reason', () => {
    const { sections } = buildSections(
      [
        item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' }),
        item('d1', 'dem', { other: 1 }), // no start_datetime
      ],
      [optical, dem],
      NOTHING,
    );
    expect(sections[0].items).toHaveLength(1);
    expect(sections[1].items).toEqual([]);
    expect(sections[1].groupingError).toContain('start_datetime');
    expect(sections[1].notes[0]).toContain('Grouping failed');
    expect(sections[0].groupingError).toBeNull();
  });

  it('handles no features and no datasets', () => {
    expect(buildSections([], [], NOTHING)).toEqual({ sections: [], stray: 0 });
  });
});

describe('incompleteNote', () => {
  it.each([
    ['timeout', 'Results incomplete: the source timed out.'],
    ['unreachable', 'Results incomplete: the source was not reachable.'],
    ['upstream_error', 'Results incomplete: the source reported an error.'],
    ['unrecognised_answer', 'Results incomplete: the source sent an unreadable answer.'],
    ['something_new', 'Results incomplete (something_new).'],
  ])('says %s in words', (reason, text) => {
    expect(incompleteNote(reason)).toBe(text);
  });
});

describe('firstSectionWithItems / totalItems', () => {
  it('picks the first section, in list order, that has scenes', () => {
    const { sections } = buildSections([item('d1', 'dem', { start_datetime: '2011-01-01T00:00:00Z' })], [optical, dem], NOTHING);
    expect(firstSectionWithItems(sections)?.datasetId).toBe('dem');
    expect(totalItems(sections)).toBe(1);
  });

  it('is null when no section has scenes', () => {
    const { sections } = buildSections([], [optical, dem], NOTHING);
    expect(firstSectionWithItems(sections)).toBeNull();
    expect(totalItems(sections)).toBe(0);
  });
});

describe('hasResultsPanel', () => {
  it('is on with scenes, and off for no search', () => {
    const { sections } = buildSections([item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' })], [optical], NOTHING);
    expect(hasResultsPanel(sections)).toBe(true);
    expect(hasResultsPanel([])).toBe(false);
  });

  it('is off for a single dataset with nothing found, on for several with nothing found', () => {
    expect(hasResultsPanel(buildSections([], [optical], NOTHING).sections)).toBe(false);
    expect(hasResultsPanel(buildSections([], [optical, dem], NOTHING).sections)).toBe(true);
  });
});

describe('combineAnswers ("Load more", M3-10b)', () => {
  it("keeps the first answer's dropped filters and names every failed source once", () => {
    const first = {
      ignoredFilters: ['datetime'],
      ignoredFiltersByCollection: { dem: ['datetime'] },
      incompleteCollections: [{ collection: 'eopf', reason: 'timeout' }],
    };
    const next = {
      ignoredFilters: ['other'],
      ignoredFiltersByCollection: { dem: ['other'], later: ['datetime'] },
      incompleteCollections: [
        { collection: 'eopf', reason: 'unreachable' },
        { collection: 'optical', reason: 'upstream_error' },
      ],
    };
    expect(combineAnswers(first, next)).toEqual({
      ignoredFilters: ['datetime'],
      ignoredFiltersByCollection: { dem: ['datetime'], later: ['datetime'] },
      incompleteCollections: [
        { collection: 'eopf', reason: 'timeout' },
        { collection: 'optical', reason: 'upstream_error' },
      ],
    });
  });

  it('takes the next answer when the first named nothing', () => {
    const next = { ignoredFilters: ['datetime'], ignoredFiltersByCollection: {}, incompleteCollections: [] };
    expect(combineAnswers(NOTHING, next).ignoredFilters).toEqual(['datetime']);
  });
});

describe('needsFallback (M3-10 F7)', () => {
  const empty = () => buildSections([], [optical, dem], NOTHING).sections;

  it('is due for an empty section of a dataset with a time axis when a date range was searched', () => {
    expect(needsFallback(empty()[0], optical, '2026-07-01', '2026-07-31', false)).toBe(true);
    expect(needsFallback(empty()[0], optical, '', '2026-07-31', false)).toBe(true);
    expect(needsFallback(empty()[0], optical, '2026-07-01', '', false)).toBe(true);
  });

  it('is not due without a date range, nor for a dataset without a time axis', () => {
    expect(needsFallback(empty()[0], optical, '', '', false)).toBe(false);
    expect(needsFallback(empty()[1], dem, '2026-07-01', '2026-07-31', false)).toBe(false);
  });

  it('is not due for a section with scenes, a grouping failure or a source that did not answer in full', () => {
    const [withScenes] = buildSections([item('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' })], [optical], NOTHING).sections;
    const [broken] = buildSections([item('o1', 'optical', {})], [optical], NOTHING).sections;
    const [incomplete] = buildSections([], [optical, dem], {
      ...NOTHING,
      incompleteCollections: [{ collection: 'optical', reason: 'timeout' }],
    }).sections;
    expect(incomplete.incomplete).toBe(true);
    for (const section of [withScenes, broken, incomplete]) {
      expect(needsFallback(section, optical, '2026-07-01', '2026-07-31', false)).toBe(false);
    }
  });

  it('is not due while the source still has pages', () => {
    expect(needsFallback(empty()[0], optical, '2026-07-01', '2026-07-31', true)).toBe(false);
  });

  it('runs once: not again for a section it has run for, nor for one found by name', () => {
    const [section] = empty();
    expect(needsFallback({ ...section, origin: 'fallback' }, optical, '2026-07-01', '2026-07-31', false)).toBe(false);
    expect(needsFallback({ ...section, origin: 'name' }, optical, '2026-07-01', '2026-07-31', false)).toBe(false);
  });
});

describe('withSourceState (M3-10b)', () => {
  const [empty, withScenes] = buildSections(
    [item('d1', 'dem', { start_datetime: '2011-01-01T00:00:00Z' })],
    [optical, dem],
    NOTHING,
  ).sections;

  it('an empty section whose source has pages left says to load more, not that there is nothing', () => {
    expect(withSourceState(empty, true).notes).toEqual(['Load more to see if there are any.']);
    expect(withSourceState(empty, false)).toBe(empty);
  });

  it('leaves a section with scenes, a failed source or a fallback as it is', () => {
    const [incomplete] = buildSections([], [optical], { ...NOTHING, incompleteCollections: [{ collection: 'optical', reason: 'timeout' }] }).sections;
    for (const section of [withScenes, incomplete, { ...empty, origin: 'fallback' as const }]) {
      expect(withSourceState(section, true)).toBe(section);
    }
  });
});
