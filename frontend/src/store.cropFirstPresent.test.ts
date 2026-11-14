// @vitest-environment jsdom
//
// DS-04c (Otto, 10.11.2026): a crop where the dialog has no table of bands reads the band each scene of a `first_present`
// dataset carries (Sentinel-1: `vv` or `hh`), not the first of the list; scenes of two bands make no crop and the dialog
// says why before anything is sent. Synthetic collection and scenes only.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { cropAssetsOf, downloadRequestFor, downloadRequestForSelection, mixedBandsNote } from './download';
import { bboxToPolygon } from './geoUtils';
import { useAppStore } from './store';
import type { Collection, StacItem, TimeStepGroup } from './types';

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.5, 47.5, 11.5, 48.5]);

const RADAR = {
  id: 'radar',
  title: 'Radar',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 7, max_zoom: 19, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'pyramid' as const, overview_resampling: 'average' as const, overview_substitute: null },
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
  'earthx:license_flags': { tier: 'processing', distribution: true, derivatives: true },
} as unknown as Collection;

const scene = (id: string, day: string, bands: string[]): StacItem => ({
  id,
  collection: 'radar',
  bbox: [10, 47, 12, 49],
  properties: { datetime: `${day}T16:58:00Z` },
  assets: Object.fromEntries(bands.map((band) => [band, { href: `https://assets.example.org/${id}/${band}.tif`, type: COG }])),
});

const VV = scene('VV_SCENE', '2026-10-18', ['vv', 'vh']);
const HH = scene('HH_SCENE', '2026-10-19', ['hh', 'hv']);
const HH2 = scene('HH_SCENE_2', '2026-10-19', ['hh', 'hv']);
const ITEMS = [VV, HH, HH2];
const GROUPS: TimeStepGroup[] = [
  { key: ['2026-10-18'], label: '18 Oct', items: [VV] } as unknown as TimeStepGroup,
  { key: ['2026-10-19'], label: '19 Oct', items: [HH, HH2] } as unknown as TimeStepGroup,
];
const DATASET = datasetsFrom([RADAR])[0];

const state = () => useAppStore.getState();
let downloads: Record<string, unknown>[] = [];

beforeEach(() => {
  downloads = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      // No table of bands: the scenes list none, the case this is about.
      if (url.endsWith('/bands')) return new Response(JSON.stringify({ bands: [] }), { status: 200 });
      if (url.endsWith('/download')) {
        downloads.push(JSON.parse(String(init?.body)));
        return new Response(new Blob(['zip']), { status: 200, headers: { 'X-Total-Groups': '1', 'X-Skipped-Groups': '0' } });
      }
      return new Response('{}', { status: 404 });
    }),
  );
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  useAppStore.setState({
    datasets: datasetsFrom([RADAR]), selectedDatasetIds: ['radar'], datasetId: 'radar', openSectionId: 'radar',
    items: ITEMS, groups: GROUPS, sections: [{ datasetId: 'radar', items: ITEMS, groups: GROUPS }] as never,
    activeGroupIndex: 1, expandedGroupIndex: 1, selectedIds: [], focusMode: false, downloaded: {}, layers: [], aoi: AOI,
    downloadDialogLayerId: null, downloadSelection: false, downloadOutcome: null, downloading: false, error: null, notice: null,
  });
});

afterEach(() => {
  state().closeDownloadDialog();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const bandsLoaded = () => vi.waitFor(() => expect(state().downloadBandsLoading).toBe(false));

describe('cropAssetsOf and mixedBandsNote', () => {
  it('reads the band the scenes carry, in the order of the list', () => {
    expect(cropAssetsOf(DATASET, [HH, HH2])).toEqual(['hh']);
    expect(cropAssetsOf(DATASET, [VV])).toEqual(['vv']);
    expect(cropAssetsOf(DATASET, [HH, VV])).toEqual(['vv', 'hh']);
  });

  it('falls back to the first of the list without scenes, and has none for scenes that carry none', () => {
    expect(cropAssetsOf(DATASET)).toEqual(['vv']);
    expect(cropAssetsOf(DATASET, [])).toEqual(['vv']);
    expect(cropAssetsOf(DATASET, [scene('VH_ONLY', '2026-10-20', ['vh'])])).toEqual([]);
  });

  it('keeps the standard asset of a dataset that draws all its assets', () => {
    const optical = datasetsFrom([{ ...RADAR, 'earthx:default_render': { ...RADAR['earthx:default_render']!, assets: ['visual'], rescale: null, asset_selection: 'all' } } as Collection])[0];
    expect(cropAssetsOf(optical, [scene('S2', '2026-10-18', ['visual', 'red'])])).toEqual(['visual']);
    expect(mixedBandsNote(optical, ['visual', 'red'])).toBeNull();
  });

  it('refuses two bands of a first_present dataset, and nothing else', () => {
    expect(mixedBandsNote(DATASET, ['vv', 'hh'])).toBe('These scenes carry different bands (vv, hh): crop the scenes of one band at a time.');
    expect(mixedBandsNote(DATASET, ['hh'])).toBeNull();
    expect(mixedBandsNote(undefined, ['vv', 'hh'])).toBeNull();
  });

  it('takes only the scenes of the groups asked for', () => {
    expect(downloadRequestForSelection(DATASET, [['HH_SCENE']], AOI, ITEMS)?.assets).toEqual(['hh']);
    expect(downloadRequestForSelection(DATASET, [['HH_SCENE']], AOI)?.assets).toEqual(['vv']);
    expect(downloadRequestForSelection(DATASET, [['HH_SCENE']], null, ITEMS)).toBeNull();
  });
});

describe('"Download crop" of a first_present dataset without a table of bands', () => {
  it('asks for hh for an HH pass', async () => {
    useAppStore.setState({ selectedIds: ['HH_SCENE', 'HH_SCENE_2'] });
    state().openDownloadForSelection('crop');
    await bandsLoaded();
    await state().confirmDownload();
    expect(downloads).toHaveLength(1);
    expect(downloads[0].assets).toEqual(['hh']);
  });

  it('asks for vv for a VV pass', async () => {
    useAppStore.setState({ selectedIds: ['VV_SCENE'], activeGroupIndex: 0 });
    state().openDownloadForSelection('crop');
    await bandsLoaded();
    await state().confirmDownload();
    expect(downloads[0].assets).toEqual(['vv']);
  });

  it('sends nothing for a VV and an HH pass together and says why', async () => {
    useAppStore.setState({ selectedIds: ['VV_SCENE', 'HH_SCENE'] });
    state().openDownloadForSelection('crop');
    await bandsLoaded();
    await state().confirmDownload();
    expect(downloads).toHaveLength(0);
    expect(state().error).toBe('These scenes carry different bands (vv, hh): crop the scenes of one band at a time.');
  });

  it('keeps the band of an HH pass in a layer pinned from the results, and crops it with hh', async () => {
    useAppStore.setState({ selectedIds: ['HH_SCENE', 'HH_SCENE_2'] });
    state().addCurrentToLayers();
    const [layer] = state().layers;
    expect(layer.restore.assets).toEqual(['hh']);
    expect(downloadRequestFor(layer, state().datasets)?.assets).toEqual(['hh']);
    // A layer pinned before DS-04c keeps no bands and crops as it did.
    const { assets: _, ...older } = layer.restore;
    expect(downloadRequestFor({ ...layer, restore: older }, state().datasets)?.assets).toEqual(['vv']);
  });
});
