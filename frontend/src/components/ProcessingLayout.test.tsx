// @vitest-environment jsdom
//
// The processing panel in the order of UI-03b (plan §7.6, Otto, 3.11.2026): the sections at their fixed places, the steps as cards with a
// head of their own, no Esc that closes anything, the colormap of the preview chosen as everywhere (UI-03d), and the contract of the
// layout in `index.css` (width, touch height). No backend: `fetch` answers the process description and the estimate.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, EarthxMask, StacAsset, StacItem } from '../types';
import css from '../index.css?raw';
import tokens from '../tokens.css?raw';
import ProcessingPanel from './ProcessingPanel';
import { tipOf } from '../fixtures/tips';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const DESCRIPTION = '/processing/processes/recipe?dataset=sentinel-2-c1-l2a';
const ESTIMATE_URL = '/processing/processes/recipe/estimate';

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
    typeof label === 'string' ? (b.textContent?.trim() === label || b.getAttribute('aria-label') === label) : label.test(b.textContent ?? ''),
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
const expression = (step = 0) => container.querySelectorAll<HTMLTextAreaElement>('textarea[data-band-target]')[step];
const nameField = (step = 0) => container.querySelectorAll<HTMLInputElement>('input[id$="-name"]')[step];

async function addBandMath(text = 'nir - red') {
  click(button('Band math'));
  typeInto(expression(store().steps.filter((s) => s.op === 'band_math').length - 1), text);
}

const rule = (selector: string): string => {
  const start = css.indexOf(`${selector} {`);
  expect(start, `no rule for ${selector}`).toBeGreaterThanOrEqual(0);
  return css.slice(start, css.indexOf('}', start));
};

const sections = () => [...container.querySelectorAll('.pp-body > section')].map((s) => s.getAttribute('aria-label'));

describe('the sections of the panel', () => {
  it('stand in one order: Selection, Bands, Processing steps, Output, Preview on the map; Review and Start at the foot', async () => {
    select(scene());
    await openPanel();
    expect(sections()).toEqual(['Selection', 'Bands', 'Processing steps', 'Output', 'Preview on the map']);
    expect(container.querySelector('.processing-panel > .pp-foot')!.getAttribute('aria-label')).toBe('Review');
    // Each has its heading, in the same element.
    for (const section of container.querySelectorAll('.pp-body > section')) expect(section.querySelector('h3.pp-heading'), section.getAttribute('aria-label') ?? '').not.toBeNull();
  });

  it('keep their places whatever the steps are: a step adds a card, the sections do not move', async () => {
    select(scene());
    await openPanel();
    const before = sections();
    click(button('Band math'));
    click(button('Normalize'));
    expect(sections()).toEqual(before);
    expect(container.querySelectorAll('.pp-steps > li')).toHaveLength(2);
  });

  it('hold the area, the recipe and the summary of the selection in the first section, not in the head', async () => {
    select(scene());
    await openPanel();
    const head = container.querySelector('.pp-head')!;
    expect(head.querySelector('[aria-label="Area"], .pp-recipe')).toBeNull();
    expect(head.textContent).toContain('Processing');
    const selection = container.querySelector('section[aria-label="Selection"]')!;
    expect(selection.querySelector('[aria-label="Area"]')).not.toBeNull();
    expect(selection.querySelector('.pp-recipe')).not.toBeNull();
    expect(selection.textContent).toContain('Sentinel-2 L2A');
  });

  it('give way to the reason why nothing can be processed, which is all the body says', async () => {
    select(scene(), dataset({ 'earthx:license_flags': { tier: 'viewer' } }));
    await openPanel();
    expect(sections()).toEqual([]);
    expect(container.querySelector('.pp-body .hint')).not.toBeNull();
  });
});

