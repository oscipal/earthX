// @vitest-environment jsdom
//
// Permalinks in the processing panel (M4-19e): "Share" keeps the order and the view, an address with
// `?permalink=` brings them back. No backend, `fetch` answers by route.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import { bboxToPolygon } from '../geoUtils';
import { GONE_TEXT, KEYS_STORAGE, loadKeys, openPermalinkInAddress } from '../permalink';
import type { Order } from '../processing';
import { useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import ProcessingPanel from './ProcessingPanel';
import css from '../index.css?raw';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const DATASET = 'sentinel-2-c1-l2a';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const ID = 'AbCdEfGhIjKlMnOpQrSt_-';
const KEY = 'kKkKkKkKkKkKkKkKkKkKkK';
const OLD_AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
const SHARED_AOI = bboxToPolygon([10.1, 50.1, 10.2, 50.2]);
const EXPIRES = new Date(Date.now() + 30 * 86_400_000).toISOString();

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

const ORDER: Order = {
  recipe_version: 1,
  inputs: [{ name: 'input', dataset: DATASET, groups: [['NEW_A']], assets: ['red', 'nir'] }],
  aoi: SHARED_AOI as GeoJSON.Polygon,
  steps: [{ op: 'band_math', op_version: 1, params: { expression: '(nir - red) / (nir + red)' } }],
  output: { kind: 'raster', format: 'cog', dtype: 'float32' },
};
const VIEW = { center: [10.15, 50.15], zoom: 11.5, range: { vmin: 0, vmax: 0.8, colormap: 'viridis' } };

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

let fetchMock: ReturnType<typeof vi.fn>;
let container: HTMLDivElement;
let root: Root;
let link: () => Response;

const settle = () =>
  act(async () => {
    for (let i = 0; i < 8; i++) await Promise.resolve();
  });
const onAddress = (search: string) => window.history.replaceState(null, '', `/${search}`);
const open = async () => {
  await act(() => openPermalinkInAddress());
  await settle();
};
const draft = () => useProcessingStore.getState();

beforeEach(async () => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  localStorage.clear();
  link = () => json({ order: ORDER, view: VIEW, expires_at: EXPIRES });
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url === `/processing/processes/recipe?dataset=${DATASET}`) return json(s2);
    if (url.endsWith('/items/NEW_A') || url.endsWith('/items/NEW_B')) return json(scene(url.slice(-5)));
    if (url === `/processing/permalinks/${ID}` && !init?.method) return link();
    if (url === '/processing/permalinks' && init?.method === 'POST') {
      return json({ id: ID, expires_at: EXPIRES, delete_key: KEY }, 201);
    }
    if (url === `/processing/permalinks/${ID}` && init?.method === 'DELETE') return new Response(null, { status: 204 });
    return json({ detail: 'not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, descriptions: {}, jobs: [] });
  useAppStore.setState({
    datasets: [option],
    datasetId: null,
    selectedDatasetIds: [],
    items: [],
    groups: [],
    selectedIds: [],
    aoi: OLD_AOI,
    aoiPoint: null,
    error: null,
    notice: null,
    flyToView: null,
    viewportBbox: [10, 50, 10.3, 50.3],
    mapZoom: 11.5,
  });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<ProcessingPanel />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  onAddress('');
});

describe('opening a link', () => {
  it('brings back the dataset, the scenes, the area, the steps and the view, and clears the address', async () => {
    onAddress(`?permalink=${ID}&other=1`);
    await open();
    const app = useAppStore.getState();
    expect(app.datasetId).toBe(DATASET);
    expect(app.selectedIds).toEqual(['NEW_A']);
    expect(app.aoi).toEqual(SHARED_AOI);
    expect(app.error).toBeNull();
    expect(app.notice).toBeNull();
    expect(app.flyToView).toEqual({ center: [10.15, 50.15], zoom: 11.5 });
    expect(draft().open).toBe(true);
    expect(draft().area).toBe('aoi');
    expect(draft().picked).toEqual(['red', 'nir']);
    expect(draft().steps.map((s) => s.values.expression)).toEqual(['(nir - red) / (nir + red)']);
    expect(draft().dtype).toBe('float32');
    expect(draft().range).toEqual({ vmin: '0', vmax: '0.8', colormap: 'viridis' });
    expect(draft().rangeByHand).toBe(true); // it holds against a measure of the preview
    expect(window.location.search).toBe('?other=1');
  });

  it('brings back the order without a job or a result, ready to be reviewed and started again', async () => {
    onAddress(`?permalink=${ID}`);
    await open();
    expect(draft().jobs).toEqual([]);
    const label = (text: string) => [...container.querySelectorAll('button')].find((b) => b.textContent === text) as HTMLButtonElement;
    expect(label('Review').disabled).toBe(false);
    expect(label('Start job')).toBeDefined();
    expect(fetchMock.mock.calls.map(([url]) => url).filter((url) => String(url).includes('/jobs/'))).toEqual([]);
  });

  it('reads the link once, however often the app starts', async () => {
    onAddress(`?permalink=${ID}`);
    await act(async () => {
      await Promise.all([openPermalinkInAddress(), openPermalinkInAddress()]);
    });
    expect(fetchMock.mock.calls.filter(([url]) => url === `/processing/permalinks/${ID}`)).toHaveLength(1);
  });

  it('does nothing for an address without a link or with something that is none', async () => {
    onAddress('?permalink=short');
    await open();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(draft().open).toBe(false);
  });

  it('says a link has expired or never existed, and changes nothing', async () => {
    link = () => json({ detail: 'there is no such permalink' }, 404);
    onAddress(`?permalink=${ID}`);
    await open();
    expect(useAppStore.getState().error).toBe(GONE_TEXT);
    expect(useAppStore.getState().aoi).toEqual(OLD_AOI);
    expect(draft().open).toBe(false);
    expect(window.location.search).toBe('');
  });

  it('says why a link cannot be opened when the server is down or answers nonsense', async () => {
    link = () => json({ detail: 'down' }, 503);
    onAddress(`?permalink=${ID}`);
    await open();
    expect(useAppStore.getState().error).toMatch(/could not be opened/u);
    link = () => json({ order: 'x', view: VIEW, expires_at: EXPIRES });
    onAddress(`?permalink=${ID}`);
    await open();
    expect(useAppStore.getState().error).toMatch(/could not be opened.*cannot read/u);
  });

  it('refuses an order whose steps the dataset does not take, and keeps the selection', async () => {
    link = () =>
      json({ order: { ...ORDER, steps: [{ op: 'warp', op_version: 1, params: {} }] }, view: VIEW, expires_at: EXPIRES });
    onAddress(`?permalink=${ID}`);
    await open();
    expect(useAppStore.getState().error).toMatch(/not available/u);
    expect(useAppStore.getState().selectedIds).toEqual([]);
    expect(draft().open).toBe(false);
  });

  it('says a dataset that left the catalog has been retired, with the reason of the server, and changes nothing', async () => {
    const reason = "dataset 'gone-dataset' was retired on 2026-10-25: a test; use 'other' instead";
    link = () => json({ order: { ...ORDER, inputs: [{ ...ORDER.inputs[0], dataset: 'gone-dataset' }] }, view: VIEW, expires_at: EXPIRES });
    const answer = fetchMock as unknown as (url: string, init?: RequestInit) => Promise<Response>;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) =>
        url === '/processing/processes/recipe?dataset=gone-dataset' ? json({ detail: reason }, 410) : answer(url, init),
      ),
    );
    onAddress(`?permalink=${ID}`);
    await open();
    expect(useAppStore.getState().error).toBe(`Dataset retired: ${reason}`);
    expect(useAppStore.getState().aoi).toEqual(OLD_AOI);
    expect(draft().open).toBe(false);
  });

  it('keeps the plain message for a dataset the server does not know either', async () => {
    link = () => json({ order: { ...ORDER, inputs: [{ ...ORDER.inputs[0], dataset: 'never-was' }] }, view: VIEW, expires_at: EXPIRES });
    onAddress(`?permalink=${ID}`);
    await open();
    expect(useAppStore.getState().error).toBe('Pick a dataset first.');
  });

  it('says a scene is gone from the catalog', async () => {
    link = () => json({ order: { ...ORDER, inputs: [{ ...ORDER.inputs[0], groups: [['GONE']] }] }, view: VIEW, expires_at: EXPIRES });
    onAddress(`?permalink=${ID}`);
    await open();
    expect(useAppStore.getState().error).toMatch(/GONE/u);
    expect(draft().open).toBe(false);
  });

  it('selects the scenes of every group and leaves the pass to the user', async () => {
    link = () => json({ order: { ...ORDER, inputs: [{ ...ORDER.inputs[0], groups: [['NEW_A'], ['NEW_B']] }] }, view: VIEW, expires_at: EXPIRES });
    onAddress(`?permalink=${ID}`);
    await open();
    expect(useAppStore.getState().error).toBeNull();
    expect(useAppStore.getState().selectedIds).toEqual(['NEW_A', 'NEW_B']);
    expect(draft().passKey).toBeNull();
  });

  it('covers the whole scenes and keeps the area on the map for an order without one', async () => {
    const { aoi: _aoi, ...whole } = ORDER;
    link = () => json({ order: whole, view: { ...VIEW, range: null }, expires_at: EXPIRES });
    onAddress(`?permalink=${ID}`);
    await open();
    expect(draft().area).toBe('scene');
    expect(useAppStore.getState().aoi).toEqual(OLD_AOI);
    expect(draft().range).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdylgn' });
    expect(draft().rangeByHand).toBe(false);
    expect(useAppStore.getState().notice).toBeNull();
  });
});

