// @vitest-environment jsdom
//
// The output of the processing panel (NM4-43e, adr/0020 §6, §9, §14): "Select Bands that are processed", the names of the
// bands a band math step adds, and the bands of the data above as information. No backend: `fetch` answers the process
// description, the estimate and, where a test says so, a refusal.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { EMPTY_OUTPUT } from '../processingOrder';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, EarthxMask, StacAsset, StacItem } from '../types';
import ProcessingPanel from './ProcessingPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const DESCRIPTION = '/processing/processes/recipe?dataset=sentinel-2-c1-l2a';
const ESTIMATE_URL = '/processing/processes/recipe/estimate';
const HEADING = 'Select Bands that are processed';

const SCL: EarthxMask = {
  asset: 'scl',
  band: 'scl',
  classes: [{ value: 3, label: 'CLOUD_SHADOWS' }, { value: 8, label: 'CLOUD_MEDIUM_PROBABILITY' }],
  suggested: [3, 8],
  reference: '',
  note: '',
};

const uint16 = { data_type: 'uint16', nodata: 0 };
const cog = (bands: object[] = [uint16]): StacAsset => ({ href: 'https://example.org/band.tif', type: COG, 'raster:bands': bands });

// The bands of the scene, by asset key: the four of the data, the layer of the mask and `visual`, which the registry calls
// no band (three bands in one asset).
function scene(assets: Record<string, StacAsset> = {}): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id: 'S2B_A',
    collection: 'sentinel-2-c1-l2a',
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
    assets: {
      green: cog(),
      red: cog(),
      nir: cog(),
      scl: cog([{ data_type: 'uint8', nodata: 0 }]),
      visual: cog([uint16, uint16, uint16]),
      ...assets,
    },
  };
}

function dataset(extra: Record<string, unknown> = {}): DatasetOption {
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
      'earthx:mask': SCL,
      'earthx:auxiliary_assets': ['visual'],
      ...extra,
    } as unknown as Collection,
  };
}

function select(item: StacItem, option: DatasetOption = dataset()) {
  useAppStore.setState({
    datasets: [option],
    datasetId: option.id,
    items: [item],
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
    activeGroupIndex: 0,
    selectedIds: [item.id],
    aoi: AOI,
    aoiPoint: null,
    layers: [],
    mapZoom: 1.6,
    viewportBbox: null,
  });
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  });

