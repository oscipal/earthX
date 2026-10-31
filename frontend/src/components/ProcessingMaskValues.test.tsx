// @vitest-environment jsdom
//
// The "Mask by value" step of the processing panel (DS-06b): the buttons that depend on the dataset, the form for each
// condition, the order it builds, what it tells while typing, the rename of a result it looks at. No backend: `fetch`
// answers the process description and the estimate only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import cop from '../fixtures/processes/cop-dem-glo-30.json';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { orderView, selectionState, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, EarthxMask, StacItem } from '../types';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const DESCRIPTION = '/processing/processes/recipe?dataset=sentinel-2-c1-l2a';
const DEM_DESCRIPTION = '/processing/processes/recipe?dataset=cop-dem-glo-30';

// What the registry serves for `sentinel-2-c1-l2a` (`catalog/datasets.py`).
const SCL: EarthxMask = {
  asset: 'scl',
  band: 'scl',
  classes: [
    'NO_DATA',
    'SATURATED_OR_DEFECTIVE',
    'CAST_SHADOWS',
    'CLOUD_SHADOWS',
    'VEGETATION',
    'NOT_VEGETATED',
    'WATER',
    'UNCLASSIFIED',
    'CLOUD_MEDIUM_PROBABILITY',
    'CLOUD_HIGH_PROBABILITY',
    'THIN_CIRRUS',
    'SNOW or ICE',
  ].map((label, value) => ({ value, label })),
  suggested: [3, 8, 9, 10],
  reference: 'https://sentiwiki.copernicus.eu/web/s2-processing',
  note: 'Class names follow the current Sentinel-2 L2A documentation. Older processing baselines name some classes differently.',
};

const band = { data_type: 'uint16', nodata: 0 };

function scene(id: string, withLayer = true): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id,
    collection: 'sentinel-2-c1-l2a',
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
    assets: {
      red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [band] },
      nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [band] },
      ...(withLayer
        ? { scl: { href: 'https://example.org/scl.tif', type: COG, gsd: 20, 'raster:bands': [{ data_type: 'uint8', nodata: 0 }] } }
        : {}),
    },
  };
}

function dataset(mask: unknown = SCL): DatasetOption {
  return {
    id: 'sentinel-2-c1-l2a',
    title: 'Sentinel-2 L2A',
    viewable: true,
    groupBy: ['datetime'],
    zoom: { min: 8, max: 14 },
    browse: 'quicklook',
    quicklookNodataMax: null,
    resultsGroupBy: ['datetime'],
    hasTimeAxis: true,
    collection: {
      id: 'sentinel-2-c1-l2a',
      'earthx:format': 'cog',
      'earthx:license_flags': { tier: 'processing' },
      'earthx:capabilities': { interpolation: true },
      ...(mask === undefined ? {} : { 'earthx:mask': mask }),
    } as unknown as Collection,
  };
}

function select(items: StacItem[], option: DatasetOption = dataset()) {
  useAppStore.setState({
    datasets: [option],
    datasetId: option.id,
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: items.map((i) => i.id),
    aoi: AOI,
    aoiPoint: null,
    layers: [],
    mapZoom: 1.6,
    viewportBbox: null,
  });
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

const ESTIMATE = {
  estimate: { size: 4_000_000, duration: 'PT3.4S', outputPixels: 1_000_000, inputPixels: 2_000_000, inputBytes: 4_000_000, assets: 3, units: 1 },
  skippedItems: [],
};

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === DESCRIPTION) return json(s2);
    if (url === DEM_DESCRIPTION) return json(cop);
    if (url === '/processing/processes/recipe/estimate' && init?.method === 'POST') return json(ESTIMATE);
    if (url.includes('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return new Response('{}', { status: 404, headers: { 'Content-Type': 'application/problem+json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [], preview: null, previewNote: null });
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

async function openPanel() {
  act(() => root.render(<ProcessingPanel />));
  act(() => useProcessingStore.getState().openProcessing());
  await flush();
}

function button(label: string | RegExp): HTMLButtonElement {
  const found = [...container.querySelectorAll('button')].find((b) =>
    typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? ''),
  );
  if (!found) throw new Error(`no button ${String(label)} in ${container.textContent}`);
  return found as HTMLButtonElement;
}

