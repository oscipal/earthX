import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HttpError } from './api';
import { json, selectionIdOf, selectionServer, type SelectionServerOptions } from './fixtures/selectionTiler';
import {
  ensureSelection,
  knownSelections,
  renewSelection,
  resetSelections,
  selectionIdOfUrl,
  selectionKeyOf,
  watchGoneSelections,
  withSelection,
} from './mosaicSelection';

const DATASET = 'sentinel-2-c1-l2a';

function stubTiler(options: SelectionServerOptions = {}) {
  const server = selectionServer(options);
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => (await server.answer(url, init)) ?? json({ detail: 'not found' }, 404));
  vi.stubGlobal('fetch', fetchMock);
  return { server, fetchMock };
}

beforeEach(() => resetSelections());
afterEach(() => vi.unstubAllGlobals());

describe('the key of a selection', () => {
  it('is the same for the same scenes and assets in any order, each once', () => {
    expect(selectionKeyOf(DATASET, ['b', 'a'], ['S2', 'S1', 'S2'])).toBe(selectionKeyOf(DATASET, ['a', 'b'], ['S1', 'S2']));
  });

  it.each([
    ['another dataset', selectionKeyOf('other', ['a'], ['S1', 'S2'])],
    ['another asset', selectionKeyOf(DATASET, ['b'], ['S1', 'S2'])],
    ['another list of scenes', selectionKeyOf(DATASET, ['a'], ['S1', 'S3'])],
  ])('is another for %s', (_, other) => {
    expect(other).not.toBe(selectionKeyOf(DATASET, ['a'], ['S1', 'S2']));
  });

  it('cannot be mixed up by a name that holds the separator of another', () => {
    expect(selectionKeyOf(DATASET, ['a,b'], ['S1', 'S2'])).not.toBe(selectionKeyOf(DATASET, ['a', 'b'], ['S1', 'S2']));
    expect(selectionKeyOf(DATASET, ['a'], ['S1,S2'])).not.toBe(selectionKeyOf(DATASET, ['a'], ['S1', 'S2']));
  });
});

describe('ensureSelection', () => {
  it('creates a selection once per key, for any number of asks', async () => {
    const { server } = stubTiler();
    const first = await ensureSelection(DATASET, ['S2', 'S1'], ['visual']);
    const again = await ensureSelection(DATASET, ['S1', 'S2'], ['visual']);
    expect(again).toBe(first);
    expect(server.created).toHaveLength(1);
    expect(first.id).toBe(selectionIdOf(DATASET, ['visual'], ['S1', 'S2']));
    expect(knownSelections.get(selectionKeyOf(DATASET, ['visual'], ['S1', 'S2']))).toBe(first);
  });

  it('shares one request between asks that come while it is being created', async () => {
    const { fetchMock } = stubTiler();
    const [a, b, c] = await Promise.all([
      ensureSelection(DATASET, ['S1', 'S2'], ['visual']),
      ensureSelection(DATASET, ['S2', 'S1'], ['visual']),
      ensureSelection(DATASET, ['S1', 'S2'], ['visual']),
    ]);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(b).toBe(a);
    expect(c).toBe(a);
  });

  it('creates another selection for another asset of the same scenes', async () => {
    const { server } = stubTiler();
    const [visual, red] = await Promise.all([ensureSelection(DATASET, ['S1', 'S2'], ['visual']), ensureSelection(DATASET, ['S1', 'S2'], ['red'])]);
    expect(server.created).toHaveLength(2);
    expect(visual.id).not.toBe(red.id);
  });

  it('sends the scenes and the assets in the body, sorted, never in the URL', async () => {
    const { fetchMock } = stubTiler();
    await ensureSelection(DATASET, ['S2', 'S1'], ['nir', 'red']);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`/collections/${DATASET}/mosaic`);
    expect(JSON.parse(String(init?.body))).toEqual({ items: ['S1', 'S2'], assets: ['nir', 'red'] });
  });

  it('passes the refusal of the tiler on, keeps nothing, and creates again at the next ask', async () => {
    let refuse = true;
    const { server } = stubTiler({ create: () => (refuse ? json({ detail: 'the scenes are of different passes' }, 422) : undefined) });
    await expect(ensureSelection(DATASET, ['S1', 'S2'], ['visual'])).rejects.toMatchObject({ status: 422, message: 'the scenes are of different passes' });
    expect(knownSelections.size).toBe(0);
    refuse = false;
    await expect(ensureSelection(DATASET, ['S1', 'S2'], ['visual'])).resolves.toMatchObject({ datasetId: DATASET });
    expect(server.created).toHaveLength(2);
  });

  it('fails for a network that fails, as for a refusal', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    await expect(ensureSelection(DATASET, ['S1', 'S2'], ['visual'])).rejects.toThrow('Failed to fetch');
  });
});

