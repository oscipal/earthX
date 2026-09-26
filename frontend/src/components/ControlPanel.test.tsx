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
import ControlPanel from './ControlPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
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
    return container.querySelector('.place-search-row button') as HTMLButtonElement;
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

  it('shows the picked place under the field while its AOI is still active, and drops the line once the AOI changes', async () => {
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
    expect(container.textContent).toContain('Neuland · © OpenStreetMap contributors');

    act(() => useAppStore.setState({ aoi: null }));
    root.render(<ControlPanel />);
    expect(container.textContent).not.toContain('Neuland · © OpenStreetMap contributors');
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

  it('disables both date fields and shows the acquisition period', () => {
    useAppStore.setState({ datasets: datasetsFrom([NO_TIME_AXIS]), datasetId: NO_TIME_AXIS.id });
    act(() => root.render(<ControlPanel />));

    const [from, to] = dateInputs();
    expect(from.disabled).toBe(true);
    expect(to.disabled).toBe(true);
    expect(container.textContent).toContain('No time axis – acquired Dec 2010 to Jan 2015');
  });

  it('leaves the fields enabled for a dataset with a time axis', () => {
    useAppStore.setState({ datasets: datasetsFrom([WITH_TIME_AXIS]), datasetId: WITH_TIME_AXIS.id });
    act(() => root.render(<ControlPanel />));

    const [from, to] = dateInputs();
    expect(from.disabled).toBe(false);
    expect(to.disabled).toBe(false);
    expect(container.textContent).not.toContain('No time axis');
  });

  it('leaves the fields enabled when no dataset is picked yet', () => {
    useAppStore.setState({ datasets: [], datasetId: null });
    act(() => root.render(<ControlPanel />));

    const [from, to] = dateInputs();
    expect(from.disabled).toBe(false);
    expect(to.disabled).toBe(false);
  });
});
