// UI-08 (Otto, 16.11.2026): a layer whose tiles failed while the services restarted loads them again by itself, without a reload of the page.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { isPassingFailure, RETRY_DELAYS_MS, watchTileRetry } from './tileRetry';

type Handler = (event: object) => void;

// A fake map: the handlers it was given, the sources it has and the tiles it was asked to load again.
function fakeMap(sources = ['layer-src-L1-0', 'res-tiles-src-0', 'basemap']) {
  const handlers = new Map<string, Handler>();
  const known = new Set(sources);
  const refreshed: string[] = [];
  const map = {
    on: (type: string, handler: Handler) => handlers.set(type, handler),
    getSource: (id: string) => (known.has(id) ? {} : undefined),
    refreshTiles: (id: string, tiles: { x: number; y: number; z: number }[]) => refreshed.push(...tiles.map((t) => `${id}/${t.z}/${t.x}/${t.y}`)),
  };
  watchTileRetry(map as unknown as Parameters<typeof watchTileRetry>[0]);
  const tile = (z: number, x: number, y: number, state = 'errored') => ({ tileID: { canonical: { x, y, z } }, state });
  return {
    refreshed,
    remove: (id: string) => known.delete(id),
    fail: (sourceId: string, status: number | undefined, at: [number, number, number] = [14, 8668, 5456]) =>
      handlers.get('error')!({ sourceId, tile: tile(...at), error: status === undefined ? new Error('broken') : { status } }),
    load: (sourceId: string, at: [number, number, number] = [14, 8668, 5456]) => handlers.get('sourcedata')!({ sourceId, tile: tile(...at, 'loaded') }),
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('a tile that failed while a service restarted', () => {
  it.each([502, 503, 504, 500, 0, 429, 408])('is asked again after a %i', (status) => {
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

  it('gives up after about four minutes of failures', () => {
    const map = fakeMap();
    for (const delay of RETRY_DELAYS_MS) {
      map.fail('layer-src-L1-0', 502);
      vi.advanceTimersByTime(delay);
    }
    expect(map.refreshed).toHaveLength(RETRY_DELAYS_MS.length);
    expect(RETRY_DELAYS_MS.reduce((a, b) => a + b, 0)).toBeGreaterThanOrEqual(240_000);
    map.fail('layer-src-L1-0', 502);
    vi.advanceTimersByTime(60_000);
    expect(map.refreshed).toHaveLength(RETRY_DELAYS_MS.length);
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
  it.each([400, 404, 410, 422, 403])('a refusal (%i)', (status) => {
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

  it('a source that was removed meanwhile (its layer is gone)', () => {
    const map = fakeMap();
    map.fail('layer-src-L1-0', 502);
    map.remove('layer-src-L1-0');
    vi.advanceTimersByTime(1_000);
    expect(map.refreshed).toEqual([]);
  });

  it('an event that names no tile (a failed style or source)', () => {
    const handlers = new Map<string, Handler>();
    const refreshTiles = vi.fn();
    watchTileRetry({ on: (t: string, h: Handler) => handlers.set(t, h), getSource: () => ({}), refreshTiles } as unknown as Parameters<typeof watchTileRetry>[0]);
    handlers.get('error')!({ sourceId: 'layer-src-L1-0', error: { status: 502 } });
    handlers.get('error')!({ error: { status: 502 } });
    vi.advanceTimersByTime(60_000);
    expect(refreshTiles).not.toHaveBeenCalled();
  });
});

describe('isPassingFailure', () => {
  it('takes no answer, a timeout, too many requests and a server error as passing', () => {
    for (const status of [0, 408, 429, 500, 502, 503, 504, 599]) expect(isPassingFailure(status)).toBe(true);
    for (const status of [undefined, 200, 204, 301, 400, 401, 403, 404, 410, 422, 600]) expect(isPassingFailure(status)).toBe(false);
  });
});