describe('renewSelection', () => {
  it('creates the same list again, which is the same id', async () => {
    const { server } = stubTiler();
    const selection = await ensureSelection(DATASET, ['S1', 'S2'], ['visual']);
    server.selections.clear(); // the tiler forgot it
    await expect(renewSelection(selection.id)).resolves.toBe(true);
    expect(server.created.map((c) => c.id)).toEqual([selection.id, selection.id]);
    expect(server.selections.has(selection.id)).toBe(true);
  });

  it('is one request for the callers that ask together', async () => {
    const { server } = stubTiler();
    const selection = await ensureSelection(DATASET, ['S1', 'S2'], ['visual']);
    await Promise.all([renewSelection(selection.id), renewSelection(selection.id), renewSelection(selection.id)]);
    expect(server.created).toHaveLength(2);
  });

  it('is false for an id the page never made, and asks nothing', async () => {
    const { fetchMock } = stubTiler();
    await expect(renewSelection('f'.repeat(32))).resolves.toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('is false, not an error, where the tiler no longer takes the list', async () => {
    let refuse = false;
    stubTiler({ create: () => (refuse ? json({ detail: 'gone' }, 422) : undefined) });
    const selection = await ensureSelection(DATASET, ['S1', 'S2'], ['visual']);
    refuse = true;
    await expect(renewSelection(selection.id)).resolves.toBe(false);
  });
});

describe('withSelection', () => {
  const gone = () => new HttpError(410, 'no selection');

  it('answers what the question answers', async () => {
    stubTiler();
    const selection = await ensureSelection(DATASET, ['S1', 'S2'], ['visual']);
    await expect(withSelection(selection, async () => 'ok')).resolves.toBe('ok');
  });

  it('creates the selection again after a 410 and asks once more', async () => {
    const { server } = stubTiler();
    const selection = await ensureSelection(DATASET, ['S1', 'S2'], ['visual']);
    const ask = vi.fn().mockRejectedValueOnce(gone()).mockResolvedValueOnce('second');
    await expect(withSelection(selection, ask)).resolves.toBe('second');
    expect(ask).toHaveBeenCalledTimes(2);
    expect(server.created).toHaveLength(2);
  });

  it('asks only twice: a tiler that keeps saying 410 ends in its error', async () => {
    stubTiler();
    const selection = await ensureSelection(DATASET, ['S1', 'S2'], ['visual']);
    const ask = vi.fn().mockRejectedValue(gone());
    await expect(withSelection(selection, ask)).rejects.toMatchObject({ status: 410 });
    expect(ask).toHaveBeenCalledTimes(2);
  });

  it.each([
    ['another status', new HttpError(503, 'down')],
    ['a network that fails', new TypeError('Failed to fetch')],
  ])('creates nothing again for %s', async (_, error) => {
    const { server } = stubTiler();
    const selection = await ensureSelection(DATASET, ['S1', 'S2'], ['visual']);
    await expect(withSelection(selection, vi.fn().mockRejectedValue(error))).rejects.toBe(error);
    expect(server.created).toHaveLength(1);
  });

  it('gives the 410 back where the selection cannot be created again', async () => {
    const selection = { id: 'f'.repeat(32), datasetId: DATASET, tiles: 't', tilejson: 'j' };
    await expect(withSelection(selection, vi.fn().mockRejectedValue(gone()))).rejects.toMatchObject({ status: 410 });
  });
});

describe('selectionIdOfUrl', () => {
  const id = '0123456789abcdef0123456789abcdef';

  it('finds the id in the address of a tile and of a TileJSON', () => {
    expect(selectionIdOfUrl(`/collections/d/mosaic/${id}/tiles/WebMercatorQuad/3/4/5?tilesize=512`)).toBe(id);
    expect(selectionIdOfUrl(`https://api.example.org/collections/d/mosaic/${id}/WebMercatorQuad/tilejson.json?op=x`)).toBe(id);
  });

  it.each(['/collections/d/items/S1/tiles/WebMercatorQuad/3/4/5', '/collections/d/mosaic', `/collections/d/mosaic/${id.toUpperCase()}/tiles`, '/collections/d/mosaic/abc/tiles', ''])(
    'finds none in %s',
    (url) => {
      expect(selectionIdOfUrl(url)).toBeNull();
    },
  );
});

describe('watchGoneSelections', () => {
  // A map that holds raster sources and tells when its sources are loaded again; errors are fired by the test.
  function fakeMap(sources: Record<string, { type: string; tiles?: string[] }>) {
    let onError: (event: unknown) => void = () => {};
    const reloaded: [string, string[]][] = [];
    const map = {
      on: (name: string, handler: (event: unknown) => void) => {
        if (name === 'error') onError = handler;
      },
      getStyle: () => ({ sources }),
      getSource: (id: string) => ({ setTiles: (tiles: string[]) => reloaded.push([id, tiles]) }),
    };
    return { map, reloaded, fire: (event: unknown) => onError(event) };
  }
  const tile = (id: string, over: object = {}) => ({ error: { status: 410, url: `/collections/${DATASET}/mosaic/${id}/tiles/WebMercatorQuad/3/4/5?tilesize=512`, ...over } });
  // Long enough for a renewal that is going to happen to have happened.
  const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 30));

  async function watched(sourcesOf: (id: string) => Record<string, { type: string; tiles?: string[] }>) {
    const tiler = stubTiler();
    const selection = await ensureSelection(DATASET, ['S1', 'S2'], ['visual']);
    const live = fakeMap(sourcesOf(selection.id));
    let clock = 1_000;
    watchGoneSelections(live.map as never, () => clock);
    return { ...tiler, ...live, selection, advance: (ms: number) => (clock += ms) };
  }
  const sources = (id: string) => ({
    'tiles-src-0': { type: 'raster', tiles: [`/collections/${DATASET}/mosaic/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512`] },
    'tiles-src-1': { type: 'raster', tiles: [`/collections/${DATASET}/mosaic/${'a'.repeat(32)}/tiles/WebMercatorQuad/{z}/{x}/{y}`] },
    'tiles-src-2': { type: 'raster', tiles: [`/collections/${DATASET}/items/S1/tiles/WebMercatorQuad/{z}/{x}/{y}`] },
    'aoi-src': { type: 'geojson' },
  });

  it('creates the selection of a tile that answered 410 again, and loads the sources that name it again, no others', async () => {
    const live = await watched(sources);
    live.fire(tile(live.selection.id));
    await vi.waitFor(() => expect(live.reloaded).toHaveLength(1));
    expect(live.server.created.map((c) => c.id)).toEqual([live.selection.id, live.selection.id]);
    expect(live.reloaded[0][0]).toBe('tiles-src-0');
    expect(live.reloaded[0][1][0]).toContain(`/mosaic/${live.selection.id}/`);
  });

  it('creates it once for the many tiles of a view that fail together', async () => {
    const live = await watched(sources);
    for (let i = 0; i < 12; i++) live.fire(tile(live.selection.id));
    await vi.waitFor(() => expect(live.reloaded).toHaveLength(1));
    await settle();
    expect(live.server.created).toHaveLength(2);
    expect(live.reloaded).toHaveLength(1);
  });

  it.each([
    ['another status of a tile', tile('0'.repeat(32), { status: 503 })],
    ['a failure with no status', { error: new TypeError('Failed to fetch') }],
    ['an error with no error', {}],
    ['a 410 of a request that names no selection', { error: { status: 410, url: '/collections/d/items/S1/tiles/WebMercatorQuad/1/1/1' } }],
    ['a 410 with no address', { error: { status: 410 } }],
  ])('leaves %s to MapLibre', async (_, event) => {
    const live = await watched(sources);
    live.fire(event);
    await settle();
    expect(live.server.created).toHaveLength(1);
    expect(live.reloaded).toEqual([]);
  });

  it('leaves a selection the page never made alone: there is nothing to create it from', async () => {
    const live = await watched(sources);
    live.fire(tile('a'.repeat(32)));
    await settle();
    expect(live.server.created).toHaveLength(1);
    expect(live.reloaded).toEqual([]);
  });

  it('loads nothing again where the tiler no longer takes the list', async () => {
    const live = await watched(sources);
    live.server.created.length = 0;
    vi.stubGlobal('fetch', vi.fn(async () => json({ detail: 'no' }, 422)));
    live.fire(tile(live.selection.id));
    await settle();
    expect(live.reloaded).toEqual([]);
  });

  it('renews again after a while, but not without end: a tiler whose tiles stay 410 is left alone', async () => {
    const live = await watched(sources);
    for (let round = 1; round <= 5; round++) {
      live.fire(tile(live.selection.id));
      await settle();
      live.advance(10_000);
    }
    expect(live.server.created.length).toBe(1 + 3);
    expect(live.reloaded).toHaveLength(3);
  });
});
