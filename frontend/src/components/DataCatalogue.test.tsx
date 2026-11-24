// @vitest-environment jsdom
//
// The Data catalogue (UI-05 §4): a window opened and closed with its symbol in the rail and closed with the red x, never by
// Esc or a click beside it; groups in the order of `earthx:category`, "Add" and "Remove" for "Search and area", the
// details of one dataset, and marks for a prototype source and one that needs an account. Synthetic collections only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '../App';
import { datasetsFrom } from '../datasets';
import { resetJobs, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection } from '../types';

vi.mock('./MapView', () => ({ default: () => null }));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

const VIEWER = { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'preview_tiles' as const, quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'own' as const, overview_resampling: null, overview_substitute: null };
const CAPABILITIES = { roi: true, time_range: true, band_math: true, interpolation: false, quad_pol: false, single_coverage_product: false, ml_processing: false };

function collection(id: string, title: string, category: string | null, extra: Partial<Collection> = {}): Collection {
  return {
    id,
    title,
    'earthx:category': category,
    'earthx:viewer': VIEWER,
    'earthx:capabilities': CAPABILITIES,
    'earthx:source': { asset_hosts: ['assets.example.org'], endpoint: 'https://stac.example.org/v1', page_url: 'https://viewer.example.org/collections/' + id, source_collection_id: id },
    extent: { spatial: { bbox: [[-180, -60, 180, 84]] }, temporal: { interval: [['2020-01-01T00:00:00Z', null]] } },
    ...extra,
  } as Collection;
}

// A listed entry (M5-40): a catalogue entry with a link, no viewer, keywords from its source.
function listed(id: string, title: string, category: string, extra: Partial<Collection> = {}): Collection {
  return {
    id,
    title,
    keywords: ['flood', 'gauges'],
    'earthx:entry': 'listed',
    'earthx:category': category,
    'earthx:access': { cors: null, account: 'paid', delivery: 'order' },
    'earthx:listing': { source_url: `https://data.example.org/${id}`, publisher: 'Example Office', approved_on: '2026-11-10' },
    links: [{ rel: 'via', href: `https://data.example.org/${id}` }],
    extent: { spatial: { bbox: [[6, 47, 15, 55]] }, temporal: { interval: [[null, null]] } },
    ...extra,
  } as Collection;
}

// Synthetic classes of a band (M5-62), as the collection publishes them.
const RAW_CLASSES = [
  { value: 1, name: 'low', title: 'Low', color_hint: '1F77B4' },
  { value: 2, name: 'high', title: 'High', color_hint: 'FF7F0E' },
];

const FULL = [
  collection('relief', 'Relief model', 'elevation', {
    'earthx:band_units': { data: 'm', raw: 'DN', ratio: '1' },
    'earthx:bands': [{ name: 'data', description: 'Surface height (DSM)' }, { name: 'raw', description: 'Raw counts', 'classification:classes': RAW_CLASSES }, { name: 'ratio', description: 'Share' }],
  }),
  collection('beta', 'Beta optical', 'optical'),
  collection('alpha', 'Alpha optical', 'optical'),
  // The backend publishes `earthx:notices` (DS-04b); the viewer shows none of them (Otto, 10.11.2026).
  collection('odd', 'Odd one', 'other', {
    'earthx:notices': [
      { code: 'approximate_geolocation', label: 'Approximate geolocation', tooltip: 'Placed by ground control points.' },
    ],
  } as Partial<Collection>),
  collection('broken', 'Broken entry', 'optical', { 'earthx:viewer': null }),
  collection('closed', 'Closed source', 'radar', { 'earthx:access': { cors: null, account: 'free_account' } }),
  collection('proto', 'Prototype source', 'radar', { 'earthx:legal_status': 'unclear', 'earthx:legal_note': 'The terms of reuse are not published' }),
];
const LISTED = [
  listed('gauges', 'Gauges of the Danube', 'water'),
  listed('coast', 'Coastline', 'water'),
  listed('aerial', 'Aerial photos 1950', 'optical'),
];
const COLLECTIONS = [...FULL, ...LISTED];

// What `/stac/collections` answers (M5-40): pages of one category or of the full entries, by title, with a token.
const CATEGORIES = [
  { id: 'optical', title: 'Optical imagery' },
  { id: 'radar', title: 'Radar' },
  { id: 'elevation', title: 'Elevation' },
  { id: 'land_cover', title: 'Land cover and land use' },
  { id: 'weather_climate', title: 'Weather and climate' },
  { id: 'water', title: 'Water and sea' },
  { id: 'nature', title: 'Nature and environment' },
  { id: 'geology_soil', title: 'Geology and soil' },
  { id: 'boundaries', title: 'Boundaries, addresses and cadastre' },
  { id: 'infrastructure', title: 'Buildings, transport and utilities' },
  { id: 'population', title: 'Population and society' },
  { id: 'agriculture', title: 'Agriculture and forestry' },
  { id: 'other', title: 'Other' },
];
const REGIONS = [
  { code: 'AT', name: 'Austria', level: 'state' },
  { code: 'DE', name: 'Germany', level: 'state' },
  { code: 'DE-BY', name: 'Bayern', level: 'subdivision', state: 'DE' },
];

