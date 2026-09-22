import { describe, expect, it } from 'vitest';

import {
  datasetsFrom,
  defaultRenderOf,
  groupByOf,
  maturityNote,
  quicklookAsset,
  quicklookPlan,
  zoomRangeOf,
} from './datasets';
import type { Collection, EarthxViewer, StacItem } from './types';

function collection(overrides: Partial<Collection> = {}): Collection {
  return { id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', ...overrides };
}

// A viewer block with the zoom range filled in, so a case about grouping does
// not have to carry two numbers it says nothing about (and vice versa).
function viewer(overrides: Partial<EarthxViewer> = {}): EarthxViewer {
  return { group_by: ['datetime'], min_zoom: 0, max_zoom: 19, ...overrides };
}

describe('groupByOf', () => {
  it('reads earthx:viewer.group_by', () => {
    expect(groupByOf(collection({ 'earthx:viewer': viewer({ group_by: ['datetime', 'grid:code'] }) }))).toEqual([
      'datetime',
      'grid:code',
    ]);
  });

  it('is null when earthx:viewer is missing', () => {
    expect(groupByOf(collection())).toBeNull();
  });

  it('is null when group_by is empty', () => {
    expect(groupByOf(collection({ 'earthx:viewer': viewer({ group_by: [] }) }))).toBeNull();
  });
});

describe('datasetsFrom', () => {
  it('a dataset without earthx:viewer.group_by is not viewable, and says why', () => {
    const [option] = datasetsFrom([collection()]);
    expect(option.viewable).toBe(false);
    if (!option.viewable) expect(option.reason).toMatch(/group_by/);
  });

  it('the other datasets in the list stay selectable', () => {
    const good = collection({ id: 'sentinel-2-c1-l2a', 'earthx:viewer': viewer() });
    const bad = collection({ id: 'broken-dataset' });
    const options = datasetsFrom([good, bad]);
    expect(options.find((o) => o.id === 'sentinel-2-c1-l2a')?.viewable).toBe(true);
    expect(options.find((o) => o.id === 'broken-dataset')?.viewable).toBe(false);
  });

  it('a dataset without a usable zoom range is not viewable, and says which field', () => {
    const [option] = datasetsFrom([
      collection({ 'earthx:viewer': { group_by: ['datetime'] } as EarthxViewer }),
    ]);
    expect(option.viewable).toBe(false);
    if (!option.viewable) expect(option.reason).toMatch(/min_zoom/);
  });

  it('a viewable dataset carries its zoom range', () => {
    const [option] = datasetsFrom([
      collection({ 'earthx:viewer': viewer({ min_zoom: 8, max_zoom: 14 }) }),
    ]);
    expect(option.viewable).toBe(true);
    if (option.viewable) expect(option.zoom).toEqual({ min: 8, max: 14 });
  });

  it('a viewable dataset carries its group_by', () => {
    const [option] = datasetsFrom([
      collection({ 'earthx:viewer': viewer({ group_by: ['datetime', 'grid:code'] }) }),
    ]);
    expect(option.viewable).toBe(true);
    if (option.viewable) expect(option.groupBy).toEqual(['datetime', 'grid:code']);
  });
});

describe('defaultRenderOf', () => {
  it('reads earthx:default_render', () => {
    const render = {
      title: 'True colour (TCI)',
      assets: ['visual'],
      rescale: [[0, 255]] as [number, number][],
      colormap_name: null,
      expression: null,
      resampling: 'nearest',
    };
    expect(defaultRenderOf(collection({ 'earthx:default_render': render }))).toEqual(render);
  });

  it('is null when the registry has not set one yet', () => {
    expect(defaultRenderOf(collection())).toBeNull();
  });
});

function item(assets: StacItem['assets']): StacItem {
  return { id: 'an-item', properties: {}, assets };
}

describe('quicklookAsset', () => {
  it('picks the thumbnail role first', () => {
    const it_ = item({
      overview: { href: 'https://example.test/overview.jpg', roles: ['overview'] },
      thumbnail: { href: 'https://example.test/thumb.jpg', roles: ['thumbnail'] },
    });
    expect(quicklookAsset(it_)?.href).toBe('https://example.test/thumb.jpg');
  });

  it('falls back to overview when there is no thumbnail role', () => {
    const it_ = item({
      overview: { href: 'https://example.test/overview.jpg', roles: ['overview'] },
      data: { href: 'https://example.test/data.tif', roles: ['data'] },
    });
    expect(quicklookAsset(it_)?.href).toBe('https://example.test/overview.jpg');
  });

  it('falls back to the first image/* asset', () => {
    const it_ = item({
      data: { href: 'https://example.test/data.tif', type: 'image/tiff; application=geotiff' },
      other: { href: 'https://example.test/other.json', type: 'application/json' },
    });
    expect(quicklookAsset(it_)?.href).toBe('https://example.test/data.tif');
  });

  it('is null when nothing matches', () => {
    const it_ = item({ other: { href: 'https://example.test/other.json', type: 'application/json' } });
    expect(quicklookAsset(it_)).toBeNull();
  });
});

describe('zoomRangeOf', () => {
  it('reads the released levels of earthx:viewer', () => {
    expect(zoomRangeOf(collection({ 'earthx:viewer': viewer({ min_zoom: 8, max_zoom: 14 }) }))).toEqual({
      min: 8,
      max: 14,
    });
  });

  it('the ceiling itself is allowed', () => {
    expect(zoomRangeOf(collection({ 'earthx:viewer': viewer({ min_zoom: 0, max_zoom: 22 }) }))).toEqual({
      min: 0,
      max: 22,
    });
  });

  it('a single released level is a range of its own', () => {
    // What the browse preview uses: read one level, overzoom everything above it.
    expect(zoomRangeOf(collection({ 'earthx:viewer': viewer({ min_zoom: 8, max_zoom: 8 }) }))).toEqual({
      min: 8,
      max: 8,
    });
  });

  it('is null when the dataset names no viewer block at all', () => {
    expect(zoomRangeOf(collection())).toBeNull();
  });

  it.each([
    ['the fields are missing', {}],
    ['min is above max', { min_zoom: 14, max_zoom: 8 }],
    ['a level is negative', { min_zoom: -1, max_zoom: 14 }],
    ['a level is fractional', { min_zoom: 8.5, max_zoom: 14 }],
    ['a level is not a number', { min_zoom: 'eight' }],
    ['a level is null', { min_zoom: null }],
    // The registry's own ceiling (catalog.registry.MAX_TILE_ZOOM = 22), mirrored
    // so a range the backend would refuse is not treated as viewable here — and
    // so `addSource` never gets a maxzoom past MapLibre's own limit of 24.
    ['a level is past the registry ceiling', { max_zoom: 23 }],
  ])('is null when %s — no guessed range', (_case, broken) => {
    const block = { group_by: ['datetime'], ...broken } as unknown as EarthxViewer;
    expect(zoomRangeOf(collection({ 'earthx:viewer': block }))).toBeNull();
  });
});

describe('maturityNote', () => {
  it('warns for a staging source (D23: visible in the viewer, not only in the registry)', () => {
    expect(maturityNote(collection({ 'earthx:maturity': 'staging' }))).toMatch(/without notice/);
  });

  it('warns for an experimental source', () => {
    expect(maturityNote(collection({ 'earthx:maturity': 'experimental' }))).toMatch(/no stability/);
  });

  it('says nothing for a settled source', () => {
    expect(maturityNote(collection({ 'earthx:maturity': 'stable' }))).toBeNull();
  });

  it('says nothing when the field is absent or empty', () => {
    expect(maturityNote(collection())).toBeNull();
    expect(maturityNote(collection({ 'earthx:maturity': '' }))).toBeNull();
    expect(maturityNote(collection({ 'earthx:maturity': null }))).toBeNull();
  });

  it('passes an unknown value through rather than swallowing it', () => {
    expect(maturityNote(collection({ 'earthx:maturity': 'deprecated' }))).toBe('deprecated');
  });
});

describe('quicklookPlan', () => {
  const render = {
    title: 'True colour',
    assets: ['SR_10m:b04,b03,b02'],
    rescale: [[0, 0.3]] as [number, number][],
    colormap_name: null,
    expression: null,
    resampling: 'nearest',
  };
  const zarrLike = collection({
    id: 'sentinel-2-l2a-zarr3',
    'earthx:viewer': viewer({ min_zoom: 8, max_zoom: 14 }),
    'earthx:default_render': render,
  });

  function option(from: Collection) {
    return datasetsFrom([from])[0];
  }

  it('uses the published quicklook where the item carries one', () => {
    const scene = item({ thumbnail: { href: 'https://example.test/thumb.jpg', roles: ['thumbnail'] } });
    expect(quicklookPlan(scene, option(zarrLike))).toEqual({
      kind: 'image',
      href: 'https://example.test/thumb.jpg',
    });
  });

  it('falls back to tiles on the coarsest released level where the source publishes none', () => {
    // adr/0007 §12.7: this source has no thumbnail, overview, preview or visual
    // asset anywhere, so the substitute comes from the tile path (§12.4).
    const scene = item({ SR_10m: { href: 'https://data.test/x.zarr/r10m', roles: ['data'] } });
    expect(quicklookPlan(scene, option(zarrLike))).toEqual({
      kind: 'tiles',
      asset: 'SR_10m:b04,b03,b02',
      zoom: 8,
      // The registry's stretch travels with it: a preview rendered without it
      // does not look like the full-resolution view of the same scene.
      render: { rescale: '0,0.3', colormapName: undefined, expression: undefined },
    });
  });

  it('is null when the source publishes neither a quicklook nor a standard visualisation', () => {
    const bare = collection({ 'earthx:viewer': viewer() });
    const scene = item({ data: { href: 'https://example.test/x.tif', roles: ['data'] } });
    expect(quicklookPlan(scene, option(bare))).toBeNull();
  });

  it('is null for a dataset that is not viewable at all', () => {
    const scene = item({ data: { href: 'https://example.test/x.tif', roles: ['data'] } });
    expect(quicklookPlan(scene, option(collection()))).toBeNull();
  });

  it('a default visualisation with no asset gives nothing to render', () => {
    const empty = collection({
      'earthx:viewer': viewer(),
      'earthx:default_render': { ...render, assets: [] },
    });
    const scene = item({ data: { href: 'https://example.test/x.tif', roles: ['data'] } });
    expect(quicklookPlan(scene, option(empty))).toBeNull();
  });
});
