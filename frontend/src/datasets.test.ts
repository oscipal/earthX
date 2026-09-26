import { describe, expect, it } from 'vitest';

import {
  acquisitionNote,
  browseOf,
  datasetsFrom,
  defaultRenderOf,
  groupByOf,
  maturityNote,
  quicklookAsset,
  quicklookNodataMaxOf,
  quicklookPlan,
  resultsGroupByOf,
  timeAxisOf,
  zoomFloorHint,
  zoomRangeOf,
} from './datasets';
import type { Collection, EarthxCapabilities, EarthxViewer, StacItem } from './types';

function capabilities(overrides: Partial<EarthxCapabilities> = {}): EarthxCapabilities {
  return {
    roi: true,
    time_range: true,
    band_math: true,
    interpolation: true,
    ml_processing: true,
    quad_pol: false,
    single_coverage_product: false,
    ...overrides,
  };
}

function collection(overrides: Partial<Collection> = {}): Collection {
  return {
    id: 'sentinel-2-c1-l2a',
    title: 'Sentinel-2 L2A',
    'earthx:capabilities': capabilities(),
    ...overrides,
  };
}

// A viewer block with the zoom range and the M3-12 fields filled in, so a case
// about grouping does not have to carry numbers it says nothing about (and vice
// versa). `preview_tiles` is the default `browse` because most cases here are
// about the tile-fallback mechanism it drives; a case about `quicklook` or
// `full_resolution` sets it explicitly.
function viewer(overrides: Partial<EarthxViewer> = {}): EarthxViewer {
  return {
    group_by: ['datetime'],
    min_zoom: 0,
    max_zoom: 19,
    browse: 'preview_tiles',
    quicklook_nodata_max: null,
    results_group_by: ['datetime'],
    ...overrides,
  };
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

  it('a viewable dataset carries browse, its freistellung threshold and its results grouping', () => {
    const [option] = datasetsFrom([
      collection({
        'earthx:viewer': viewer({
          browse: 'quicklook',
          quicklook_nodata_max: 16,
          results_group_by: ['datetime', 's2:datatake_id'],
        }),
      }),
    ]);
    expect(option.viewable).toBe(true);
    if (option.viewable) {
      expect(option.browse).toBe('quicklook');
      expect(option.quicklookNodataMax).toBe(16);
      expect(option.resultsGroupBy).toEqual(['datetime', 's2:datatake_id']);
      expect(option.hasTimeAxis).toBe(true);
    }
  });

  it('a dataset without earthx:viewer.browse is not viewable, and says why', () => {
    const [option] = datasetsFrom([
      collection({ 'earthx:viewer': { ...viewer(), browse: undefined as unknown as never } }),
    ]);
    expect(option.viewable).toBe(false);
    if (!option.viewable) expect(option.reason).toMatch(/browse/);
  });

  it('a dataset with an unrecognised browse value is not viewable', () => {
    const [option] = datasetsFrom([
      collection({ 'earthx:viewer': { ...viewer(), browse: 'thumbnail-only' as unknown as never } }),
    ]);
    expect(option.viewable).toBe(false);
    if (!option.viewable) expect(option.reason).toMatch(/browse/);
  });

  it('a dataset without earthx:viewer.results_group_by is not viewable', () => {
    const [option] = datasetsFrom([
      collection({ 'earthx:viewer': { ...viewer(), results_group_by: [] } }),
    ]);
    expect(option.viewable).toBe(false);
    if (!option.viewable) expect(option.reason).toMatch(/results_group_by/);
  });

  it('a dataset without earthx:capabilities.time_range is not viewable', () => {
    const [option] = datasetsFrom([
      collection({ 'earthx:viewer': viewer(), 'earthx:capabilities': undefined }),
    ]);
    expect(option.viewable).toBe(false);
    if (!option.viewable) expect(option.reason).toMatch(/time_range/);
  });

  it('hasTimeAxis carries a false value through — false is not a gap', () => {
    const [option] = datasetsFrom([
      collection({ 'earthx:viewer': viewer(), 'earthx:capabilities': capabilities({ time_range: false }) }),
    ]);
    expect(option.viewable).toBe(true);
    if (option.viewable) expect(option.hasTimeAxis).toBe(false);
  });
});