const ESTIMATE = {
  estimate: { size: 4_000_000, duration: 'PT3.4S', outputPixels: 1_000_000, inputPixels: 2_000_000, inputBytes: 4_000_000, assets: 3, units: 1 },
  skippedItems: [],
};

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;
let estimate: () => Response;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  localStorage.clear();
  estimate = () => json(ESTIMATE);
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === DESCRIPTION) return json(s2);
    if (url === ESTIMATE_URL && init?.method === 'POST') return estimate();
    if (url.includes('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ type: 'about:blank', title: 'Refused', status: 404, detail: 'no route' }, 404);
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

function button(label: string | RegExp, within: ParentNode = container): HTMLButtonElement {
  const found = [...within.querySelectorAll('button')].find((b) =>
    typeof label === 'string' ? b.textContent?.trim() === label : label.test(b.textContent ?? ''),
  );
  if (!found) throw new Error(`no button ${String(label)} in ${container.textContent}`);
  return found as HTMLButtonElement;
}

const hasButton = (label: string, within: ParentNode = container) =>
  [...within.querySelectorAll('button')].some((b) => b.textContent?.trim() === label);

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
const out = () => container.querySelector('section[aria-label="Output"]')!;
const info = () => container.querySelector('section[aria-label="Bands"]')!;
const group = (label: string) => out().querySelector(`[aria-label="${label}"]`);
const names = (where: ParentNode | null) => [...(where?.querySelectorAll('.pp-chip') ?? [])].map((c) => c.childNodes[0].textContent);
const checked = () =>
  [...out().querySelectorAll<HTMLButtonElement>('.pp-chip[aria-pressed="true"]')].map((c) => c.childNodes[0].textContent);
const outChip = (name: string) => [...out().querySelectorAll<HTMLButtonElement>('.pp-chip')].find((c) => c.childNodes[0].textContent === name)!;
const infoChip = (name: string) => [...info().querySelectorAll<HTMLButtonElement>('.pp-chip')].find((c) => c.childNodes[0].textContent === name)!;
const heading = () => out().querySelector('h3')!.textContent;
const summary = () => out().querySelector('[aria-label="Output summary"]')!.textContent;
const expression = (step = 0) => container.querySelectorAll<HTMLTextAreaElement>('textarea[data-band-target]')[step];
const nameField = (step = 0) => container.querySelectorAll<HTMLInputElement>('input[id$="-name"]')[step];
const startButton = () => button(/Start job|Starting/);

async function addBandMath(text = 'nir - red') {
  click(button('＋ Band math'));
  typeInto(expression(store().steps.filter((s) => s.op === 'band_math').length - 1), text);
}

function sentOrder() {
  const call = [...fetchMock.mock.calls].reverse().find(([u]) => String(u).endsWith('/estimate'));
  return JSON.parse(call![1].body).inputs.recipe;
}

async function review() {
  click(button('Review'));
  await flush();
}

describe('what is in the output when the panel opens (adr/0020 §9)', () => {
  it('is nothing for a dataset with several bands, with the heading there all the same', async () => {
    select(scene());
    await openPanel();
    expect(heading()).toBe(HEADING);
    expect(checked()).toEqual([]);
    expect(summary()).toBe('0 bands · float32');
  });

  it('is nothing after reproject, mask or normalize either, and nothing without a step', async () => {
    select(scene());
    await openPanel();
    for (const op of ['＋ Reproject and resample', '＋ Mask', '＋ Normalize']) {
      click(button(op));
      expect(checked(), op).toEqual([]);
    }
  });

  it('keeps the heading whatever is chosen: empty, in part, all', async () => {
    select(scene());
    await openPanel();
    expect(heading()).toBe(HEADING);
    click(outChip('red'));
    expect(heading()).toBe(HEADING);
    click(button('All'));
    expect(checked()).toEqual(['green', 'red', 'nir']);
    expect(heading()).toBe(HEADING);
    click(button('None'));
    expect(heading()).toBe(HEADING);
  });

  it('locks the start while the output is empty, and says why in the tooltip', async () => {
    select(scene());
    await openPanel();
    click(button('＋ Mask'));
    expect(startButton().disabled).toBe(true);
    expect(startButton().title).toBe(EMPTY_OUTPUT);
    expect(EMPTY_OUTPUT).toBe('Pick at least one band for the output.');
    click(outChip('red'));
    expect(startButton().title).not.toBe(EMPTY_OUTPUT);
  });

  it('checks the one band of a dataset that has one, once: a later "None" stays, until the panel is opened again', async () => {
    const dem: StacItem = { ...scene(), assets: { dem: cog([{ data_type: 'float32', nodata: -9999 }]) } };
    select(dem, dataset({ 'earthx:mask': undefined, 'earthx:auxiliary_assets': undefined }));
    await openPanel();
    expect(checked()).toEqual(['dem']);
    click(button('None'));
    await flush();
    expect(checked()).toEqual([]);
    // Another step does not bring it back.
    click(button('＋ Reproject and resample'));
    await flush();
    expect(checked()).toEqual([]);
  });

  it('does not count the auxiliary assets and the layer of the mask as bands to pick for the person', async () => {
    const only: StacItem = { ...scene(), assets: { red: cog(), scl: cog([{ data_type: 'uint8', nodata: 0 }]), visual: cog([uint16, uint16, uint16]) } };
    select(only);
    await openPanel();
    // `red` is the only band that is neither layer nor auxiliary asset: it is the one band of this dataset.
    expect(checked()).toEqual(['red']);
  });

  it('lists the layer of the mask, unchecked and not part of "All", and does not list the auxiliary assets', async () => {
    select(scene());
    await openPanel();
    expect(names(group('Bands of the data'))).toEqual(['green', 'red', 'nir', 'scl']);
    click(button('All'));
    expect(checked()).toEqual(['green', 'red', 'nir']);
  });

  it('shows an auxiliary asset that the order has already, so that it can be left out', async () => {
    select(scene());
    await openPanel();
    act(() => store().setOutput(['visual_1']));
    expect(names(group('Bands of the data'))).toContain('visual_1');
    expect(checked()).toEqual(['visual_1']);
    click(outChip('visual_1'));
    expect(names(group('Bands of the data'))).not.toContain('visual_1');
  });
});

describe('the results of band math steps', () => {
  it('are checked as soon as the step is added, with a name of their own', async () => {
    select(scene());
    await openPanel();
    await addBandMath();
    expect(names(group('New bands'))).toEqual(['result']);
    expect(checked()).toEqual(['result']);
    expect(nameField().value).toBe('result');
    expect(container.querySelector('.pp-step-title')!.textContent).toContain('1. result');
  });

  it('are the output alone by default: no other band comes with them', async () => {
    select(scene());
    await openPanel();
    await addBandMath('(nir - red) / (nir + red)');
    await review();
    expect(sentOrder().output.bands).toEqual(['result']);
    expect(sentOrder().inputs[0]).not.toHaveProperty('assets');
    expect(sentOrder().recipe_version).toBe(2);
    expect(sentOrder().steps[0]).toEqual({
      op: 'band_math',
      op_version: 2,
      params: { expression: '(nir - red) / (nir + red)', name: 'result' },
    });
  });

  it('can be taken out, and are checked again when the next step adds one', async () => {
    select(scene());
    await openPanel();
    await addBandMath();
    click(outChip('result'));
    expect(checked()).toEqual([]);
    click(outChip('red'));
    await addBandMath('green - nir');
    expect(names(group('New bands'))).toEqual(['result', 'result_1']);
    expect(checked()).toEqual(['result_1', 'red']);
  });

  it('vanish from the output with their step', async () => {
    select(scene());
    await openPanel();
    await addBandMath();
    await addBandMath('green - nir');
    expect(checked()).toEqual(['result', 'result_1']);
    click(button('✕ Remove'));
    expect(checked()).toEqual(['result_1']);
    expect(store().output).toEqual(['result_1']);
  });

  it('are two bands of one order when two steps run one after the other, the second seeing the first', async () => {
    select(scene());
    await openPanel();
    await addBandMath('(nir - red) / (nir + red)');
    await addBandMath('(green - nir) / (green + nir)');
    // The second step offers the first result as a chip, the first step none.
    const chips = [...container.querySelectorAll('[aria-label="Results of earlier steps"]')];
    expect(chips).toHaveLength(1);
    expect(names(chips[0])).toEqual(['result']);
    await review();
    expect(sentOrder().output.bands).toEqual(['result', 'result_1']);
    expect(sentOrder().steps.map((s: { params: { name: string } }) => s.params.name)).toEqual(['result', 'result_1']);
  });

  it('are put into the expression that has the cursor by the chip of the step, and nowhere otherwise (review of #250)', async () => {
    select(scene());
    await openPanel();
    await addBandMath();
    await addBandMath('');
    const chip = () => button('result', container.querySelector('[aria-label="Results of earlier steps"]')!);
    // No cursor in an expression: nothing is inserted, and the focus stays where it was.
    act(() => nameField(1).focus());
    click(chip());
    expect(expression(1).value).toBe('');
    expect(document.activeElement).toBe(nameField(1));
    act(() => nameField(1).blur());
    click(chip());
    expect(expression(1).value).toBe('');
    // With the cursor in the expression, the name goes there.
    act(() => expression(1).focus());
    click(chip());
    expect(expression(1).value).toBe('result');
    typeInto(expression(1), 'result * 2');
    expression(1).setSelectionRange(0, 0);
    click(chip());
    expect(expression(1).value).toBe('result result * 2');
    expect(store().steps[1].values.expression).toBe('result result * 2');
  });
});

describe('what an expression names', () => {
  const problemOf = (step = 0) => container.querySelectorAll('.pp-step')[step].querySelector('.hint-text.error')?.textContent ?? null;

  it('is a band of the data or a result of a step before: anything else is told at once, as a name is', async () => {
    select(scene());
    await openPanel();
    await addBandMath('');
    const seen: Array<string | null> = [];
    for (const typed of ['r', 're', 'red', 'red - ne', 'red - nir']) {
      typeInto(expression(0), typed);
      seen.push(problemOf());
    }
    expect(seen).toEqual(["'r' is not a band name", "'re' is not a band name", null, "'ne' is not a band name", null]);
  });

  it('holds back the steps, the review and the start, with the reason as their tooltips', async () => {
    select(scene());
    await openPanel();
    await addBandMath('red - re');
    const why = "Step 1: 're' is not a band name";
    expect(button('＋ Mask').disabled).toBe(true);
    expect(button('＋ Mask').title).toBe(why);
    expect(button('Review').disabled).toBe(true);
    expect(button('Review').title).toBe(why);
    expect(startButton().disabled).toBe(true);
    expect(startButton().title).toBe(why);
    await review();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
    typeInto(expression(0), 'red - nir');
    expect(button('Review').disabled).toBe(false);
    expect(button('＋ Mask').disabled).toBe(false);
  });

  it('takes the result of an earlier step and the name of a function, not a number or a longer name for a band', async () => {
    select(scene());
    await openPanel();
    await addBandMath('red');
    await addBandMath('where(result > 0.5e1, sqrt(nir), minimum(red, 2))');
    expect(problemOf(1)).toBeNull();
    typeInto(expression(1), 'result2 + 1');
    expect(problemOf(1)).toBe("'result2' is not a band name");
  });

  it('is not held to bands where the dataset lists none', async () => {
    select({ ...scene(), assets: {} });
    await openPanel();
    await addBandMath('anything + 1');
    expect(problemOf()).toBeNull();
  });
});

describe('the resolution of a reproject step (review of #250)', () => {
  beforeEach(() => {
    const previous = fetchMock.getMockImplementation() as (url: string, init?: RequestInit) => Promise<Response>;
    fetchMock.mockImplementation(async (url: string, init?: RequestInit) =>
      url === '/processing/crs/EPSG%3A3035'
        ? json({ code: 'EPSG:3035', name: 'ETRS89 / LAEA Europe', kind: 'projected', unit: { name: 'metre', kind: 'linear', toBase: 1 } })
        : previous(url, init),
    );
  });
  const field = (name: string) => container.querySelector<HTMLInputElement>(`input[id$="-${name}"]`)!;

  it('has its unit small beside its label, once the code is known', async () => {
    select(scene());
    await openPanel();
    click(button('＋ Reproject and resample'));
    const label = field('resolution').closest('label')!;
    expect(label.querySelector('[aria-label="Unit"]')).toBeNull();
    typeInto(field('crs'), 'EPSG:3035');
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 450));
    });
    expect(label.querySelector('.pp-label [aria-label="Unit"]')?.textContent).toBe('in m');
  });

  it('says what format a code needs, not the pattern', async () => {
    select(scene());
    await openPanel();
    click(button('＋ Reproject and resample'));
    typeInto(field('crs'), 'EPSG:30');
    expect(container.textContent).toContain('Needs to be in the format "EPSG:3035"');
    expect(container.textContent).not.toContain('Does not match');
  });
});

