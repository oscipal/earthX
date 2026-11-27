// @vitest-environment jsdom
//
// A "SAR dB" step in the Processing panel (DS-05a): it proposes the first band of digital numbers and names its band after it, the quantity
// of the registry goes with it without a field, the band follows a change of the band read unless the person named it, and the preview is
// drawn with the operator's look (`greys_r` from the 2nd to the 98th percentile). No backend: `fetch` answers the process description and the
// statistics.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import radar from '../fixtures/processes/sentinel-1-grd.json';
import { bboxToPolygon } from '../geoUtils';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([14.4, 47.4, 14.6, 47.6]);

const band = { data_type: 'uint16', nodata: 0 };
const scene: StacItem = {
  id: 'S1A_IW_GRDH_1SDV_SYNTH',
  collection: 'sentinel-1-grd',
  bbox: [13, 47, 16, 49],
  geometry: bboxToPolygon([13, 47, 16, 49]),
  properties: { datetime: '2026-11-20T05:10:00Z', 'sar:polarizations': ['VV', 'VH'] },
  assets: {
    vv: { href: 'https://example.org/vv.tif', type: COG, 'raster:bands': [band] },
    vh: { href: 'https://example.org/vh.tif', type: COG, 'raster:bands': [band] },
  },
} as unknown as StacItem;

const DATASET: DatasetOption = {
  id: 'sentinel-1-grd',
  title: 'Sentinel-1 GRD',
  viewable: true,
  groupBy: ['datetime'],
  zoom: { min: 0, max: 19 },
  browse: 'preview_tiles',
  quicklookNodataMax: null,
  resultsGroupBy: ['datetime'],
  hasTimeAxis: true,
  collection: {
    id: 'sentinel-1-grd',
    'earthx:format': 'cog',
    'earthx:georeferencing': 'gcp_tps',
    'earthx:license_flags': { tier: 'processing' },
    'earthx:capabilities': { interpolation: true, band_math: true, sar_backscatter: true },
    'earthx:band_units': { vv: 'DN', vh: 'DN', hh: 'DN', hv: 'DN' },
  } as unknown as Collection,
};

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
const measured = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response;

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/processing/processes/recipe?dataset=sentinel-1-grd') return json(radar);
      if (init?.method === 'POST' && url.endsWith('/statistics')) return measured({ bands: [], exact: true, factor: 1 });
      if (url.includes('/tilejson.json')) return json({ tilejson: '3.0.0' });
      if (url.includes('/statistics?')) return measured({ vv_db: { count: 900, min: 30, max: 60, percentile_2: 38, percentile_98: 51, unit: 'dB' } });
      return new Response('{}', { status: 404, headers: { 'Content-Type': 'application/problem+json' } });
    }),
  );
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [], preview: null, previewNote: null });
  useAppStore.setState({
    datasets: [DATASET],
    datasetId: 'sentinel-1-grd',
    items: [scene],
    groups: [{ key: ['2026-11-20'], label: '2026-11-20', items: [scene] }],
    activeGroupIndex: 0,
    selectedIds: [scene.id],
    aoi: AOI,
   
    layers: [],
    mapZoom: 9,
    viewportBbox: null,
    dock: null,
  });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

async function flush() {
  await act(async () => {
    for (let i = 0; i < 20; i++) await Promise.resolve();
  });
}

async function afterDebounce() {
  act(() => {
    vi.advanceTimersByTime(400);
  });
  await flush();
}

const store = () => useProcessingStore.getState();
const click = (element: HTMLElement) => act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const button = (text: string) => [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === text)!;
const tiles = () => new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams;
const drawn = () => [tiles().get('colormap_name'), tiles().get('rescale')];
const sarDb = () => store().steps.find((step) => step.op === 'sar_db')!;

async function openWithSarDb() {
  act(() => root.render(<ProcessingPanel />));
  act(() => store().openProcessing());
  await flush();
  vi.useFakeTimers();
  click(button('SAR dB'));
  await afterDebounce();
}

describe('a SAR dB step', () => {
  it('reads the first band of digital numbers, adds it in dB and draws it grey on the usual scale', async () => {
    await openWithSarDb();
    expect(sarDb().values).toMatchObject({ bands: 'vv', name: 'vv_db' });
    expect(store().output).toContain('vv_db');
    expect(container.querySelector('[id$="-quantity"]')).toBeNull();
    const params = JSON.parse(tiles().get('params')!);
    expect(params).toEqual({ bands: ['vv'], name: 'vv_db', quantity: 'amplitude' });
    expect(drawn()).toEqual(['greys_r', '38,51']);
  });

  it('names its band after the band it reads, unless the person named it', async () => {
    await openWithSarDb();
    act(() => store().updateStep(sarDb().key, 'bands', 'vh'));
    expect(sarDb().values.name).toBe('vh_db');
    expect(store().output).toContain('vh_db');
    act(() => store().renameResult(sarDb().key, 'cross'));
    act(() => store().updateStep(sarDb().key, 'bands', 'vv'));
    expect(sarDb().values.name).toBe('cross');
  });

  it('offers a rename in its head like the other steps that add a band', async () => {
    await openWithSarDb();
    expect(container.querySelector('button[aria-label="Rename"]')).not.toBeNull();
  });
});