describe('the card of a step', () => {
  const card = (index = 0) => container.querySelectorAll<HTMLElement>('.pp-steps > li')[index];

  it('has a head with its name and the buttons Move up, Move down and Remove, each with its tooltip, as symbols', async () => {
    select(scene());
    await openPanel();
    click(button('Normalize'));
    click(button('Mask by class'));
    const head = card(0).querySelector('.pp-step-head')!;
    expect(head.querySelector('.pp-step-title')!.textContent).toContain('1. Normalize');
    expect([...head.querySelectorAll('button')].map((b) => [b.getAttribute('aria-label'), tipOf(b), b.querySelector('svg')?.getAttribute('class')?.split(' ').at(-1), b.textContent])).toEqual([
      ['Move up', 'Move this step up', 'lucide-arrow-up', ''],
      ['Move down', 'Move this step down', 'lucide-arrow-down', ''],
      ['Remove', 'Remove this step', 'lucide-trash-2', ''],
    ]);
    // The first cannot move up and the last cannot move down; the middle ones can both.
    expect(button('Move up', card(0)).disabled).toBe(true);
    expect(button('Move down', card(0)).disabled).toBe(false);
    expect(button('Move up', card(1)).disabled).toBe(false);
    expect(button('Move down', card(1)).disabled).toBe(true);
  });

  it('moves and removes a step with the buttons of its head', async () => {
    select(scene());
    await openPanel();
    click(button('Normalize'));
    click(button('Mask by class'));
    expect(store().steps.map((s) => s.op)).toEqual(['normalize', 'mask']);
    click(button('Move down', card(0)));
    expect(store().steps.map((s) => s.op)).toEqual(['mask', 'normalize']);
    click(button('Remove', card(0)));
    expect(store().steps.map((s) => s.op)).toEqual(['normalize']);
  });

  it('offers "Rename" only where a step has a name, and takes it to the field of the name, which keeps the rules', async () => {
    select(scene());
    await openPanel();
    click(button('Normalize'));
    expect([...card(0).querySelectorAll('button')].some((b) => b.getAttribute('aria-label') === 'Rename')).toBe(false);
    await addBandMath('nir - red');
    const rename = button('Rename', card(1));
    expect(tipOf(rename)).toBe('Rename the band this step adds');
    click(rename);
    expect(document.activeElement).toBe(nameField(0));
    // Typing a name that breaks a rule is told at once, as before: the head only moves the cursor.
    typeInto(nameField(0), 'not a name');
    expect(card(1).querySelector('.error')).not.toBeNull();
  });

  it('keeps the fields of every operator in one grid: a name and a control, as in the settings bar', async () => {
    select(scene());
    await openPanel();
    for (const op of ['Band math', 'Reproject and resample', 'Normalize', 'Mask by class']) click(button(op));
    const fields = [...container.querySelectorAll('.pp-steps label.vc-field.pp-field')];
    expect(fields.length).toBeGreaterThan(4);
    for (const field of fields) expect(field.firstElementChild!.classList.contains('pp-label') || field.firstElementChild!.tagName === 'SPAN', field.textContent ?? '').toBe(true);
    expect(rule('.processing-panel .vc-field,\n.inspector .vc-field')).toContain('grid-template-columns: var(--form-label-width) minmax(0, 1fr)');
  });
});

describe('what the panel does not do', () => {
  it('stays open on Escape, in the panel, in a field and on the map: Esc closes nothing (Otto, 2.11.2026)', async () => {
    select(scene());
    await openPanel();
    click(button('Band math'));
    for (const target of [container.querySelector('.processing-panel')!, expression(0), document.body, document]) {
      act(() => void target.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true, cancelable: true })));
    }
    expect(store().open).toBe(true);
    expect(container.querySelector('.processing-panel')).not.toBeNull();
    expect(store().steps).toHaveLength(1);
    // The red x does close it: the test above would pass for a panel that cannot.
    click(container.querySelector<HTMLButtonElement>('.pp-head .close-x')!);
    expect(store().open).toBe(false);
  });

  it('draws the colormap of the preview with the field every other place uses, "More…" and "Reverse" included', async () => {
    select(scene());
    await openPanel();
    await addBandMath('(nir - red) / (nir + red)');
    await flush();
    const preview = container.querySelector('section[aria-label="Preview on the map"]')!;
    const field = preview.querySelector('label.vc-colormap');
    expect(field, preview.textContent ?? '').not.toBeNull();
    expect(field!.querySelector('.vc-colormap-row select')).not.toBeNull();
    expect(field!.querySelector('button.vc-reverse')).not.toBeNull();
    expect([...field!.querySelectorAll('option')].map((o) => o.textContent)).toContain('More…');
  });
});

describe('the layout contract in index.css (UI-03b)', () => {
  it('gives the sheet the wide width of the tokens, from the top to the foot, with a line on the left and no corners', () => {
    const sheet = rule('.processing-sheet');
    for (const declaration of ['top: 0', 'right: 0', 'bottom: 0', 'width: var(--sheet-wide-width)']) expect(sheet).toContain(declaration);
    expect(rule('  .processing-sheet .processing-panel')).toContain('border-radius: 0');
    expect(/--sheet-wide-width: clamp\(520px, 34vw, 640px\)/u.test(tokens)).toBe(true);
    expect(css).not.toContain('--pp-sheet-width');
  });

  it('makes every control of the panel at least as high as a control, which is a finger high on touch and under 900 px', () => {
    // A button with only an icon is square and a control high (UI-04 part 3a: the one `.icon-btn`, no `.pp-icon-btn` of its own).
    expect(css).toMatch(/(?<!,)\n\.icon-btn \{[^}]*\n  width: var\(--control-height\);\n  height: var\(--control-height\);/u);
    expect(rule('.btn')).toContain('min-height: var(--control-height)');
    expect(rule('.btn.seg')).toContain('font-size: var(--text-xs)');
    expect(rule('.pp-details summary')).toContain('min-height: var(--control-height)');
    expect(rule('.pp-check')).toContain('min-height: var(--control-height)');
    expect(rule('.pp-title-row')).toContain('min-height: var(--control-height)');
  });

  it('puts the map controls and the status line left of the sheet while it is open (wide windows)', () => {
    expect(css).toMatch(/@media \(min-width: 900px\) \{[^@]*\.app\.has-sheet \.maplibregl-ctrl-bottom-right \{\s*right: var\(--sheet-wide-width\);/u);
  });

  it('is a sheet from the bottom under 900 px with a narrower column of labels, the name of a step over its buttons', () => {
    const narrow = css.slice(css.indexOf('@media (max-width: 899px) {\n  /* The panel lies over the map'));
    expect(narrow).toContain('--form-label-width: 96px');
    expect(narrow).toMatch(/\.pp-step-head \{\s*flex-wrap: wrap;/u);
  });
});
