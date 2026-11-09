// @vitest-environment jsdom
//
// DS-04c: a dataset whose scenes carry one of several band sets (`asset_selection: first_present`, Sentinel-1: `vv`/`vh`
// or `hh`/`hv`). The view draws each scene with the band it carries, and "Originals" offers that band. Synthetic only.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { useAppStore } from './store';
import type { Collection, StacItem, TimeStepGroup } from './types';

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const HOST = 'assets.example.org';

const RADAR = {
  id: 'radar',
  title: 'Radar',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 7, max_zoom: 19, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  'earthx:default_render': {
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
  },
  'earthx:source': { asset_hosts: [HOST] },
} as unknown as Collection;

const scene = (id: string, day: string, bands: string[]): StacItem => ({
  id,
  collection: 'radar',
  bbox: [10, 47, 13, 49],
  properties: { datetime: `${day}T16:58:00Z` },
  assets: Object.fromEntries(bands.map((band) => [band, { href: `https://${HOST}/${id}/${band}.tif`, type: COG }])),
});

const VV = scene('VV_SCENE', '2026-10-18', ['vv', 'vh']);
const HH = scene('HH_SCENE', '2026-10-19', ['hh', 'hv']);
const NEITHER = scene('VH_ONLY', '2026-10-20', ['vh']);
const ITEMS = [VV, HH, NEITHER];
const GROUPS = ITEMS.map((item) => ({ key: [item.properties.datetime as string], label: item.id, items: [item] }) as unknown as TimeStepGroup);

const state = () => useAppStore.getState();

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  useAppStore.setState({
    datasets: datasetsFrom([RADAR]), selectedDatasetIds: ['radar'], datasetId: 'radar', openSectionId: 'radar',
    items: ITEMS, groups: GROUPS, sections: [{ datasetId: 'radar', items: ITEMS, groups: GROUPS }] as never,
    activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: [], focusMode: false, cropToAoi: false, viewAoi: null, downloaded: {}, appliedRender: {},
    savedLooks: {}, viewLooks: {}, shownImage: null, mosaics: {}, layers: [], viewLayerId: null, resultViewLayerId: null, aoi: null, error: null, notice: null,
    pinLoading: false, resultsOnMap: true, downloadOriginalLinks: null,
  });
});
afterEach(() => vi.unstubAllGlobals());

describe('the view of a first_present dataset', () => {
  it('draws each scene with the band it carries', async () => {
    useAppStore.setState({ selectedIds: ['VV_SCENE', 'HH_SCENE'] });
    await state().enterFocus(false);
    expect(state().downloaded.VV_SCENE.asset).toBe('vv');
    expect(state().downloaded.HH_SCENE.asset).toBe('hh');
    expect(state().downloaded.HH_SCENE.tileUrl).toContain('asset=hh');
  });

  it('starts an HH scene with the stretch of hh', async () => {
    useAppStore.setState({ selectedIds: ['HH_SCENE'] });
    await state().enterFocus(false);
    expect(state().appliedRender.rescale).toBe('70,750');
  });

  it('leaves out a scene that carries none of the bands and says why', async () => {
    // The stretch is measured, so that its own notice does not stand in the place of this one.
    const statistics = { vv: { min: 0, max: 900, percentile_2: 80, percentile_98: 260, count: 9 } };
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(statistics), { status: 200 })));
    useAppStore.setState({ selectedIds: ['VV_SCENE', 'VH_ONLY'] });
    await state().enterFocus(false);
    expect(Object.keys(state().downloaded)).toEqual(['VV_SCENE']);
    expect(state().notice).toBe('Scene VH_ONLY carries none of the assets Radar is drawn from.');
  });

  it('opens no view when no scene carries one of the bands', async () => {
    useAppStore.setState({ selectedIds: ['VH_ONLY'] });
    await state().enterFocus(false);
    expect(state().focusMode).toBe(false);
    expect(state().error).toBe('Scene VH_ONLY carries none of the assets Radar is drawn from.');
  });
});

describe('"Originals" of a first_present dataset', () => {
  it('offers the band each scene carries, and none it lacks', () => {
    useAppStore.setState({ selectedIds: ['VV_SCENE', 'HH_SCENE', 'VH_ONLY'] });
    state().openDownloadForSelection('originals');
    expect(state().downloadOriginalLinks?.map((link) => [link.itemId, link.asset])).toEqual([
      ['VV_SCENE', 'vv'],
      ['HH_SCENE', 'hh'],
    ]);
  });
});
