// @vitest-environment jsdom
//
// "Load recipe…" (M4-19d) in the processing panel and its store: no backend,
// `fetch` answers by route.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const DATASET = 'sentinel-2-c1-l2a';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);

function scene(id: string): StacItem {
  return {
    id,
    collection: DATASET,
    bbox: [10, 50, 11, 51],
    geometry: bboxToPolygon([10, 50, 11, 51]),
    properties: { datetime: '2026-07-01T10:00:00Z' },
    assets: {
      red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
    },
  };
}

const option: DatasetOption = {
  id: DATASET,
  title: 'Sentinel-2 L2A',
  viewable: true,
  groupBy: ['datetime'],
  zoom: { min: 8, max: 14 },
  browse: 'quicklook',
  quicklookNodataMax: null,
  resultsGroupBy: ['datetime'],
  hasTimeAxis: true,
  collection: {
    id: DATASET,
    'earthx:format': 'cog',
    'earthx:license_flags': { tier: 'processing' },
    'earthx:capabilities': { interpolation: true },
  } as unknown as Collection,
};

const mathStep = (expression: string, name: string) => ({ op: 'band_math', op_version: 2, params: { expression, name } });

const recipe = (patch: Record<string, unknown> = {}) =>
  JSON.stringify({
    recipe_version: 2,
    inputs: [{ name: 'input', dataset: DATASET, groups: [['NEW_A']] }],
    steps: [mathStep('(nir - red) / (nir + red)', 'ndvi')],
    output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['ndvi'] },
    ...patch,
  });

// The same recipe as a file of version 1 (adr/0020 §11): it names assets, and `band_math` replaced all bands by one.
const recipeV1 = (patch: Record<string, unknown> = {}) =>
  JSON.stringify({
    recipe_version: 1,
    inputs: [{ name: 'input', dataset: DATASET, groups: [['NEW_A']], assets: ['red', 'nir'] }],
    steps: [{ op: 'band_math', op_version: 1, params: { expression: '(nir - red) / (nir + red)' } }],
    output: { kind: 'raster', format: 'cog', dtype: 'float32' },
    ...patch,
  });

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

