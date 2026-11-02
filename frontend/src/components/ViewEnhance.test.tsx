// @vitest-environment jsdom
//
// UI-03d (Otto, 2.11.2026) in the view of scenes: "Enhance contrast" (each band, each channel of a colour picture on its own, from its
// 2nd to its 98th percentile, at once; a second click puts back what was drawn), the histograms of "Scale" with their sliders, and what
// "Add to layers" pins: an index alone, or the whole view. `fetch` answers the statistics of the first scene.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import { useAppStore, type AppState } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import { forgetHistograms } from './useHistograms';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const collection = (trueColor: boolean): Collection =>
  ({
    id: 'optical',
    title: 'Sentinel-2 L2A',
    'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    ...(trueColor ? { 'earthx:true_color': ['red', 'green', 'blue'] } : {}),
    'earthx:index_presets': SENTINEL_2_PRESETS,
  }) as unknown as Collection;

const info = (id: string): DownloadedInfo => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 8, maxZoom: 14 });
const item = (id: string): StacItem => ({ id, collection: 'optical', bbox: [0, 0, 1, 1], properties: { datetime: '2026-07-01T10:00:00Z' }, assets: {} });

// A histogram of four bins from `low` to `high`, evenly filled.
const histogram = (low: number, high: number) => [[25, 25, 25, 25], [0, 1, 2, 3, 4].map((i) => low + ((high - low) * i) / 4)];
// The minimum and the maximum a tenth of the range beyond the two percentiles.
const band = (p2: number, p98: number) => {
  const [min, max] = [p2 - (p98 - p2) / 10, p98 + (p98 - p2) / 10];
  return { min, max, percentile_2: p2, percentile_98: p98, histogram: histogram(min, max) };
};
// The three channels of the true-colour asset, each of its own spread, and the one band of an index.
const VISUAL = { b1: band(100, 900), b2: band(200, 1200), b3: band(300, 1800) };
const INDEX = { NDVI: band(-0.2, 0.8) };

let container: HTMLDivElement;
let root: Root;
let withHistograms = true;
const fetchMock = vi.fn(async (url: string) => {
  const body = url.includes('op=band_math') ? INDEX : VISUAL;
  const answer = withHistograms ? body : Object.fromEntries(Object.entries(body).map(([k, v]) => [k, { ...v, histogram: undefined }]));
  return new Response(JSON.stringify(answer), { status: 200, headers: { 'Content-Type': 'application/json' } });
});

function mount(over: Partial<AppState> = {}, trueColor = true) {
  const items = [item('s0')];
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection(trueColor)]),
      datasetId: 'optical',
      items,
      groups: [{ key: ['a'], label: '2026-07-01', items }],
      selectedIds: [],
      downloaded: { s0: info('s0') },
      focusMode: true,
      cropToAoi: false,
      viewAoi: null,
      showDownloaded: true,
      shownImage: null,
      viewLooks: {},
      savedLooks: {},
      appliedRender: { rescale: '0,3000' },
      pendingColormapName: '',
      pendingVmin: '0',
      pendingVmax: '3000',
      pendingChannels: [],
      pendingIndex: '',
      pendingBand: '',
      pendingUnit: 'value',
      enhance: null,
      mosaics: {},
      mapZoom: 12,
      layers: [],
      viewOfLayer: false,
      focusLoading: false,
      pinLoading: false,
      dock: null,
      ...over,
    });
    root.render(<ViewerControls />);
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  withHistograms = true;
  forgetHistograms();
  fetchMock.mockClear();
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

const state = () => useAppStore.getState();
const quickButton = (name: string) => [...container.querySelectorAll<HTMLButtonElement>('.vc-quick button')].find((b) => b.textContent === name)!;
const press = async (name: string) => {
  await act(async () => {
    quickButton(name).click();
  });
  await settle();
};
const settle = () =>
  act(async () => {
    await vi.waitFor(() => expect(state().focusLoading).toBe(false));
    await new Promise((r) => setTimeout(r, 10));
  });
const on = (name: string) => quickButton(name).getAttribute('aria-pressed') === 'true';
const hists = () => [...container.querySelectorAll<HTMLElement>('.range-hist')];
const slider = (label: string) => container.querySelector<HTMLInputElement>(`.range-hist input[aria-label="${label}"]`)!;
const field = (label: string) => [...container.querySelectorAll<HTMLLabelElement>('.vc-num')].find((l) => l.querySelector('.sr-only')?.textContent === label)!.querySelector('input')!;
const slide = (input: HTMLInputElement, value: number) =>
  act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!.call(input, String(value));
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });

