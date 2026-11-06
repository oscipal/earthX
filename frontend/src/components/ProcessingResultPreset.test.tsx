// @vitest-environment jsdom
//
// The look of a result layer for a band with the expression of an index preset of its dataset (NM4-14b, D2): the layer
// starts with it, a band chosen later has it, "Auto" gives it back, and no other band or dataset gets it. No backend: `fetch`
// answers the TileJSON.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import { jobEntry, NOW } from '../fixtures/jobEntries';
import { SENTINEL_2_PRESETS } from '../fixtures/indexPresets';
import type { Order } from '../processing';
import { setTrackerOptions, useProcessingStore, type JobEntry } from '../processingStore';
import { defaultRange, resultBands } from '../resultLayer';
import { useAppStore } from '../store';
import type { Collection } from '../types';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const HREF = `/results/${RESULT}/WebMercatorQuad/tilejson.json`;
const TILE_JSON = { bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 19, data_type: 'float32', tiles: ['http://tiler/x'] };

const stat = (minimum: number, maximum: number, p2: number, p98: number) => ({ minimum, maximum, mean: 0, count: 1000, valid_percent: 100, percentile_2: p2, percentile_98: p98 });
// Snow beyond −1…1 in its 2–98 %: without the preset this would be drawn 2–98 % in viridis.
const WIDE = stat(-4, 9, -2.5, 6);
const IN_RANGE = stat(-0.3, 0.9, -0.05, 0.8);

const STEP = (name: string, expression: string) => ({ op: 'band_math', op_version: 2, params: { expression, name } });
const NDWI = '(green - nir) / (green + nir)';
const ORDER = {
  recipe_version: 2,
  inputs: [{ name: 'in', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }],
  steps: [STEP('NDWI', '(green-nir)/(green+nir)'), STEP('own', '(nir - green) / (nir + green)')],
  output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDWI', 'own', 'red'] },
} as unknown as Order;
const PROPERTIES = {
  'processing:expression': { format: 'numexpr', expression: '(nir - green) / (nir + green)', name: 'own' },
  bands: [
    { name: 'NDWI', data_type: 'float32', statistics: WIDE },
    { name: 'own', data_type: 'float32', statistics: WIDE },
    { name: 'red', data_type: 'float32', statistics: IN_RANGE },
  ],
};

function dataset(id: string, presets: unknown[]): DatasetOption {
  return {
    id,
    title: id,
    viewable: true,
    groupBy: ['datetime'],
    zoom: { min: 8, max: 14 },
    browse: 'quicklook',
    quicklookNodataMax: null,
    resultsGroupBy: ['datetime'],
    hasTimeAxis: true,
    collection: { id, 'earthx:index_presets': presets } as unknown as Collection,
  };
}

function entry(over: Partial<JobEntry> = {}): JobEntry {
  return jobEntry(1, {
    jobID: JOB,
    phase: 'successful',
    tiles: { href: HREF, width: 1000, gsd: 10 },
    title: 'Band math · Sentinel-2 L2A',
    order: ORDER,
    bands: resultBands(PROPERTIES, ORDER),
    ...over,
  });
}

const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers({ toFake: ['Date'], now: NOW });
  sessionStorage.clear();
  localStorage.clear();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => (url === HREF ? json(TILE_JSON) : json({ title: 'Not found' }))),
  );
  useProcessingStore.getState().resetDraft();
  useAppStore.setState({
    layers: [],
    dock: 'layers',
    mapZoom: 5,
    viewportBbox: null,
    notice: null,
    datasets: [dataset('sentinel-2-c1-l2a', SENTINEL_2_PRESETS)],
    resultViewLayerId: null,
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
  setTrackerOptions({});
});

const layers = () => useAppStore.getState().layers;
const query = () => new URL((layers()[0].overlays[0] as { tileUrl: string }).tileUrl, 'http://localhost').searchParams;
const look = () => [query().get('rescale'), query().get('colormap_name')];

async function show(over: Partial<JobEntry> = {}) {
  useProcessingStore.setState({ jobs: [entry(over)] });
  await useProcessingStore.getState().showResultOnMap(JOB);
}

describe('the layer of a result with an index', () => {
  it('starts with the preset where the band it starts with has its expression, whatever the values are', async () => {
    await show({ shownBand: 'NDWI' });
    expect(look()).toEqual(['-1,1', 'rdbu']);
    expect(layers()[0].result!.preset).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdbu' });
  });

  it('draws a band of the same job whose expression is changed by the rule it had', async () => {
    await show({ shownBand: 'own' });
    expect(look()).toEqual(['-2.5,6', 'viridis']);
    expect(layers()[0].result!.preset).toBeNull();
  });

  it('changes with the band that is chosen, and gives "Auto" the preset of the band shown', async () => {
    await show({ shownBand: 'own' });
    act(() => useProcessingStore.getState().chooseResultBand(layers()[0].id, 0));
    expect(look()).toEqual(['-1,1', 'rdbu']);
    expect(defaultRange(layers()[0].result!, useProcessingStore.getState().range)).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdbu' });
    act(() => useProcessingStore.getState().chooseResultBand(layers()[0].id, 1));
    expect(look()).toEqual(['-2.5,6', 'viridis']);
    expect(layers()[0].result!.preset).toBeNull();
    act(() => useProcessingStore.getState().chooseResultBand(layers()[0].id, 2));
    expect(look()).toEqual(['-0.05,0.8', 'viridis']);
  });

  it('lets the range the user had set for the band go first', async () => {
    const hand = { vmin: '0', vmax: '0.5', colormap: 'magma' };
    await show({ shownBand: 'NDWI', bandRanges: { NDWI: hand } });
    expect(look()).toEqual(['0,0.5', 'magma']);
  });

  it('has no preset for a job kept without its order: the results name the expression, but not the dataset', async () => {
    const properties = { ...PROPERTIES, 'processing:expression': { format: 'numexpr', expression: NDWI, name: 'NDWI' } };
    const bands = resultBands(properties, null);
    expect(bands.map((b) => b.expression ?? null)).toEqual([NDWI, null, null]);
    useProcessingStore.setState({ jobs: [entry({ order: null, bands })] });
    await useProcessingStore.getState().showResultOnMap(JOB);
    // No order: the dataset is not known either, so no preset is looked up.
    expect(layers()[0].result!.preset).toBeNull();
  });

  it('never gives the preset of one dataset to the expression of a job of another', async () => {
    useAppStore.setState({ datasets: [dataset('sentinel-2-c1-l2a', []), dataset('other', SENTINEL_2_PRESETS)] });
    await show({ shownBand: 'NDWI' });
    expect(look()).toEqual(['-2.5,6', 'viridis']);
  });

  it('draws a result of one band with the preset as well', async () => {
    const one = {
      recipe_version: 2,
      inputs: [{ name: 'in', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }],
      steps: [STEP('NDWI', NDWI)],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDWI'] },
    } as unknown as Order;
    const properties = { 'processing:expression': { format: 'numexpr', expression: NDWI, name: 'NDWI' }, bands: [PROPERTIES.bands[0]] };
    useProcessingStore.setState({ jobs: [entry({ order: one, bands: resultBands(properties, one), statistics: null })] });
    await useProcessingStore.getState().showResultOnMap(JOB);
    expect(layers()[0].result!.bands).toBeUndefined();
    expect(look()).toEqual(['-1,1', 'rdbu']);
  });
});
