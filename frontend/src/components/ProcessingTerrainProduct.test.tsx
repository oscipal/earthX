// @vitest-environment jsdom
//
// A change of the product of a "Terrain" step (Otto, 17.11.2026, error since UI-09): the band takes the name of the new product and is drawn
// with its look (adr/0035) — slope `rdylgn_r`, hillshade `greys_r` from the minimum to the maximum, aspect `hsv` on 0 to 360 — unless the person
// named the band or applied a range by hand first (hand before look). No backend: `fetch` answers the process description and the statistics.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import dem from '../fixtures/processes/cop-dem-glo-30.json';
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
const AOI = bboxToPolygon([7.4, 46.4, 7.6, 46.6]);

const scene: StacItem = {
  id: 'Copernicus_DSM_COG_10_N46_00_E007_00_DEM',
  collection: 'cop-dem-glo-30',
  bbox: [7, 46, 8, 47],
  geometry: bboxToPolygon([7, 46, 8, 47]),
  properties: { datetime: '2021-04-22T00:00:00Z', gsd: 30 },
  assets: { data: { href: 'https://example.org/dem.tif', type: COG, 'raster:bands': [{ data_type: 'float32', nodata: -32767, unit: 'm' }] } },
} as unknown as StacItem;

const DATASET: DatasetOption = {
  id: 'cop-dem-glo-30',
  title: 'Copernicus DEM GLO-30',
  viewable: true,
  groupBy: ['datetime'],
  zoom: { min: 7, max: 14 },
  browse: 'quicklook',
  quicklookNodataMax: null,
  resultsGroupBy: ['datetime'],
  hasTimeAxis: false,
  collection: {
    id: 'cop-dem-glo-30',
    'earthx:format': 'cog',
    'earthx:license_flags': { tier: 'processing' },
    'earthx:capabilities': { interpolation: true, terrain: true, band_math: true },
    'earthx:band_units': { data: 'm' },
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
      if (url === '/processing/processes/recipe?dataset=cop-dem-glo-30') return json(dem);
      if (init?.method === 'POST' && url.endsWith('/statistics')) return measured({ bands: [], exact: true, factor: 1 });
      if (url.includes('/tilejson.json')) return json({ tilejson: '3.0.0' });
      if (url.includes('/statistics?')) return measured({ band: { count: 900, min: 2, max: 88, percentile_2: 5, percentile_98: 40, unit: null } });
      return new Response('{}', { status: 404, headers: { 'Content-Type': 'application/problem+json' } });
    }),
  );
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [], preview: null, previewNote: null });
  useAppStore.setState({
    datasets: [DATASET],
    datasetId: 'cop-dem-glo-30',
    items: [scene],
    groups: [{ key: ['2021-04-22'], label: '2021-04-22', items: [scene] }],
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
const terrain = () => store().steps.find((step) => step.op === 'terrain')!;

function choose(product: string) {
  const select = container.querySelector<HTMLSelectElement>('select[id$="-product"]')!;
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!.call(select, product);
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

async function openWithTerrain() {
  act(() => root.render(<ProcessingPanel />));
  act(() => store().openProcessing());
  await flush();
  vi.useFakeTimers();
  click(button('Terrain'));
  await afterDebounce();
}

describe('a change of the product of a Terrain step', () => {
  it('names the band after the new product and draws it with that product’s look', async () => {
    await openWithTerrain();
    expect(terrain().values.name).toBe('slope');
    expect(drawn()).toEqual(['rdylgn_r', '5,40']);

    choose('hillshade');
    await afterDebounce();
    expect(terrain().values.name).toBe('hillshade');
    expect(store().output).toContain('hillshade');
    expect(drawn()).toEqual(['greys_r', '2,88']);

    choose('aspect');
    await afterDebounce();
    expect(terrain().values.name).toBe('aspect');
    expect(drawn()).toEqual(['hsv', '0,360']);
  });

  it('keeps a name the person gave the band', async () => {
    await openWithTerrain();
    act(() => store().renameResult(terrain().key, 'relief'));
    choose('hillshade');
    await afterDebounce();
    expect(terrain().values.name).toBe('relief');
    expect(drawn()[0]).toBe('greys_r');
    expect(store().rangeDraft.colormap).toBe('greys_r');
  });

  it('keeps a range the person applied by hand', async () => {
    await openWithTerrain();
    act(() => useProcessingStore.setState({ range: { vmin: '10', vmax: '20', colormap: 'magma' }, rangeByHand: true }));
    choose('aspect');
    await afterDebounce();
    expect(drawn()).toEqual(['magma', '10,20']);
  });

  it('takes the look of the new product after "Auto-scale", which held no colormap of the person’s', async () => {
    await openWithTerrain();
    act(() => store().autoStretch());
    await afterDebounce();
    expect(drawn()[0]).toBe('rdylgn_r');
    choose('hillshade');
    await afterDebounce();
    expect(drawn()).toEqual(['greys_r', '2,88']);
    choose('aspect');
    await afterDebounce();
    expect(drawn()).toEqual(['hsv', '0,360']);
  });

  it('keeps a colormap the person chose through "Auto-scale" and the change of the product', async () => {
    await openWithTerrain();
    act(() => useProcessingStore.setState({ rangeDraft: { ...store().rangeDraft, colormap: 'magma' } }));
    act(() => store().autoStretch());
    await afterDebounce();
    choose('hillshade');
    await afterDebounce();
    expect(drawn()).toEqual(['magma', '2,88']);
  });

  it('pins the preview of the new product under its name, drawn with its look', async () => {
    await openWithTerrain();
    // Two bands in the output: the preview is named after the band it shows.
    act(() => store().setOutput(['data', 'slope']));
    act(() => store().setShown('slope'));
    await afterDebounce();
    choose('hillshade');
    await afterDebounce();
    expect(store().shown).toBe('hillshade');
    act(() => store().pinPreview());
    const [layer] = useAppStore.getState().layers;
    expect(layer.name).toContain('hillshade');
    expect(layer.name).not.toContain('slope');
    const overlay = layer.overlays.find((one) => one.kind === 'raster');
    if (overlay?.kind !== 'raster') throw new Error('the pinned preview has no tiles');
    const url = new URL(overlay.tileUrl, 'http://localhost');
    expect(url.searchParams.get('colormap_name')).toBe('greys_r');
  });
});