describe('the name of a result', () => {
  async function twoSteps() {
    select(scene());
    await openPanel();
    await addBandMath('(nir - red) / (nir + red)');
    await addBandMath('result * 2');
    click(button('＋ Normalize'));
  }

  // The name is typed into the field and taken over when the field is left, as a person does it.
  function rename(step: number, text: string, leave = true) {
    act(() => nameField(step).focus());
    typeInto(nameField(step), text);
    if (leave) act(() => nameField(step).blur());
  }
  const hint = () => container.querySelector('.hint-text.error[id$="-problem"]')?.textContent ?? null;

  it('is result by default, and result_1, result_2 where that is taken', async () => {
    select(scene());
    await openPanel();
    await addBandMath('nir');
    await addBandMath('red');
    await addBandMath('green');
    expect(store().steps.map((s) => s.values.name)).toEqual(['result', 'result_1', 'result_2']);
  });

  it('takes the next free name when a band of the data is called result', async () => {
    select(scene({ result: cog() }));
    await openPanel();
    await addBandMath('nir');
    expect(store().steps[0].values.name).toBe('result_1');
  });

  it('is followed by the later expressions, the normalize step and the output when it is renamed', async () => {
    await twoSteps();
    expect(store().steps[2].values.bands).toBe('result_1');
    rename(0, 'NDVI');
    expect(store().steps[1].values.expression).toBe('NDVI * 2');
    expect(store().output).toEqual(['NDVI', 'result_1']);
    rename(1, 'Double');
    expect(store().steps[2].values.bands).toBe('Double');
    expect(store().output).toEqual(['NDVI', 'Double']);
    expect(container.querySelectorAll('.pp-step-title')[0].textContent).toContain('1. NDVI');
  });

  it('is taken over when Enter is pressed in the field', async () => {
    await twoSteps();
    act(() => nameField(0).focus());
    typeInto(nameField(0), 'NDVI');
    expect(store().steps[0].values.name).toBe('result');
    act(() => nameField(0).dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true })));
    expect(store().steps[0].values.name).toBe('NDVI');
  });

  it('is not taken while it is typed: r, re, red leave the steps and the output with the name they had', async () => {
    await twoSteps();
    const seen: string[] = [];
    const watch = () => seen.push(`${store().steps[0].values.name}|${store().steps[1].values.expression}|${store().output.join(',')}`);
    act(() => nameField(0).focus());
    for (const typed of ['r', 're', 'red']) {
      typeInto(nameField(0), typed);
      watch();
    }
    // `red` is a band of the data: told at once, in the field, with the frame turned to an error.
    expect(nameField(0).getAttribute('aria-invalid')).toBe('true');
    expect(hint()).toBe("'red' is already a band name");
    act(() => nameField(0).blur());
    watch();
    expect(new Set(seen)).toEqual(new Set(['result|result * 2|result,result_1']));
    expect(store().steps[0].values.name).toBe('result');
    // The field keeps what was typed, so that it can be put right.
    expect(nameField(0).value).toBe('red');
    expect(hint()).toBe("'red' is already a band name");
  });

  it('holds back the steps, the review and the start while a name breaks a rule, and says why in their tooltips', async () => {
    await twoSteps();
    act(() => nameField(0).focus());
    typeInto(nameField(0), 'red');
    const why = "Step 1: 'red' is already a band name";
    expect(store().nameProblems).toEqual({ [store().steps[0].key]: "'red' is already a band name" });
    for (const label of ['＋ Band math', '＋ Mask', '＋ Normalize', '＋ Reproject and resample']) {
      expect(button(label).disabled, label).toBe(true);
      expect(button(label).title, label).toBe(why);
    }
    expect(button('Review').disabled).toBe(true);
    expect(button('Review').title).toBe(why);
    expect(startButton().disabled).toBe(true);
    expect(startButton().title).toBe(why);
    await review();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
    // Put right, everything is open again.
    typeInto(nameField(0), 'NDVI');
    act(() => nameField(0).blur());
    expect(store().nameProblems).toEqual({});
    expect(button('Review').disabled).toBe(false);
    expect(button('＋ Band math').disabled).toBe(false);
    expect(hint()).toBeNull();
  });

  it('is let go of with its step: a removed step holds nothing back', async () => {
    await twoSteps();
    act(() => nameField(1).focus());
    typeInto(nameField(1), 'scl');
    expect(store().nameProblems).not.toEqual({});
    click(button('✕ Remove', container.querySelectorAll('.pp-step')[1]));
    expect(store().nameProblems).toEqual({});
    expect(button('Review').disabled).toBe(false);
  });

  it.each([
    ['one a result has already, in another spelling', 'RESULT_1', "'RESULT_1' is already used by another step"],
    ['a band of the data', 'RED', "'RED' is already a band name"],
    ['the layer of the mask, which nobody reads', 'scl', "'scl' is already a band name"],
    ['a Python keyword', 'not', "'not' cannot be used in an expression"],
    ['a function of the expressions', 'sqrt', "'sqrt' is the name of a function"],
    ['not a name', '2fast', 'Use letters, digits and _, a letter first, at most 32 characters'],
    ['empty', '', 'Enter a name'],
  ])('is never taken when it is %s: a hint under the field at once, nothing sent', async (_why, typed, reason) => {
    await twoSteps();
    rename(0, typed);
    expect(nameField(0).getAttribute('aria-invalid')).toBe('true');
    expect(hint()).toBe(reason);
    expect(store().steps[0].values.name).toBe('result');
    expect(store().steps[1].values.expression).toBe('result * 2');
    await review();
    expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith('/estimate'))).toBe(false);
  });

  it('is refused when a step reads a result that a later step adds, with the step named', async () => {
    select(scene());
    await openPanel();
    await addBandMath('red');
    await addBandMath('nir - red');
    typeInto(expression(0), 'result_1 + 1');
    expect(container.textContent).toContain("'result_1' is added by a later step");
  });
});

