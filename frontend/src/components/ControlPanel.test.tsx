// @vitest-environment jsdom
//
// M3-06b: `AoiExtras` (inside `ControlPanel.tsx`) now calls the backend
// (`POST /aoi/upload`, M3-06a) instead of parsing the file in the browser.
// This mounts the real component to prove the wiring end to end — a plain
// unit test of `readAoiFile` (`aoiFile.test.ts`) already covers the mapping
// itself, this is about the file input actually reaching the store.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { useAppStore } from '../store';
import type { Collection } from '../types';
import { lockedWithoutReason } from '../fixtures/lockedControls';
import ControlPanel from './ControlPanel';
import { tipOf } from '../fixtures/tips';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  // Dropdowns open in `.app` (`Popover`), outside the panel.
  container.className = 'app';
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({ aoi: null, aoiPoint: null, lastAoi: null, lastAoiPoint: null, error: null, config: null });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

function jsonResponse(status: number, body: unknown): Response {
  return { ok: status >= 200 && status < 300, status, statusText: 'Error', json: async () => body } as Response;
}

function uploadInput(): HTMLInputElement {
  return container.querySelector('.aoi-extras input[type="file"]') as HTMLInputElement;
}

// Flushes pending microtasks (the fetch/json chain inside `readAoiFile`) — a
// macrotask boundary flushes all of them first, so this is more robust than
// awaiting a fixed number of `Promise.resolve()`s.
function flush(): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

async function selectFile(file: File): Promise<void> {
  await act(async () => {
    const input = uploadInput();
    Object.defineProperty(input, 'files', { value: [file], configurable: true });
    input.dispatchEvent(new Event('change', { bubbles: true }));
    await flush();
  });
}

describe('AoiExtras: uploading a file goes through POST /aoi/upload (M3-06b)', () => {
  it('turns a Point answer into aoi/aoiPoint, and lastAoi picks it up too', async () => {
    const point: GeoJSON.Point = { type: 'Point', coordinates: [8, 49] };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, point)));
    act(() => root.render(<ControlPanel />));

    await selectFile(new File(['{}'], 'a.geojson'));

    const state = useAppStore.getState();
    expect(state.aoiPoint).toEqual(point);
    expect(state.aoi).toMatchObject({ type: 'Polygon' }); // buffered square, geoUtils.test.ts covers the math
    expect(state.lastAoi).toEqual(state.aoi);
    expect(state.lastAoiPoint).toEqual(point);
    expect(state.error).toBeNull();
  });

  it('turns a Polygon answer into aoi directly, with no buffered point', async () => {
    const square: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]] };
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, square)));
    act(() => root.render(<ControlPanel />));

    await selectFile(new File(['{}'], 'a.geojson'));

    const state = useAppStore.getState();
    expect(state.aoi).toEqual(square);
    expect(state.aoiPoint).toBeNull();
  });

  it('shows the mapped message in error and leaves the existing AOI untouched on a rejection', async () => {
    const existing: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]] };
    useAppStore.setState({ aoi: existing, aoiPoint: null });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(400, { detail: 'not valid JSON' })));
    act(() => root.render(<ControlPanel />));

    await selectFile(new File(['{}'], 'bad.geojson'));

    const state = useAppStore.getState();
    expect(state.error).toBe('Could not use "bad.geojson" as an AOI: not valid JSON.');
    expect(state.aoi).toBe(existing);
  });

  it('disables the file input while the request is in flight, and re-enables it after', async () => {
    let resolveFetch!: (value: Response) => void;
    const pending = new Promise<Response>((resolve) => {
      resolveFetch = resolve;
    });
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pending));
    act(() => root.render(<ControlPanel />));

    await act(async () => {
      const input = uploadInput();
      Object.defineProperty(input, 'files', { value: [new File(['{}'], 'a.geojson')], configurable: true });
      input.dispatchEvent(new Event('change', { bubbles: true }));
      await flush();
    });
    expect(uploadInput().disabled).toBe(true);

    await act(async () => {
      resolveFetch(jsonResponse(200, { type: 'Point', coordinates: [0, 0] }));
      await flush();
    });
    expect(uploadInput().disabled).toBe(false);
  });
});

