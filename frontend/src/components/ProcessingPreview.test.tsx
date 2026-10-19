// @vitest-environment jsdom
//
// The map preview of the processing panel (M4-13c-2): the section of the panel,
// the "Preview" badge, the preview as a layer, and the ways into the panel from
// the layer manager and the full-resolution view. No backend: `fetch` answers the
// process description only; the tiles are never requested (the map is not here).

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { DatasetOption } from '../datasets';
import s2 from '../fixtures/processes/sentinel-2-c1-l2a.json';
import type { MapLayer } from '../layers';
import { layerProcessBlock, orderView, useProcessingStore } from '../processingStore';
import { bboxToPolygon } from '../geoUtils';
import { useAppStore } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import LayerManager from './LayerManager';
import PreviewBadge from './PreviewBadge';
import ProcessingPanel from './ProcessingPanel';
import ViewBar from './ViewBar';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const AOI = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);

function scene(id: string, gsd: number | null = 10): StacItem {
  const bbox: [number, number, number, number] = [10, 50, 11, 51];
  return {
    id,
    collection: 'sentinel-2-c1-l2a',
    bbox,
    geometry: bboxToPolygon(bbox),
    properties: { datetime: '2026-07-01T10:00:00Z', ...(gsd ? { gsd } : {}) },
    assets: {
      red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
    },
  };
}

function dataset(tier = 'processing'): DatasetOption {
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
      'earthx:license_flags': { tier },
      'earthx:capabilities': { interpolation: true },
    } as unknown as Collection,
  };
}

function select(items: StacItem[], tier = 'processing') {
  useAppStore.setState({
    datasets: [dataset(tier)],
    datasetId: 'sentinel-2-c1-l2a',
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: items.map((i) => i.id),
    aoi: AOI,
    aoiPoint: null,
    layers: [],
    focusMode: false,
    error: null,
  });
}

function pinned(id: string, over: Partial<MapLayer['restore']> = {}, layer: Partial<MapLayer> = {}): MapLayer {
  return {
    id,
    name: `Layer ${id}`,
    visible: true,
    opacity: 1,
    overlays: [],
    restore: {
      focusMode: false,
      downloaded: {},
      appliedRender: {},
      activeGroupIndex: 0,
      selectedIds: ['S2B_A'],
      itemIds: ['S2B_A'],
      groupItemIds: [['S2B_A']],
      aoi: AOI,
      cropToAoi: false,
      datasetId: 'sentinel-2-c1-l2a',
      ...over,
    },
    ...layer,
  };
}

function json(body: unknown) {
  return new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
}

let container: HTMLDivElement;
let root: Root;
// The catalog behind `/stac/.../items/<id>`: a scene, or the status it answers with.
let catalog: Record<string, StacItem | number>;
// Requests held back until a test answers them.
let pending: Record<string, Promise<Response> | undefined>;
let fetchMock: ReturnType<typeof vi.fn>;
const ITEM_URL = '/stac/collections/sentinel-2-c1-l2a/items/';

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear();
  catalog = {};
  pending = {};
  fetchMock = vi.fn(async (url: string) => {
    if (url === '/processing/processes/recipe?dataset=sentinel-2-c1-l2a') return json(s2);
    if (pending[url]) return pending[url];
    if (url.startsWith(ITEM_URL)) {
      const entry = catalog[decodeURIComponent(url.slice(ITEM_URL.length))];
      if (typeof entry === 'object') return json(entry);
      return new Response(JSON.stringify({ title: 'Refused', detail: 'the catalog is down' }), {
        status: entry ?? 404,
        headers: { 'Content-Type': 'application/problem+json' },
      });
    }
    return new Response('{}', { status: 404, headers: { 'Content-Type': 'application/problem+json' } });
  });
  vi.stubGlobal('fetch', fetchMock);
  useProcessingStore.getState().resetDraft();
  useProcessingStore.setState({ open: false, jobsOpen: false, descriptions: {}, jobs: [], preview: null });
  useAppStore.setState({ mapZoom: 1.6, viewportBbox: null, layers: [], layerManagerOpen: false });
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
    for (let i = 0; i < 5; i++) await Promise.resolve();
  });
}

function mount(node = <ProcessingPanel />) {
  act(() => root.render(node));
}