// What the backend answers (M5-40): pages of one category or of the full entries, by title, with a token, by GET or by
// POST with filters; and the lists of `/catalogue`. The filters of a POST are recorded, not applied, except `region`.
function backend(pool: Collection[]) {
  const requests: URLSearchParams[] = [];
  const bodies: Record<string, unknown>[] = [];
  const fetchStub = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), 'http://test');
    if (url.pathname === '/catalogue/categories') return new Response(JSON.stringify({ categories: CATEGORIES }), { status: 200 });
    if (url.pathname === '/catalogue/regions') return new Response(JSON.stringify({ regions: REGIONS }), { status: 200 });
    const body = init?.method === 'POST' ? (JSON.parse(String(init.body)) as Record<string, unknown>) : null;
    if (body) bodies.push(body);
    const params = body
      ? new URLSearchParams(Object.entries(body).filter(([, v]) => typeof v !== 'object').map(([k, v]) => [k, String(v)]))
      : url.searchParams;
    requests.push(params);
    let hits = pool;
    if (params.get('entry') === 'full') hits = hits.filter((c) => c['earthx:entry'] !== 'listed');
    if (params.has('category')) hits = hits.filter((c) => c['earthx:category'] === params.get('category'));
    const region = (body?.region as string[] | undefined)?.[0];
    if (region) hits = hits.filter((c) => ((c as { 'earthx:regions'?: string[] })['earthx:regions'] ?? []).includes(region));
    hits = [...hits].sort((a, b) => (a.title!.toLowerCase() < b.title!.toLowerCase() ? -1 : 1));
    if (body && typeof body.q === 'string') {
      // The search with text (M5-22c): full entries only (M5-40 F7), 20 a page by offset; here the title holds the text.
      const q = body.q.toLowerCase();
      const found = hits.filter((c) => c['earthx:entry'] !== 'listed' && c.title!.toLowerCase().includes(q));
      const offset = Number(body.offset ?? 0);
      const more = offset + 20 < found.length;
      return new Response(
        JSON.stringify({
          collections: found.slice(offset, offset + 20),
          links: more ? [{ rel: 'next', method: 'POST', href: '/stac/collections', body: { ...body, offset: offset + 20 } }] : [],
          numberMatched: found.length,
        }),
        { status: 200 },
      );
    }
    const start = Number(params.get('token') ?? '0');
    const limit = Number(params.get('limit') ?? '100');
    const page = hits.slice(start, start + limit);
    const nextToken = start + limit < hits.length ? String(start + limit) : null;
    const next = nextToken
      ? body
        ? { rel: 'next', method: 'POST', href: 'http://api.example.org/stac/collections', body: { ...body, token: nextToken } }
        : { rel: 'next', href: `http://api.example.org/stac/collections?${new URLSearchParams({ ...Object.fromEntries(params), token: nextToken })}` }
      : null;
    const answer = {
      collections: page,
      links: next ? [next] : [],
      ...(params.has('token') || hits.length > 10_000 ? {} : { numberMatched: hits.length }),
    };
    return new Response(JSON.stringify(answer), { status: 200 });
  });
  return { fetchStub, requests, bodies };
}

// IntersectionObserver as the window would drive it: a test says when the end of a group shows.
const observed: { target: Element; callback: IntersectionObserverCallback }[] = [];
class FakeObserver {
  private readonly callback: IntersectionObserverCallback;
  constructor(callback: IntersectionObserverCallback) {
    this.callback = callback;
  }
  observe(target: Element) {
    observed.push({ target, callback: this.callback });
  }
  disconnect() {
    for (let i = observed.length - 1; i >= 0; i -= 1) if (observed[i].callback === this.callback) observed.splice(i, 1);
  }
}
async function scrollToEnds() {
  await act(async () => {
    for (const { target, callback } of [...observed]) {
      callback([{ isIntersecting: true, target } as IntersectionObserverEntry], {} as IntersectionObserver);
    }
  });
  await act(async () => {});
}

const catalogueWindow = () => container.querySelector<HTMLElement>('#data-catalogue');
const symbol = () => container.querySelector<HTMLButtonElement>('#rail-catalogue')!;
const click = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const groupNames = () => [...container.querySelectorAll('.catalogue-group-name')].map((el) => el.textContent);
const entryTitles = () => [...container.querySelectorAll('.catalogue-entry-title')].map((el) => el.textContent);
const entry = (title: string) =>
  [...container.querySelectorAll<HTMLElement>('.catalogue-entry')].find((el) => el.querySelector('.catalogue-entry-title')?.textContent === title)!;
