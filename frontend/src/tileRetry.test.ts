// UI-08 (Otto, 16.11.2026): a layer whose tiles failed while the services restarted loads them again by itself, without a reload of the page.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import maplibreTypes from 'maplibre-gl/dist/maplibre-gl.d.ts?raw';

import { isPassingFailure, RECOVERY_GAP_MS, RETRY_DELAYS_MS, watchTileRetry, type RetryMap, type TileManagerLike } from './tileRetry';

type Handler = (event: object) => void;

// A fake map: the handlers it was given, the sources it has with their tiles in view, and the tiles it loaded again and in which state.
function fakeMap(sources = ['layer-src-L1-0', 'res-tiles-src-0', 'basemap']) {
  const handlers = new Map<string, Handler>();
  const known = new Set(sources);
  const refreshed: string[] = [];
  const states: string[] = [];
  const tiles = new Map<string, Map<string, { state: string; tileID: { canonical: { x: number; y: number; z: number } } }>>();
  const managerOf = (sourceId: string): TileManagerLike => {
    const own = tiles.get(sourceId) ?? new Map();
    tiles.set(sourceId, own);
    return {
      getIds: () => [...own.keys()],
      getTileByID: (id: string) => own.get(id),
      _reloadTile: (id: string, state: string) => {
        const { x, y, z } = own.get(id)!.tileID.canonical;
        refreshed.push(`${sourceId}/${z}/${x}/${y}`);
        states.push(state);
      },
    };
  };
  const map = {
    on: (type: string, handler: Handler) => handlers.set(type, handler),
    getSource: (id: string) => (known.has(id) ? {} : undefined),
    style: { tileManagers: Object.fromEntries(sources.map((id) => [id, managerOf(id)])) },
  };
  watchTileRetry(map as unknown as RetryMap);
  const tile = (z: number, x: number, y: number, state = 'errored') => ({ tileID: { canonical: { x, y, z } }, state });
  const place = (sourceId: string, [z, x, y]: [number, number, number], state: string) => {
    const own = tiles.get(sourceId) ?? new Map();
    tiles.set(sourceId, own);
    own.set(`${z}/${x}/${y}`, tile(z, x, y, state));
  };
  return {
    refreshed,
    states,
    remove: (id: string) => known.delete(id),
    leave: (sourceId: string) => tiles.get(sourceId)?.clear(),
    fail: (sourceId: string, status: number | undefined, at: [number, number, number] = [14, 8668, 5456]) => {
      place(sourceId, at, 'errored');
      handlers.get('error')!({ sourceId, tile: tile(...at), error: status === undefined ? new Error('broken') : { status } });
    },
    failWithout: (sourceId: string | undefined, error: object) => {
      // The tile is in view and failed, but the event does not name it.
      place('layer-src-L1-0', [14, 8668, 5456], 'errored');
      handlers.get('error')!({ sourceId, error });
    },
    load: (sourceId: string, at: [number, number, number] = [14, 8668, 5456]) => {
      place(sourceId, at, 'loaded');
      handlers.get('sourcedata')!({ sourceId, tile: tile(...at, 'loaded') });
    },
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('a tile that failed while a service restarted', () => {
  it.each([502, 503, 504, 0, 429, 408])('is asked again after a %i', (status) => {
    const map = fakeMap();
    map.fail('layer-src-L1-0', status);
    expect(map.refreshed).toEqual([]);
    vi.advanceTimersByTime(RETRY_DELAYS_MS[0]);
    expect(map.refreshed).toEqual(['layer-src-L1-0/14/8668/5456']);
  });

  it('is asked again with a growing pause until the tiler answers, also for the search results and the view', () => {
    const map = fakeMap();
    map.fail('res-tiles-src-0', 502);
    vi.advanceTimersByTime(1_000);
    map.fail('res-tiles-src-0', 502);
    vi.advanceTimersByTime(1_999);
    expect(map.refreshed).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(map.refreshed).toHaveLength(2);
    map.load('res-tiles-src-0');
    // Loaded: a later restart starts with the short pause again.
    map.fail('res-tiles-src-0', 503);
    vi.advanceTimersByTime(1_000);
    expect(map.refreshed).toHaveLength(3);
  });

  it('is asked once per failure, not once per event of the same failure', () => {
    const map = fakeMap();
    map.fail('layer-src-L1-0', 502);
    map.fail('layer-src-L1-0', 502);
    vi.advanceTimersByTime(60_000);
    expect(map.refreshed).toEqual(['layer-src-L1-0/14/8668/5456']);
  });

  it('gives up after about two minutes of failures', () => {
    const map = fakeMap();
    for (const delay of RETRY_DELAYS_MS) {
      map.fail('layer-src-L1-0', 502);
      vi.advanceTimersByTime(delay);
    }
    expect(map.refreshed).toHaveLength(RETRY_DELAYS_MS.length);
    expect(RETRY_DELAYS_MS.reduce((a, b) => a + b, 0)).toBeGreaterThanOrEqual(120_000);
    map.fail('layer-src-L1-0', 502);
    vi.advanceTimersByTime(60_000);
    expect(map.refreshed).toHaveLength(RETRY_DELAYS_MS.length);
  });

  it('is asked again at once when another tile of its source loads (the service is back), also after it gave up', () => {
    const map = fakeMap();
    for (const delay of RETRY_DELAYS_MS) {
      map.fail('layer-src-L1-0', 502);
      vi.advanceTimersByTime(delay);
    }
    const before = map.refreshed.length;
    map.load('layer-src-L1-0', [14, 9, 9]);
    expect(map.refreshed.slice(before)).toEqual(['layer-src-L1-0/14/8668/5456']);
    // Its count starts afresh: a failure now waits 1 s.
    map.fail('layer-src-L1-0', 502);
    vi.advanceTimersByTime(1_000);
    expect(map.refreshed).toHaveLength(before + 2);
  });

  it('asks a source again at once at most every 10 s, so a tile refused for good is not asked over and over', () => {
    const map = fakeMap();
    for (const delay of RETRY_DELAYS_MS) {
      map.fail('layer-src-L1-0', 502);
      vi.advanceTimersByTime(delay);
    }
    map.fail('layer-src-L1-0', 502);
    const before = map.refreshed.length;
    map.load('layer-src-L1-0', [14, 9, 9]);
    map.load('layer-src-L1-0', [14, 9, 10]);
    vi.advanceTimersByTime(RECOVERY_GAP_MS - 1);
    map.load('layer-src-L1-0', [14, 9, 11]);
    expect(map.refreshed.length - before).toBe(1);
    vi.advanceTimersByTime(1);
    map.fail('layer-src-L1-0', 502);
    map.load('layer-src-L1-0', [14, 9, 12]);
    expect(map.refreshed.length - before).toBe(2);
  });

  it('does not take the load of a tile of another source or of the basemap for the service being back', () => {
    const map = fakeMap();
    for (const delay of RETRY_DELAYS_MS) {
      map.fail('layer-src-L1-0', 502);
      vi.advanceTimersByTime(delay);
    }
    const before = map.refreshed.length;
    map.load('res-tiles-src-0', [14, 9, 9]);
    map.load('basemap', [14, 9, 9]);
    expect(map.refreshed).toHaveLength(before);
  });

  it('keeps the tiles apart', () => {
    const map = fakeMap();
    map.fail('layer-src-L1-0', 502, [14, 1, 1]);
    map.fail('layer-src-L1-0', 502, [14, 1, 2]);
    vi.advanceTimersByTime(1_000);
    expect(map.refreshed).toEqual(['layer-src-L1-0/14/1/1', 'layer-src-L1-0/14/1/2']);
  });
});

describe('what is not asked again', () => {
  it.each([400, 404, 410, 422, 403, 500])('a refusal or a fault of the tiler (%i)', (status) => {
    const map = fakeMap();
    map.fail('layer-src-L1-0', status);
    vi.advanceTimersByTime(60_000);
    expect(map.refreshed).toEqual([]);
  });

  it('an error without a status (a picture that cannot be read)', () => {
    const map = fakeMap();
    map.fail('layer-src-L1-0', undefined);
    vi.advanceTimersByTime(60_000);
    expect(map.refreshed).toEqual([]);
  });

  it('the tiles of the basemap and of what is no layer', () => {
    const map = fakeMap(['basemap', 'coverage-src']);
    map.fail('basemap', 502);
    map.fail('coverage-src', 502);
    vi.advanceTimersByTime(60_000);
    expect(map.refreshed).toEqual([]);
  });

  it('a tile that left the view meanwhile, or loaded by itself', () => {
    const map = fakeMap();
    map.fail('layer-src-L1-0', 502);
    map.leave('layer-src-L1-0');
    map.fail('res-tiles-src-0', 502);
    map.load('res-tiles-src-0');
    vi.advanceTimersByTime(60_000);
    expect(map.refreshed).toEqual([]);
  });

  it('a source that was removed meanwhile (its layer is gone)', () => {
    const map = fakeMap();
    map.fail('layer-src-L1-0', 502);
    map.remove('layer-src-L1-0');
    vi.advanceTimersByTime(1_000);
    expect(map.refreshed).toEqual([]);
  });

  it('an event that names no tile (a failed style or source)', () => {
    const map = fakeMap();
    map.failWithout('layer-src-L1-0', { status: 502 });
    map.failWithout(undefined, { status: 502 });
    vi.advanceTimersByTime(60_000);
    expect(map.refreshed).toEqual([]);
  });
});

describe('how a tile is loaded again', () => {
  it('in the state "loading", which draws nothing until the picture is there (not "expired", which draws a tile without one)', () => {
    const map = fakeMap();
    map.fail('layer-src-L1-0', 503);
    vi.advanceTimersByTime(1_000);
    expect(map.states).toEqual(['loading']);
  });

  it('with the parts of MapLibre that are there: the tile managers of the style, their tiles by id and `_reloadTile`', () => {
    // `MapView.tsx` hands the map itself to `watchTileRetry`, so `tsc` checks the shapes as well.
    expect(maplibreTypes).toMatch(/\btileManagers: \{\s*\[_: string\]: TileManager;/u);
    expect(maplibreTypes).toMatch(/\bgetIds\(\): string\[\];/u);
    expect(maplibreTypes).toMatch(/\bgetTileByID\(id: string\): Tile \| undefined;/u);
    expect(maplibreTypes).toMatch(/\b_reloadTile\(id: string, state: TileState\): Promise<void>;/u);
  });
});

describe('isPassingFailure', () => {
  it('takes no answer, a timeout, too many requests and a gateway or a service away as passing, not a fault of the tiler', () => {
    for (const status of [0, 408, 429, 502, 503, 504]) expect(isPassingFailure(status)).toBe(true);
    for (const status of [undefined, 200, 204, 301, 400, 401, 403, 404, 410, 422, 500, 501, 599, 600]) expect(isPassingFailure(status)).toBe(false);
  });
});