describe('browseOf', () => {
  it('reads earthx:viewer.browse', () => {
    expect(browseOf(collection({ 'earthx:viewer': viewer({ browse: 'full_resolution' }) }))).toBe(
      'full_resolution',
    );
  });

  it('is null when earthx:viewer is missing', () => {
    expect(browseOf(collection())).toBeNull();
  });

  it('is null for a value the viewer does not recognise', () => {
    expect(
      browseOf(collection({ 'earthx:viewer': { ...viewer(), browse: 'something-else' as unknown as never } })),
    ).toBeNull();
  });
});

describe('resultsGroupByOf', () => {
  it('reads earthx:viewer.results_group_by', () => {
    expect(
      resultsGroupByOf(collection({ 'earthx:viewer': viewer({ results_group_by: ['start_datetime'] }) })),
    ).toEqual(['start_datetime']);
  });

  it('is null when empty or earthx:viewer is missing', () => {
    expect(resultsGroupByOf(collection({ 'earthx:viewer': viewer({ results_group_by: [] }) }))).toBeNull();
    expect(resultsGroupByOf(collection())).toBeNull();
  });
});

describe('quicklookNodataMaxOf', () => {
  it('reads the number the registry sets', () => {
    expect(quicklookNodataMaxOf(collection({ 'earthx:viewer': viewer({ quicklook_nodata_max: 16 }) }))).toBe(16);
  });

  it('is null when the registry sets none', () => {
    expect(quicklookNodataMaxOf(collection({ 'earthx:viewer': viewer({ quicklook_nodata_max: null }) }))).toBeNull();
    expect(quicklookNodataMaxOf(collection())).toBeNull();
  });
});

describe('timeAxisOf', () => {
  it('reads earthx:capabilities.time_range', () => {
    expect(timeAxisOf(collection({ 'earthx:capabilities': capabilities({ time_range: false }) }))).toBe(false);
    expect(timeAxisOf(collection({ 'earthx:capabilities': capabilities({ time_range: true }) }))).toBe(true);
  });

  it('is null — a gap, not "no axis" — when earthx:capabilities is missing', () => {
    expect(timeAxisOf(collection({ 'earthx:capabilities': undefined }))).toBeNull();
  });
});

