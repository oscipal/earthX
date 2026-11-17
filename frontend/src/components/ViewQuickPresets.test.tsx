// @vitest-environment jsdom
//
// Composites and steps under "Quick processing" (M5-14, adr/0030 F7): from the registry, after the indices, before "Enhance contrast";
// none where the dataset offers none. A composite fills the three channels with its ranges and draws a colour picture; a step takes the
// look of its operator from the process description (adr/0035) and, where that is no fixed range, the range from a measure of the band
// as it is drawn. No backend: `fetch` answers the description and the statistics.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import dem from '../fixtures/processes/cop-dem-glo-30.json';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import { downloadsIndexOnly } from '../indexDownload';
import type { MapLayer } from '../layers';
import { forgetPresetLooks } from '../presetLooks';
import { colourView, useAppStore } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const VIEWER = { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'pyramid', overview_resampling: 'average', overview_substitute: null };
const FALSE_COLOUR = { name: 'false_colour_ir', title: 'False colour (IR)', expressions: ['nir', 'red', 'green'], rescale: [[0, 0.5], [0, 0.3], [0, 0.3]], reference: 'https://example.org/fc' };
const step = (name: string, title: string, params: Record<string, unknown>) => ({ name, title, op: 'terrain', op_version: 1, params: { ...params, bands: ['data'], method: 'horn', name } });
const STEPS = [
  step('hillshade', 'Hillshade', { product: 'hillshade', azimuth: 315, altitude: 45, z_factor: 1, multidirectional: false }),
  step('slope', 'Slope', { product: 'slope', slope_unit: 'degrees' }),
  step('aspect', 'Aspect', { product: 'aspect' }),
];

const optical = {
  id: 'optical',
  title: 'Sentinel-2 L2A',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:viewer': VIEWER,
  'earthx:true_color': ['red', 'green', 'blue'],
  'earthx:index_presets': SENTINEL_2_PRESETS,
  'earthx:composite_presets': [FALSE_COLOUR],
  'earthx:step_presets': [],
} as unknown as Collection;