describe('the bands of the data above', () => {
  it('are information: a click puts the name into the expression that has the cursor, and does nothing otherwise', async () => {
    select(scene());
    await openPanel();
    await addBandMath('');
    expect(infoChip('red').hasAttribute('aria-pressed')).toBe(false);
    click(infoChip('red'));
    expect(expression().value).toBe('');
    expect(store().output).toEqual(['result']);
    act(() => expression().focus());
    click(infoChip('nir'));
    expect(expression().value).toBe('nir');
    expect(store().output).toEqual(['result']);
  });

  it('do not take the cursor from another field, and put the name nowhere else (review of #250)', async () => {
    select(scene());
    await openPanel();
    await addBandMath('nir');
    act(() => nameField(0).focus());
    click(infoChip('red'));
    // The cursor is in the name field, not in an expression: nothing is inserted, and the cursor stays where it was.
    expect(expression().value).toBe('nir');
    expect(nameField(0).value).toBe('result');
    expect(document.activeElement).toBe(nameField(0));
    act(() => nameField(0).blur());
    click(infoChip('red'));
    expect(expression().value).toBe('nir');
    expect(document.activeElement).not.toBe(expression());
    // A press on the chip does not take the focus either, so it can be used with the cursor in an expression.
    act(() => expression().focus());
    const down = new MouseEvent('mousedown', { bubbles: true, cancelable: true });
    act(() => {
      infoChip('red').dispatchEvent(down);
    });
    expect(down.defaultPrevented).toBe(true);
  });

  it('have no "Select all bands", no "Clear" and no limit, and leave the auxiliary assets out', async () => {
    select(scene());
    await openPanel();
    expect(hasButton('Select all bands', info())).toBe(false);
    expect(hasButton('Clear', info())).toBe(false);
    expect(names(info())).toEqual(['green', 'red', 'nir', 'scl']);
    expect(container.textContent).not.toMatch(/at most 16|takes at most/);
  });

  it('say what they are in a tooltip, not in a sentence', async () => {
    select(scene());
    await openPanel();
    const tip = info().querySelector('.tip');
    expect(tip?.getAttribute('data-tip')).toBe('Bands of the data. Click one to put its name into an expression.');
  });
});