let fetchMock: ReturnType<typeof vi.fn>;
let container: HTMLDivElement;
let root: Root;
const stored = scene('ON_SCREEN');

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  fetchMock = vi.fn(async (url: string) => {
    if (url === `/processing/processes/recipe?dataset=${DATASET}`) return json(s2);
    if (url.endsWith('/items/NEW_A')) return json(scene('NEW_A'));
    return json({ detail: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [] });
  useAppStore.setState({
    datasets: [option],
    datasetId: DATASET,
    selectedDatasetIds: [DATASET],
    items: [stored],
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [stored] }],
    activeGroupIndex: 0,
    selectedIds: [stored.id],
    aoi: AOI,
    aoiPoint: null,
    error: null,
  });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<ProcessingPanel />));
  act(() => useProcessingStore.getState().openProcessing());
  await act(async () => {
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const load = (text: string) => act(() => useProcessingStore.getState().loadRecipe(text));
const draft = () => useProcessingStore.getState();

describe('loadRecipe', () => {
  it('takes the steps and the data type and leaves the selection and the AOI alone', async () => {
    const result = await load(recipe());
    expect(result).toEqual({ ok: true, notes: [] });
    expect(draft().steps.map((s) => [s.op, s.values.expression, s.values.name])).toEqual([['band_math', '(nir - red) / (nir + red)', 'ndvi']]);
    expect(draft().output).toEqual(['ndvi']);
    expect(draft().dtype).toBe('float32');
    expect(useAppStore.getState().selectedIds).toEqual([stored.id]);
    expect(useAppStore.getState().aoi).toBe(AOI);
    expect(draft().area).toBe('scene');
  });

  it('takes the output of the file, naming a band of the data and a result alike', async () => {
    const result = await load(recipe({ output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red', 'ndvi'] } }));
    expect(result).toEqual({ ok: true, notes: [] });
    expect(draft().output).toEqual(['red', 'ndvi']);
  });

  it('writes a file of version 1 as version 2 and says so: the result of band_math is the output, the assets are gone', async () => {
    const result = await load(recipeV1());
    expect(result).toEqual({ ok: true, notes: [], converted: true });
    expect(draft().steps.map((s) => [s.op, s.opVersion, s.values.expression, s.values.name])).toEqual([
      ['band_math', 2, '(nir - red) / (nir + red)', 'band_math'],
    ]);
    expect(draft().output).toEqual(['band_math']);
    expect(draft().dtype).toBe('float32');
  });

  it('does not say "converted" for a file of version 2', async () => {
    const result = await load(recipe());
    expect(result.ok && result.converted).toBeUndefined();
  });

  it('loads a recipe with reproject v2, which the server still takes, as the listed version', async () => {
    const step = { op: 'reproject', op_version: 2, params: { crs: 'EPSG:3035', resolution: 30, resampling: 'bilinear' } };
    const result = await load(recipe({ steps: [step], output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red', 'nir'] } }));
    expect(result).toEqual({ ok: true, notes: ['Step 1 (reproject): version 2 is taken as version 4.'] });
    expect(draft().steps.map((s) => [s.op, s.opVersion, s.values.resampling])).toEqual([['reproject', 4, 'bilinear']]);
  });

  it('replaces the steps that were there', async () => {
    await load(recipe());
    await load(recipe({ steps: [mathStep('nir', 'copy')], output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['copy'] } }));
    expect(draft().steps.map((s) => s.values.expression)).toEqual(['nir']);
    expect(draft().output).toEqual(['copy']);
  });

  it('says a band is not in the selection and does not order anything around', async () => {
    const result = await load(recipe({ steps: [mathStep('swir / nir', 'ratio')], output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['ratio'] } }));
    expect(result).toEqual({ ok: true, notes: ['Band swir is not in this selection.'] });
    expect(draft().steps[0].values.expression).toBe('swir / nir');
  });

  it('says "no steps" for the recipe of a crop, and keeps the draft', async () => {
    await load(recipe());
    const output = { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' };
    const inputs = [{ name: 'input', dataset: DATASET, groups: [['NEW_A']], assets: ['red'] }];
    expect(await load(recipe({ inputs, steps: [], output }))).toEqual({ ok: false, reason: 'This recipe has no steps.' });
    expect(draft().steps).toHaveLength(1);
  });

  it.each([
    ['a file that is not JSON', '{', /not valid JSON/u],
    ['a GeoJSON', JSON.stringify({ type: 'FeatureCollection', features: [] }), /not a recipe/u],
    ['an unknown version', recipe({ recipe_version: 3 }), /version 3/u],
    ['an operator the dataset lacks', recipe({ steps: [{ op: 'warp', op_version: 1, params: {} }] }), /not available/u],
    ['parameters the form refuses', recipe({ steps: [mathStep('', 'ndvi')] }), /Required/u],
  ])('refuses %s and changes nothing', async (_name, text, reason) => {
    const before = draft().steps;
    const result = await load(text);
    expect(result.ok).toBe(false);
    expect(!result.ok && result.reason).toMatch(reason);
    expect(draft().steps).toBe(before);
  });
});

describe('the "Load recipe…" control', () => {
  const input = () => container.querySelector('input[type="file"]') as HTMLInputElement;
  const pick = async (file: File) => {
    Object.defineProperty(input(), 'files', { value: [file], configurable: true });
    await act(async () => {
      input().dispatchEvent(new Event('change', { bubbles: true }));
    });
  };
  const text = (content: string, name = 'recipe.json') => {
    const file = new File([content], name, { type: 'application/json' });
    file.text = async () => content;
    return file;
  };

  it('takes the steps as soon as a file is picked, and leaves selection and AOI alone', async () => {
    await pick(text(recipe()));
    expect(draft().steps).toHaveLength(1);
    expect(container.textContent).toContain('Recipe loaded.');
    expect(container.querySelector('.pp-recipe .tip')).toBeNull();
    expect(useAppStore.getState().aoi).toBe(AOI);
    expect(useAppStore.getState().selectedIds).toEqual([stored.id]);
  });

  it('says a file of version 1 has been converted, with a tooltip', async () => {
    await pick(text(recipeV1()));
    expect(draft().steps).toHaveLength(1);
    expect(container.querySelector('.pp-recipe [role="status"]')?.textContent).toContain('Recipe loaded.');
    expect(container.querySelector('.pp-recipe .tip')?.getAttribute('data-tip')).toBe('Converted from recipe version 1.');
  });

  it('says why a file is turned away before reading it', async () => {
    await pick(text('x', 'recipe.txt'));
    expect(container.textContent).toContain('Pick a .json file.');
    const big = new File([new Uint8Array(1_048_577)], 'big.json');
    await pick(big);
    expect(container.textContent).toContain('The file is larger than 1 MB.');
  });

  it('shows the reason a recipe is refused, and keeps the draft', async () => {
    await pick(text(recipe()));
    await pick(text('{'));
    expect(container.textContent).toContain('The file is not valid JSON.');
    expect(draft().steps).toHaveLength(1);
  });
});