const heights = {
  id: 'cop-dem-glo-30',
  title: 'Copernicus DEM GLO-30',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, band_math: true, interpolation: true, terrain: true },
  'earthx:default_render': { title: 'Elevation', assets: ['data'], rescale: [[0, 3000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
  'earthx:viewer': VIEWER,
  'earthx:true_color': [],
  'earthx:index_presets': [],
  'earthx:composite_presets': [],
  'earthx:step_presets': STEPS,
} as unknown as Collection;

const info = (datasetId: string, asset: string): DownloadedInfo => ({
  datasetId,
  tileUrl: `/collections/${datasetId}/items/s0/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=${asset}`,
  bounds: [0, 0, 1, 1],
  asset,
  minZoom: 8,
  maxZoom: 14,
});

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;

function mount(collection: Collection, asset: string, rescale = '0,3000') {
  const items: StacItem[] = [{ id: 's0', collection: collection.id, bbox: [0, 0, 1, 1], properties: { datetime: '2026-07-01T10:00:00Z' }, assets: {} } as StacItem];
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection]),
      datasetId: collection.id,
      items,
      groups: [{ key: ['a'], label: '2026-07-01', items }],
      selectedIds: [],
      downloaded: { s0: info(collection.id, asset) },
      focusMode: true,
      cropToAoi: false,
      showDownloaded: true,
      shownImage: null,
      viewLooks: {},
      savedLooks: {},
      appliedRender: { rescale },
      pendingColormapName: '',
      pendingVmin: '0',
      pendingVmax: '3000',
      pendingIndex: '',
      pendingBand: '',
      pendingChannels: [],
      pendingUnit: 'value',
      enhance: null,
      mosaics: {},
      mapZoom: 12,
      layers: [],
      focusLoading: false,
      pinLoading: false,
      notice: null,
      dock: null,
    });
    root.render(<ViewerControls />);
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  forgetPresetLooks();
  fetchMock = vi.fn(async (url: string) => {
    if (url.includes('/processing/processes/recipe?dataset=cop-dem-glo-30')) return new Response(JSON.stringify(dem), { status: 200, headers: { 'Content-Type': 'application/json' } });
    if (url.includes('/statistics?')) return new Response(JSON.stringify({ hillshade: { min: 3, max: 251, percentile_2: 40, percentile_98: 220 } }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    return new Response('{}', { status: 404 });
  });
  vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const quick = () => [...container.querySelectorAll<HTMLButtonElement>('.vc-quick button')].map((b) => b.textContent);
const press = async (name: string) => {
  await act(async () => {
    [...container.querySelectorAll<HTMLButtonElement>('.vc-quick button')].find((b) => b.textContent === name)!.click();
    for (let i = 0; i < 20; i++) await Promise.resolve();
  });
};
const fields = () => {
  const s = useAppStore.getState();
  return { index: s.pendingIndex, colormap: s.pendingColormapName, vmin: s.pendingVmin, vmax: s.pendingVmax, channels: s.pendingChannels.map((c) => `${c.vmin},${c.vmax}`) };
};

describe('composites under "Quick processing"', () => {
  it('stand after the indices and before "Enhance contrast"', () => {
    mount(optical, 'visual');
    expect(quick()).toEqual([...SENTINEL_2_PRESETS.map((p) => p.name), 'False colour (IR)', 'Enhance contrast']);
  });

  it('fill the three channels with the ranges of the registry and make the view a colour picture', async () => {
    mount(optical, 'visual');
    await press('False colour (IR)');
    expect(fields()).toMatchObject({ index: 'false_colour_ir', colormap: '', channels: ['0,0.5', '0,0.3', '0,0.3'] });
    expect(colourView(useAppStore.getState())).toBe(true);
    // A colour picture has no colormap.
    expect(container.textContent).not.toContain('Colormapviridis');
  });

  it('go off with a second click, back to the picture of the dataset', async () => {
    mount(optical, 'visual');
    await press('False colour (IR)');
    await press('False colour (IR)');
    expect(fields().index).toBe('');
  });
});

describe('steps under "Quick processing"', () => {
  it('are the steps of the registry, and no "Enhance contrast" for one band of heights', () => {
    mount(heights, 'data');
    expect(quick()).toEqual(['Hillshade', 'Slope', 'Aspect']);
  });

  it('draw an aspect in hsv on its fixed 0 to 360, whatever was measured (adr/0035)', async () => {
    mount(heights, 'data');
    await press('Aspect');
    expect(fields()).toMatchObject({ index: 'aspect', colormap: 'hsv', vmin: '0', vmax: '360' });
  });

  it('draw a hillshade in greys from the minimum to the maximum of a measure of the hillshade itself', async () => {
    mount(heights, 'data');
    await press('Hillshade');
    expect(fields()).toMatchObject({ index: 'hillshade', colormap: 'greys_r', vmin: '3', vmax: '251' });
    const asked = new URL(String(fetchMock.mock.calls.find(([url]) => String(url).includes('/statistics'))![0]), 'http://localhost');
    expect(asked.searchParams.get('op')).toBe('terrain');
    expect(asked.searchParams.get('band')).toBe('hillshade');
  });

  it('take a slope at the usual scale of the measure, in rdylgn_r', async () => {
    mount(heights, 'data');
    await press('Slope');
    expect(fields()).toMatchObject({ index: 'slope', colormap: 'rdylgn_r', vmin: '40', vmax: '220' });
  });

  it('say so where the description does not come, with no range made up', async () => {
    fetchMock.mockImplementation(async () => new Response('{}', { status: 503 }));
    mount(heights, 'data');
    await press('Hillshade');
    expect(fields()).toMatchObject({ index: 'hillshade', colormap: '', vmin: '', vmax: '' });
    expect(useAppStore.getState().notice).toContain('Hillshade cannot be drawn now');
    // "Apply" waits for a range: a step is never drawn with one made up.
    const apply = container.querySelector<HTMLButtonElement>('.vc-apply')!;
    expect(apply.getAttribute('aria-disabled')).toBe('true');
    expect(apply.dataset.tip).toBe('The range of this step is being measured');
  });

  it('take the range of the look on "Auto-scale" also before a click fetched the description (an aspect stays 0 to 360)', async () => {
    mount(heights, 'data');
    act(() => useAppStore.setState({ pendingIndex: 'aspect', pendingColormapName: 'magma', pendingVmin: '5', pendingVmax: '9' }));
    await act(async () => {
      await useAppStore.getState().autoStretch();
    });
    expect(fields()).toMatchObject({ index: 'aspect', colormap: 'magma', vmin: '0', vmax: '360' });
  });

  it('keep the range of the image they were measured on: a measure that comes after a change of the preset is dropped', async () => {
    mount(heights, 'data');
    await act(async () => {
      const pressing = useAppStore.getState().quickIndex('hillshade');
      useAppStore.getState().chooseViewIndex('aspect');
      await pressing;
    });
    expect(fields()).toMatchObject({ index: 'aspect' });
  });
});

describe('the download of a pinned layer of a preset (until M5-14 PR B)', () => {
  const layer = (index: string, datasetId: string) => ({ restore: { indexOnly: true, datasetId, appliedRender: { index } } }) as unknown as MapLayer;

  it('is the index alone for an index, the bands of the scenes for a step or a composite', () => {
    const datasets = datasetsFrom([optical, heights]);
    expect(downloadsIndexOnly(layer('NDVI', 'optical'), datasets)).toBe(true);
    expect(downloadsIndexOnly(layer('false_colour_ir', 'optical'), datasets)).toBe(false);
    expect(downloadsIndexOnly(layer('hillshade', 'cop-dem-glo-30'), datasets)).toBe(false);
  });
});

describe('a dataset without presets', () => {
  it('has no "Quick processing" at all', () => {
    mount({ ...heights, 'earthx:step_presets': [] } as Collection, 'data');
    expect([...container.querySelectorAll('.insp-heading')].map((h) => h.textContent)).not.toContain('Quick processing');
  });
});