async function openPanel() {
  mount();
  act(() => useProcessingStore.getState().openProcessing());
  await flush();
}

function button(label: string | RegExp, within: Element = container): HTMLButtonElement {
  const found = [...within.querySelectorAll('button')].find((b) =>
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

const expression = () => container.querySelector<HTMLTextAreaElement>('textarea[id$="-expression"]')!;
const section = () => container.querySelector('section[aria-label="Preview on the map"]')!;
const store = () => useProcessingStore.getState();

// The preview follows 400 ms after the last change: real timers up to here (the
// description is fetched), fake ones for the wait.
function afterDebounce() {
  act(() => {
    vi.advanceTimersByTime(400);
  });
}

async function withNdvi(items = [scene('S2B_A')]) {
  select(items);
  await openPanel();
  vi.useFakeTimers();
  click(button('＋ Band math'));
  typeInto(expression(), '(nir - red) / (nir + red)');
  afterDebounce();
}

describe('the preview section', () => {
  it('says nothing before there is a step, and asks to complete the first one', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    expect(section().querySelector('.hint-text')).toBeNull();
    expect(section().querySelector('.pp-range')).toBeNull();
    click(button('＋ Band math'));
    expect(section().textContent).toContain('Complete the step to see the preview.');
    expect(store().preview).toBeNull();
  });

  it('shows the first step on every scene of the order, 400 ms after the last input', async () => {
    select([scene('S2B_A'), scene('S2B_B')]);
    await openPanel();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    act(() => {
      vi.advanceTimersByTime(399);
    });
    expect(store().preview).toBeNull();
    typeInto(expression(), '(nir - red) / (nir + red)');
    act(() => {
      vi.advanceTimersByTime(399);
    });
    expect(store().preview).toBeNull(); // the typing started the wait again
    act(() => {
      vi.advanceTimersByTime(1);
    });
    const preview = store().preview!;
    expect(preview.scenes.map((s) => s.id)).toEqual(['S2B_A', 'S2B_B']);
    const params = new URL(preview.scenes[0].url, 'http://localhost').searchParams;
    expect(params.getAll('asset')).toEqual(['red', 'nir']);
    expect(params.get('op')).toBe('band_math');
    expect(JSON.parse(params.get('params')!)).toEqual({ expression: '(nir - red) / (nir + red)' });
    expect(params.get('rescale')).toBe('-1,1');
    expect(params.get('colormap_name')).toBe('rdylgn');
    expect(section().textContent).toContain('Where scenes overlap');
  });

  it('is cut to the AOI only for "AOI only"', async () => {
    await withNdvi();
    expect(store().preview!.clipToAoi).toBe(false);
    click(button('AOI only'));
    afterDebounce();
    expect(store().preview!.clipToAoi).toBe(true);
    expect(store().preview!.scenes[0].url).not.toContain('10.4');
  });

  it('takes the picture away at once when the step is taken out or the panel closes', async () => {
    await withNdvi();
    expect(store().preview).not.toBeNull();
    typeInto(expression(), '');
    expect(store().preview).toBeNull();
    typeInto(expression(), 'nir / red');
    afterDebounce();
    expect(store().preview).not.toBeNull();
    act(() => store().closeProcessing());
    expect(store().preview).toBeNull();
  });

  it('drops the picture with the draft when the dataset changes', async () => {
    await withNdvi();
    act(() => useAppStore.setState({ datasetId: 'other' }));
    expect(store().preview).toBeNull();
    expect(store().steps).toEqual([]);
  });

  it('does not draw a picture that was still due when the panel closes or the dataset changes', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    act(() => store().closeProcessing());
    afterDebounce();
    expect(store().preview).toBeNull();

    act(() => store().openProcessing());
    typeInto(expression(), 'nir / red');
    act(() => useAppStore.setState({ datasetId: 'other' }));
    afterDebounce();
    expect(store().preview).toBeNull();
  });

  it('keeps the picture it has when the input comes back to it within 400 ms', async () => {
    await withNdvi();
    const before = store().preview;
    typeInto(expression(), 'nir / red');
    act(() => {
      vi.advanceTimersByTime(300);
    });
    typeInto(expression(), '(nir - red) / (nir + red)');
    afterDebounce();
    expect(store().preview).toBe(before);
  });

  it('takes the picture away at once when the AOI of "AOI only" goes, and leaves it for "Whole scene"', async () => {
    await withNdvi();
    const before = store().preview;
    act(() => useAppStore.setState({ aoi: bboxToPolygon([10.1, 50.1, 10.2, 50.2]) }));
    afterDebounce();
    expect(store().preview).toBe(before); // "Whole scene" does not read the AOI
    click(button('AOI only'));
    afterDebounce();
    expect(store().preview!.clipToAoi).toBe(true);
    act(() => useAppStore.setState({ aoi: null }));
    expect(store().preview).toBeNull();
  });

  it('says why there is no picture for more bands than the map takes', async () => {
    const wide = scene('S2B_A');
    for (let i = 1; i <= 17; i++) wide.assets[`b${i}`] = { href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] };
    select([wide]);
    await openPanel();
    click(button('＋ Band math'));
    typeInto(expression(), Array.from({ length: 17 }, (_, i) => `b${i + 1}`).join(' + '));
    expect(section().textContent).toContain('No preview: the map takes at most 16 bands.');
    expect(store().preview).toBeNull();
  });

  it('asks for a pass while the scenes belong to several', async () => {
    const a = scene('S2B_A');
    const b = scene('S2B_B');
    select([a, b]);
    useAppStore.setState({
      groups: [
        { key: ['2026-07-02'], label: '2026-07-02', items: [b] },
        { key: ['2026-07-01'], label: '2026-07-01', items: [a] },
      ],
    });
    await openPanel();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    expect(section().textContent).toContain('Choose a pass to see the preview.');
    expect(store().preview).toBeNull();
  });

  it('shows a reason, no controls and no picture when the first step runs only as a job', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    vi.useFakeTimers();
    click(button('＋ Reproject and resample'));
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    afterDebounce();
    expect(section().textContent).toContain('No preview: the first step runs only as a job.');
    expect(section().querySelector('.pp-range')).toBeNull();
    expect(store().preview).toBeNull();
  });

  it('says the job runs all steps while the map shows the first', async () => {
    await withNdvi();
    expect(section().textContent).not.toContain('the job runs all steps');
    click(button('＋ Band math'));
    expect(section().textContent).toContain('The map shows the first step; the job runs all steps.');
    expect(store().preview!.title).toBe('Band math');
  });

  it('asks for a band when none is named', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    click(button('＋ Band math'));
    typeInto(expression(), '1 + 1');
    expect(section().textContent).toContain('Pick a band, or name it in the expression, to see the preview.');
    expect(store().preview).toBeNull();
  });

  describe('range and colormap (F3 (1))', () => {
    const inputs = () => [...section().querySelectorAll<HTMLInputElement>('input[type="number"]')];

    it('starts at -1 to 1 with rdylgn and draws a new range only after "Apply"', async () => {
      await withNdvi();
      expect(inputs().map((i) => i.value)).toEqual(['-1', '1']);
      expect(section().querySelector('select')!.value).toBe('rdylgn');
      typeInto(inputs()[1], '0.8');
      afterDebounce();
      expect(new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams.get('rescale')).toBe('-1,1');
      click(button('Apply'));
      afterDebounce();
      expect(new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams.get('rescale')).toBe('-1,0.8');
    });

    it('refuses a range that is no range, and keeps the picture it has', async () => {
      await withNdvi();
      typeInto(inputs()[0], '2');
      expect(section().textContent).toContain('The lower end of the range must be below the upper end.');
      expect(button('Apply').disabled).toBe(true);
      typeInto(inputs()[0], '');
      expect(section().textContent).toContain('Enter a number for both ends of the range.');
      expect(store().range).toEqual({ vmin: '-1', vmax: '1', colormap: 'rdylgn' });
      expect(store().preview).not.toBeNull();
    });

    it('takes another colormap, or none', async () => {
      await withNdvi();
      const select_ = section().querySelector('select')!;
      act(() => {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, 'value')!.set!;
        setter.call(select_, '');
        select_.dispatchEvent(new Event('change', { bubbles: true }));
      });
      click(button('Apply'));
      afterDebounce();
      expect(new URL(store().preview!.scenes[0].url, 'http://localhost').searchParams.has('colormap_name')).toBe(false);
    });

    it('locks "Auto stretch" and says why', async () => {
      await withNdvi();
      const auto = button('Auto stretch');
      expect(auto.disabled).toBe(true);
      expect(auto.title).toContain('statistics');
    });
  });
});