const action = (title: string) => entry(title).querySelector<HTMLElement>('.catalogue-action')!;

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  observed.length = 0;
  vi.stubGlobal('IntersectionObserver', FakeObserver);
  vi.stubGlobal('fetch', backend(COLLECTIONS).fetchStub);
  useProcessingStore.setState({ open: false, detailJobID: null, jobs: [] });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<App />));
  // The App loads the full entries of the stubbed backend first; the datasets of the test come after.
  await act(async () => {});
  act(() =>
    useAppStore.setState({
      datasets: datasetsFrom(FULL),
      catalogueCategories: CATEGORIES,
      catalogueRegions: null,
      catalogueFilter: { bySearchPanel: false, region: '', from: '', to: '', category: '' },
      catalogueSearch: '',
      dateFrom: '',
      dateTo: '',
      aoi: null,
      addedDatasetIds: ['relief'],
      selectedDatasetIds: [],
      datasetId: null,
      catalogueOpen: false,
      sections: [],
      dock: null,
      searching: false,
      sceneLookupLoading: false,
    }),
  );
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  resetJobs();
  localStorage.clear();
  vi.unstubAllGlobals();
});

describe('the window', () => {
  it('opens with its symbol, the second in the rail, and closes with a second click', () => {
    expect(catalogueWindow()).toBeNull();
    expect(symbol().getAttribute('aria-expanded')).toBe('false');
    click(symbol());
    expect(catalogueWindow()).not.toBeNull();
    expect(symbol().getAttribute('aria-expanded')).toBe('true');
    expect(symbol().getAttribute('aria-controls')).toBe('data-catalogue');
    click(symbol());
    expect(catalogueWindow()).toBeNull();
  });

  it('closes with the red x in its head', () => {
    click(symbol());
    click(catalogueWindow()!.querySelector('.catalogue-head .close-x')!);
    expect(catalogueWindow()).toBeNull();
  });

  it('does not close with Esc, nor with a click beside it on the map', () => {
    click(symbol());
    act(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    act(() => catalogueWindow()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    click(container.querySelector('.app')!);
    expect(catalogueWindow()).not.toBeNull();
  });

  it('leaves the panel of the dock as it is', () => {
    act(() => useAppStore.setState({ dock: 'controls' }));
    click(symbol());
    expect(useAppStore.getState().dock).toBe('controls');
    expect(catalogueWindow()!.classList.contains('beside-dock')).toBe(true);
  });

  it('gives way to a panel of the rail in a narrow window, where it would cover it, and shows the panel open under it', () => {
    const narrow = vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} }));
    vi.stubGlobal('matchMedia', narrow);
    act(() => useAppStore.setState({ dock: 'controls' }));
    click(symbol());
    click(container.querySelector('#rail-controls')!);
    expect(catalogueWindow()).toBeNull();
    expect(useAppStore.getState().dock).toBe('controls');
    click(symbol());
    click(container.querySelector('#rail-layers')!);
    expect(catalogueWindow()).toBeNull();
    expect(useAppStore.getState().dock).toBe('layers');
  });

  it('stays open beside a panel opened in a wide window', () => {
    vi.stubGlobal('matchMedia', vi.fn(() => ({ matches: false, addEventListener() {}, removeEventListener() {} })));
    click(symbol());
    click(container.querySelector('#rail-layers')!);
    expect(catalogueWindow()).not.toBeNull();
    expect(useAppStore.getState().dock).toBe('layers');
  });

  it('has a head of its own with the title, the place for the search later', () => {
    click(symbol());
    expect(catalogueWindow()!.querySelector('.catalogue-head h2')?.textContent).toBe('Data catalogue');
  });
});