// M3-07b: `PlaceSearchField` calls `POST /geocode` and takes the chosen hit as
// the AOI. `placeSearch.test.ts` covers the request/response mapping itself;
// this is about the field, list and selection actually reaching the store —
// the same split `AoiExtras`'s tests above make with `aoiFile.test.ts`.
describe('PlaceSearchField: searching a place and picking a hit (M3-07b)', () => {
  const BERLIN_OUTLINE: GeoJSON.Polygon = {
    type: 'Polygon',
    coordinates: [[[13.0, 52.3], [13.8, 52.3], [13.8, 52.7], [13.0, 52.7], [13.0, 52.3]]],
  };

  function placeInput(): HTMLInputElement {
    return container.querySelector('.place-search-row input[type="text"]') as HTMLInputElement;
  }

  function findButton(): HTMLButtonElement {
    return container.querySelector('.place-search-row > button') as HTMLButtonElement;
  }

  function resultButtons(): HTMLButtonElement[] {
    return [...container.querySelectorAll('.place-results .place-result')] as HTMLButtonElement[];
  }

  // React tracks a controlled input's value through its own value tracker, so
  // setting `.value` directly and firing a plain event leaves it thinking
  // nothing changed. Going through the native setter (bypassing React's
  // override) is the usual way around that without a testing-library helper.
  function typeInto(input: HTMLInputElement, value: string): void {
    const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')!.set!;
    setter.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function pressEnter(input: HTMLInputElement): void {
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
  }

  function placeResponse(results: unknown[]): unknown {
    return {
      results,
      attribution: '© OpenStreetMap contributors',
      attribution_url: 'https://www.openstreetmap.org/copyright',
      license: 'ODbL-1.0',
    };
  }

  it('does not search on every keystroke, only on Enter (Nominatim forbids autocomplete)', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, placeResponse([])));
    vi.stubGlobal('fetch', fetchSpy);
    act(() => root.render(<ControlPanel />));

    await act(async () => {
      typeInto(placeInput(), 'Neuland');
      await flush();
    });
    expect(fetchSpy).not.toHaveBeenCalled();

    await act(async () => {
      pressEnter(placeInput());
      await flush();
    });
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe('/geocode');
    expect(init.body).toBe(JSON.stringify({ q: 'Neuland' }));
  });

  it('does not send an empty or whitespace-only search', async () => {
    const fetchSpy = vi.fn().mockResolvedValue(jsonResponse(200, placeResponse([])));
    vi.stubGlobal('fetch', fetchSpy);
    act(() => root.render(<ControlPanel />));

    await act(async () => {
      typeInto(placeInput(), '   ');
      pressEnter(placeInput());
      await flush();
    });
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(findButton().disabled).toBe(true);
  });

  it('takes a hit with an outline as the AOI, buffers no point, and does not start a dataset search', async () => {
    const runSearch = vi.fn();
    useAppStore.setState({ runSearch });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          200,
          placeResponse([
            {
              name: 'Neuland',
              display_name: 'Neuland, Testland',
              kind: 'boundary/administrative',
              bbox: [13.0, 52.3, 13.8, 52.7],
              outline: BERLIN_OUTLINE,
              outline_simplified: false,
            },
          ]),
        ),
      ),
    );
    act(() => root.render(<ControlPanel />));

    await act(async () => {
      typeInto(placeInput(), 'Neuland');
      pressEnter(placeInput());
      await flush();
    });
    expect(resultButtons()).toHaveLength(1);

    await act(async () => {
      resultButtons()[0].click();
    });

    const state = useAppStore.getState();
    expect(state.aoi).toEqual({ ...BERLIN_OUTLINE, properties: { source: 'OpenStreetMap / Nominatim', attribution: '© OpenStreetMap contributors', license: 'ODbL-1.0' } });
    expect(state.aoiPoint).toBeNull();
    expect(state.lastAoi).toEqual(state.aoi);
    expect(state.flyToBbox).toEqual([13.0, 52.3, 13.8, 52.7]);
    expect(runSearch).not.toHaveBeenCalled();
    // the list closes once a hit is chosen
    expect(resultButtons()).toHaveLength(0);
  });

  it('falls back to the bbox as a rectangle when a hit carries no outline (a point/line hit)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          200,
          placeResponse([
            {
              name: 'Bahnhof Neuland',
              display_name: 'Bahnhof Neuland, Testland',
              kind: 'railway/station',
              bbox: [13.4, 52.5, 13.401, 52.501],
              outline: null,
              outline_simplified: false,
            },
          ]),
        ),
      ),
    );
    act(() => root.render(<ControlPanel />));

    await act(async () => {
      typeInto(placeInput(), 'Bahnhof');
      pressEnter(placeInput());
      await flush();
    });
    await act(async () => {
      resultButtons()[0].click();
    });

    expect(useAppStore.getState().aoi).toMatchObject({ type: 'Polygon' });
  });

  describe('the results lie over the panel and are worked with the keyboard (Otto, 30.09.2026)', () => {
    const HIT = {
      name: 'Neuland',
      display_name: 'Neuland, Testland',
      kind: 'boundary/administrative',
      bbox: [13.0, 52.3, 13.8, 52.7],
      outline: BERLIN_OUTLINE,
      outline_simplified: false,
    };
    async function found() {
      vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, placeResponse([HIT, { ...HIT, name: 'Altland' }]))));
      act(() => root.render(<ControlPanel />));
      const panel = container.querySelector('.control-panel')!;
      act(() => typeInto(placeInput(), 'Neuland'));
      const before = panel.innerHTML;
      await act(async () => {
        pressEnter(placeInput());
        await flush();
      });
      return { panel, before };
    }
    const key = (el: Element, k: string) => act(() => el.dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true })));

    it('the list opens outside the panel and moves nothing in it', async () => {
      const { panel, before } = await found();
      const list = container.querySelector('.place-results') as HTMLElement;
      expect(list).not.toBeNull();
      expect(panel.contains(list)).toBe(false);
      expect(list.style.position).toBe('fixed');
      expect(panel.innerHTML).toBe(before);
    });

    it('arrow down moves from the field into the list; Escape leaves it open (Otto, 2.11.2026)', async () => {
      await found();
      placeInput().focus();
      key(placeInput(), 'ArrowDown');
      expect(document.activeElement).toBe(resultButtons()[0]);
      key(resultButtons()[0], 'ArrowDown');
      expect(document.activeElement).toBe(resultButtons()[1]);
      key(resultButtons()[1], 'ArrowUp');
      expect(document.activeElement).toBe(resultButtons()[0]);
      key(resultButtons()[0], 'Escape');
      expect(container.querySelector('.place-results')).not.toBeNull();
    });

    it('a click beside it closes it', async () => {
      await found();
      act(() => document.body.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true })));
      expect(container.querySelector('.place-results')).toBeNull();
    });

    it('the "×" empties the field, closes the list and keeps the focus in the field', async () => {
      await found();
      const clear = container.querySelector('.place-search-row .clear-btn') as HTMLButtonElement;
      expect(clear.getAttribute('aria-label')).toBe('Clear place name');
      act(() => clear.click());
      expect(placeInput().value).toBe('');
      expect(container.querySelector('.place-results')).toBeNull();
      expect(container.querySelector('.place-search-row .clear-btn')).toBeNull();
      expect(document.activeElement).toBe(placeInput());
    });
  });

  it('shows "No place found." with attribution for an empty result list', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(200, placeResponse([]))));
    act(() => root.render(<ControlPanel />));

    await act(async () => {
      typeInto(placeInput(), 'bxlxrghqz');
      pressEnter(placeInput());
      await flush();
    });

    expect(container.textContent).toContain('No place found.');
    expect(container.textContent).toContain('© OpenStreetMap contributors');
  });

  it('renders the attribution as a link only when its URL is https', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(200, {
          results: [],
          attribution: 'Untrusted',
          attribution_url: 'javascript:alert(1)',
          license: 'ODbL-1.0',
        }),
      ),
    );
    act(() => root.render(<ControlPanel />));

    await act(async () => {
      typeInto(placeInput(), 'x');
      pressEnter(placeInput());
      await flush();
    });

    expect(container.querySelector('.place-attribution a')).toBeNull();
    expect(container.textContent).toContain('Untrusted');
  });

  it('maps a route error into the shared error line and leaves the AOI untouched', async () => {
    const existing: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[0, 0], [0, 1], [1, 1], [1, 0], [0, 0]]] };
    useAppStore.setState({ aoi: existing });
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(jsonResponse(422, { detail: 'search text is empty' })),
    );
    act(() => root.render(<ControlPanel />));

    await act(async () => {
      typeInto(placeInput(), 'x');
      pressEnter(placeInput());
      await flush();
    });

    const state = useAppStore.getState();
    expect(state.error).toBe('Could not search for this place: search text is empty.');
    expect(state.aoi).toBe(existing);
    expect(resultButtons()).toHaveLength(0);
  });

  // UI-05, F8 (Otto, 06.11.2026): behind an (i) at the field, not as a line under it.
  it('names the picked place and its attribution behind an (i) while its AOI is still active, and drops it once the AOI changes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResponse(
          200,
          placeResponse([
            {
              name: 'Neuland',
              display_name: 'Neuland, Testland',
              kind: 'boundary/administrative',
              bbox: [13.0, 52.3, 13.8, 52.7],
              outline: BERLIN_OUTLINE,
              outline_simplified: false,
            },
          ]),
        ),
      ),
    );
    act(() => root.render(<ControlPanel />));

    await act(async () => {
      typeInto(placeInput(), 'Neuland');
      pressEnter(placeInput());
      await flush();
    });
    await act(async () => {
      resultButtons()[0].click();
    });
    const tip = () => container.querySelector('.place-search-row .tip');
    expect(tip()?.getAttribute('data-tip')).toBe('Neuland · © OpenStreetMap contributors');
    expect(container.textContent).not.toContain('Neuland · © OpenStreetMap contributors');

    act(() => useAppStore.setState({ aoi: null }));
    root.render(<ControlPanel />);
    expect(tip()).toBeNull();
  });
});

