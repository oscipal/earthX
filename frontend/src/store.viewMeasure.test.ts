// @vitest-environment jsdom
//
// "auto-scale" and "Enhance contrast" of the view measure the area of the crop (UI-03e), in the values the tiles draw; without a crop, or
// where the tiler does not take the area, the first whole scene as before.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { SENTINEL_2_PRESETS } from './fixtures/indexPresets';
import { useAppStore, viewMeasure } from './store';
import type { Collection, DownloadedInfo, StacItem } from './types';
import { forgetAreaAnswers, SCENE_MEASURE_NOTICE } from './viewMeasure';

const TIFF = 'image/tiff; application=geotiff; profile=cloud-optimized';
const collection = {
  id: 's2',
  title: 's2',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:true_color': ['red', 'green', 'blue'],
  'earthx:index_presets': SENTINEL_2_PRESETS,
} as unknown as Collection;

const bands = (count: number, extra: Record<string, unknown> = {}) => Array.from({ length: count }, () => ({ data_type: 'uint8', nodata: 0, ...extra }));
const scene = (id: string): StacItem => ({
  id,
  collection: 's2',
  bbox: [10, 47, 11, 48],
  properties: { datetime: '2026-07-01T10:00:00Z' },
  assets: {
    visual: { href: 'x', type: TIFF, 'raster:bands': bands(3) },
    red: { href: 'x', type: TIFF, 'raster:bands': bands(1, { data_type: 'uint16', scale: 0.0001, offset: -0.1 }) },
  } as StacItem['assets'],
});
const info: DownloadedInfo = {
  datasetId: 's2',
  tileUrl: '/collections/s2/items/a1/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual',
  bounds: [10, 47, 11, 48],
  asset: 'visual',
  minZoom: 8,
  maxZoom: 14,
};
const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };

const state = () => useAppStore.getState();
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const band = (name: string, minimum: number, maximum: number, low: number, high: number) => ({
  name,
  unit: null,
  statistics: { minimum, maximum, count: 10, percentile_2: low, percentile_98: high, histogram: [[1, 2], [minimum, (minimum + maximum) / 2, maximum]] },
});

function openView(crop: boolean) {
  const items = [scene('a1')];
  useAppStore.setState({
    datasets: datasetsFrom([collection]),
    datasetId: 's2',
    sections: [],
    openSectionId: null,
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    selectedIds: ['a1'],
    downloaded: { a1: info },
    focusMode: true,
    cropToAoi: crop,
    viewAoi: crop ? AOI : null,
    shownImage: null,
    viewLooks: {},
    savedLooks: {},
    appliedRender: { rescale: '0,255' },
    pendingBand: '',
    pendingIndex: '',
    pendingUnit: 'value',
    pendingVmin: '0',
    pendingVmax: '255',
    pendingChannels: [],
    layers: [],
    mosaics: {},
    mapZoom: 12,
    error: null,
    notice: null,
    enhance: null,
  });
}

let fetchMock: ReturnType<typeof vi.fn>;
const answer = (...replies: (() => Response)[]) => {
  fetchMock = vi.fn(async () => (replies.shift() ?? (() => json({})))());
  vi.stubGlobal('fetch', fetchMock);
};
const calls = () => fetchMock.mock.calls.map((call) => ({ url: String((call as unknown[])[0]), init: (call as unknown[])[1] as RequestInit | undefined }));