describe('the list', () => {
  beforeEach(async () => {
    click(symbol());
    await act(async () => {});
  });

  it('groups full and listed entries by category in the order of categories.yaml, each by title, "Other" last', () => {
    expect(groupNames()).toEqual(['Optical imagery', 'Radar', 'Elevation', 'Water and sea', 'Other']);
    expect(entryTitles()).toEqual([
      'Aerial photos 1950', 'Alpha optical', 'Beta optical', 'Broken entry', 'Closed source', 'Prototype source',
      'Relief model', 'Coastline', 'Gauges of the Danube', 'Odd one',
    ]);
  });

  it('shows no group without entries', () => {
    expect(groupNames()).not.toContain('Nature and environment');
  });

  it('counts the entries of a group in its head', () => {
    const head = [...container.querySelectorAll('.catalogue-group-head')].find((h) => h.textContent?.includes('Water and sea'))!;
    expect(head.querySelector('.catalogue-group-count')?.textContent).toBe('2');
  });

  it('links a listed entry to its page at the source, without a mark and without "Add"', () => {
    const link = action('Gauges of the Danube');
    expect(link.tagName).toBe('A');
    expect(link.textContent).toBe('Source');
    expect(link.getAttribute('href')).toBe('https://data.example.org/gauges');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(entry('Gauges of the Danube').querySelector('.badge')).toBeNull();
  });

  it('folds a group with its head and opens it again', () => {
    const head = container.querySelector<HTMLButtonElement>('.catalogue-group-head')!;
    expect(head.getAttribute('aria-expanded')).toBe('true');
    click(head);
    expect(head.getAttribute('aria-expanded')).toBe('false');
    expect(entryTitles()).not.toContain('Alpha optical');
    click(head);
    expect(entryTitles()).toContain('Alpha optical');
  });

  it('offers "Remove" for a dataset in the panel and "Add" for the others', () => {
    expect(action('Relief model').textContent).toBe('Remove');
    expect(action('Alpha optical').textContent).toBe('Add');
  });

  it('"Add" puts the dataset at the end of the panel without choosing it, and saves the list', () => {
    click(action('Alpha optical'));
    const s = useAppStore.getState();
    expect(s.addedDatasetIds).toEqual(['relief', 'alpha']);
    expect(s.selectedDatasetIds).toEqual([]);
    expect(s.revealedDataset?.id).toBe('alpha');
    expect(JSON.parse(localStorage.getItem('earthx.datasets')!)).toEqual(['relief', 'alpha']);
    expect(action('Alpha optical').textContent).toBe('Remove');
  });

  it('"Remove" takes a chosen dataset out of the panel and unchooses it, and keeps the results', () => {
    const sections = [{ datasetId: 'relief', items: [], groups: [] }] as never;
    act(() => useAppStore.setState({ selectedDatasetIds: ['relief'], datasetId: 'relief', sections }));
    click(action('Relief model'));
    const s = useAppStore.getState();
    expect(s.addedDatasetIds).toEqual([]);
    expect(s.selectedDatasetIds).toEqual([]);
    expect(s.sections).toBe(sections);
    expect(JSON.parse(localStorage.getItem('earthx.datasets')!)).toEqual([]);
  });

  it('locks "Remove" of a chosen dataset while a search runs, with the reason', () => {
    act(() => useAppStore.setState({ selectedDatasetIds: ['relief'], searching: true }));
    const remove = action('Relief model');
    expect(remove.getAttribute('aria-disabled')).toBe('true');
    expect(remove.getAttribute('data-tip')).toBe('Wait until the search is finished');
    click(remove);
    expect(useAppStore.getState().addedDatasetIds).toEqual(['relief']);
  });

  it('locks "Add" of a dataset that cannot be shown, with the reason, and adds nothing', () => {
    const add = action('Broken entry');
    expect(add.getAttribute('aria-disabled')).toBe('true');
    expect(add.getAttribute('data-tip')).toMatch(/^Not viewable: earthx:viewer/u);
    click(add);
    expect(useAppStore.getState().addedDatasetIds).toEqual(['relief']);
  });

  it('links a dataset that needs an account to its source instead of "Add", marked "Account"', () => {
    const link = action('Closed source');
    expect(link.tagName).toBe('A');
    expect(link.getAttribute('href')).toBe('https://viewer.example.org/collections/closed');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
    expect(entry('Closed source').querySelector('.badge')?.textContent).toBe('Account');
    expect(useAppStore.getState().addDataset('closed')).toBeUndefined();
    expect(useAppStore.getState().addedDatasetIds).toEqual(['relief']);
  });

  it('marks a prototype source, and only that one, as "Prototype"', () => {
    expect(entry('Prototype source').querySelector('.badge')?.textContent).toBe('Prototype');
    const marked = [...container.querySelectorAll('.catalogue-entry')].filter((el) => el.querySelector('.badge')?.textContent === 'Prototype');
    expect(marked).toHaveLength(1);
  });

  it('shows the notices of a dataset as no mark: they are a sentence of its description (Otto, 10.11.2026)', () => {
    expect(entry('Odd one').querySelector('.badge')).toBeNull();
    expect(container.textContent).not.toContain('Approximate geolocation');
  });

  it('has no tooltip at the name of a dataset', () => {
    for (const name of container.querySelectorAll('.catalogue-entry-name')) expect(name.hasAttribute('data-tip')).toBe(false);
  });
});

