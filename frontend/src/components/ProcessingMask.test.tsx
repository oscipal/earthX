// @vitest-environment jsdom
//
// The mask step of the processing panel (M4-18c): the classes to hide as boxes with the names of the
// registry, the layer in the order without being picked, the preview of a mask as the first step.
// No backend: `fetch` answers the process description and the estimate only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { NO_PREVIEW } from '../processingPreview';
import { useProcessingStore } from '../processingStore';
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

const classes = () => container.querySelector<HTMLFieldSetElement>('fieldset.pp-classes');
const box = (value: number) =>
  [...classes()!.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')].find((input) =>
    input.parentElement!.textContent!.startsWith(`${value} · `),
  )!;
const ticked = () =>
  [...classes()!.querySelectorAll<HTMLInputElement>('input[type="checkbox"]')]
    .filter((input) => input.checked)
    .map((input) => Number(input.parentElement!.textContent!.split(' · ')[0]));
const chip = (name: string) => [...container.querySelectorAll<HTMLButtonElement>('.pp-chip')].find((c) => c.textContent === name)!;
const chips = () => [...container.querySelectorAll('.pp-chip')].map((c) => c.textContent);
const section = () => container.querySelector('section[aria-label="Preview on the map"]')!;
const store = () => useProcessingStore.getState();

async function withMask(items = [scene('S2B_A')], option = dataset()) {
  select(items, option);
  await openPanel();
  click(button('＋ Mask'));
}

function sentOrder() {
  const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith('/estimate'));
  return JSON.parse(call![1].body).inputs.recipe;
}

async function review() {
  click(button('Review'));
  await flush();
}

describe('the mask step is a form, no longer "not supported by this panel"', () => {
  it('is offered with a button that works', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    expect(button('＋ Mask').disabled).toBe(false);
    expect(container.textContent).not.toContain('not supported by this panel');
  });
});

describe('the classes to hide', () => {
  it('shows one box per class with the registry name, the suggested ones ticked', async () => {
    await withMask();
    expect(classes()!.querySelector('legend')!.textContent).toBe('Classes to hide');
    const labels = [...classes()!.querySelectorAll('label')].map((l) => l.textContent);
    expect(labels).toHaveLength(12);
    expect(labels[3]).toContain('3 · CLOUD_SHADOWS');
    expect(labels[8]).toContain('8 · CLOUD_MEDIUM_PROBABILITY');
    expect(labels[11]).toContain('11 · SNOW or ICE');
    expect(ticked()).toEqual([3, 8, 9, 10]);
  });

  it('marks what is suggested, without deciding for the user', async () => {
    await withMask();
    const suggested = [...classes()!.querySelectorAll('label')].filter((l) => l.textContent!.includes('(suggested)'));
    expect(suggested).toHaveLength(4);
    // Nothing is sent unseen: the ticks are in the recipe the review shows and the server receives.
    expect(store().steps[0].values).toEqual({ source: 'scl', classes: '3, 8, 9, 10' });
  });

  it('takes the layer from the registry: there is no field for the band', async () => {
    await withMask();
    expect(container.querySelector('[id$="-source"]')).toBeNull();
    expect(classes()!.textContent).toContain('The layer scl is read for it and left out of the result.');
  });

  it('points to the table and warns that older baselines name classes differently (plan §8)', async () => {
    await withMask();
    expect(classes()!.textContent).toContain('Older processing baselines name some classes differently');
    const link = classes()!.querySelector('a')!;
    expect(link.getAttribute('href')).toBe('https://sentiwiki.copernicus.eu/web/s2-processing');
    expect(link.getAttribute('rel')).toContain('noreferrer');
    expect(link.getAttribute('target')).toBe('_blank');
  });

  it('writes the ticked classes into the recipe, ascending, whatever order they were ticked in', async () => {
    await withMask();
    click(box(11));
    click(box(0));
    click(box(3)); // off
    expect(ticked()).toEqual([0, 8, 9, 10, 11]);
    await review();
    const mask = sentOrder().steps[0];
    expect(mask).toEqual({ op: 'mask', op_version: 1, params: { source: 'scl', classes: [0, 8, 9, 10, 11] } });
  });

  it('does not send an order with no class ticked, and says why', async () => {
    await withMask();
    for (const value of [3, 8, 9, 10]) click(box(value));
    expect(ticked()).toEqual([]);
    await review();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
    expect(classes()!.textContent).toContain('Required.');
  });

  it('has the text field of the schema where the dataset names no layer', async () => {
    await withMask([scene('S2B_A')], dataset(null));
    expect(classes()).toBeNull();
    expect(container.querySelector('[id$="-source"]')).not.toBeNull();
    click(chip('red'));
    click(chip('scl'));
    typeInto(container.querySelector<HTMLInputElement>('[id$="-source"]')!, 'scl');
    typeInto(container.querySelector<HTMLInputElement>('[id$="-classes"]')!, '9, 3, 9');
    await review();
    expect(sentOrder().steps[0].params.classes).toEqual([3, 9]);
  });

  it('does not use a field of the collection it cannot read', async () => {
    await withMask([scene('S2B_A')], dataset({ asset: 'scl', band: 'scl', classes: [{ value: 'x', label: 1 }] }));
    expect(classes()).toBeNull();
  });
});