// M3-12, F6 (Otto, 26.09.2026): a dataset without a time axis locks the date
// fields instead of hiding them, with the acquisition period underneath.
describe('AcquisitionDateFields: a dataset without a time axis', () => {
  const CAPABILITIES = {
    roi: true,
    time_range: false,
    band_math: true,
    interpolation: true,
    ml_processing: true,
    quad_pol: false,
    single_coverage_product: true,
  };

  const NO_TIME_AXIS: Collection = {
    id: 'cop-dem-glo-30',
    title: 'Copernicus DEM GLO-30',
    extent: { temporal: { interval: [['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z']] } },
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': {
      group_by: ['start_datetime'],
      min_zoom: 0,
      max_zoom: 15,
      browse: 'full_resolution',
      quicklook_nodata_max: null,
      results_group_by: ['start_datetime'],
    },
  };

  const WITH_TIME_AXIS: Collection = {
    id: 'sentinel-2-c1-l2a',
    title: 'Sentinel-2 L2A',
    'earthx:capabilities': { ...CAPABILITIES, time_range: true, single_coverage_product: false },
    'earthx:viewer': {
      group_by: ['datetime'],
      min_zoom: 0,
      max_zoom: 19,
      browse: 'quicklook',
      quicklook_nodata_max: 16,
      results_group_by: ['datetime'],
    },
  };

  function dateInputs(): HTMLInputElement[] {
    return [...container.querySelectorAll('.date-field input[type="date"]')] as HTMLInputElement[];
  }

  it('disables both date fields and names the acquisition period in their tooltip, not under them', () => {
    useAppStore.setState({
      datasets: datasetsFrom([NO_TIME_AXIS]),
      selectedDatasetIds: [NO_TIME_AXIS.id],
      datasetId: NO_TIME_AXIS.id,
    });
    act(() => root.render(<ControlPanel />));

    const [from, to] = dateInputs();
    expect(from.disabled).toBe(true);
    expect(to.disabled).toBe(true);
    expect(tipOf(from)).toBe('No time axis – acquired Dec 2010 to Jan 2015');
    expect(tipOf(to)).toBe('No time axis – acquired Dec 2010 to Jan 2015');
    expect(container.textContent).not.toContain('No time axis');
  });

  it('fills the locked fields with the acquisition period when chosen (Otto, 06.11.2026)', () => {
    useAppStore.setState({ datasets: datasetsFrom([NO_TIME_AXIS]), selectedDatasetIds: [], datasetId: null, dateFrom: '', dateTo: '' });
    act(() => root.render(<ControlPanel />));
    act(() => useAppStore.getState().toggleDatasetSelected(NO_TIME_AXIS.id));
    const [from, to] = dateInputs();
    expect([from.value, to.value]).toEqual(['2010-12-01', '2015-01-31']);
    expect(from.disabled && to.disabled).toBe(true);
  });

  it('leaves the fields enabled for a dataset with a time axis', () => {
    useAppStore.setState({
      datasets: datasetsFrom([WITH_TIME_AXIS]),
      selectedDatasetIds: [WITH_TIME_AXIS.id],
      datasetId: WITH_TIME_AXIS.id,
    });
    act(() => root.render(<ControlPanel />));

    const [from, to] = dateInputs();
    expect(from.disabled).toBe(false);
    expect(to.disabled).toBe(false);
    expect(container.textContent).not.toContain('No time axis');
  });

  it('leaves the fields enabled when no dataset is picked yet', () => {
    useAppStore.setState({ datasets: [], selectedDatasetIds: [], datasetId: null });
    act(() => root.render(<ControlPanel />));

    const [from, to] = dateInputs();
    expect(from.disabled).toBe(false);
    expect(to.disabled).toBe(false);
  });
});

