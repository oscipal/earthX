// The Data catalogue's model (UI-05 §4): groups, first visit, saved ids, and the rows of the details, including what a
// collection gets wrong or leaves out. Synthetic collections only.

import { describe, expect, it } from 'vitest';

import {
  accountOf,
  catalogueGroups,
  catalogueRows,
  firstVisitDatasets,
  knownDatasets,
  notAddableReason,
  prototypeNote,
  resolutionText,
  sourceRow,
  spatialExtentText,
  temporalExtentText,
} from './catalogue';
import { datasetsFrom } from './datasets';
import type { Collection } from './types';

const VIEWER = { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'preview_tiles' as const, quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'own' as const, overview_resampling: null, overview_substitute: null };
const CAPABILITIES = { roi: true, time_range: true, band_math: true, interpolation: false, quad_pol: false, single_coverage_product: false, ml_processing: false };

function collection(id: string, category: string | null, extra: Partial<Collection> = {}): Collection {
  return { id, title: id, 'earthx:category': category, 'earthx:viewer': VIEWER, 'earthx:capabilities': CAPABILITIES, ...extra } as Collection;
}

const rowsOf = (c: Collection) => Object.fromEntries(catalogueRows(datasetsFrom([c])[0]).map((row) => [row.label, row]));
const textOf = (c: Collection, label: string) => rowsOf(c)[label].values.map((v) => v.text).join(' | ');

describe('catalogueGroups', () => {
  it('keeps the order of the field, sorts by title in a group and leaves out empty groups', () => {
    const datasets = datasetsFrom([collection('z-dem', 'elevation'), collection('b', 'optical'), collection('a', 'optical'), collection('wx', 'weather_climate')]);
    expect(catalogueGroups(datasets).map((g) => [g.title, g.datasets.map((d) => d.id)])).toEqual([
      ['Optical', ['a', 'b']],
      ['Elevation', ['z-dem']],
      ['Weather and climate', ['wx']],
    ]);
  });

  it.each([null, undefined, '', 'Optical', 'satellite', 3])('puts a category of %j into "Other", last', (category) => {
    const datasets = datasetsFrom([collection('odd', category as never), collection('a', 'radar')]);
    expect(catalogueGroups(datasets).map((g) => g.title)).toEqual(['Radar', 'Other']);
  });

  it('is empty without datasets', () => {
    expect(catalogueGroups([])).toEqual([]);
  });
});

describe('firstVisitDatasets (F3)', () => {
  it('takes every dataset that can be added while there are at most six', () => {
    const datasets = datasetsFrom([collection('dem', 'elevation'), collection('s2', 'optical')]);
    expect(firstVisitDatasets(datasets)).toEqual(['s2', 'dem']);
  });

  it('takes the first six in the order of the groups where there are more', () => {
    const many = Array.from({ length: 9 }, (_, i) => collection(`e${i}`, i < 4 ? 'elevation' : 'optical'));
    expect(firstVisitDatasets(datasetsFrom(many))).toEqual(['e4', 'e5', 'e6', 'e7', 'e8', 'e0']);
  });

  it('leaves out what cannot be shown and what needs an account', () => {
    const datasets = datasetsFrom([
      collection('broken', 'optical', { 'earthx:viewer': null }),
      collection('closed', 'optical', { 'earthx:access': { cors: null, account: 'requester_pays' } }),
      collection('open', 'optical'),
    ]);
    expect(firstVisitDatasets(datasets)).toEqual(['open']);
  });
});

describe('knownDatasets', () => {
  const datasets = datasetsFrom([collection('a', 'optical'), collection('b', 'radar'), collection('broken', 'optical', { 'earthx:viewer': null })]);

  it('keeps the saved order and drops unknown, retired and doubled ids', () => {
    expect(knownDatasets(['b', 'sentinel-2-l2a-zarr3', 'nope', 'a', 'b'], datasets)).toEqual(['b', 'a']);
  });

  it('drops a dataset that can no longer be shown', () => {
    expect(knownDatasets(['broken', 'a'], datasets)).toEqual(['a']);
  });

  it('keeps an empty list empty: the user removed everything on purpose', () => {
    expect(knownDatasets([], datasets)).toEqual([]);
  });
});