describe('the layer in the order', () => {
  it('is added with the mask step, without being picked, and read as an asset of the order', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    expect(chips()).toEqual(['red', 'nir', 'scl']);
    expect(chip('scl').getAttribute('aria-pressed')).toBe('false');
    click(button('＋ Mask'));
    expect(chip('scl').getAttribute('aria-pressed')).toBe('true');
    expect(chip('red').getAttribute('aria-pressed')).toBe('false');
    click(chip('red'));
    await review();
    expect(sentOrder().inputs[0].assets).toEqual(['red', 'scl']);
  });

  it('cannot be left out while a mask step needs it, and can once the step is gone', async () => {
    await withMask();
    expect(chip('scl').title).toContain('layer of the mask step');
    click(chip('scl'));
    expect(chip('scl').getAttribute('aria-pressed')).toBe('true');
    expect(store().picked).toEqual([]);
    click(button('✕ Remove'));
    expect(chip('scl').getAttribute('aria-pressed')).toBe('false');
  });

  it('says in the review that the order reads it and the result does not hold it', async () => {
    await withMask();
    const foot = () => container.querySelector('section[aria-label="Review"]')!.textContent;
    expect(foot()).toContain('The order also reads the mask layer scl; it is not in the result.');
  });

  it('is named by the user as well: picking it first changes nothing once the step is removed', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(chip('scl'));
    click(button('＋ Mask'));
    click(button('✕ Remove'));
    expect(chip('scl').getAttribute('aria-pressed')).toBe('true');
  });

  it('says so where the scene has no such layer, and does not invent one', async () => {
    await withMask([scene('S2B_A', false)]);
    expect(chips()).toEqual(['red', 'nir']);
    const foot = container.querySelector('section[aria-label="Review"]')!.textContent;
    expect(foot).toContain('The scenes have no mask layer scl');
    expect(store().picked).toEqual([]);
  });

  it('does not decide the data type: the layer leaves the result', async () => {
    await withMask();
    click(chip('red'));
    // uint16 with a nodata value on `red` alone; the uint8 layer would force float32 if it counted.
    expect(container.querySelector('[aria-label="Data type"]')!.textContent).toContain('uint16');
  });
});