// UI-05 §3.3 (Otto, 06.11.2026): the days offered are the temporal extent of the ticked datasets, an open end being today.
describe('AcquisitionDateFields: the days of the ticked datasets', () => {
  const CAPABILITIES = {
    roi: true,
    time_range: true,
    band_math: true,
    interpolation: true,
    ml_processing: true,
    quad_pol: false,
    single_coverage_product: false,
  };
  const VIEWER = {
    group_by: ['datetime'],
    min_zoom: 0,
    max_zoom: 14,
    browse: 'quicklook' as const,
    quicklook_nodata_max: null,
    results_group_by: ['datetime'],
  };
  const timed = (id: string, interval: [string | null, string | null]): Collection => ({
    id,
    title: id,
    extent: { temporal: { interval: [interval] } },
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': VIEWER,
  });
  const OPTICAL = timed('optical', ['2015-06-27T10:25:31Z', null]);
  const RADAR = timed('radar', ['2014-10-03T00:00:00Z', '2021-12-23T23:59:59Z']);
  const inputs = () => [...container.querySelectorAll('.date-field input[type="date"]')] as HTMLInputElement[];
  const leave = (input: HTMLInputElement, value: string) =>
    act(() => {
      useAppStore.getState()[input.getAttribute('aria-label') === 'From date' ? 'setDateFrom' : 'setDateTo'](value);
    });

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date'], now: new Date('2026-11-06T12:00:00Z') });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  function setUp(selected: string[], dates: { dateFrom?: string; dateTo?: string } = {}) {
    useAppStore.setState({
      datasets: datasetsFrom([OPTICAL, RADAR]),
      selectedDatasetIds: selected,
      datasetId: selected[0] ?? null,
      multiSelect: true,
      dateFrom: dates.dateFrom ?? '',
      dateTo: dates.dateTo ?? '',
    });
    act(() => root.render(<ControlPanel />));
  }

  it('offers the days of one dataset, an open end being today', () => {
    setUp(['optical']);
    expect(inputs().map((i) => [i.min, i.max])).toEqual([
      ['2015-06-27', '2026-11-06'],
      ['2015-06-27', '2026-11-06'],
    ]);
  });

  it('offers the days of several, earliest start to latest end', () => {
    setUp(['optical', 'radar']);
    expect([inputs()[0].min, inputs()[0].max]).toEqual(['2014-10-03', '2026-11-06']);
  });

  it('offers any day while no dataset is ticked', () => {
    setUp([]);
    expect(inputs().every((i) => !i.hasAttribute('min') && !i.hasAttribute('max'))).toBe(true);
  });

  it('moves a day typed outside onto the nearest one when the field is left, and leaves one inside', () => {
    setUp(['radar']);
    const [from, to] = inputs();
    leave(from, '2001-01-01');
    act(() => from.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
    expect(useAppStore.getState().dateFrom).toBe('2014-10-03');
    leave(to, '2030-01-01');
    act(() => to.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
    expect(useAppStore.getState().dateTo).toBe('2021-12-23');
    leave(to, '2020-02-02');
    act(() => to.dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
    expect(useAppStore.getState().dateTo).toBe('2020-02-02');
  });

  // Otto's review of part 1 (06.11.2026): a choice fills the fields with the first and the last day; what the user types
  // stays until the next choice.
  const dates = () => inputs().map((i) => i.value);

  it('fills the fields with the first and the last day of a chosen dataset, an open end being today', () => {
    setUp([]);
    act(() => useAppStore.getState().toggleDatasetSelected('optical'));
    expect(dates()).toEqual(['2015-06-27', '2026-11-06']);
  });

  it('fills them anew with each choice: the earliest and the latest day over all chosen', () => {
    setUp([]);
    act(() => useAppStore.getState().toggleDatasetSelected('radar'));
    expect(dates()).toEqual(['2014-10-03', '2021-12-23']);
    act(() => useAppStore.getState().toggleDatasetSelected('optical'));
    expect(dates()).toEqual(['2014-10-03', '2026-11-06']);
  });

  it('keeps what the user types until the next choice, which fills the fields anew', () => {
    setUp([]);
    act(() => useAppStore.getState().toggleDatasetSelected('optical'));
    act(() => useAppStore.getState().setDateFrom('2024-03-01'));
    act(() => useAppStore.getState().setDateTo('2024-04-01'));
    act(() => root.render(<ControlPanel />));
    expect(dates()).toEqual(['2024-03-01', '2024-04-01']);
    act(() => useAppStore.getState().toggleDatasetSelected('radar'));
    expect(dates()).toEqual(['2014-10-03', '2026-11-06']);
  });

  it('empties the fields when the last chosen dataset is dropped', () => {
    setUp([]);
    act(() => useAppStore.getState().toggleDatasetSelected('optical'));
    act(() => useAppStore.getState().toggleDatasetSelected('optical'));
    expect(dates()).toEqual(['', '']);
  });
});

// M3-10 (Otto, 30.09.2026): one toggle button per dataset, any number at once,
// every picked dataset searched together. No text filter, no tick boxes.
describe('DatasetPicker: choosing datasets (M3-10)', () => {
  const CAPABILITIES = {
    roi: true,
    time_range: true,
    band_math: true,
    interpolation: true,
    ml_processing: true,
    quad_pol: false,
    single_coverage_product: false,
  };

  function collection(id: string, title: string, extra: Partial<Collection> = {}): Collection {
    return {
      id,
      title,
      'earthx:capabilities': CAPABILITIES,
      'earthx:viewer': {
        group_by: ['datetime'],
        min_zoom: 0,
        max_zoom: 14,
        browse: 'quicklook',
        quicklook_nodata_max: null,
        results_group_by: ['datetime'],
      },
      ...extra,
    };
  }

  const OPTICAL = collection('optical', 'Optical imagery', {
    description: 'Multispectral optical imagery.',
    keywords: ['sentinel-2'],
    'earthx:maturity': 'staging',
  });
  const DEM = collection('dem', 'Elevation model', {
    description: 'A digital surface model.',
    keywords: ['terrain'],
    extent: { temporal: { interval: [['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z']] } },
    'earthx:capabilities': { ...CAPABILITIES, time_range: false },
  });
  const BROKEN: Collection = { id: 'broken', title: 'Broken data', 'earthx:capabilities': CAPABILITIES };

  function setUp(selected: string[]) {
    useAppStore.setState({
      datasets: datasetsFrom([OPTICAL, DEM, BROKEN]),
      addedDatasetIds: ['optical', 'dem', 'broken'],
      selectedDatasetIds: selected,
      multiSelect: false,
      lastPickedDatasetId: null,
      datasetId: selected[0] ?? null,
      sections: [],
      openSectionId: null,
      items: [],
      groups: [],
      aoi: null,
      sceneNameQuery: '',
      showCoverage: false,
      coverageDatasetId: null,
    });
    act(() => root.render(<ControlPanel />));
  }

  function buttons(): HTMLButtonElement[] {
    return [...container.querySelectorAll('.dataset-list .dataset-toggle')] as HTMLButtonElement[];
  }
  function multiButton(): HTMLInputElement {
    return container.querySelector('.multi-select-toggle input') as HTMLInputElement;
  }
  function titles(): string[] {
    return buttons().map((b) => b.querySelector('.dataset-toggle-title')!.textContent ?? '');
  }
  function searchButton(): HTMLButtonElement {
    return container.querySelector('.control-footer .btn.primary') as HTMLButtonElement;
  }

  it('lists every dataset as a toggle button, the picked ones pressed', () => {
    setUp(['optical']);
    expect(titles()).toEqual(['Optical imagery', 'Elevation model', 'Broken data']);
    expect(buttons().map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false', 'false']);
    expect(container.textContent).not.toContain('selected');
  });

  it('has no tick boxes per dataset (only the multiple-datasets one) and no text filter', () => {
    setUp(['optical']);
    expect(container.querySelectorAll('.dataset-list input[type="checkbox"]')).toHaveLength(0);
    expect(container.querySelector('input[type="search"]')).toBeNull();
    expect(container.querySelector('[aria-label="Filter datasets"]')).toBeNull();
  });

  it('starts with nothing chosen and the switch off', () => {
    setUp([]);
    expect(buttons().map((b) => b.getAttribute('aria-pressed'))).toEqual(['false', 'false', 'false']);
    expect(multiButton().checked).toBe(false);
  });

  it('a click chooses that dataset, a second click on another replaces it', () => {
    setUp([]);
    act(() => buttons()[0].click());
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical']);
    act(() => buttons()[1].click());
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['dem']);
    expect(buttons().map((b) => b.getAttribute('aria-pressed'))).toEqual(['false', 'true', 'false']);
  });

  it('a click on the chosen dataset drops it again', () => {
    setUp(['optical']);
    act(() => buttons()[0].click());
    expect(useAppStore.getState().selectedDatasetIds).toEqual([]);
    expect(useAppStore.getState().datasetId).toBeNull();
  });

  it('shows "Select multiple datasets" as a small check box beside the label', () => {
    setUp([]);
    expect(multiButton().type).toBe('checkbox');
    expect(container.querySelector('.dataset-label')?.textContent).toContain('Select multiple datasets');
  });

  it('"Select multiple datasets" lets clicks switch datasets on and off; ending it keeps the last one', () => {
    setUp([]);
    act(() => multiButton().click());
    act(() => buttons()[0].click());
    act(() => buttons()[1].click());
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical', 'dem']);
    act(() => buttons()[0].click());
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['dem']);
    act(() => buttons()[0].click());
    act(() => multiButton().click());
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical']);
    expect(multiButton().checked).toBe(false);
  });

  it('a click picks a dataset, another click drops it again — any number at once', () => {
    setUp(['optical']);
    useAppStore.setState({ multiSelect: true });
    act(() => root.render(<ControlPanel />));
    act(() => buttons()[1].click());
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical', 'dem']);
    expect(buttons().map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'true', 'false']);
    act(() => buttons()[0].click());
    expect(useAppStore.getState().selectedDatasetIds).toEqual(['dem']);
    act(() => buttons()[1].click());
    expect(useAppStore.getState().selectedDatasetIds).toEqual([]);
  });

  it('locks the buttons while a search runs', () => {
    setUp(['optical']);
    useAppStore.setState({ searching: true });
    act(() => root.render(<ControlPanel />));
    expect(buttons().every((b) => b.disabled)).toBe(true);
    useAppStore.setState({ searching: false });
  });

  it('shows a dataset that cannot be shown disabled, with the reason', () => {
    setUp(['optical']);
    const broken = buttons()[2];
    expect(broken.disabled).toBe(true);
    expect(tipOf(broken)).toContain('not viewable');
    expect(tipOf(broken)).toContain('group_by');
  });

  // Otto, 4.11.2026: no tooltip at a dataset, but the reason where one cannot be chosen (above).
  it('shows the maturity chip and has no tooltip at a dataset that can be chosen', () => {
    setUp(['optical']);
    expect(buttons()[0].querySelector('.maturity-chip')?.textContent).toBe('staging');
    expect(buttons()[0].hasAttribute('data-tip')).toBe(false);
    expect(buttons()[0].hasAttribute('title')).toBe(false);
  });

  // UI-05 (Otto, 06.11.2026): pages of at most six; jsdom has no layout, so the panel keeps three rows.
  describe('pages of datasets', () => {
    const many = Array.from({ length: 7 }, (_, i) => collection(`extra-${i}`, `Extra ${i}`));
    const previous = () => container.querySelector('.dataset-pages [aria-label="Previous page"]') as HTMLButtonElement;
    const next = () => container.querySelector('.dataset-pages [aria-label="Next page"]') as HTMLButtonElement;
    const count = () => container.querySelector('.dataset-page-count')?.textContent;
    function setUpMany(selected: string[] = []) {
      const datasets = datasetsFrom([OPTICAL, DEM, ...many]);
      useAppStore.setState({ datasets, addedDatasetIds: datasets.map((d) => d.id), selectedDatasetIds: selected, datasetId: selected[0] ?? null, multiSelect: true });
      act(() => root.render(<ControlPanel />));
    }

    it('shows six of nine, with "1 / 2" and the first arrow locked with its reason', () => {
      setUpMany();
      expect(titles()).toEqual(['Optical imagery', 'Elevation model', 'Extra 0', 'Extra 1', 'Extra 2', 'Extra 3']);
      expect(count()).toBe('1 / 2');
      expect(previous().getAttribute('aria-disabled')).toBe('true');
      expect(tipOf(previous())).toBe('Already on the first page');
      expect(next().hasAttribute('aria-disabled')).toBe(false);
    });

    it('turns to the next page and back; the last arrow is locked there; a click on a locked arrow does nothing', () => {
      setUpMany();
      act(() => next().click());
      expect(titles()).toEqual(['Extra 4', 'Extra 5', 'Extra 6']);
      expect(count()).toBe('2 / 2');
      expect(next().getAttribute('aria-disabled')).toBe('true');
      expect(tipOf(next())).toBe('Already on the last page');
      act(() => next().click());
      expect(count()).toBe('2 / 2');
      act(() => previous().click());
      expect(count()).toBe('1 / 2');
      act(() => previous().click());
      expect(count()).toBe('1 / 2');
    });

    it('keeps the rows of a full page on the last one, so the panel does not jump', () => {
      setUpMany();
      const rows = () => (container.querySelector('.dataset-list') as HTMLElement).style.getPropertyValue('--dataset-rows');
      expect(rows()).toBe('3');
      act(() => next().click());
      expect(rows()).toBe('3');
    });

    it('keeps a dataset picked on another page picked, and searches it with the rest', () => {
      setUpMany(['extra-6']);
      act(() => buttons()[0].click());
      expect(useAppStore.getState().selectedDatasetIds).toEqual(['optical', 'extra-6']);
      act(() => next().click());
      expect(buttons().find((b) => b.textContent === 'Extra 6')?.getAttribute('aria-pressed')).toBe('true');
    });

    // Otto's review of part 1 (06.11.2026): small, at the right of the heading "Datasets", not under the list.
    it('stands in the heading row, right of "Datasets" and before "Select multiple datasets", not under the grid', () => {
      setUpMany();
      const pages = container.querySelector('.dataset-pages')!;
      const heading = container.querySelector('.dataset-label')!;
      expect(heading.contains(pages)).toBe(true);
      expect(pages.parentElement?.firstChild?.textContent).toBe('Datasets');
      expect(pages.compareDocumentPosition(heading.querySelector('.multi-select-toggle')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
      expect(container.querySelector('.dataset-list')!.contains(pages)).toBe(false);
      expect(container.querySelector('.dataset-list')!.nextElementSibling?.classList.contains('dataset-pages')).toBe(false);
    });

    it('shows "1 / 1" with both arrows locked when all fit on one page', () => {
      setUp([]);
      expect(count()).toBe('1 / 1');
      expect(previous().getAttribute('aria-disabled')).toBe('true');
      expect(next().getAttribute('aria-disabled')).toBe('true');
    });
  });

  it('with nothing ticked, asks for a dataset and keeps Search off even with an AOI', () => {
    setUp([]);
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } });
    act(() => root.render(<ControlPanel />));
    // The reason stands in the tooltip of the locked button, not in a paragraph below it (NM4-22).
    expect(tipOf(searchButton())).toBe('Choose a dataset to search');
    expect(container.textContent).not.toContain('Choose a dataset to search');
    expect(searchButton().disabled).toBe(true);
  });

  it('with one ticked and an AOI, Search is on', () => {
    setUp(['optical']);
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } });
    act(() => root.render(<ControlPanel />));
    expect(container.textContent).not.toContain('Choose a dataset to search.');
    expect(searchButton().disabled).toBe(false);
  });

  it('sums the scenes over every section for the count under Search', () => {
    setUp(['optical', 'dem']);
    const item = { id: 'x', bbox: null, properties: {}, assets: {} };
    useAppStore.setState({
      sections: [
        { datasetId: 'optical', items: [item, item], groups: [], notes: [], groupingError: null, origin: 'search', incomplete: false },
        { datasetId: 'dem', items: [item], groups: [], notes: [], groupingError: null, origin: 'search', incomplete: false },
      ],
    });
    act(() => root.render(<ControlPanel />));
    expect(container.textContent).toContain('3 scenes found');
  });

  it('the scene name field has a "×" while it holds text, which empties it', () => {
    setUp(['optical']);
    const clear = () => container.querySelector('.scene-name-field .clear-btn') as HTMLButtonElement | null;
    expect(clear()).toBeNull();
    act(() => useAppStore.setState({ sceneNameQuery: 'S2B_42' }));
    expect(clear()?.getAttribute('aria-label')).toBe('Clear scene name');
    act(() => clear()!.click());
    expect(useAppStore.getState().sceneNameQuery).toBe('');
    expect(clear()).toBeNull();
  });

  describe('the date fields', () => {
    function dateInputs(): HTMLInputElement[] {
      return [...container.querySelectorAll('.date-field input[type="date"]')] as HTMLInputElement[];
    }

    it('stay usable while one ticked dataset has a time axis, and name each one without behind an (i)', () => {
      setUp(['optical', 'dem']);
      expect(dateInputs().every((i) => !i.disabled)).toBe(true);
      expect(container.querySelector('.date-label .tip')?.getAttribute('data-tip')).toBe(
        'Elevation model: No time axis – acquired Dec 2010 to Jan 2015',
      );
      expect(container.textContent).not.toContain('No time axis');
    });

    it('lock only when every ticked dataset lacks a time axis, with the period in the tooltip', () => {
      setUp(['dem']);
      expect(dateInputs().every((i) => i.disabled)).toBe(true);
      // one dataset: the note without a title prefix, as before
      expect(tipOf(dateInputs()[0])).toBe('No time axis – acquired Dec 2010 to Jan 2015');
      expect(container.querySelector('.date-label .tip')).toBeNull();
    });

    it('have no (i) and no tooltip with a time axis only', () => {
      setUp(['optical']);
      expect(container.querySelector('.date-label .tip')).toBeNull();
      expect(dateInputs()[0].hasAttribute('data-tip')).toBe(false);
    });
  });

  it('names the maturity of every ticked dataset in a warning at "Datasets", by title once there are several, not as a paragraph', () => {
    setUp(['optical', 'dem']);
    const tip = container.querySelector('.dataset-label .tip.warn');
    expect(tip?.getAttribute('data-tip')).toBe('Optical imagery: staging: the provider may withdraw this collection without notice');
    expect(container.textContent).not.toContain('without notice');
    expect(container.querySelector('.dataset-notes')).toBeNull();
  });

  it('has no warning at "Datasets" while every ticked dataset is settled', () => {
    setUp(['dem']);
    expect(container.querySelector('.dataset-label .tip')).toBeNull();
  });

  it('keeps the search button in a footer of its own, outside the scrolling part', () => {
    setUp(['optical']);
    const panel = container.querySelector('.control-panel')!;
    const scroll = panel.querySelector('.control-scroll')!;
    const footer = panel.querySelector('.control-footer')!;
    expect(footer.querySelector('.btn.primary')).not.toBeNull();
    expect(scroll.querySelector('.btn.primary')).toBeNull();
    expect(scroll.querySelector('.dataset-list')).not.toBeNull();
  });

  describe('the "Coverage" button (M3-10, Otto 30.09.2026)', () => {
    function button(): HTMLButtonElement {
      return container.querySelector('.coverage-button-wrap > .btn:first-child') as HTMLButtonElement;
    }
    function choices(): HTMLButtonElement[] {
      return [...container.querySelectorAll('.coverage-choice-item')] as HTMLButtonElement[];
    }

    it('sits right under the grid of dataset buttons, outside it, and not in the footer', () => {
      setUp(['optical']);
      expect(button()).not.toBeNull();
      const grid = container.querySelector('.dataset-list')!;
      expect(grid.nextElementSibling?.classList.contains('coverage-button-wrap')).toBe(true);
      expect(grid.querySelector('.coverage-button-wrap')).toBeNull();
      expect(container.querySelector('.control-footer .coverage-button-wrap')).toBeNull();
      expect(button().textContent).toBe('Coverage');
    });

    it('opens the choice of dataset over the panel, moving nothing in it', () => {
      setUp(['optical', 'dem']);
      const panel = container.querySelector('.control-panel')!;
      const before = panel.innerHTML;
      act(() => button().click());
      const choice = container.querySelector('.coverage-choice') as HTMLElement;
      expect(choice).not.toBeNull();
      expect(panel.contains(choice)).toBe(false);
      expect(choice.style.position).toBe('fixed');
      // Only the button's own state changes; nothing is inserted into the panel.
      expect(panel.innerHTML.replace(/aria-expanded="true"/, 'aria-expanded="false"')).toBe(before);
    });

    it('is worked with the keyboard: arrow down opens it at the first entry, arrows move, Escape closes nothing', () => {
      setUp(['optical', 'dem']);
      button().focus();
      act(() => button().dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })));
      expect(document.activeElement).toBe(choices()[0]);
      act(() => choices()[0].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })));
      expect(document.activeElement).toBe(choices()[1]);
      act(() => choices()[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })));
      expect(document.activeElement).toBe(choices()[0]); // wraps round
      act(() => document.activeElement!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
      expect(container.querySelector('.coverage-choice')).not.toBeNull();
      expect(document.activeElement).toBe(choices()[0]);
    });

    it('"Hide coverage" is on only while a coverage map is shown, and hides it', () => {
      const clear = () => container.querySelector('.coverage-button-wrap > .btn:nth-child(2)') as HTMLButtonElement;
      setUp(['optical']);
      expect(clear().textContent).toBe('Hide coverage');
      expect(clear().disabled).toBe(true);
      act(() => button().click());
      expect(useAppStore.getState().showCoverage).toBe(true);
      expect(clear().disabled).toBe(false);
      act(() => clear().click());
      expect(useAppStore.getState().showCoverage).toBe(false);
      expect(useAppStore.getState().coverageDatasetId).toBeNull();
      expect(clear().disabled).toBe(true);
    });

    it('"Coverage" and "Hide coverage" share one row', () => {
      setUp(['optical']);
      const row = container.querySelector('.coverage-button-wrap')!;
      expect([...row.children].map((c) => c.textContent)).toEqual(['Coverage', 'Hide coverage']);
    });

    it('is visible but off when no dataset is picked', () => {
      setUp([]);
      expect(button()).not.toBeNull();
      expect(button().disabled).toBe(true);
      expect(container.querySelector('.coverage-choice')).toBeNull();
    });

    it('with one dataset picked, a click shows its coverage; another click hides it — no question asked', () => {
      setUp(['optical']);
      act(() => button().click());
      expect(useAppStore.getState().showCoverage).toBe(true);
      expect(useAppStore.getState().coverageDatasetId).toBe('optical');
      expect(container.querySelector('.coverage-choice')).toBeNull();
      expect(button().getAttribute('aria-pressed')).toBe('true');
      act(() => button().click());
      expect(useAppStore.getState().showCoverage).toBe(false);
    });

    it('with several picked, nothing is drawn until the click, and the click offers the choice', () => {
      setUp(['optical', 'dem']);
      expect(container.querySelector('.coverage-choice')).toBeNull();
      expect(useAppStore.getState().showCoverage).toBe(false);
      act(() => button().click());
      expect(useAppStore.getState().showCoverage).toBe(false); // still nothing drawn
      expect(choices().map((c) => c.textContent)).toEqual(['Optical imagery', 'Elevation model']);
    });

    it('choosing a dataset draws its coverage and closes the choice', () => {
      setUp(['optical', 'dem']);
      act(() => button().click());
      act(() => choices()[1].click());
      expect(useAppStore.getState().coverageDatasetId).toBe('dem');
      expect(useAppStore.getState().showCoverage).toBe(true);
      expect(container.querySelector('.coverage-choice')).toBeNull();
      expect(container.textContent).toContain('Coverage · Elevation model');
    });

    it('with the coverage on and several picked, the choice holds the datasets only, with no entry "Hide coverage", and marks the current one (UI-04 part 4)', () => {
      setUp(['optical', 'dem']);
      act(() => button().click());
      act(() => choices()[0].click());
      act(() => button().click());
      expect(choices().map((c) => c.textContent)).toEqual(['Optical imagery', 'Elevation model']);
      expect(container.querySelector('.coverage-choice')?.textContent).not.toMatch(/Hide coverage/u);
      expect(choices()[0].getAttribute('aria-checked')).toBe('true');
      expect(choices()[1].getAttribute('aria-checked')).toBe('false');
    });

    it('with the coverage on and several picked, it is hidden with the button "Hide coverage" beside "Coverage", not from the choice', () => {
      setUp(['optical', 'dem']);
      act(() => button().click());
      act(() => choices()[0].click());
      expect(useAppStore.getState().showCoverage).toBe(true);
      const hide = container.querySelector('.coverage-button-wrap > .btn:nth-child(2)') as HTMLButtonElement;
      expect(hide.textContent).toBe('Hide coverage');
      act(() => hide.click());
      expect(useAppStore.getState().showCoverage).toBe(false);
    });

    it('chooses another dataset from the choice while the coverage is on, and the map follows without being hidden first', () => {
      setUp(['optical', 'dem']);
      act(() => button().click());
      act(() => choices()[0].click());
      act(() => button().click());
      act(() => choices()[1].click());
      expect(useAppStore.getState()).toMatchObject({ showCoverage: true, coverageDatasetId: 'dem' });
    });

    it('a click outside closes the choice without drawing anything; Escape does not close it (Otto, 2.11.2026)', () => {
      setUp(['optical', 'dem']);
      act(() => button().click());
      act(() => {
        document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      });
      expect(container.querySelector('.coverage-choice')).not.toBeNull();
      act(() => {
        document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }));
      });
      expect(container.querySelector('.coverage-choice')).toBeNull();
      expect(useAppStore.getState().showCoverage).toBe(false);
    });

    it('has no dataset choice in the legend any more: the button is the one place', () => {
      setUp(['optical', 'dem']);
      act(() => button().click());
      act(() => choices()[0].click());
      expect(container.querySelector('select')).toBeNull();
      expect(container.querySelector('.coverage-controls')).not.toBeNull();
    });

    it('shows the legend under the datasets only while the coverage is on', () => {
      setUp(['optical']);
      expect(container.querySelector('.coverage-controls')).toBeNull();
      act(() => button().click());
      expect(container.querySelector('.coverage-controls')).not.toBeNull();
    });
  });
});

// UI-04 §7.5 no. 8: what is locked says why in its tooltip.
describe('locked controls of the menu', () => {
  it('name their reason: Find without a name, Last AOI without one, Search without a dataset or an AOI', () => {
    useAppStore.setState({ datasets: [], datasetId: null, selectedDatasetIds: [], searching: false, sceneLookupLoading: false });
    act(() => root.render(<ControlPanel />));
    expect(lockedWithoutReason(container)).toEqual([]);
    const button = (text: string) => [...container.querySelectorAll('button')].find((b) => b.textContent?.trim().endsWith(text));
    expect(button('Find')?.getAttribute('data-tip')).toBe('Type a place name first');
    expect(button('Last AOI')?.getAttribute('data-tip')).toBe('No earlier AOI in this browser');
    expect(button('Search')?.getAttribute('data-tip')).toBe('Choose a dataset to search');
  });
});

