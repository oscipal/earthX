// NM4-53: the images of the view — one time step of one dataset each.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import type { Collection, DownloadedInfo, StacItem, TimeStepGroup } from './types';
import { datasetIdsOf, imagesOf, imagesOfDataset, platformLabel, satellitesOf, satelliteShort, sectionsForView, type ViewSection } from './viewImages';

const S2: Collection = {
  id: 's2',
  title: 'Sentinel-2 L2A',
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 19, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: null, colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:search_filters': [
    {
      property: 'platform',
      kind: 'values',
      title: 'Satellite',
      group: 'Acquisition',
      description: 'The satellite.',
      oneOf: [
        { const: 'sentinel-2a', title: 'Sentinel-2A' },
        { const: 'sentinel-2b', title: 'Sentinel-2B' },
      ],
    },
  ],
};
const DEM: Collection = { ...S2, id: 'dem', title: 'Copernicus DEM', 'earthx:search_filters': [] };
const datasets = datasetsFrom([S2, DEM]);

const scene = (id: string, datetime: string | null, platform?: string): StacItem => ({
  id,
  bbox: [0, 0, 1, 1],
  properties: { ...(datetime ? { datetime } : {}), ...(platform ? { platform } : {}) },
  assets: {},
});
const info = (datasetId: string): DownloadedInfo => ({ datasetId, tileUrl: 't', bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 0, maxZoom: 19 });
const group = (label: string, items: StacItem[]): TimeStepGroup => ({ key: [label], label, items });

const a1 = scene('A1', '2025-08-03T10:00:00Z', 'sentinel-2b');
const a2 = scene('A2', '2025-08-03T10:00:05Z', 'sentinel-2b');
const b1 = scene('B1', '2025-07-29T10:00:00Z', 'sentinel-2a');
const d1 = scene('D1', null);
const sections: ViewSection[] = [
  { datasetId: 's2', items: [a1, a2, b1], groups: [group('2025-08-03', [a1, a2]), group('2025-07-29', [b1])] },
  { datasetId: 'dem', items: [d1], groups: [group('dem', [d1])] },
];

describe('imagesOf', () => {
  it('makes one image per group and dataset, the earliest day first, datasets in the order of the sections', () => {
    const downloaded = { A1: info('s2'), A2: info('s2'), B1: info('s2'), D1: info('dem') };
    const images = imagesOf(downloaded, sections, datasets);
    expect(images.map((i) => [i.datasetId, i.date, i.ids])).toEqual([
      ['s2', '2025-07-29', ['B1']],
      ['s2', '2025-08-03', ['A1', 'A2']],
      ['dem', null, ['D1']],
    ]);
    expect(datasetIdsOf(images)).toEqual(['s2', 'dem']);
    expect(imagesOfDataset(images, 'dem')).toHaveLength(1);
  });

  it('names the satellites in the words of the registry, short, and leaves them out where a scene names none', () => {
    const images = imagesOf({ A1: info('s2'), B1: info('s2'), D1: info('dem') }, sections, datasets);
    expect(images.map(satellitesOf)).toEqual(['S2A', 'S2B', '']);
    expect(images[0].platforms).toEqual(['Sentinel-2A']);
  });

  it('shows both satellites when the scenes of one step name two', () => {
    const x = scene('X', '2025-08-03T10:00:00Z', 'sentinel-2a');
    const g = group('2025-08-03', [a1, x]);
    const images = imagesOf({ A1: info('s2'), X: info('s2') }, [{ datasetId: 's2', items: [a1, x], groups: [g] }], datasets);
    expect(satellitesOf(images[0])).toBe('S2B/S2A');
  });

  it('keeps the scenes no group holds as one image of their dataset', () => {
    const images = imagesOf({ Z1: info('s2'), Z2: info('s2') }, [], datasets);
    expect(images).toHaveLength(1);
    expect(images[0].ids).toEqual(['Z1', 'Z2']);
  });

  it('keeps the order of the groups for a product without a day', () => {
    const e1 = scene('E1', null);
    const e2 = scene('E2', null);
    const sec: ViewSection = { datasetId: 'dem', items: [e1, e2], groups: [group('first', [e1]), group('second', [e2])] };
    expect(imagesOf({ E2: info('dem'), E1: info('dem') }, [sec], datasets).map((i) => i.groupLabel)).toEqual(['first', 'second']);
  });

  it('is empty for an empty view', () => {
    expect(imagesOf({}, sections, datasets)).toEqual([]);
  });

  it('gives a key that tells two groups of one dataset and two datasets apart', () => {
    const images = imagesOf({ A1: info('s2'), B1: info('s2'), D1: info('dem') }, sections, datasets);
    expect(new Set(images.map((i) => i.key)).size).toBe(3);
  });
});

describe('satelliteShort and platformLabel', () => {
  it('shortens the naming of the Copernicus missions and leaves other labels alone', () => {
    expect(satelliteShort('Sentinel-2A')).toBe('S2A');
    expect(satelliteShort('Sentinel-1C')).toBe('S1C');
    expect(satelliteShort('Landsat 9')).toBe('Landsat 9');
    expect(satelliteShort('')).toBe('');
  });

  it('falls back to the value for a platform the registry does not name, and for an unknown dataset', () => {
    expect(platformLabel(datasets[0], 'sentinel-2z')).toBe('sentinel-2z');
    expect(platformLabel(undefined, 'sentinel-2a')).toBe('sentinel-2a');
  });
});

describe('sectionsForView', () => {
  it('puts the list\'s scenes in the place of the open section', () => {
    const open = [b1];
    const out = sectionsForView({ sections, openSectionId: 's2', datasetId: 's2', items: open, groups: [group('g', open)] });
    expect(out.map((x) => x.datasetId)).toEqual(['s2', 'dem']);
    expect(out[0].items).toBe(open);
  });

  it('adds a section for the open dataset where the search has none, and takes none without an open dataset', () => {
    expect(sectionsForView({ sections: [], openSectionId: null, datasetId: 's2', items: [a1], groups: [] }).map((x) => x.datasetId)).toEqual(['s2']);
    expect(sectionsForView({ sections, openSectionId: null, datasetId: null, items: [], groups: [] })).toEqual(sections);
  });
});