function click(element: HTMLElement) {
  act(() => element.dispatchEvent(new MouseEvent('click', { bubbles: true })));
}

function typeInto(input: HTMLInputElement | HTMLTextAreaElement, value: string) {
  const prototype = input instanceof HTMLTextAreaElement ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
  const setter = Object.getOwnPropertyDescriptor(prototype, 'value')!.set!;
  act(() => {
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}

const store = () => useProcessingStore.getState();
const hasButton = (label: string) => [...container.querySelectorAll('button')].some((b) => b.textContent?.trim() === label);
// The explanations are the tooltips (ⓘ), not text in the form.
const tipsOf = (root: Element) => [...root.querySelectorAll('[data-tip]')].map((tip) => tip.getAttribute('data-tip')).join(' ');
const dataGroup = () => container.querySelector('section[aria-label="Output"] [aria-label="Bands of the data"]')!;
const chip = (name: string) => [...dataGroup().querySelectorAll<HTMLButtonElement>('.pp-chip')].find((c) => c.textContent === name)!;

function demScene(): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id: 'DEM_A',
    collection: 'cop-dem-glo-30',
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2021-01-01T00:00:00Z', gsd: 30 },
    assets: { data: { href: 'https://example.org/dem.tif', type: COG, 'raster:bands': [{ data_type: 'float32', nodata: -32767 }] } },
  };
}

function demDataset(): DatasetOption {
  const option = dataset(undefined);
  return {
    ...option,
    id: 'cop-dem-glo-30',
    title: 'Copernicus DEM',
    collection: { id: 'cop-dem-glo-30', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:band_units': { data: 'm' } } as unknown as Collection,
  };
}

async function openDem() {
  select([demScene()], demDataset());
  await openPanel();
}

// The step form: the fields of "Mask by value".
const step = () => container.querySelector('li.pp-step')!;
const bandSelect = () => step().querySelector<HTMLSelectElement>('select[id$="-band"]')!;
const conditionSelect = () => step().querySelector<HTMLSelectElement>('select[aria-label="Condition"]')!;
const numberBox = (label: string) => step().querySelector<HTMLInputElement>(`input[aria-label="${label}"]`);
const problems = () => [...step().querySelectorAll('.hint-text.error')].map((p) => p.textContent);

function choose(select: HTMLSelectElement, value: string) {
  act(() => {
    select.value = value;
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
}

async function withMaskByValue(band: string | null = 'red') {
  select([scene('S2B_A')]);
  await openPanel();
  click(button('＋ Mask by value'));
  if (band) choose(bandSelect(), band);
}

function sentSteps() {
  const call = fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/estimate')).at(-1);
  return JSON.parse(call![1].body).inputs.recipe.steps;
}

async function review() {
  click(button('Review'));
  await flush();
}

describe('the buttons', () => {
  it('offers the mask by class and the mask by value where the dataset has a classification layer', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    expect(hasButton('＋ Mask by class')).toBe(true);
    expect(hasButton('＋ Mask by value')).toBe(true);
    expect(container.textContent).not.toContain('no classification layer');
  });

  it('offers only the mask by value where there is no layer, and says nothing of the layer', async () => {
    await openDem();
    expect(hasButton('＋ Mask by value')).toBe(true);
    expect(hasButton('＋ Mask by class')).toBe(false);
    expect(container.textContent).not.toContain('no classification layer');
    expect(container.textContent).not.toContain('Mask:');
  });
});

describe('a mask by value step', () => {
  it('is named like a step without a band of its own, and starts at "below"', async () => {
    await withMaskByValue(null);
    expect(step().querySelector('.pp-step-title')!.textContent).toBe('1. Mask_values_1 mask by value');
    expect(conditionSelect().value).toBe('lt');
    expect(bandSelect().value).toBe('');
    expect(numberBox('Value')!.value).toBe('');
  });

  it('keeps the explanations in tooltips, short', async () => {
    await withMaskByValue(null);
    const text = tipsOf(step());
    expect(text).toContain('The band whose values decide. Pixels are hidden in every band.');
    expect(text).toContain('Compared in the band\'s data type.');
    expect(text).toContain('no value are hidden too');
    expect(step().textContent).not.toContain('Compared in');
  });

  it('offers the results of earlier steps first, then the bands of the data without the helper assets', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('＋ Band math'));
    typeInto(step().querySelector<HTMLTextAreaElement>('textarea')!, '(nir - red) / (nir + red)');
    click(button('＋ Mask by value'));
    const mask = container.querySelectorAll('li.pp-step')[1];
    const groups = [...mask.querySelectorAll('optgroup')].map((g) => [g.label, [...g.querySelectorAll('option')].map((o) => o.value)]);
    expect(groups).toEqual([
      ['Results', ['result']],
      ['Data', ['red', 'nir', 'scl']],
    ]);
    // The last result is proposed, as for a normalize step.
    expect(mask.querySelector<HTMLSelectElement>('select[id$="-band"]')!.value).toBe('result');
  });

  it('shows the unit of the band beside "Hide where"', async () => {
    await openDem();
    click(button('＋ Mask by value'));
    expect(step().textContent).not.toContain('in m');
    choose(bandSelect(), 'data');
    expect(step().querySelector('.pp-unit')!.textContent).toBe('in m');
  });
});