describe('"Preview" (Otto, 19.10.2026: always coarser than the data)', () => {
  it('stands in the panel and over the map whenever there is a preview, whatever the zoom', async () => {
    mount(
      <>
        <ProcessingPanel />
        <PreviewBadge />
      </>,
    );
    select([scene('S2B_A', 10)]);
    act(() => store().openProcessing());
    await flush();
    expect(container.querySelector('.preview-badge')).toBeNull();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    afterDebounce();
    for (const zoom of [3, 12.5, 18, 22]) {
      act(() => useAppStore.setState({ mapZoom: zoom, viewportBbox: [10, 50, 11, 51] }));
      expect(section().querySelector('.pp-badge')?.textContent).toBe('Preview');
      expect(container.querySelector('.preview-badge')?.textContent).toBe('Preview');
    }
    act(() => store().closeProcessing());
    expect(container.querySelector('.preview-badge')).toBeNull();
  });

  it('holds the tiles of the preview under the pixel size of the data', async () => {
    await withNdvi([scene('S2B_A', 10)]);
    // 10 m at 51° N: level 13 is the last, and the released levels reach 14.
    expect(store().preview!.maxZoom).toBe(13);
    expect(store().preview!.maxZoom).toBeLessThan(14);
  });

  it('draws nothing, and says why, when the data names no pixel size', async () => {
    select([scene('S2B_A', null)]);
    await openPanel();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    afterDebounce();
    expect(store().preview).toBeNull();
    expect(section().textContent).toContain('No preview: the data names no pixel size');
    expect(container.querySelector('.pp-badge')).toBeNull();
  });

  it('stands for a pinned preview that is switched on, and not for one that is hidden', () => {
    const layer = (id: string, visible: boolean): MapLayer => ({
      ...pinned(id),
      visible,
      derived: 'preview',
      overlays: [{ kind: 'raster', tileUrl: 'u', bounds: [10, 50, 11, 51], minZoom: 8, maxZoom: 13, preview: true }],
    });
    useAppStore.setState({ layers: [layer('P1', false)] });
    mount(<PreviewBadge />);
    expect(container.querySelector('.preview-badge')).toBeNull();
    act(() => useAppStore.setState({ layers: [layer('P1', true)] }));
    expect(container.querySelector('.preview-badge')).not.toBeNull();
    act(() => useAppStore.setState({ mapZoom: 20 }));
    expect(container.querySelector('.preview-badge')).not.toBeNull();
  });

  it('does not stand for an ordinary layer', () => {
    useAppStore.setState({
      layers: [{ ...pinned('L1'), overlays: [{ kind: 'raster', tileUrl: 'u', bounds: [10, 50, 11, 51], minZoom: 8, maxZoom: 14 }] }],
    });
    mount(<PreviewBadge />);
    expect(container.querySelector('.preview-badge')).toBeNull();
  });
});

