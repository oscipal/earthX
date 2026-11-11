// DS-04c: the standard picture of a dataset whose items carry one of several band sets (`asset_selection: first_present`,
// Sentinel-1: `vv` or `hh`), and the preview after a search for a dataset whose quicklook the map cannot place.
// Synthetic collections and items only.

import { describe, expect, it } from 'vitest';

import { datasetsFrom, defaultRenderOf, preferredGeoreferencedAsset, quicklookPlan, standardAssetsOf } from './datasets';
import type { Collection, EarthxDefaultRender, StacItem } from './types';

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';

const FIRST_PRESENT: EarthxDefaultRender = {
  title: 'Co-polarisation (VV or HH)',
  assets: ['vv', 'hh'],
  rescale: [
    [90, 250],
    [70, 750],
  ],
  colormap_name: null,
  expression: null,
  resampling: 'nearest',
  asset_selection: 'first_present',
};

function radar(render: EarthxDefaultRender | null = FIRST_PRESENT, extra: Partial<Collection> = {}): Collection {
  return {
    id: 'radar',
    title: 'Radar',
    'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: true },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 7, max_zoom: 19, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'pyramid' as const, overview_resampling: 'average' as const },
    'earthx:default_render': render,
    ...extra,
  } as unknown as Collection;
}

const dataset = (collection = radar()) => datasetsFrom([collection])[0];

// A scene in radar geometry: its bands carry no CRS, its thumbnail a PNG the map cannot place.
function scene(bands: string[], thumbnail = true): StacItem {
  const assets: StacItem['assets'] = Object.fromEntries(bands.map((band) => [band, { href: `https://assets.example.org/${band}.tif`, type: COG }]));
  if (thumbnail) assets.thumbnail = { href: 'https://assets.example.org/quick-look.png', type: 'image/png', roles: ['thumbnail'] };
  return { id: `S_${bands.join('_')}`, bbox: [10, 47, 13, 49], properties: { datetime: '2026-10-18T16:58:48Z' }, assets };
}

describe('defaultRenderOf with first_present', () => {
  it('draws a VV scene with vv and the stretch of vv', () => {
    const render = defaultRenderOf(radar(), scene(['vv', 'vh']));
    expect(render?.assets).toEqual(['vv']);
    expect(render?.rescale).toEqual([[90, 250]]);
  });

  it('draws an HH scene with hh and the stretch of hh, not the first pair of the list', () => {
    const render = defaultRenderOf(radar(), scene(['hh', 'hv']));
    expect(render?.assets).toEqual(['hh']);
    expect(render?.rescale).toEqual([[70, 750]]);
  });

  it('takes the first of the list where a scene carries both', () => {
    expect(defaultRenderOf(radar(), scene(['hh', 'vv']))?.assets).toEqual(['vv']);
  });

  it('has nothing to draw for a scene that carries none of the list', () => {
    expect(defaultRenderOf(radar(), scene(['vh']))).toBeNull();
    expect(defaultRenderOf(radar(), { assets: {} })).toBeNull();
  });

  it('stands for the dataset with the first of the list where no scene is given', () => {
    expect(defaultRenderOf(radar())?.assets).toEqual(['vv']);
    expect(defaultRenderOf(radar())?.rescale).toEqual([[90, 250]]);
  });

  it('keeps no stretch where the registry sets none', () => {
    expect(defaultRenderOf(radar({ ...FIRST_PRESENT, rescale: null }), scene(['hh']))?.rescale).toBeNull();
  });

  it('leaves `all` and a backend without the field as they were: every asset, every pair', () => {
    const all = { ...FIRST_PRESENT, asset_selection: 'all' as const };
    expect(defaultRenderOf(radar(all), scene(['hh']))).toEqual(all);
    const { asset_selection: _, ...older } = FIRST_PRESENT;
    expect(defaultRenderOf(radar(older), scene(['hh']))?.assets).toEqual(['vv', 'hh']);
  });

  it('says nothing for a dataset without a standard picture', () => {
    expect(defaultRenderOf(radar(null), scene(['vv']))).toBeNull();
    expect(standardAssetsOf(radar(null))).toEqual([]);
  });
});

describe('standardAssetsOf (the originals offered)', () => {
  it('offers every asset of the list for first_present, of which a scene has the one it carries', () => {
    expect(standardAssetsOf(radar())).toEqual(['vv', 'hh']);
  });

  it('offers the drawn asset alone otherwise', () => {
    expect(standardAssetsOf(radar({ ...FIRST_PRESENT, assets: ['visual', 'red'], asset_selection: 'all' }))).toEqual(['visual']);
  });
});

describe('preferredGeoreferencedAsset with first_present', () => {
  it('names the asset the scene is drawn with', () => {
    expect(preferredGeoreferencedAsset(dataset(), scene(['hh', 'hv']))).toBe('hh');
    expect(preferredGeoreferencedAsset(dataset())).toBe('vv');
  });
});

describe('quicklookPlan for a dataset whose quicklook the map cannot place', () => {
  it('draws the preview tiles of the band the scene carries instead of a thumbnail that would not show', () => {
    const plan = quicklookPlan(scene(['hh', 'hv']), dataset());
    expect(plan).toEqual({ kind: 'tiles', asset: 'hh', minZoom: 7, maxZoom: 7, render: { expression: undefined, colormapName: undefined, rescale: '70,750' } });
  });

  it('draws them for a VV scene with the stretch of vv', () => {
    const plan = quicklookPlan(scene(['vv', 'vh']), dataset());
    expect(plan?.kind === 'tiles' && [plan.asset, plan.render.rescale]).toEqual(['vv', '90,250']);
  });

  it('has no preview for a scene that carries none of the bands', () => {
    expect(quicklookPlan(scene(['vh']), dataset())).toBeNull();
  });

  it('keeps the thumbnail of a scene the map can place (a CRS and a georeferenced band)', () => {
    const placed = scene(['vv']);
    placed.properties['proj:code'] = 'EPSG:32632';
    placed.assets.vv = { ...placed.assets.vv, 'proj:transform': [10, 0, 600000, 0, -10, 5300000], 'proj:shape': [100, 100] } as never;
    expect(quicklookPlan(placed, dataset())).toEqual({ kind: 'image', href: 'https://assets.example.org/quick-look.png' });
  });

  it('shows nothing for a `quicklook` dataset whose thumbnail cannot be placed, as before', () => {
    const viewer = { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'own' as const, overview_resampling: null };
    expect(quicklookPlan(scene(['vv']), dataset(radar(FIRST_PRESENT, { 'earthx:viewer': viewer } as never)))).toBeNull();
  });
});