describe('no limit of bands (adr/0020 §7)', () => {
  const MANY = Object.fromEntries(Array.from({ length: 20 }, (_, i) => [`b${String(i + 1).padStart(2, '0')}`, cog()]));

  it('takes 20 bands into one order, which was refused above 16', async () => {
    select({ ...scene(), assets: MANY }, dataset({ 'earthx:mask': undefined, 'earthx:auxiliary_assets': undefined }));
    await openPanel();
    click(button('＋ Reproject and resample'));
    expect(checked()).toEqual([]);
    click(button('All'));
    expect(checked()).toHaveLength(20);
    expect(hasButton('All')).toBe(false);
    act(() => {
      store().updateStep(store().steps[0].key, 'crs', 'EPSG:3035');
      store().updateStep(store().steps[0].key, 'resolution', '30');
      store().updateStep(store().steps[0].key, 'resampling', 'nearest');
    });
    await review();
    expect(sentOrder().output.bands).toHaveLength(20);
    expect(container.textContent).not.toMatch(/At most 16 bands/);
  });
});

describe('the memory limit of a job (adr/0020 §7)', () => {
  const REASON = 'This job would need about 2.4 GB of memory, more than the 1.5 GB a job may use. Put fewer bands in the output.';

  it('keeps the start shut with the reason of the server as its tooltip, and writes no line for it in the panel', async () => {
    estimate = () => json({ type: 'about:blank', title: 'Too large', status: 413, detail: REASON }, 413);
    select(scene());
    await openPanel();
    await addBandMath();
    await review();
    expect(startButton().disabled).toBe(true);
    expect(startButton().title).toBe(REASON);
    expect(container.textContent).not.toContain(REASON);
    expect(container.textContent).not.toContain('The whole scene is too large');
  });

  it('still says a whole scene is too large for another 413', async () => {
    estimate = () => json({ type: 'about:blank', title: 'Too large', status: 413, detail: 'The output would be 7 GB, more than a job may write.' }, 413);
    select(scene());
    await openPanel();
    await addBandMath();
    await review();
    expect(container.textContent).toContain('The whole scene is too large for one job.');
  });
});