describe('the preview as a layer (§3.4)', () => {
  it('"＋ Add preview to layers" pins it on top, with the badge right, and leaves the others', async () => {
    await withNdvi([scene('S2B_A'), scene('S2B_B')]);
    useAppStore.setState({ layers: [pinned('L1')] });
    click(button('＋ Add preview to layers'));
    const [layer, other] = useAppStore.getState().layers;
    expect(other.id).toBe('L1');
    expect(other.visible).toBe(true);
    expect(layer).toMatchObject({ name: 'Preview · Band math', derived: 'preview', visible: true, opacity: 1 });
    expect(layer.overlays).toHaveLength(2);
    expect(layer.overlays[0]).toMatchObject({ kind: 'raster', minZoom: 8, maxZoom: 13, preview: true });
    expect(layer.restore).toMatchObject({ itemIds: ['S2B_A', 'S2B_B'], datasetId: 'sentinel-2-c1-l2a', focusMode: false });
    expect(useAppStore.getState().layerManagerOpen).toBe(true);
  });

  it('keeps the tile URL of the preview, and the AOI out of it', async () => {
    await withNdvi();
    click(button('AOI only'));
    afterDebounce();
    click(button('＋ Add preview to layers'));
    const layer = useAppStore.getState().layers[0];
    expect(layer.restore.cropToAoi).toBe(true);
    const url = (layer.overlays[0] as { tileUrl: string }).tileUrl;
    expect(url.startsWith('earthx-clip://')).toBe(true);
    expect(url).toContain('op=band_math');
    expect(url).not.toContain('10.4');
  });

  it('cannot be pinned before there is a picture', async () => {
    select([scene('S2B_A')]);
    await openPanel();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), 'nir / red');
    // The step is complete, the picture follows in 400 ms.
    expect(button('＋ Add preview to layers').disabled).toBe(true);
    afterDebounce();
    expect(button('＋ Add preview to layers').disabled).toBe(false);
  });

  it('leaves the other layers as they are, also when the panel was opened from one of them', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L0'), pinned('L1')] });
    mount(
      <>
        <ProcessingPanel />
        <LayerManager />
      </>,
    );
    click(button('⚙', container.querySelectorAll('.layer-row')[1] as HTMLElement));
    await flush();
    vi.useFakeTimers();
    click(button('＋ Band math'));
    typeInto(expression(), '(nir - red) / (nir + red)');
    afterDebounce();
    click(button('＋ Add preview to layers'));
    expect(useAppStore.getState().layers.map((l) => [l.id.startsWith('P') ? 'preview' : l.id, l.visible])).toEqual([
      ['preview', true],
      ['L0', true],
      ['L1', true],
    ]);
  });
});