describe('"Enhance contrast"', () => {
  it('stretches each channel of the colour picture from its own 2nd to its 98th percentile, at once, and is on', async () => {
    mount();
    expect(on('Enhance contrast')).toBe(false);
    await press('Enhance contrast');
    expect(state().appliedRender.rescale).toBe('100,900;200,1200;300,1800');
    expect(on('Enhance contrast')).toBe(true);
    // Counter-check: not the one shared range "auto-scale" puts in the fields.
    expect(state().appliedRender.rescale).not.toBe('100,1800');
  });

  it('puts back what was drawn before with a second click', async () => {
    mount();
    await press('Enhance contrast');
    await press('Enhance contrast');
    expect(state().appliedRender).toEqual({ rescale: '0,3000' });
    expect(state().pendingUnit).toBe('value');
    expect(on('Enhance contrast')).toBe(false);
  });

  it('is what "auto-scale" measures for a band of its own: the 2nd to the 98th percentile of an index', async () => {
    mount();
    await press('NDVI');
    await press('Enhance contrast');
    expect(state().appliedRender).toMatchObject({ index: 'NDVI', rescale: '-0.2,0.8' });
    expect(on('Enhance contrast')).toBe(true);
    expect(on('NDVI')).toBe(true);
  });

  it('is off once the fields ask for something else, or a band or an index is picked', async () => {
    mount();
    await press('Enhance contrast');
    act(() => state().setPendingPercent('low', '5'));
    expect(on('Enhance contrast')).toBe(false);
    act(() => state().setPendingPercent('low', '2'));
    expect(on('Enhance contrast')).toBe(true);
    await press('NDWI');
    expect(on('Enhance contrast')).toBe(false);
  });

  it('is only the look: "Add to layers" pins the whole view', async () => {
    mount();
    await press('Enhance contrast');
    act(() => state().addCurrentToLayers());
    expect(state().layers).toHaveLength(1);
    expect(state().layers[0].restore.indexOnly).toBeUndefined();
    expect(state().layers[0].restore.appliedRender.rescale).toBe('100,900;200,1200;300,1800');
    // The tiles of the layer take one range per channel.
    const raster = state().layers[0].overlays.find((o) => o.kind === 'raster');
    expect(raster && raster.kind === 'raster' ? new URL(raster.tileUrl, 'http://x').searchParams.getAll('rescale') : []).toEqual(['100,900', '200,1200', '300,1800']);
  });
});

describe('"Add to layers" with an index of "Quick processing"', () => {
  it('pins the index alone, and the whole view without one', async () => {
    mount();
    await press('NDVI');
    act(() => state().addCurrentToLayers());
    expect(state().layers[0].restore).toMatchObject({ indexOnly: true, appliedRender: { index: 'NDVI' } });
    await press('NDVI');
    act(() => state().addCurrentToLayers());
    expect(state().layers[0].restore.indexOnly).toBeUndefined();
  });
});

describe('the histograms of "Scale"', () => {
  it('are three for the colour picture, one for each channel in its colour, with a row of fields for each', async () => {
    mount();
    await settle();
    await vi.waitFor(() => expect(hists()).toHaveLength(3));
    expect(hists().map((h) => h.className)).toEqual(['range-hist range-hist-red', 'range-hist range-hist-green', 'range-hist range-hist-blue']);
    expect(container.querySelectorAll('.vc-num input')).toHaveLength(6);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('histogram_bins=64'))).toBe(true);
  });

  it('move a channel of their own: the slider writes the field of that channel and no other, and a field moves its slider', async () => {
    mount();
    await vi.waitFor(() => expect(hists()).toHaveLength(3));
    slide(slider('green vmin'), 500);
    expect(state().pendingChannels).toEqual([{ vmin: '0', vmax: '3000' }, { vmin: '500', vmax: '3000' }, { vmin: '0', vmax: '3000' }]);
    expect(field('green vmin').value).toBe('500');
    act(() => state().setPendingChannel(2, 'vmax', '1500'));
    expect(slider('blue vmax').value).toBe('1500');
    // The lower slider never passes the upper one.
    slide(slider('green vmin'), 9000);
    expect(state().pendingChannels[1].vmin).toBe('3000');
  });

  it('is one for an index, and "Enhance contrast" moves its sliders to the range it draws', async () => {
    mount();
    await press('NDVI');
    await vi.waitFor(() => expect(hists()).toHaveLength(1));
    await press('Enhance contrast');
    // In percentiles: the sliders stand where the 2nd and the 98th percentile of the histogram lie.
    expect(state().pendingUnit).toBe('percent');
    const low = Number(slider('vmin').value);
    const high = Number(slider('vmax').value);
    expect(low).toBeCloseTo(-0.3 + 0.02 * 1.2, 5);
    expect(high).toBeCloseTo(-0.3 + 0.98 * 1.2, 5);
  });

  it('write whole percents in percentiles', async () => {
    mount({ pendingUnit: 'percent', pendingPercentLow: '2', pendingPercentHigh: '98' });
    await press('NDVI');
    act(() => state().setPendingUnit('percent'));
    await vi.waitFor(() => expect(hists()).toHaveLength(1));
    slide(slider('vmin'), -0.3 + 0.25 * 1.2);
    expect(state().pendingPercentLow).toBe('25');
  });

  it('are not there where the statistics have none, and the fields are as before', async () => {
    withHistograms = false;
    mount({}, false);
    await settle();
    await new Promise((r) => setTimeout(r, 20));
    expect(hists()).toHaveLength(0);
    expect(container.querySelectorAll('.vc-num input')).toHaveLength(2);
  });
});

describe('a reversed colormap (UI-03d)', () => {
  it('is drawn, kept by "Apply to all" and pinned with the layer as the tiler\'s name with "_r"', async () => {
    mount();
    await press('NDVI');
    act(() => state().setPendingColormapName('rdylgn_r'));
    await act(async () => {
      await state().applyRender();
    });
    expect(state().appliedRender.colormapName).toBe('rdylgn_r');
    await act(async () => {
      await state().saveViewLook();
    });
    expect(state().savedLooks.optical).toMatchObject({ colormapName: 'rdylgn_r' });
    act(() => state().addCurrentToLayers());
    const raster = state().layers[0].overlays.find((o) => o.kind === 'raster');
    expect(raster && raster.kind === 'raster' ? new URL(raster.tileUrl, 'http://x').searchParams.get('colormap_name') : null).toBe('rdylgn_r');
  });
});