describe('the bands a normalize step converts', () => {
  it('start as the last result, and are chosen among the bands of the data and the results before the step', async () => {
    select(scene());
    await openPanel();
    await addBandMath();
    click(button('＋ Normalize'));
    expect(store().steps[1].values.bands).toBe('result');
    const picker = container.querySelector('fieldset.pp-classes')!;
    expect(names(picker)).toEqual(['result', 'green', 'red', 'nir']);
    click(button('red', picker));
    expect(store().steps[1].values.bands).toBe('result, red');
    click(button('result', picker));
    click(button('red', picker));
    expect(store().steps[1].values.bands).toBe('');
  });

  it('is told to pick a band when none is chosen', async () => {
    select(scene());
    await openPanel();
    click(button('＋ Normalize'));
    await review();
    expect(container.textContent).toContain('Pick at least one band.');
  });
});

describe('a recipe of version 1 that is loaded', () => {
  it('is written as version 2: names for the band math steps, the output of the end of the chain, a tooltip that says so', async () => {
    select(scene());
    await openPanel();
    const recipe = {
      recipe_version: 1,
      inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']], assets: ['red', 'nir'] }],
      steps: [
        { op: 'band_math', op_version: 1, params: { expression: 'nir - red' } },
        { op: 'band_math', op_version: 1, params: { expression: 'band_math * 2' } },
      ],
      output: { kind: 'raster', format: 'cog', dtype: 'float32' },
    };
    const result = await store().loadRecipe(JSON.stringify(recipe));
    expect(result).toMatchObject({ ok: true, converted: true });
    await flush();
    expect(store().steps.map((s) => [s.opVersion, s.values.name])).toEqual([[2, 'band_math_1'], [2, 'band_math']]);
    expect(store().steps[1].values.expression).toBe('band_math_1 * 2');
    // Version 1 ended with the last result alone, and so does the output now.
    expect(store().output).toEqual(['band_math']);
    expect(checked()).toEqual(['band_math']);
  });
});