describe('the details', () => {
  beforeEach(async () => {
    click(symbol());
    await act(async () => {});
  });

  const value = (label: string) =>
    [...container.querySelectorAll('.catalogue-row-pair')].find((el) => el.querySelector('dt')?.textContent === label)?.querySelector('dd');

  it('ask for a choice until a dataset is clicked', () => {
    expect(container.querySelector('.catalogue-empty')?.textContent).toBe('Choose a dataset to see its details');
    click(entry('Alpha optical').querySelector('.catalogue-entry-name')!);
    expect(container.querySelector('.catalogue-details h3')?.textContent).toBe('Alpha optical');
    expect(entry('Alpha optical').getAttribute('aria-current')).toBe('true');
  });

  it('show the rows in the order of a STAC browser, "—" where the collection carries nothing', () => {
    click(entry('Alpha optical').querySelector('.catalogue-entry-name')!);
    const labels = [...container.querySelectorAll('.catalogue-row-pair dt')].map((dt) => dt.textContent);
    expect(labels).toEqual([
      'Description', 'Keywords', 'Provider', 'Source', 'License', 'Attribution', 'Spatial extent', 'Temporal extent', 'Resolution',
      'Bands', 'Data region', 'Citation', 'Last checked', 'Maturity', 'Processing', 'Quick processing',
    ]);
    expect(value('Provider')?.textContent).toBe('—');
    expect(value('Spatial extent')?.textContent).toBe('180° W – 180° E · 60° S – 84° N');
    expect(value('Temporal extent')?.textContent).toBe('2020-01-01 – today');
    expect(value('Last checked')?.textContent).toBe('—');
  });

  it('show the bands as a table Band | Description | Unit, without a text around it (M5-59)', () => {
    click(entry('Relief model').querySelector('.catalogue-entry-name')!);
    const table = value('Bands')!.querySelector('table.catalogue-bands')!;
    expect([...table.querySelectorAll('thead th')].map((th) => th.textContent)).toEqual(['Band', 'Description', 'Unit']);
    expect([...table.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((cell) => cell.textContent))).toEqual([
      ['data', 'Surface height (DSM)', 'm'],
      ['raw', 'Raw counts', 'DN, uncalibrated digital numbers'],
      ['ratio', 'Share', '–'],
    ]);
    expect(value('Bands')!.querySelectorAll('p, .hint')).toHaveLength(0);
  });

  it('show the classes of a band under the bands: the band as heading, Value | Class | Colour, a swatch and the hex (M5-62)', () => {
    click(entry('Relief model').querySelector('.catalogue-entry-name')!);
    const tables = value('Bands')!.querySelectorAll('table');
    expect(tables).toHaveLength(2);
    const classes = value('Bands')!.querySelector('table.catalogue-classes')!;
    expect(classes.querySelector('caption')?.textContent).toBe('raw');
    expect([...classes.querySelectorAll('thead th')].map((th) => th.textContent)).toEqual(['Value', 'Class', 'Colour']);
    expect([...classes.querySelectorAll('tbody tr')].map((tr) => [...tr.children].map((cell) => cell.textContent))).toEqual([
      ['1', 'Low', '#1f77b4'],
      ['2', 'High', '#ff7f0e'],
    ]);
    const swatches = [...classes.querySelectorAll<HTMLElement>('.class-swatch')];
    expect(swatches.map((swatch) => swatch.style.background)).toEqual(['rgb(31, 119, 180)', 'rgb(255, 127, 14)']);
    expect(value('Bands')!.querySelectorAll('p, .hint')).toHaveLength(0);
  });

  it('show no table of classes for a dataset whose bands have none', () => {
    click(entry('Alpha optical').querySelector('.catalogue-entry-name')!);
    expect(container.querySelector('table.catalogue-classes')).toBeNull();
  });

  it('keep "—" and no table where a dataset has no bands', () => {
    click(entry('Alpha optical').querySelector('.catalogue-entry-name')!);
    expect(value('Bands')!.querySelector('table')).toBeNull();
    expect(value('Bands')!.textContent).toBe('—');
  });

  it('say "Not checked yet" behind the (i) of "Last checked"', () => {
    click(entry('Alpha optical').querySelector('.catalogue-entry-name')!);
    const row = [...container.querySelectorAll('.catalogue-row-pair')].find((el) => el.querySelector('dt')?.textContent === 'Last checked')!;
    expect(row.querySelector('.tip')?.getAttribute('data-tip')).toBe('Not checked yet');
  });

  it('put the note of a prototype source behind a warning at the title', () => {
    click(entry('Prototype source').querySelector('.catalogue-entry-name')!);
    expect(container.querySelector('.catalogue-title .tip.warn')?.getAttribute('data-tip')).toBe('The terms of reuse are not published');
  });

  it('go back to the list with "Back"', () => {
    click(entry('Alpha optical').querySelector('.catalogue-entry-name')!);
    expect(catalogueWindow()!.classList.contains('showing-details')).toBe(true);
    click(container.querySelector('.catalogue-back')!);
    expect(catalogueWindow()!.classList.contains('showing-details')).toBe(false);
    expect(container.querySelector('.catalogue-details')).toBeNull();
  });
});

describe('a listed entry in the details', () => {
  beforeEach(async () => {
    click(symbol());
    await act(async () => {});
    click(entry('Gauges of the Danube').querySelector('.catalogue-entry-name')!);
  });

  const labels = () => [...container.querySelectorAll('.catalogue-row-pair dt')].map((dt) => dt.textContent);
  const value = (label: string) =>
    [...container.querySelectorAll('.catalogue-row-pair')].find((el) => el.querySelector('dt')?.textContent === label)?.querySelector('dd');

  it('show its keywords and its source, and no rows that belong to display or processing', () => {
    expect(value('Keywords')?.textContent).toBe('floodgauges');
    expect([...value('Keywords')!.querySelectorAll('.catalogue-value')].map((v) => v.textContent)).toEqual(['flood', 'gauges']);
    expect(value('Source')?.querySelector('a')?.getAttribute('href')).toBe('https://data.example.org/gauges');
    expect(labels()).not.toContain('Bands');
    expect(labels()).not.toContain('Processing');
    expect(labels()).not.toContain('Quick processing');
  });

  it('carry no mark at the title', () => {
    expect(container.querySelector('.catalogue-title .badge')).toBeNull();
  });
});

