// @vitest-environment jsdom
//
// NM4-65 part 3 (Otto, 31.10.2026): every layer carries the acquisition date of its scenes — UTC, YYYY-MM-DD, the span where
// they differ, none for data without a time axis such as the elevation model. It is read where the layer is made and kept in
// it, for scene layers, previews and results alike.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { datesOfIds, knownItems } from './layerDate';
import { useAppStore } from './store';
import type { Collection, StacItem } from './types';

const CAPABILITIES = { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };

const collection = (id: string, groupBy: string, timeRange: boolean): Collection => ({
  id,
  title: id === 's2' ? 'Sentinel-2 L2A' : 'Copernicus DEM',
  'earthx:capabilities': { ...CAPABILITIES, time_range: timeRange },
  'earthx:viewer': { group_by: [groupBy], min_zoom: 0, max_zoom: 14, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: [groupBy] },
  'earthx:default_render': { title: 'Standard', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
});

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };
const s2Scene = (id: string, datetime: string): StacItem => ({ id, collection: 's2', bbox: [10, 47, 11, 48], properties: { datetime, platform: 'sentinel-2a' }, assets: {} });
const demTile = (id: string): StacItem => ({ id, collection: 'dem', bbox: [10, 47, 11, 48], properties: { start_datetime: '2011-01-01T00:00:00Z' }, assets: {} });

// a1 and a2 share a day, a3 is late in the evening UTC of the same day, b1 is five days later.
const FEATURES = [
  s2Scene('a1', '2026-07-01T10:00:00Z'),
  s2Scene('a2', '2026-07-01T10:00:05Z'),
  s2Scene('a3', '2026-07-01T23:59:59Z'),
  s2Scene('b1', '2026-07-06T10:00:00Z'),
  demTile('d1'),
];
const state = () => useAppStore.getState();
const json = (body: unknown, status = 200) => ({ ok: status < 300, status, statusText: '', json: async () => body }) as Response;

async function searched() {
  useAppStore.setState({
    datasets: datasetsFrom([collection('s2', 'datetime', true), collection('dem', 'start_datetime', false)]),
    selectedDatasetIds: ['s2', 'dem'],
    multiSelect: true,
    datasetId: 's2',
    sections: [],
    selectedIds: [],
    layers: [],
    aoi: AOI,
    dateFrom: '',
    dateTo: '',
    focusMode: false,
    resultsOnMap: true,
    mosaics: {},
    downloaded: {},
    shownImage: null,
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.includes('/statistics')) return json({ '1': { min: 0, max: 255, percentile_2: 5, percentile_98: 250 } });
      if (url.includes('/mosaic/')) return json({ detail: 'no' }, 422);
      return json({ features: FEATURES, numberReturned: FEATURES.length, links: [] });
    }),
  );
  await state().runSearch();
}

afterEach(() => vi.unstubAllGlobals());

describe('datesOfIds', () => {
  const items = FEATURES;
  it('is the day of the scenes in UTC, or the span of days', () => {
    expect(datesOfIds(['a1', 'a2'], items)).toBe('2026-07-01');
    expect(datesOfIds(['a1', 'a3'], items)).toBe('2026-07-01');
    expect(datesOfIds(['a1', 'b1'], items)).toBe('2026-07-01 – 2026-07-06');
  });

  it('is nothing for data without a time axis, for scenes it does not know and for none', () => {
    expect(datesOfIds(['d1'], items)).toBeNull();
    expect(datesOfIds(['unknown'], items)).toBeNull();
    expect(datesOfIds([], items)).toBeNull();
  });

  it('takes the day of the scenes it knows when others are missing, and does not mix up a date that is none', () => {
    expect(datesOfIds(['d1', 'b1', 'unknown'], items)).toBe('2026-07-06');
    expect(datesOfIds(['x'], [{ id: 'x', collection: 's2', properties: { datetime: 'not a date' }, assets: {} } as StacItem])).toBeNull();
  });

  it('reads the UTC day of an instant given with an offset', () => {
    const late = s2Scene('late', '2026-07-01T23:30:00-02:00');
    expect(datesOfIds(['late'], [late])).toBe('2026-07-02');
  });
});

describe('knownItems', () => {
  it('lists the scenes of the search once', async () => {
    await searched();
    expect(knownItems(state()).map((item) => item.id).sort()).toEqual(['a1', 'a2', 'a3', 'b1', 'd1']);
  });
});

describe('the layers of the view', () => {
  beforeEach(async () => {
    await searched();
  });

  it('"Add all to layers" gives each image the date of its own scenes and the elevation model none', async () => {
    for (const id of ['a1', 'a2', 'b1']) state().toggleSelected(id);
    state().setOpenSection('dem');
    state().toggleSelected('d1');
    state().setOpenSection('s2');
    await state().enterFocus(true);
    state().addAllToLayers();
    const byName = Object.fromEntries(state().layers.map((l) => [l.restore.datasetId + ':' + l.restore.itemIds.join(','), l.date]));
    expect(byName).toEqual({ 's2:a1,a2': '2026-07-01', 's2:b1': '2026-07-06', 'dem:d1': undefined });
    expect(state().layers.find((l) => l.restore.datasetId === 'dem')).not.toHaveProperty('date');
  });

  it('a layer of the scenes ticked inside an image shows their day, not that of the whole image', async () => {
    for (const id of ['a1', 'a3']) state().toggleSelected(id);
    await state().enterFocus(true);
    state().addCurrentToLayers();
    expect(state().layers[0].date).toBe('2026-07-01');
  });

  it('keeps its date when the search moves on', async () => {
    for (const id of ['a1', 'a2']) state().toggleSelected(id);
    await state().enterFocus(true);
    state().addCurrentToLayers();
    state().clearSearchResults();
    expect(state().layers[0].date).toBe('2026-07-01');
  });
});

describe('a layer a derived picture pins', () => {
  beforeEach(async () => {
    await searched();
  });
  const overlays = [{ kind: 'raster' as const, tileUrl: 'https://t/{z}/{x}/{y}', bounds: [10, 47, 11, 48] as [number, number, number, number], minZoom: 0, maxZoom: 14 }];

  it('looks the scenes of a preview up', () => {
    state().pinDerivedLayer({ name: 'Preview · NDVI', derived: 'preview', overlays, itemIds: ['a1', 'b1'], cropToAoi: false });
    expect(state().layers[0].date).toBe('2026-07-01 – 2026-07-06');
  });

  it('shows the date of the job for a result, and none where the job has none', () => {
    state().pinDerivedLayer({ name: 'Result · A', derived: 'result', overlays, itemIds: [], cropToAoi: false, date: '2026-07-01' });
    state().pinDerivedLayer({ name: 'Result · B', derived: 'result', overlays, itemIds: [], cropToAoi: false, date: null });
    const [b, a] = state().layers;
    expect(a.date).toBe('2026-07-01');
    expect(b).not.toHaveProperty('date');
  });

  it('prefers the date it is given to a look-up of scenes that are not in the search any more', () => {
    state().clearSearchResults();
    state().pinDerivedLayer({ name: 'Result · C', derived: 'result', overlays, itemIds: ['a1'], cropToAoi: false, date: '2026-06-30' });
    expect(state().layers[0].date).toBe('2026-06-30');
  });
});

beforeEach(() => {
  useAppStore.setState({ layers: [] });
});
