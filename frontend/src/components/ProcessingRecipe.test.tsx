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
const FILE_AOI = bboxToPolygon([9, 47, 9.05, 47.05]);

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

const recipe = (patch: Record<string, unknown> = {}) =>
  JSON.stringify({
    recipe_version: 1,
    inputs: [{ name: 'input', dataset: DATASET, groups: [['NEW_A']], assets: ['red', 'nir'] }],
    aoi: FILE_AOI,
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

const load = (text: string, mode: 'steps' | 'everything') =>
  act(() => useProcessingStore.getState().loadRecipe(text, mode));
const draft = () => useProcessingStore.getState();

describe('loadRecipe, steps only', () => {
  it('takes the steps and the data type and leaves the selection and the AOI alone', async () => {
    const result = await load(recipe(), 'steps');
    expect(result).toEqual({ ok: true, notes: [] });
    expect(draft().steps.map((s) => [s.op, s.values.expression])).toEqual([['band_math', '(nir - red) / (nir + red)']]);
    expect(draft().dtype).toBe('float32');
    expect(useAppStore.getState().selectedIds).toEqual([stored.id]);
    expect(useAppStore.getState().aoi).toBe(AOI);
    expect(draft().area).toBe('scene');
  });

  it('replaces the steps that were there', async () => {
    await load(recipe(), 'steps');
    await load(recipe({ steps: [{ op: 'band_math', op_version: 1, params: { expression: 'nir' } }] }), 'steps');
    expect(draft().steps.map((s) => s.values.expression)).toEqual(['nir']);
  });

  it('says a band is not in the selection and does not order anything around', async () => {
    const result = await load(recipe({ steps: [{ op: 'band_math', op_version: 1, params: { expression: 'swir / nir' } }] }), 'steps');
    expect(result).toEqual({ ok: true, notes: ['Band swir is not in this selection.'] });
    expect(draft().steps[0].values.expression).toBe('swir / nir');
  });

  it('says "no steps" for the recipe of a crop, and keeps the draft', async () => {
    await load(recipe(), 'steps');
    const output = { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' };
    expect(await load(recipe({ steps: [], output }), 'steps')).toEqual({ ok: false, reason: 'This recipe has no steps.' });
    expect(draft().steps).toHaveLength(1);
  });

  it.each([
    ['a file that is not JSON', '{', /not valid JSON/u],
    ['a GeoJSON', JSON.stringify({ type: 'FeatureCollection', features: [] }), /not a recipe/u],
    ['an unknown version', recipe({ recipe_version: 3 }), /version 3/u],
    ['an operator the dataset lacks', recipe({ steps: [{ op: 'warp', op_version: 1, params: {} }] }), /not available/u],
    ['parameters the form refuses', recipe({ steps: [{ op: 'band_math', op_version: 1, params: { expression: '' } }] }), /Required/u],
  ])('refuses %s and changes nothing', async (_name, text, reason) => {
    const before = draft().steps;
    const result = await load(text, 'steps');
    expect(result.ok).toBe(false);
    expect(!result.ok && result.reason).toMatch(reason);
    expect(draft().steps).toBe(before);
  });
});

describe('loadRecipe, everything', () => {
  it('takes scenes (fetched, as they are not on screen), area, steps and data type', async () => {
    expect(await load(recipe(), 'everything')).toEqual({ ok: true, notes: [] });
    expect(useAppStore.getState().selectedIds).toEqual(['NEW_A']);
    expect(useAppStore.getState().aoi).toEqual(FILE_AOI);
    expect(draft().area).toBe('aoi');
    expect(draft().extraScenes?.items.map((i) => i.id)).toEqual(['NEW_A']);
    expect(draft().picked).toEqual(['red', 'nir']);
    expect(draft().steps).toHaveLength(1);
  });

  it('is "Whole scene" for a recipe without an AOI, and leaves the AOI on the map', async () => {
    const { aoi: _aoi, ...rest } = JSON.parse(recipe());
    await load(JSON.stringify(rest), 'everything');
    expect(draft().area).toBe('scene');
    expect(useAppStore.getState().aoi).toBe(AOI);
  });

  it('takes the scenes of a crop and no steps', async () => {
    const output = { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' };
    expect(await load(recipe({ steps: [], output }), 'everything')).toEqual({ ok: true, notes: [] });
    expect(draft().steps).toEqual([]);
    expect(draft().dtype).toBeNull();
  });

  it('names the scenes the source lacks and changes nothing of the draft', async () => {
    const text = recipe({ inputs: [{ name: 'input', dataset: DATASET, groups: [['NEW_A', 'GONE_B']], assets: ['red'] }] });
    const result = await load(text, 'everything');
    expect(!result.ok && result.reason).toMatch(/GONE_B: not found in the catalog/u);
    expect(draft().steps).toEqual([]);
    expect(useAppStore.getState().aoi).toBe(AOI);
  });

  it('refuses a dataset this site does not list', async () => {
    const text = recipe({ inputs: [{ name: 'input', dataset: 'unknown-set', groups: [['A']], assets: ['red'] }] });
    expect(await load(text, 'everything')).toEqual({ ok: false, reason: 'Pick a dataset first.' });
  });

  it('refuses a dataset whose licence does not allow processing', async () => {
    useAppStore.setState({
      datasets: [{ ...option, collection: { ...option.collection, 'earthx:license_flags': { tier: 'view' } } as unknown as Collection }],
    });
    const result = await load(recipe(), 'everything');
    expect(!result.ok && result.reason).toMatch(/does not allow processing/u);
  });
});

describe('the "Load recipe…" control', () => {
  const buttons = () => [...container.querySelectorAll('button')].map((b) => b.textContent?.trim());
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

  it('offers "Steps only" and "Everything" once a file is picked, then takes the steps', async () => {
    expect(buttons()).not.toContain('Steps only');
    await pick(text(recipe()));
    expect(buttons()).toEqual(expect.arrayContaining(['Steps only', 'Everything', 'Cancel']));
    const steps = [...container.querySelectorAll('button')].find((b) => b.textContent === 'Steps only')!;
    await act(async () => steps.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(draft().steps).toHaveLength(1);
    expect(container.textContent).toContain('Recipe loaded.');
    expect(buttons()).not.toContain('Steps only');
  });

  it('says why a file is turned away before reading it', async () => {
    await pick(text('x', 'recipe.txt'));
    expect(container.textContent).toContain('Pick a .json file.');
    const big = new File([new Uint8Array(1_048_577)], 'big.json');
    await pick(big);
    expect(container.textContent).toContain('The file is larger than 1 MB.');
    expect(buttons()).not.toContain('Steps only');
  });

  it('shows the reason a recipe is refused', async () => {
    await pick(text('{'));
    const everything = [...container.querySelectorAll('button')].find((b) => b.textContent === 'Everything')!;
    await act(async () => everything.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(container.textContent).toContain('The file is not valid JSON.');
  });
});