describe('acquisitionNote', () => {
  const noAxis = (interval: (string | null)[]) =>
    collection({
      'earthx:capabilities': capabilities({ time_range: false }),
      extent: { temporal: { interval: [interval] } },
    });

  it('formats the fixed acquisition period for a dataset without a time axis', () => {
    expect(acquisitionNote(noAxis(['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z']))).toBe(
      'No time axis – acquired Dec 2010 to Jan 2015',
    );
  });

  it('is null for a dataset with a time axis, whatever the extent says', () => {
    const withAxis = collection({
      'earthx:capabilities': capabilities({ time_range: true }),
      extent: { temporal: { interval: [['2020-01-01T00:00:00Z', null]] } },
    });
    expect(acquisitionNote(withAxis)).toBeNull();
  });

  it('is null when the extent is open at either end', () => {
    expect(acquisitionNote(noAxis([null, '2015-01-31T23:59:59Z']))).toBeNull();
    expect(acquisitionNote(noAxis(['2010-12-01T00:00:00Z', null]))).toBeNull();
  });

  it('is null when the extent is missing entirely', () => {
    expect(acquisitionNote(collection({ 'earthx:capabilities': capabilities({ time_range: false }) }))).toBeNull();
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

  it('is null for browse: full_resolution, even with a default visualisation set', () => {
    // The DEM's case (M3-12): no coarse-tile substitute either, because it would
    // be a near-empty world tile clipped to one item (M3-02 F-05) — the viewer
    // shows the AOI crop in full resolution directly instead (`store.ts`).
    const noPreview = collection({
      'earthx:viewer': viewer({ browse: 'full_resolution' }),
      'earthx:default_render': render,
    });
    const scene = item({ data: { href: 'https://example.test/x.tif', roles: ['data'] } });
    expect(quicklookPlan(scene, option(noPreview))).toBeNull();
  });

  it('is null for browse: quicklook when the item carries no quicklook of its own', () => {
    // Sentinel-2 COG's case: no coarse-tile fallback for a dataset the registry
    // says publishes quicklooks — a missing one here is a gap, not a cue to
    // improvise a preview.
    const quicklookDataset = collection({
      'earthx:viewer': viewer({ browse: 'quicklook', quicklook_nodata_max: 16 }),
      'earthx:default_render': render,
    });
    const scene = item({ data: { href: 'https://example.test/x.tif', roles: ['data'] } });
    expect(quicklookPlan(scene, option(quicklookDataset))).toBeNull();
  });
});

describe('zoomFloorHint', () => {
  function option(overrides: Partial<{ min: number; max: number }> = {}) {
    const { min = 8, max = 14 } = overrides;
    return datasetsFrom([
      collection({
        id: 'sentinel-2-l2a-zarr3',
        title: 'Sentinel-2 L2A (Zarr3)',
        'earthx:viewer': viewer({ min_zoom: min, max_zoom: max }),
      }),
    ])[0];
  }

  it('names the level to reach and the dataset it is about', () => {
    const text = zoomFloorHint(option(), 5);
    expect(text).toContain('level 8');
    expect(text).toContain('Sentinel-2 L2A (Zarr3)');
  });

  it('points at the coverage layer as what answers this zoom', () => {
    expect(zoomFloorHint(option(), 5)).toContain('coverage layer');
  });

  it('is null at the floor itself — the floor is released', () => {
    expect(zoomFloorHint(option(), 8)).toBeNull();
  });

  it('is null above the floor', () => {
    expect(zoomFloorHint(option(), 14)).toBeNull();
  });

  it('is null for a dataset released from z0, whatever the zoom', () => {
    expect(zoomFloorHint(option({ min: 0 }), 0)).toBeNull();
  });

  it('is null when no dataset is selected or it is not viewable', () => {
    expect(zoomFloorHint(undefined, 0)).toBeNull();
    expect(zoomFloorHint(datasetsFrom([collection()])[0], 0)).toBeNull();
  });

  it('is null for browse: full_resolution below its own floor (M3-12, Otto 26.09.2026)', () => {
    // No "Zoom in" hint for a dataset whose tiles are already per-item (M3-09) —
    // there is nothing a released range would be hiding several scenes behind.
    const [noPreview] = datasetsFrom([
      collection({ 'earthx:viewer': viewer({ min_zoom: 8, max_zoom: 14, browse: 'full_resolution' }) }),
    ]);
    expect(zoomFloorHint(noPreview, 5)).toBeNull();
  });

  it.each([
    ['not a number', Number.NaN],
    ['infinite', Number.POSITIVE_INFINITY],
    ['negative infinite', Number.NEGATIVE_INFINITY],
  ])('is null for a map zoom that is %s', (_case, zoom) => {
    // NaN compares false against everything, so without a guard a broken reading
    // would become a standing hint rather than no hint.
    expect(zoomFloorHint(option(), zoom)).toBeNull();
  });

  it('a fractional map zoom counts as the level it has not reached yet', () => {
    // MapLibre reports a continuous zoom; 7.9 is still below the z8 the source
    // starts at, and the tiles are still not requested.
    expect(zoomFloorHint(option(), 7.9)).toContain('level 8');
    expect(zoomFloorHint(option(), 8.1)).toBeNull();
  });
});