describe('paging', () => {
  const many = Array.from({ length: 120 }, (_, i) => listed(`entry-${String(i).padStart(3, '0')}`, `Entry ${String(i).padStart(3, '0')}`, 'nature'));

  it('loads a group a page at a time, the next one when the end of the group shows, until the last', async () => {
    const { fetchStub, requests } = backend([...COLLECTIONS, ...many]);
    vi.stubGlobal('fetch', fetchStub);
    click(symbol());
    await act(async () => {});
    const nature = () => [...container.querySelectorAll('.catalogue-group')].find((g) => g.getAttribute('aria-label') === 'Nature and environment')!;
    const titles = () => [...nature().querySelectorAll('.catalogue-entry-title')].map((el) => el.textContent);
    expect(titles()).toHaveLength(50);
    expect(nature().querySelector('.catalogue-group-count')?.textContent).toBe('120');
    await scrollToEnds();
    expect(titles()).toHaveLength(100);
    await scrollToEnds();
    expect(titles()).toEqual(many.map((c) => c.title));
    expect(nature().querySelector('.catalogue-more')).toBeNull();
    const pages = requests.filter((p) => p.get('category') === 'nature');
    expect(pages.map((p) => [p.get('limit'), p.get('token')])).toEqual([['50', null], ['50', '50'], ['50', '100']]);
  });

  it('asks for every group by its category, never for the whole list', async () => {
    const { fetchStub, requests } = backend(COLLECTIONS);
    vi.stubGlobal('fetch', fetchStub);
    click(symbol());
    await act(async () => {});
    const asked = requests.map((p) => p.get('category')).filter((c): c is string => c !== null);
    expect(new Set(asked)).toEqual(new Set([
      'optical', 'radar', 'elevation', 'land_cover', 'weather_climate', 'water', 'nature', 'geology_soil', 'boundaries',
      'infrastructure', 'population', 'agriculture', 'other',
    ]));
    expect(requests.every((p) => p.has('category') || p.get('entry') === 'full')).toBe(true);
  });

  it('says so in the group where a page cannot be loaded, and keeps what it has', async () => {
    const { fetchStub } = backend([...COLLECTIONS, ...many]);
    vi.stubGlobal('fetch', fetchStub);
    click(symbol());
    await act(async () => {});
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{"detail":"broken"}', { status: 500 })));
    await scrollToEnds();
    const nature = [...container.querySelectorAll('.catalogue-group')].find((g) => g.getAttribute('aria-label') === 'Nature and environment')!;
    expect(nature.querySelectorAll('.catalogue-entry-title')).toHaveLength(50);
    expect(nature.querySelector('.catalogue-error')?.textContent).toMatch(/^Could not load/u);
  });
});