describe('the ways into the panel (§3.5)', () => {
  it('"⚙" at a layer makes its selection again, then opens the panel on "Whole scene"', async () => {
    select([scene('S2B_A'), scene('S2B_B')]);
    useAppStore.setState({ layers: [pinned('L1', { selectedIds: [], itemIds: ['S2B_B'], groupItemIds: [['S2B_B']] })], selectedIds: ['S2B_A'] });
    mount(
      <>
        <LayerManager />
        <ProcessingPanel />
      </>,
    );
    expect(store().open).toBe(false);
    click(button('⚙'));
    await flush();
    expect(useAppStore.getState().selectedIds).toEqual(['S2B_B']);
    expect(useAppStore.getState().aoi).toBe(AOI);
    expect(store()).toMatchObject({ open: true, area: 'scene' });
    expect(container.textContent).toContain('S2B_B');
  });

  it('starts on "AOI only" for a layer that was cropped to its AOI', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L1', { cropToAoi: true, focusMode: true })] });
    mount(<LayerManager />);
    click(button('⚙'));
    await flush();
    expect(store()).toMatchObject({ open: true, area: 'aoi' });
  });

  it('starts on "Whole scene" for a layer cropped with no AOI left to it', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L1', { cropToAoi: true, aoi: null })] });
    mount(<LayerManager />);
    click(button('⚙'));
    await flush();
    expect(store().area).toBe('scene');
  });

  it('is locked for a preview, and says so', () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [{ ...pinned('P1'), derived: 'preview' }] });
    mount(<LayerManager />);
    const gear = button('⚙');
    expect(gear.disabled).toBe(true);
    expect(gear.title).toBe('A result cannot be processed further yet.');
    click(gear);
    expect(store().open).toBe(false);
  });

  it('is locked for a dataset whose licence is below processing', () => {
    select([scene('S2B_A')], 'display');
    useAppStore.setState({ layers: [pinned('L1')] });
    mount(<LayerManager />);
    expect(button('⚙').disabled).toBe(true);
    expect(button('⚙').title).toContain('does not allow processing');
  });

  it('does not offer to download a preview, which is no scene file', () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L1'), { ...pinned('P1'), derived: 'preview' }] });
    mount(<LayerManager />);
    const rows = [...container.querySelectorAll('.layer-row')];
    expect(rows.map((row) => [...row.querySelectorAll('button')].some((b) => b.textContent === '⇩'))).toEqual([true, false]);
  });

  describe('scenes the results on screen lack (Otto, 19.10.2026)', () => {
    const itemRequests = () => fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith('/stac'));
    const layerOf = (...ids: string[]) =>
      pinned('L1', { itemIds: ids, selectedIds: ids, groupItemIds: [ids], cropToAoi: true, focusMode: true });

    it('fetches them one by one, with no search, and then opens the panel', async () => {
      select([scene('S2B_A')]);
      catalog.GONE = scene('GONE');
      useAppStore.setState({ layers: [layerOf('S2B_A', 'GONE')] });
      mount(
        <>
          <LayerManager />
          <ProcessingPanel />
        </>,
      );
      click(button('⚙'));
      await flush();
      expect(itemRequests()).toEqual([`${ITEM_URL}GONE`]);
      expect(useAppStore.getState().selectedIds).toEqual(['S2B_A', 'GONE']);
      expect(store()).toMatchObject({ open: true, area: 'aoi' });
      expect(store().extraScenes!.items.map((i) => i.id)).toEqual(['GONE']);
      // The results on screen stay as they are.
      expect(useAppStore.getState().items.map((i) => i.id)).toEqual(['S2B_A']);
      expect(container.textContent).toContain('2 scenes');
    });

    it('puts a fetched scene of a pass the results hold into that pass, and another one into a pass of its own', async () => {
      select([scene('S2B_A')]);
      catalog.SAME_DAY = scene('SAME_DAY');
      catalog.OTHER_DAY = { ...scene('OTHER_DAY'), properties: { datetime: '2026-06-01T10:00:00Z' } };
      useAppStore.setState({ layers: [pinned('L1', { itemIds: ['S2B_A', 'SAME_DAY'], selectedIds: ['S2B_A', 'SAME_DAY'] })] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      const view = orderView(useAppStore.getState(), store());
      expect(view.passes.map((p) => p.items.map((i) => i.id))).toEqual([['S2B_A', 'SAME_DAY']]);

      act(() =>
        useAppStore.setState({ layers: [pinned('L2', { itemIds: ['S2B_A', 'OTHER_DAY'], selectedIds: ['S2B_A', 'OTHER_DAY'] })] }),
      );
      click(button('⚙'));
      await flush();
      const second = orderView(useAppStore.getState(), store());
      expect(second.passes.map((p) => p.items.map((i) => i.id))).toEqual([['S2B_A'], ['OTHER_DAY']]);
    });

    it('asks only for the scenes it lacks', async () => {
      select([scene('S2B_A'), scene('S2B_B')]);
      catalog.GONE = scene('GONE');
      useAppStore.setState({ layers: [layerOf('S2B_A', 'S2B_B', 'GONE')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(itemRequests()).toEqual([`${ITEM_URL}GONE`]);
    });

    it('asks for nothing when the results hold every scene', async () => {
      select([scene('S2B_A')]);
      useAppStore.setState({ layers: [layerOf('S2B_A')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(itemRequests()).toEqual([]);
      expect(store().extraScenes).toBeNull();
    });

    it('names the scene the catalog no longer has, and does not open the panel', async () => {
      select([scene('S2B_A')]);
      useAppStore.setState({ layers: [layerOf('S2B_A', 'GONE')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(store().open).toBe(false);
      expect(useAppStore.getState().error).toBe('Could not load the scenes of this layer. GONE: not found in the catalog');
    });

    it('gives the reason when the catalog cannot be reached, and opens nothing', async () => {
      select([scene('S2B_A')]);
      catalog.GONE = 502;
      catalog.ALSO = scene('ALSO');
      useAppStore.setState({ layers: [layerOf('S2B_A', 'GONE', 'ALSO')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(store().open).toBe(false);
      expect(store().extraScenes).toBeNull();
      expect(useAppStore.getState().error).toContain('Could not load the scenes of this layer. GONE:');
      expect(useAppStore.getState().error).toContain('the catalog is down');
      expect(useAppStore.getState().error).not.toContain('ALSO');
    });

    it('lets a newer entry win over one still waiting for the catalog', async () => {
      select([scene('S2B_A')]);
      let answer!: (r: Response) => void;
      pending[`${ITEM_URL}SLOW`] = new Promise<Response>((resolve) => (answer = resolve));
      useAppStore.setState({ layers: [layerOf('S2B_A', 'SLOW'), { ...layerOf('S2B_A'), id: 'L2' }] });
      mount(<LayerManager />);
      const gears = () => [...container.querySelectorAll<HTMLButtonElement>('.layer-row button')].filter((b) => b.textContent === '⚙');
      click(gears()[0]);
      await flush();
      click(gears()[1]);
      await flush();
      expect(store()).toMatchObject({ open: true, extraScenes: null });
      expect(useAppStore.getState().selectedIds).toEqual(['S2B_A']);
      answer(json(scene('SLOW')));
      await flush();
      expect(store().extraScenes).toBeNull();
      expect(useAppStore.getState().selectedIds).toEqual(['S2B_A']);
    });

    it('does the same for the full-resolution view, and says "view"', async () => {
      select([scene('S2B_A')]);
      catalog.GONE = scene('GONE');
      const tile: DownloadedInfo = { tileUrl: 'u', bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 };
      useAppStore.setState({ focusMode: true, downloaded: { S2B_A: tile, GONE: tile } });
      mount(<ViewerControls />);
      click(button('⚙ Process'));
      await flush();
      expect(itemRequests()).toEqual([`${ITEM_URL}GONE`]);
      expect(store().open).toBe(true);

      act(() => store().closeProcessing());
      delete catalog.GONE;
      click(button('⚙ Process'));
      await flush();
      expect(store().open).toBe(false);
      expect(useAppStore.getState().error).toBe('Could not load the scenes of this view. GONE: not found in the catalog');
    });

    it('lets the scenes of the entry go with the draft when the dataset changes', async () => {
      select([scene('S2B_A')]);
      catalog.GONE = scene('GONE');
      useAppStore.setState({ layers: [layerOf('S2B_A', 'GONE')] });
      mount(<LayerManager />);
      click(button('⚙'));
      await flush();
      expect(store().extraScenes).not.toBeNull();
      act(() => useAppStore.setState({ datasetId: 'other' }));
      expect(store().extraScenes).toBeNull();
    });
  });

  it('starts on "Whole scene" from the selection, whatever an entry from a layer chose before (Otto, 19.10.2026)', async () => {
    select([scene('S2B_A')]);
    useAppStore.setState({ layers: [pinned('L1', { cropToAoi: true, focusMode: true })] });
    mount(
      <>
        <LayerManager />
        <ProcessingPanel />
        <ViewBar />
      </>,
    );
    click(button('⚙', container.querySelector('.layer-row') as HTMLElement));
    await flush();
    expect(store()).toMatchObject({ open: true, area: 'aoi' });

    act(() => store().closeProcessing());
    click(button('⚙ Process'));
    expect(store()).toMatchObject({ open: true, area: 'scene' });

    // Also while the panel stays open: every entry sets the area.
    click(button('AOI only'));
    expect(store().area).toBe('aoi');
    click(button('⚙ Process'));
    expect(store().area).toBe('scene');
  });

  it('"⚙ Process" of the full-resolution view takes the scenes of the view, cropped or whole', async () => {
    select([scene('S2B_A'), scene('S2B_B')]);
    const tile: DownloadedInfo = { tileUrl: 'u', bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 };
    useAppStore.setState({ focusMode: true, cropToAoi: true, downloaded: { S2B_B: tile }, selectedIds: ['S2B_A', 'S2B_B'] });
    mount(<ViewerControls />);
    click(button('⚙ Process'));
    await flush();
    expect(useAppStore.getState().selectedIds).toEqual(['S2B_B']);
    expect(store()).toMatchObject({ open: true, area: 'aoi' });

    act(() => store().closeProcessing());
    useAppStore.setState({ cropToAoi: false });
    click(button('⚙ Process'));
    await flush();
    expect(store().area).toBe('scene');
  });

  it('locks "⚙ Process" of the full-resolution view for a dataset below processing', () => {
    select([scene('S2B_A')], 'catalog');
    const tile: DownloadedInfo = { tileUrl: 'u', bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 };
    useAppStore.setState({ focusMode: true, downloaded: { S2B_A: tile } });
    mount(<ViewerControls />);
    expect(button('⚙ Process').disabled).toBe(true);
  });
});

describe('layerProcessBlock', () => {
  it('names the reason, or none', () => {
    const datasets = [dataset()];
    expect(layerProcessBlock(pinned('L1'), datasets)).toBeNull();
    expect(layerProcessBlock({ ...pinned('P1'), derived: 'preview' }, datasets)).toBe('A result cannot be processed further yet.');
    expect(layerProcessBlock(pinned('L1', { datasetId: 'unknown' }), datasets)).toBe('Pick a dataset first.');
    expect(layerProcessBlock(pinned('L1', { itemIds: [] }), datasets)).toBe('Select a scene first.');
  });
});