beforeEach(() => {
  forgetAreaAnswers();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('what the view is measured with', () => {
  it('is one object for one state, so that a component can select it', () => {
    openView(true);
    expect(viewMeasure(state())).toBe(viewMeasure(state()));
    useAppStore.setState({ pendingBand: 'red' });
    expect(viewMeasure(state())?.area?.order.output).toMatchObject({ bands: ['red'] });
  });

  it('asks the area of the crop only', () => {
    openView(false);
    expect(viewMeasure(state())?.area).toBeNull();
    openView(true);
    expect(viewMeasure(state())?.area?.order.aoi).toEqual(AOI);
  });

  it('is none before a scene is open', () => {
    openView(true);
    useAppStore.setState({ downloaded: {}, items: [], groups: [] });
    expect(viewMeasure(state())).toBeNull();
  });
});

describe('"auto-scale" over the area', () => {
  it('measures the colour picture in the order of the item, the AOI in the body', async () => {
    openView(true);
    answer(() => json({ exact: true, factor: 1, bands: [band('visual_1', 3, 250, 10, 200), band('visual_2', 4, 240, 20, 190), band('visual_3', 5, 230, 30, 180)] }));
    await state().autoStretch();
    expect(calls().map((c) => c.url)).toEqual(['/collections/s2/statistics']);
    expect(JSON.parse(String(calls()[0].init?.body)).output.bands).toEqual(['visual_1', 'visual_2', 'visual_3']);
    expect([state().pendingVmin, state().pendingVmax]).toEqual(['10', '200']);
    expect(state().notice).toBeNull();
  });

  it('turns the range of a band back into the raw numbers the tile draws', async () => {
    openView(true);
    useAppStore.setState({ pendingBand: 'red' });
    answer(() => json({ exact: true, factor: 1, bands: [band('red', 0.1, 0.4, 0.12, 0.31)] }));
    await state().autoStretch();
    expect(Number(state().pendingVmin)).toBeCloseTo(2200, 3);
    expect(Number(state().pendingVmax)).toBeCloseTo(4100, 3);
  });

  it('measures an index as it is, the step in the order', async () => {
    openView(true);
    state().chooseViewIndex('NDVI');
    answer(() => json({ exact: true, factor: 1, bands: [band('NDVI', -0.2, 0.9, -0.1, 0.8)] }));
    await state().autoStretch();
    expect(JSON.parse(String(calls()[0].init?.body)).steps[0]).toMatchObject({ op: 'band_math', op_version: 2 });
    expect([state().pendingVmin, state().pendingVmax]).toEqual(['-0.1', '0.8']);
  });

  it('falls back to the first whole scene where the tiler does not take the area, and says so', async () => {
    openView(true);
    answer(() => json({ detail: 'a measure opens at most 16 files' }, 413), () => json({ '1': { min: 0, max: 255, percentile_2: 7, percentile_98: 211, count: 5 } }));
    await state().autoStretch();
    expect(calls().map((c) => new URL(c.url, 'http://x').pathname)).toEqual(['/collections/s2/statistics', '/collections/s2/items/a1/statistics']);
    expect([state().pendingVmin, state().pendingVmax]).toEqual(['7', '211']);
    expect(state().notice).toBe(SCENE_MEASURE_NOTICE);
  });

  it('says what went wrong, and changes nothing, on another failure', async () => {
    openView(true);
    answer(() => json({ detail: 'down' }, 503));
    await state().autoStretch();
    expect(state().notice).toMatch(/^Could not measure a stretch automatically/u);
    expect([state().pendingVmin, state().pendingVmax]).toEqual(['0', '255']);
  });

  it('asks the first scene where the view is not cropped', async () => {
    openView(false);
    answer(() => json({ '1': { min: 0, max: 255, percentile_2: 7, percentile_98: 211, count: 5 } }));
    await state().autoStretch();
    expect(calls().map((c) => c.init?.method ?? 'GET')).toEqual(['GET']);
    expect([state().pendingVmin, state().pendingVmax]).toEqual(['7', '211']);
  });
});

describe('"Enhance contrast" over the area', () => {
  it('takes each channel at the percentiles of its own values, in the values of the area', async () => {
    openView(true);
    answer(() => json({ exact: true, factor: 1, bands: [band('visual_1', 3, 250, 10, 200), band('visual_2', 4, 240, 20, 190), band('visual_3', 5, 230, 30, 180)] }));
    await state().enhanceContrast();
    expect(state().pendingChannels).toEqual([
      { vmin: '10', vmax: '200' },
      { vmin: '20', vmax: '190' },
      { vmin: '30', vmax: '180' },
    ]);
    expect(state().appliedRender.rescale).toBe('10,200;20,190;30,180');
    expect(calls()).toHaveLength(1);
  });
});
