// @vitest-environment jsdom
//
// "Measured on the first scene" (Otto, 3.11.2026, zu #282): wherever the first whole scene stands in for the area of the crop, the view says so
// beside its fields, always in the same words, with the reason behind a ⓘ. It says nothing where the area is measured or the view is not cropped.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { useAppStore, type AppState } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import { forgetAreaAnswers, MEASURED_ON_SCENE } from '../viewMeasure';
import { forgetHistograms } from './useHistograms';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const collection = {
  id: 'optical',
  title: 'Optical',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'pyramid' as const, overview_resampling: 'average' as const },
} as unknown as Collection;

const TIFF = 'image/tiff; application=geotiff; profile=cloud-optimized';
const item = (id: string): StacItem => ({
  id,
  collection: 'optical',
  bbox: [10, 47, 11, 48],
  properties: { datetime: '2026-07-01T10:00:00Z' },
  assets: { visual: { href: 'x', type: TIFF, 'raster:bands': Array.from({ length: 3 }, () => ({ data_type: 'uint8', nodata: 0 })) } } as StacItem['assets'],
});
const info = (id: string): DownloadedInfo => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/{z}/{x}/{y}?asset=visual`, bounds: [10, 47, 11, 48], asset: 'visual', minZoom: 8, maxZoom: 14 });
const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
const SCENE = { '1': { min: 0, max: 255, percentile_2: 5, percentile_98: 250, count: 9, histogram: [[1, 2], [0, 128, 255]] } };
const bandOf = (name: string) => ({ name, unit: null, statistics: { minimum: 0, maximum: 255, count: 9, percentile_2: 5, percentile_98: 250, histogram: [[1, 2], [0, 128, 255]] } });
const AREA = { exact: true, factor: 1, bands: ['visual_1', 'visual_2', 'visual_3'].map(bandOf) };

let container: HTMLDivElement;
let root: Root;

async function mount(over: Partial<AppState> = {}) {
  const items = [item('s0')];
  await act(async () => {
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', sections: [], openSectionId: null, items, groups: [{ key: ['d'], label: 'd', items }],
      focusMode: true, cropToAoi: true, viewAoi: AOI, downloaded: { s0: info('s0') }, showDownloaded: true, shownImage: null, selectedIds: ['s0'],
      pendingBand: '', pendingIndex: '', pendingColormapName: '', pendingVmin: '0', pendingVmax: '255', focusLoading: false, pinLoading: false, dock: null, resultsOnMap: true, ...over,
    });
    root.render(<ViewerControls />);
  });
  // The histograms are asked for on mounting; their answer, and the refusal that comes with it, re-render the view.
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

const hint = () => container.querySelector('.hint:not(.warn)[role="status"]');

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  forgetAreaAnswers();
  forgetHistograms();
  vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('the hint beside the fields', () => {
  it.each([413, 422])('is there, with the reason behind the ⓘ, where the tiler refuses the area (%i)', async (status) => {
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => (init?.method === 'POST' ? json({ detail: 'refused' }, status) : json(SCENE))));
    await mount();
    expect(hint()?.textContent).toContain(MEASURED_ON_SCENE);
    expect(hint()?.querySelector('.tip')?.getAttribute('aria-label')).toMatch(status === 413 ? /at most 16 files/u : /does not take the area/u);
  });

  it('is there, with its reason, where the area was never asked for (the scenes are scaled differently)', async () => {
    const both = [item('s0'), item('s1')];
    (both[1].assets.visual['raster:bands'] as { scale?: number }[])[0].scale = 2;
    const fetchMock = vi.fn(async (_url: string) => json(SCENE));
    vi.stubGlobal('fetch', fetchMock);
    await mount({ items: both, groups: [{ key: ['d'], label: 'd', items: both }], downloaded: { s0: info('s0'), s1: info('s1') }, selectedIds: ['s0', 's1'] });
    expect(hint()?.textContent).toContain(MEASURED_ON_SCENE);
    expect(hint()?.querySelector('.tip')?.getAttribute('aria-label')).toMatch(/scaled differently/u);
    // The histograms too were measured on the first scene, and say so with the rest.
    const measured = fetchMock.mock.calls.map(([url]) => String(url)).filter((url) => url.includes('/statistics'));
    expect(measured).toHaveLength(1);
    expect(measured[0]).toContain('/items/s0/statistics');
    expect(measured[0]).toContain('histogram_bins');
  });

  it('is the same words for every reason', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json(SCENE)));
    await mount({ items: [], groups: [] });
    expect(hint()?.textContent?.replace('ⓘ', '').trim()).toBe(MEASURED_ON_SCENE);
  });

  it('is not there where the area is measured', async () => {
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: RequestInit) => (init?.method === 'POST' ? json(AREA) : json(SCENE))));
    await mount();
    expect(hint()).toBeNull();
  });

  it('is not there where the view is not cropped: the first scene is the question there', async () => {
    const fetchMock = vi.fn(async () => json(SCENE));
    vi.stubGlobal('fetch', fetchMock);
    await mount({ cropToAoi: false, viewAoi: null });
    expect(hint()).toBeNull();
    expect(fetchMock).toHaveBeenCalled();
  });
});