describe('the filters (Otto, 16.11.2026)', () => {
  const change = (el: HTMLInputElement | HTMLSelectElement, value: string) =>
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(el), 'value')!.set!;
      setter.call(el, value);
      el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }));
    });
  const filtersButton = () => container.querySelector<HTMLButtonElement>('.catalogue-head .catalogue-filters-btn')!;
  const popup = () => document.querySelector<HTMLElement>('.catalogue-filters-popup');
  const panelSwitch = () => popup()!.querySelector<HTMLInputElement>('input[role="switch"]')!;
  const select = (label: string) => popup()?.querySelector<HTMLSelectElement>(`select[aria-label="${label}"]`) ?? null;
  const day = (label: string) => popup()?.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`) ?? null;
  const clear = (label: string) => popup()?.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`) ?? null;
  const aoi = { type: 'Polygon', coordinates: [[[7, 46], [8, 46], [8, 47], [7, 47], [7, 46]]] } as GeoJSON.Geometry;
  let stub: ReturnType<typeof backend>;

  beforeEach(async () => {
    stub = backend(COLLECTIONS);
    vi.stubGlobal('fetch', stub.fetchStub);
    click(symbol());
    await act(async () => {});
  });

  const openFilters = async () => {
    click(filtersButton());
    await act(async () => {});
  };

  it('are a button "Filters" in the head that opens a pop-up, not a row of their own', async () => {
    expect(container.querySelector('.catalogue-head + .catalogue-filters')).toBeNull();
    expect(filtersButton().textContent).toBe('Filters');
    expect(filtersButton().getAttribute('aria-expanded')).toBe('false');
    await openFilters();
    expect(filtersButton().getAttribute('aria-expanded')).toBe('true');
    expect(popup()!.querySelector('label')?.textContent).toBe('Filter by search panel');
    expect([...popup()!.querySelectorAll('select')].map((s) => s.getAttribute('aria-label'))).toEqual(['Region', 'Category']);
    expect([...popup()!.querySelectorAll('input[type="date"]')].map((i) => i.getAttribute('aria-label'))).toEqual(['From date', 'To date']);
  });

  it('give every field an "×" to empty it while it has a value', async () => {
    await openFilters();
    expect(clear('Clear region')).toBeNull();
    change(select('Region')!, 'DE-BY');
    change(day('From date')!, '2020-01-01');
    change(day('To date')!, '2020-12-31');
    change(select('Category')!, 'water');
    for (const label of ['Clear region', 'Clear from date', 'Clear to date', 'Clear category']) {
      click(clear(label)!);
    }
    await act(async () => {});
    expect(useAppStore.getState().catalogueFilter).toEqual({ bySearchPanel: false, region: '', from: '', to: '', category: '' });
  });

  it('count what is set on the button, like "Advanced search"', async () => {
    await openFilters();
    change(select('Region')!, 'DE-BY');
    change(select('Category')!, 'water');
    expect(filtersButton().textContent).toBe('Filters · 2');
  });

  it('lock "Filter by search panel" without an AOI in the search panel, with the reason, and leave it off', async () => {
    await openFilters();
    expect(panelSwitch().getAttribute('aria-disabled')).toBe('true');
    expect(panelSwitch().closest('label')?.getAttribute('data-tip')).toBe('Draw an AOI to use this filter');
    click(panelSwitch());
    expect(useAppStore.getState().catalogueFilter.bySearchPanel).toBe(false);
  });

  it('take AOI and period of the search panel once the switch is on, and hide region and from/to', async () => {
    act(() => useAppStore.setState({ aoi, dateFrom: '2019-01-01', dateTo: '2019-06-30' }));
    await openFilters();
    change(select('Region')!, 'DE-BY');
    await act(async () => {});
    stub.bodies.length = 0;
    click(panelSwitch());
    await act(async () => {});
    expect(panelSwitch().checked).toBe(true);
    expect(select('Region')).toBeNull();
    expect(day('From date')).toBeNull();
    expect(day('To date')).toBeNull();
    expect(select('Category')).not.toBeNull();
    expect(stub.bodies.length).toBeGreaterThan(0);
    for (const body of stub.bodies) {
      expect(body.intersects).toEqual(aoi);
      expect(body.datetime).toBe('2019-01-01T00:00:00Z/2019-06-30T23:59:59Z');
      expect(body.region).toBeUndefined();
    }
    expect(filtersButton().textContent).toBe('Filters · 1');
  });

  it('keep the switch on for the session, and fall back to region and from/to when the AOI goes', async () => {
    act(() => useAppStore.setState({ aoi }));
    await openFilters();
    click(panelSwitch());
    click(symbol());
    click(symbol());
    await act(async () => {});
    await openFilters();
    expect(panelSwitch().checked).toBe(true);
    act(() => useAppStore.setState({ aoi: null }));
    await act(async () => {});
    expect(panelSwitch().checked).toBe(false);
    expect(panelSwitch().getAttribute('aria-disabled')).toBe('true');
    expect(select('Region')).not.toBeNull();
  });

  it('offer the regions, states with their subdivisions after them, and ask with the one chosen', async () => {
    await openFilters();
    expect([...select('Region')!.options].map((o) => o.textContent)).toEqual(['All regions', 'Austria', 'Germany', '   Bayern']);
    stub.bodies.length = 0;
    change(select('Region')!, 'DE-BY');
    await act(async () => {});
    expect(stub.bodies.every((b) => JSON.stringify(b.region) === '["DE-BY"]')).toBe(true);
    expect(groupNames()).toEqual([]);
    expect(container.querySelector('.catalogue-list .hint')?.textContent).toBe('No datasets to show');
  });

  it('ask with the period of the two days, either end open', async () => {
    await openFilters();
    change(day('From date')!, '2020-01-01');
    await act(async () => {});
    expect(stub.bodies.at(-1)?.datetime).toBe('2020-01-01T00:00:00Z/..');
    change(day('To date')!, '2020-12-31');
    await act(async () => {});
    expect(stub.bodies.at(-1)?.datetime).toBe('2020-01-01T00:00:00Z/2020-12-31T23:59:59Z');
    expect(day('From date')!.getAttribute('max')).toBe('2020-12-31');
    expect(day('To date')!.getAttribute('min')).toBe('2020-01-01');
  });

  it('show only the group of the category chosen', async () => {
    await openFilters();
    expect([...select('Category')!.options].map((o) => o.textContent)).toEqual(['All categories', ...CATEGORIES.map((c) => c.title)]);
    change(select('Category')!, 'water');
    await act(async () => {});
    expect(groupNames()).toEqual(['Water and sea']);
    change(select('Category')!, '');
    await act(async () => {});
    expect(groupNames()).toEqual(['Optical imagery', 'Radar', 'Elevation', 'Water and sea', 'Other']);
  });
});