describe('Share', () => {
  const button = (label: string) =>
    [...container.querySelectorAll('button')].find((b) => b.textContent === label) as HTMLButtonElement | undefined;
  const click = async (label: string) => {
    await act(async () => button(label)!.click());
    await settle();
  };
  const icon = (label: string) => container.querySelector(`button[aria-label="${label}"]`) as HTMLButtonElement | null;
  const clickIcon = async (label: string) => {
    await act(async () => icon(label)!.click());
    await settle();
  };

  beforeEach(async () => {
    onAddress(`?permalink=${ID}`);
    await open();
    fetchMock.mockClear();
  });

  it('keeps the order and the view as they are, and shows the address, the term and the key stays in the browser', async () => {
    await click('Share');
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/processing/permalinks');
    const sent = JSON.parse(init.body);
    expect(sent.order).toEqual(ORDER);
    // The centre is the viewport's, the range the one that came back with the opened link.
    expect(sent.view).toEqual({ center: [10.15, 50.15], zoom: 11.5, range: VIEW.range });
    expect((container.querySelector('input[aria-label="Link"]') as HTMLInputElement).value).toContain(`?permalink=${ID}`);
    expect(container.textContent).toContain('Anyone with the link sees your area');
    expect(loadKeys()[ID].key).toBe(KEY);
    expect(container.textContent).not.toContain(KEY);
  });

  it('leaves the range out where the user did not apply one', async () => {
    act(() => useProcessingStore.setState({ range: { vmin: '-1', vmax: '1', colormap: 'rdylgn' }, rangeByHand: false }));
    await click('Share');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).view.range).toBeNull();
  });

  it('keeps the range the user applied, also when it is the start range (the same switch as the preview and the job)', async () => {
    act(() => useProcessingStore.setState({ range: { vmin: '-1', vmax: '1', colormap: 'rdylgn' }, rangeByHand: true }));
    await click('Share');
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).view.range).toEqual({ vmin: -1, vmax: 1, colormap: 'rdylgn' });
  });

  it('is a button like "Review", close below it, and has no text under it', async () => {
    const share = button('Share')!;
    expect(share.className).toBe(button('Review')!.className);
    const box = container.querySelector('.pp-share')!;
    expect([...box.children]).toEqual([share]);
    // `.pp-foot` spaces its children by 8px, like "Review" and "Start job"; the box adds no margin of its own and the
    // button keeps the width of its label instead of the width of the panel.
    const rule = (selector: string) => new RegExp(`${selector.replace('.', '\\.')} \\{([^}]*)\\}`, 'u').exec(css)?.[1] ?? '';
    expect(rule('.pp-share')).not.toMatch(/margin/u);
    expect(rule('.pp-share')).toContain('align-items: flex-start');
    expect(rule('.pp-foot')).toContain('gap: 8px');
  });

  it('has no title field, in the panel or in what is sent', async () => {
    expect(container.querySelector('input[aria-label*="Title" i], input[placeholder*="Title" i]')).toBeNull();
    await click('Share');
    expect(Object.keys(JSON.parse(fetchMock.mock.calls[0][1].body).view).sort()).toEqual(['center', 'range', 'zoom']);
  });

  it('shows the link in a read-only text field, which the theme colours', async () => {
    await click('Share');
    const field = container.querySelector('input[aria-label="Link"]') as HTMLInputElement;
    expect([field.type, field.readOnly]).toEqual(['text', true]);
    // `input[type='text']` takes the background and text colour of the theme, so it is not white in the dark one.
    const rule = /input\[type='text'\],[^{]*\{([^}]*)\}/u.exec(css)?.[1] ?? '';
    expect(rule).toContain('background: var(--input-bg)');
    expect(rule).toContain('color: var(--text)');
  });

  it('copies the link with the copy glyph of the results list', async () => {
    const writeText = vi.fn(async () => undefined);
    vi.stubGlobal('navigator', { clipboard: { writeText } });
    await click('Share');
    expect(button('Copy link')).toBeUndefined();
    const copy = icon('Copy link')!;
    expect(copy.className).toBe('copy-btn');
    expect(copy.title).toBe('Copy link');
    const glyph = copy.innerHTML;
    await clickIcon('Copy link');
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining(`?permalink=${ID}`));
    expect(copy.innerHTML).not.toBe(glyph);
    expect(copy.innerHTML).toContain('M20 6 9 17l-5-5');
  });

  it('deletes the link with the key it was given, and forgets the key', async () => {
    const confirm = vi.spyOn(window, 'confirm');
    await click('Share');
    const cross = icon('Delete link')!;
    expect([cross.className, cross.title, cross.textContent]).toEqual(['delete-btn', 'Delete link', '✕']);
    expect(button('Delete link')).toBeUndefined();
    await clickIcon('Delete link');
    expect(confirm).not.toHaveBeenCalled();
    const call = fetchMock.mock.calls.find(([, init]) => init?.method === 'DELETE')!;
    expect(call[0]).toBe(`/processing/permalinks/${ID}`);
    expect(call[1].headers['X-Delete-Key']).toBe(KEY);
    expect(localStorage.getItem(KEYS_STORAGE)).toBe('{}');
    expect(container.textContent).toContain('Link deleted.');
    expect(button('Share')).toBeDefined();
  });

  it('keeps the link and its key when the delete fails', async () => {
    await click('Share');
    fetchMock.mockImplementationOnce(async () => json({ detail: 'down' }, 503));
    await clickIcon('Delete link');
    expect(container.textContent).toContain('could not be deleted');
    expect(loadKeys()[ID]).toBeDefined();
    expect(icon('Delete link')).not.toBeNull();
  });

  it('says why it could not be made, and offers it again', async () => {
    fetchMock.mockImplementationOnce(async () => json({ detail: 'invalid view: zoom: less_than_equal' }, 422));
    await click('Share');
    expect(container.textContent).toContain('The link could not be made');
    expect(button('Share')).toBeDefined();
    expect(localStorage.getItem(KEYS_STORAGE)).toBeNull();
  });

  it('is not offered for a batch of jobs, and says why', async () => {
    link = () => json({ order: { ...ORDER, inputs: [{ ...ORDER.inputs[0], groups: [['NEW_A', 'NEW_B']] }] }, view: VIEW, expires_at: EXPIRES });
    onAddress(`?permalink=${ID}`);
    await open();
    expect(button('Share')!.disabled).toBe(false);
    act(() => draft().setRunAs('scene'));
    expect(button('Share')!.disabled).toBe(true);
    expect(button('Share')!.title).toBe('A link holds one order: choose “One job”.');
    // The reason is the tooltip; no text stands under the button.
    expect(container.textContent).not.toContain('A link holds one order');
  });
});