describe('the order of a mask by value', () => {
  it('sends below one number', async () => {
    await withMaskByValue();
    typeInto(numberBox('Value')!, '0.2');
    click(chip('red'));
    await review();
    expect(sentSteps()).toEqual([{ op: 'mask_values', op_version: 1, params: { band: 'red', condition: 'lt', values: [0.2] } }]);
  });

  it('sends above one number', async () => {
    await withMaskByValue();
    choose(conditionSelect(), 'gt');
    typeInto(numberBox('Value')!, '-2000');
    click(chip('red'));
    await review();
    expect(sentSteps()[0].params).toEqual({ band: 'red', condition: 'gt', values: [-2000] });
  });

  it('sends between two numbers, with both boxes', async () => {
    await withMaskByValue();
    choose(conditionSelect(), 'between');
    expect(numberBox('Value')).toBeNull();
    typeInto(numberBox('From')!, '0.2');
    typeInto(numberBox('To')!, '0.8');
    click(chip('red'));
    await review();
    expect(sentSteps()[0].params).toEqual({ band: 'red', condition: 'between', values: [0.2, 0.8] });
  });

  it('sends the numbers of equal to ascending and each once', async () => {
    await withMaskByValue('scl');
    choose(conditionSelect(), 'eq');
    typeInto(step().querySelector<HTMLInputElement>('input[aria-label="Values"]')!, '9, 3, 3; 8');
    click(chip('red'));
    await review();
    expect(sentSteps()[0].params).toEqual({ band: 'scl', condition: 'eq', values: [3, 8, 9] });
  });

  it('keeps the number when the condition changes to one that takes it', async () => {
    await withMaskByValue();
    typeInto(numberBox('Value')!, '0.2');
    choose(conditionSelect(), 'between');
    expect(numberBox('From')!.value).toBe('0.2');
    expect(numberBox('To')!.value).toBe('');
    choose(conditionSelect(), 'gt');
    expect(numberBox('Value')!.value).toBe('0.2');
  });

  it('works on the DEM, which has no layer to mask by class', async () => {
    await openDem();
    click(button('＋ Mask by value'));
    choose(bandSelect(), 'data');
    choose(conditionSelect(), 'gt');
    typeInto(numberBox('Value')!, '2000');
    // The one band of the DEM is in the output already.
    await review();
    expect(sentSteps()).toEqual([{ op: 'mask_values', op_version: 1, params: { band: 'data', condition: 'gt', values: [2000] } }]);
  });

  it('reads the band it looks at, which is not in the output', async () => {
    await withMaskByValue('scl');
    typeInto(numberBox('Value')!, '3');
    click(chip('red'));
    await review();
    const call = fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/estimate')).at(-1)!;
    expect(JSON.parse(call[1].body).inputs.recipe.output.bands).toEqual(['red']);
    expect(orderView(selectionState(useAppStore.getState()), store()).assets).toEqual(['red', 'scl']);
  });
});

