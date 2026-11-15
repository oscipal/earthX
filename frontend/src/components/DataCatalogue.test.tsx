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
    'earthx:source': { asset_hosts: ['assets.example.org'], endpoint: 'https://stac.example.org/v1', source_collection_id: id },
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

const FULL = [
  collection('relief', 'Relief model', 'elevation'),
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
function backend(pool: Collection[]) {
  const requests: URLSearchParams[] = [];
  const fetchStub = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://test');
    const params = url.searchParams;
    requests.push(params);
    let hits = pool;
    if (params.get('entry') === 'full') hits = hits.filter((c) => c['earthx:entry'] !== 'listed');
    if (params.has('category')) hits = hits.filter((c) => c['earthx:category'] === params.get('category'));
    hits = [...hits].sort((a, b) => (a.title!.toLowerCase() < b.title!.toLowerCase() ? -1 : 1));
    const start = Number(params.get('token') ?? '0');
    const limit = Number(params.get('limit') ?? '100');
    const page = hits.slice(start, start + limit);
    const next = start + limit < hits.length ? new URLSearchParams({ ...Object.fromEntries(params), token: String(start + limit) }) : null;
    const body = {
      collections: page,
      links: next ? [{ rel: 'next', href: `http://api.example.org/stac/collections?${next}` }] : [],
      ...(params.has('token') ? {} : { numberMatched: hits.length }),
    };
    return new Response(JSON.stringify(body), { status: 200 });
  });
  return { fetchStub, requests };
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
    expect(link.getAttribute('href')).toBe('https://stac.example.org/v1');
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