describe('marks', () => {
  it.each([
    [undefined, null],
    ['none', null],
    ['', null],
    ['free_account', 'free_account'],
    ['requester_pays', 'requester_pays'],
  ])('reads an account of %j as %j', (account, expected) => {
    expect(accountOf(collection('x', 'optical', { 'earthx:access': { cors: null, account } }))).toBe(expected);
  });

  it('marks a prototype only at "unclear", with its note or a plain one', () => {
    expect(prototypeNote(collection('x', 'optical', { 'earthx:legal_status': 'cleared', 'earthx:legal_note': 'n' }))).toBeNull();
    expect(prototypeNote(collection('x', 'optical'))).toBeNull();
    expect(prototypeNote(collection('x', 'optical', { 'earthx:legal_status': 'unclear', 'earthx:legal_note': 'No terms published' }))).toBe('No terms published');
    expect(prototypeNote(collection('x', 'optical', { 'earthx:legal_status': 'unclear' }))).toBe('The legal status of this source is not cleared');
  });

  it('says why a dataset cannot be added', () => {
    const [closed, broken, open] = datasetsFrom([
      collection('closed', 'optical', { 'earthx:access': { cors: null, account: 'free_account' } }),
      collection('broken', 'optical', { 'earthx:viewer': null }),
      collection('open', 'optical'),
    ]);
    expect(notAddableReason(closed)).toBe('This source needs an account: open it at the source');
    expect(notAddableReason(broken)).toMatch(/^Not viewable: earthx:viewer\.group_by/u);
    expect(notAddableReason(open)).toBeNull();
  });
});