describe('what the form tells', () => {
  it('says at once what is no number, a comma for a point, and a "from" that is not below "to"', async () => {
    await withMaskByValue();
    typeInto(numberBox('Value')!, 'high');
    expect(problems()).toEqual(['Enter numbers separated by commas.']);
    typeInto(numberBox('Value')!, '0,2');
    expect(problems()).toEqual(['Use a point as the decimal mark.']);
    typeInto(numberBox('Value')!, '1e999');
    expect(problems()).toEqual(['Enter numbers separated by commas.']);
    typeInto(numberBox('Value')!, '1e39');
    expect(problems()).toEqual(['Too large or too small.']);
    choose(conditionSelect(), 'between');
    typeInto(numberBox('From')!, '0.8');
    // One box is not yet an entry.
    expect(problems()).toEqual([]);
    typeInto(numberBox('To')!, '0.2');
    expect(problems()).toEqual(['“from” must be below “to”.']);
    typeInto(numberBox('To')!, '0.9');
    expect(problems()).toEqual([]);
  });

  it('says more than 64 numbers are too many', async () => {
    await withMaskByValue('scl');
    choose(conditionSelect(), 'eq');
    typeInto(step().querySelector<HTMLInputElement>('input[aria-label="Values"]')!, Array.from({ length: 65 }, (_, i) => i).join(', '));
    expect(problems()).toEqual(['At most 64 values.']);
  });

  it('asks for the numbers after a review was asked for, and sends nothing', async () => {
    await withMaskByValue();
    click(chip('red'));
    expect(problems()).toEqual([]);
    await review();
    expect(problems()).toEqual(['Required.']);
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
  });

  it('holds back the steps, the review and the start while the band is added by a later step', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('＋ Band math'));
    typeInto(step().querySelector<HTMLTextAreaElement>('textarea')!, 'nir - red');
    click(button('＋ Mask by value'));
    act(() => store().moveStep(store().steps[1].key, -1));
    const why = "Step 1: 'result' is added by a later step";
    expect(container.querySelector('li.pp-step select[id$="-band"]')!.closest('li')!.textContent).toContain("'result' is added by a later step");
    expect(button('Review').disabled).toBe(true);
    expect(button('Review').title).toBe(why);
    expect(button('＋ Mask by class').disabled).toBe(true);
    act(() => store().moveStep(store().steps[0].key, 1));
    expect(button('Review').disabled).toBe(false);
  });

  it('tells a band of a recipe that the data do not have', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    const recipe = {
      recipe_version: 2,
      inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }],
      steps: [{ op: 'mask_values', op_version: 1, params: { band: 'chlorophyll', condition: 'lt', values: [1] } }],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red'] },
    };
    await act(async () => void (await store().loadRecipe(JSON.stringify(recipe))));
    expect(step().textContent).toContain("'chlorophyll' is not a band name");
    expect(button('Review').disabled).toBe(true);
  });
});

describe('renaming the result it looks at', () => {
  it('pulls the band of the mask along', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('＋ Band math'));
    typeInto(step().querySelector<HTMLTextAreaElement>('textarea')!, '(nir - red) / (nir + red)');
    click(button('＋ Mask by value'));
    const name = step().querySelector<HTMLInputElement>('input[id$="-name"]')!;
    typeInto(name, 'NDVI');
    act(() => void name.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
    act(() => name.blur());
    expect(store().steps.map((s) => s.values.name ?? s.values.band)).toEqual(['NDVI', 'NDVI']);
  });
});

describe('the recipe file', () => {
  it('goes out of the panel and back in unchanged', async () => {
    await withMaskByValue();
    choose(conditionSelect(), 'between');
    typeInto(numberBox('From')!, '0.2');
    typeInto(numberBox('To')!, '0.8');
    click(chip('red'));
    await review();
    const order = JSON.parse(fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/estimate')).at(-1)![1].body).inputs.recipe;
    act(() => useProcessingStore.getState().resetDraft());
    select([scene('S2B_A')]);
    await act(async () => void (await store().loadRecipe(JSON.stringify(order))));
    expect(store().steps).toMatchObject([{ op: 'mask_values', opVersion: 1, values: { band: 'red', condition: 'between', values: '0.2, 0.8' } }]);
    expect(orderView(selectionState(useAppStore.getState()), store()).built?.order?.steps).toEqual(order.steps);
  });
});