describe('the preview of a mask', () => {
  async function previewOf(steps: () => void) {
    select([scene('S2B_A')]);
    await openPanel();
    vi.useFakeTimers();
    steps();
    act(() => {
      vi.advanceTimersByTime(400);
    });
    // A chain is asked of the tiler first (`probeChain`).
    await flush();
  }

  it('is drawn when the mask is the first step: it runs as a tile, not "only as a job"', async () => {
    await previewOf(() => {
      click(button('＋ Mask'));
      click(chip('red'));
    });
    expect(section().textContent).not.toContain(NO_PREVIEW);
    expect(section().textContent).not.toContain('only as a job');
    const preview = store().preview!;
    expect(preview.title).toBe('Mask');
    const params = new URL(preview.scenes[0].url, 'http://localhost').searchParams;
    expect(params.getAll('asset')).toEqual(['red', 'scl']);
    expect(params.get('op')).toBe('mask');
    expect(JSON.parse(params.get('params')!)).toEqual({ source: 'scl', classes: [3, 8, 9, 10] });
  });

  it('shows a mask followed by a step in one picture, in the order of the steps', async () => {
    await previewOf(() => {
      click(button('＋ Mask'));
      click(button('＋ Band math'));
      typeInto(container.querySelectorAll<HTMLTextAreaElement>('textarea[id$="-expression"]')[0], '(nir - red) / (nir + red)');
    });
    const preview = store().preview!;
    expect(preview.title).toBe('Mask → Band math');
    expect(preview.stepCount).toBe(2);
    const params = new URL(preview.scenes[0].url, 'http://localhost').searchParams;
    expect(params.getAll('op')).toEqual(['mask', 'band_math']);
    expect(params.getAll('asset')).toEqual(['red', 'nir', 'scl']);
  });

  it('follows the boxes: another class is another picture', async () => {
    await previewOf(() => {
      click(button('＋ Mask'));
      click(chip('red'));
    });
    const before = store().preview!.key;
    click(box(2));
    act(() => {
      vi.advanceTimersByTime(400);
    });
    await flush();
    expect(store().preview!.key).not.toBe(before);
    const params = new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams;
    expect(JSON.parse(params.get('params')!).classes).toEqual([2, 3, 8, 9, 10]);
  });

  it('still says "only as a job" for a step that is one', async () => {
    await previewOf(() => {
      click(button('＋ Reproject and resample'));
      click(button('＋ Mask'));
    });
    expect(section().textContent).toContain(NO_PREVIEW);
    expect(store().preview).toBeNull();
  });

  it('waits for a class instead of calling an empty mask job-only', async () => {
    await previewOf(() => {
      click(button('＋ Mask'));
      for (const value of [3, 8, 9, 10]) click(box(value));
    });
    expect(section().textContent).toContain('Complete the step to see the preview.');
    expect(section().textContent).not.toContain('only as a job');
  });
});

describe('the data type after normalize (Otto, 22.10.2026)', () => {
  it('is float32 on integer bands with a stated nodata, and no integer type is offered', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(chip('red'));
    // Without a step the source type is kept: uint16, nodata stated, no scaling.
    expect(container.querySelector('[aria-label="Data type"]')!.textContent).toContain('uint16');
    click(button('＋ Normalize'));
    expect(container.querySelector('[aria-label="Data type"]')!.textContent).toContain('float32');
    const options = [...container.querySelectorAll('select option')].map((o) => o.textContent);
    expect(options).toContain('uint16 (not after normalize)');
    expect(container.textContent).toContain('Normalize ends in float32 with NaN as nodata');
    expect(container.textContent).not.toContain('Band math ends in float32');
  });
});

describe('a dataset without a classification layer', () => {
  it('does not offer a mask and says why', async () => {
    const withoutMask = structuredClone(s2) as typeof s2;
    withoutMask.inputs.recipe.schema.properties.steps.items.oneOf = withoutMask.inputs.recipe.schema.properties.steps.items.oneOf.filter(
      (variant) => !variant.$ref.includes('step_mask'),
    );
    fetchMock.mockImplementation(async (url: string) =>
      url === DESCRIPTION ? json(withoutMask) : new Response('{}', { status: 404 }),
    );
    select([scene('S2B_A', false)], dataset(null));
    await openPanel();
    expect([...container.querySelectorAll('button')].some((b) => b.textContent === '＋ Mask')).toBe(false);
    expect(container.textContent).toContain('Mask: this dataset has no classification layer to read.');
  });

  it('says nothing of the kind where the mask is offered', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    expect(container.textContent).not.toContain('no classification layer');
  });
});