describe('the rows', () => {
  it('link only https', () => {
    const c = collection('x', 'optical', {
      providers: [
        { name: 'Safe', roles: ['producer'], url: 'https://safe.example.org' },
        { name: 'Plain', roles: ['host'], url: 'http://plain.example.org' },
        { name: 'Script', roles: ['host'], url: 'javascript:alert(1)' },
        { name: 'None' },
      ],
    });
    expect(rowsOf(c).Provider.values).toEqual([
      { text: 'Safe · producer', href: 'https://safe.example.org' },
      { text: 'Plain · host', href: null },
      { text: 'Script · host', href: null },
      { text: 'None', href: null },
    ]);
  });

  it('show "—" for providers that are not a list, and leave out one without a name', () => {
    expect(textOf(collection('x', 'optical', { providers: 'ESA' as never }), 'Provider')).toBe('—');
    expect(textOf(collection('x', 'optical', { providers: [{ name: '' }, null as never] }), 'Provider')).toBe('—');
  });

  it('name the source by host and collection, linked to the endpoint, never a link that is not https', () => {
    const source = { asset_hosts: [], endpoint: 'https://stac.example.org/v1', source_collection_id: 'col' };
    expect(sourceRow(collection('x', 'optical', { 'earthx:source': source }))).toEqual([{ text: 'stac.example.org · col', href: 'https://stac.example.org/v1' }]);
    expect(sourceRow(collection('x', 'optical', { 'earthx:source': { ...source, endpoint: 'http://stac.example.org' } }))).toEqual([{ text: '—', href: null }]);
    expect(sourceRow(collection('x', 'optical'))).toEqual([{ text: '—', href: null }]);
    for (const endpoint of ['https://ex ample.org', 'https://host:99999']) {
      expect(sourceRow(collection('x', 'optical', { 'earthx:source': { ...source, endpoint } }))).toEqual([{ text: '—', href: null }]);
    }
  });

  it('write the extent in degrees with their sides, "—" for a box that is not one', () => {
    expect(spatialExtentText(collection('x', 'optical', { extent: { spatial: { bbox: [[5.9, 45.8, 10.5, 47.8]] } } }))).toBe('5.9° E – 10.5° E · 45.8° N – 47.8° N');
    expect(spatialExtentText(collection('x', 'optical', { extent: { spatial: { bbox: [[0, 0, 1]] } } }))).toBe('—');
    expect(spatialExtentText(collection('x', 'optical', { extent: { spatial: { bbox: [[0, 'a', 1, 2]] as never } } }))).toBe('—');
    expect(spatialExtentText(collection('x', 'optical'))).toBe('—');
  });

  it('write the period as UTC days, an open end as today, "No time axis" in front where the dataset has none', () => {
    const period = (interval: (string | null)[], timeRange = true) =>
      temporalExtentText(collection('x', 'optical', { extent: { temporal: { interval: [interval] } }, 'earthx:capabilities': { ...CAPABILITIES, time_range: timeRange } }));
    expect(period(['2015-06-27T10:25:31Z', null])).toBe('2015-06-27 – today');
    expect(period(['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z'], false)).toBe('No time axis · 2010-12-01 – 2015-01-31');
    expect(period(['not a date', 'neither'])).toBe('—');
    expect(period([null, '2020-01-01T00:00:00Z'])).toBe('— – 2020-01-01');
    expect(temporalExtentText(collection('x', 'optical'))).toBe('—');
  });

  it('write the resolution in metres, ignoring what is no distance', () => {
    expect(resolutionText(collection('x', 'optical', { summaries: { gsd: [10, 20, 60] } }))).toBe('10, 20, 60 m');
    expect(resolutionText(collection('x', 'optical', { summaries: { gsd: [0, -5, Number.NaN, '10' as never, 30] } }))).toBe('30 m');
    expect(resolutionText(collection('x', 'optical', { summaries: { gsd: [] } }))).toBe('—');
    expect(resolutionText(collection('x', 'optical'))).toBe('—');
  });

  it('list the bands with their unit, without the auxiliary assets and the mask, which has a row of its own', () => {
    const c = collection('x', 'optical', {
      'earthx:band_units': { red: '1', vv: 'dB', visual: null, scl: null, height: null },
      'earthx:auxiliary_assets': ['visual'],
      'earthx:mask': { asset: 'scl', band: 'scl', classes: [], suggested: [], reference: 'https://example.org', note: '' },
    });
    expect(textOf(c, 'Bands')).toBe('red, vv · dB, height');
    expect(textOf(c, 'Mask')).toBe('scl');
  });

  it('write the attribution with "[year]" for the placeholder, and the tier of the licence', () => {
    const c = collection('x', 'optical', {
      'earthx:license_flags': {
        spdx_id: 'CC-BY-4.0', name: 'CC BY 4.0', url: 'https://creativecommons.org/licenses/by/4.0/', commercial_use: true,
        distribution: true, derivatives: true, share_alike: false, attribution_required: true, tier: 'display',
        attribution_modified: 'Contains modified data {year}', attribution_unmodified: 'Data {year}', terms_url: null, terms_notice: null,
      },
    });
    expect(textOf(c, 'License')).toBe('CC BY 4.0 | Display');
    expect(textOf(c, 'Attribution')).toBe('Data [year] | Contains modified data [year]');
  });

  it('show "—" for what the collection does not carry, and "Last checked" always "—" until the health checks come', () => {
    const rows = rowsOf(collection('x', 'optical'));
    for (const label of ['Provider', 'Source', 'License', 'Attribution', 'Resolution', 'Data region', 'Citation', 'Last checked']) {
      expect(rows[label].values.map((v) => v.text), label).toEqual(['—']);
    }
    expect(rows['Last checked'].tip).toBe('Not checked yet');
  });

  it('link the DOI and add the citation', () => {
    const c = collection('x', 'optical', { 'sci:doi': '10.5281/zenodo.1', 'sci:citation': 'Someone (2021)' });
    expect(rowsOf(c).DOI.values).toEqual([
      { text: '10.5281/zenodo.1', href: 'https://doi.org/10.5281/zenodo.1' },
      { text: 'Someone (2021)', href: null },
    ]);
    expect(rowsOf(c).Citation).toBeUndefined();
  });

  it('name the row "Citation", not "DOI", where the dataset has no DOI (Otto, 10.11.2026)', () => {
    const rows = rowsOf(collection('x', 'radar', { 'sci:doi': null, 'sci:citation': 'Copernicus Sentinel-1 Level-1 GRD' }));
    expect(rows.DOI).toBeUndefined();
    expect(rows.Citation.values).toEqual([{ text: 'Copernicus Sentinel-1 Level-1 GRD', href: null }]);
    expect(rowsOf(collection('x', 'radar', { 'sci:doi': '' })).DOI).toBeUndefined();
  });

  it('list the limitations of a dataset after its description, one sentence each, and no row where it has none', () => {
    const limitations = ['Placed only by the ground control points of each scene.', 'Values are uncalibrated digital numbers (DN).'];
    const rows = catalogueRows(datasetsFrom([collection('x', 'radar', { 'earthx:limitations': limitations })])[0]);
    expect(rows.map((row) => row.label).slice(0, 2)).toEqual(['Description', 'Limitations']);
    expect(rows[1].values).toEqual(limitations.map((text) => ({ text, href: null })));
    for (const none of [undefined, null, [], ['', 3]]) {
      expect(rowsOf(collection('x', 'radar', { 'earthx:limitations': none as never })).Limitations, String(none)).toBeUndefined();
    }
  });

  it('name the operators the capabilities switch on, and the quick processing a true-colour dataset offers', () => {
    const c = collection('x', 'optical', {
      'earthx:capabilities': { ...CAPABILITIES, band_math: true, masking: true, normalization: false } as never,
      'earthx:true_color': ['red', 'green', 'blue'],
    });
    expect(textOf(c, 'Processing')).toBe('Band math, Mask by class');
    expect(textOf(c, 'Quick processing')).toBe('Enhance contrast');
    expect(textOf(collection('y', 'elevation', { 'earthx:capabilities': { ...CAPABILITIES, band_math: false } }), 'Quick processing')).toBe('—');
  });

  it('put the note of a maturity other than stable behind the (i)', () => {
    expect(rowsOf(collection('x', 'optical', { 'earthx:maturity': 'staging' })).Maturity).toEqual({
      label: 'Maturity',
      values: [{ text: 'staging', href: null }],
      tip: 'staging: the provider may withdraw this collection without notice',
    });
    expect(textOf(collection('x', 'optical', { 'earthx:maturity': 'stable' }), 'Maturity')).toBe('stable');
    expect(textOf(collection('x', 'optical'), 'Maturity')).toBe('—');
  });
});