describe('the search field (Otto, 16.11.2026)', () => {
  const field = () => container.querySelector<HTMLInputElement>('.catalogue-head .catalogue-search input')!;
  const type = async (text: string) => {
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      setter.call(field(), text);
      field().dispatchEvent(new Event('input', { bubbles: true }));
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });
    await act(async () => {});
  };
  let stub: ReturnType<typeof backend>;

  beforeEach(async () => {
    stub = backend(COLLECTIONS);
    vi.stubGlobal('fetch', stub.fetchStub);
    click(symbol());
    await act(async () => {});
  });

  it('stands in the head beside "Filters", with a magnifier, a placeholder and no "×" while empty', () => {
    const tools = container.querySelector('.catalogue-head .catalogue-tools')!;
    expect(tools.querySelector('.catalogue-search svg')).not.toBeNull();
    expect(field().getAttribute('placeholder')).toBe('Search datasets');
    expect(field().getAttribute('maxlength')).toBe('200');
    expect(tools.querySelector('.catalogue-search .clear-btn')).toBeNull();
    expect(tools.lastElementChild?.classList.contains('catalogue-filters-btn')).toBe(true);
  });

  it('shows the hits in the order of the search instead of the groups, and asks with q', async () => {
    await type('optical');
    expect(groupNames()).toEqual([]);
    expect([...container.querySelectorAll('.catalogue-hits .catalogue-entry-title')].map((e) => e.textContent)).toEqual(['Alpha optical', 'Beta optical']);
    expect(stub.bodies.at(-1)).toMatchObject({ q: 'optical' });
  });

  it('asks only once the typing stops', async () => {
    stub.bodies.length = 0;
    act(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      for (const text of ['o', 'op', 'opt']) {
        setter.call(field(), text);
        field().dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 350));
    });
    expect(stub.bodies.filter((b) => 'q' in b).map((b) => b.q)).toEqual(['opt']);
  });

  it('keeps the filters: the category and the period go with the text', async () => {
    act(() => useAppStore.setState({ catalogueFilter: { bySearchPanel: false, region: '', from: '2020-01-01', to: '', category: 'optical' } }));
    await type('optical');
    expect(stub.bodies.at(-1)).toMatchObject({ q: 'optical', category: 'optical', datetime: '2020-01-01T00:00:00Z/..' });
  });

  it('says so where nothing matches, and brings the groups back with its "×"', async () => {
    await type('nothing like this');
    expect(container.querySelector('.catalogue-list .hint')?.textContent).toBe('No datasets to show');
    click(container.querySelector('.catalogue-search .clear-btn')!);
    await act(async () => {});
    expect(field().value).toBe('');
    expect(groupNames()).toEqual(['Optical imagery', 'Radar', 'Elevation', 'Water and sea', 'Other']);
  });

  it('keeps the text for the session when the window closes and opens again', async () => {
    await type('relief');
    click(symbol());
    click(symbol());
    await act(async () => {});
    expect(field().value).toBe('relief');
    expect([...container.querySelectorAll('.catalogue-hits .catalogue-entry-title')].map((e) => e.textContent)).toEqual(['Relief model']);
  });

  it('loads more hits when their end shows', async () => {
    const many = Array.from({ length: 45 }, (_, i) => collection(`m${i}`, `Match ${String(i).padStart(2, '0')}`, 'optical'));
    vi.stubGlobal('fetch', backend([...COLLECTIONS, ...many]).fetchStub);
    await type('match');
    const hits = () => container.querySelectorAll('.catalogue-hits .catalogue-entry').length;
    expect(hits()).toBe(20);
    await scrollToEnds();
    expect(hits()).toBe(40);
    await scrollToEnds();
    expect(hits()).toBe(45);
  });
});

describe('the count in the head of a group (M5-40 H5)', () => {
  it('says "10,000+" where the API counts no further', async () => {
    const many = Array.from({ length: 10_001 }, (_, i) => listed(`e${i}`, `Entry ${String(i).padStart(5, '0')}`, 'population'));
    vi.stubGlobal('fetch', backend([...COLLECTIONS, ...many]).fetchStub);
    click(symbol());
    await act(async () => {});
    const head = [...container.querySelectorAll('.catalogue-group-head')].find((h) => h.textContent?.includes('Population and society'))!;
    expect(head.querySelector('.catalogue-group-count')?.textContent).toBe('10,000+');
  });
});

describe('without the categories of the backend', () => {
  it('says so instead of showing groups', async () => {
    act(() => useAppStore.setState({ catalogueCategories: [] }));
    click(symbol());
    await act(async () => {});
    expect(groupNames()).toEqual([]);
    expect(container.querySelector('.catalogue-list .hint')?.textContent).toBe('Could not load the categories');
  });
});
