// Otto, 15.11.2026: "a picture never disappears, in any view". The search-results view below the first level of a dataset with a pyramid
// or a substitute draws the picture of the dataset on the overview route of a footprint selection, which the tiler masks to the
// footprints of the hits that are shown (adr/0032 Nachtrag 15.11.2026). Before: nothing below the first level.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { json, selectionIdOf } from './fixtures/selectionTiler';
import { zoomMap } from './fixtures/zoomMap';
import { MAX_MOSAIC_LAYERS, setViewOpacity, syncBrowseMosaic, syncFocusRaster } from './mapLayers';
import { forgetFootprintSelections } from './overviewHits';
import type { Collection, StacItem } from './types';

const CAPABILITIES = { roi: true, time_range: false, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
const viewer = (min: number, max: number, over: Record<string, unknown> = {}) => ({
  group_by: ['datetime'],
  min_zoom: min,
  max_zoom: max,
  browse: 'full_resolution' as const,
  quicklook_nodata_max: null,
  results_group_by: ['datetime'],
  overview: 'pyramid' as const,
  overview_resampling: 'average' as const,
  overview_substitute: null,
  ...over,
});
const collection = (id: string, min: number, over: Record<string, unknown> = {}, extent = [-180, -90, 180, 84]): Collection =>
  ({
    id,
    title: id,
    extent: { spatial: { bbox: [extent] } },
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': viewer(min, 15, over),
    'earthx:default_render': { title: 'Standard', assets: ['data'], rescale: [[0, 100]], colormap_name: 'viridis', expression: null, resampling: 'nearest' },
  }) as never;

const LIST = datasetsFrom([
  collection('cover', 5),
  collection('relief', 7),
  collection('terrain', 13, { overview: 'substitute', overview_resampling: null, overview_substitute: 'relief' }, [5.9, 45.7, 10.5, 47.8]),
  collection('plain', 8, { overview: 'own', overview_resampling: null }),
]);
const byId = (id: string) => LIST.find((d) => d.id === id)!;
const hit = (id: string, collectionId: string, bbox: number[] = [8, 46, 9, 47]): StacItem =>
  ({ id, collection: collectionId, bbox, properties: { datetime: '2026-07-24T10:00:00Z' }, assets: {} }) as unknown as StacItem;

// Every map zoom from 0 to 14.9 in tenths.
const ZOOMS = Array.from({ length: 150 }, (_, i) => i / 10);

const posted: { url: string; body: { items: string[] } }[] = [];
beforeEach(() => {
  posted.length = 0;
  forgetFootprintSelections();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: { body: string }) => {
      const body = JSON.parse(init.body) as { items: string[] };
      posted.push({ url, body });
      const dataset = /collections\/([^/]+)\/overview\/footprints/.exec(url)![1];
      const id = selectionIdOf(dataset, [], body.items);
      return json({ id, tiles: `/collections/${dataset}/overview/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}` }, 201);
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const browse = (hits: StacItem[], dataset = byId('cover'), over: Record<string, unknown> = {}) => {
  const live = zoomMap();
  syncBrowseMosaic(live.map as never, { items: hits, dataset, datasets: LIST, selectedIds: [], ...over });
  return live;
};
const urlOf = (live: ReturnType<typeof zoomMap>, layerId: string) => (live.sources.get(live.layers.get(layerId)!.source!)!.tiles as string[])[0];
const hole = (live: ReturnType<typeof zoomMap>) => ZOOMS.filter((zoom) => live.picturesAt(zoom).length === 0);
const arrived = () => vi.waitFor(() => expect(posted.length).toBeGreaterThan(0));

describe('the search results of a dataset with a pyramid', () => {
  it('draw a picture at every map zoom from 0 to 14.9: the overview below the first level, the scenes from there on', async () => {
    const live = browse([hit('a', 'cover'), hit('b', 'cover')]);
    await arrived();
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    expect(hole(live)).toEqual([]);
    expect(urlOf(live, live.picturesAt(0)[0])).toMatch(/\/collections\/cover\/overview\/[0-9a-f]{32}\/tiles\/WebMercatorQuad\//);
    expect(urlOf(live, live.picturesAt(10)[0])).toContain('/collections/cover/items/');
  });

  it('are masked by a selection of the shown hits, sorted, with the look of their preview', async () => {
    const live = browse([hit('b', 'cover'), hit('a', 'cover')]);
    await arrived();
    expect(posted).toHaveLength(1);
    expect(posted[0].url).toMatch(/\/collections\/cover\/overview\/footprints$/);
    expect(posted[0].body).toEqual({ items: ['a', 'b'] });
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    const url = urlOf(live, live.picturesAt(0)[0]);
    expect(url).toContain(`/overview/${selectionIdOf('cover', [], ['a', 'b'])}/tiles/`);
    expect(url).toContain('colormap_name=viridis');
    expect(url).toContain('tilesize=512');
  });

  it('are one hit as well: the view of a single scene', async () => {
    const live = browse([hit('only', 'cover')]);
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    expect(posted[0].body).toEqual({ items: ['only'] });
    expect(hole(live)).toEqual([]);
  });

  it('lie over the hits only: the source is bounded by their box', async () => {
    const live = browse([hit('a', 'cover', [8, 46, 9, 47]), hit('b', 'cover', [10, 40, 11, 41])]);
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    const source = live.sources.get(live.layers.get(live.picturesAt(0)[0])!.source!)!;
    expect(source).toMatchObject({ minzoom: 0, maxzoom: 4, bounds: [8, 40, 11, 47] });
  });

  it('are masked to the first 40 hits, the ones the view draws above the first level', async () => {
    const hits = Array.from({ length: 60 }, (_, n) => hit(`h${String(n).padStart(2, '0')}`, 'cover'));
    browse(hits);
    await arrived();
    expect(posted[0].body.items).toHaveLength(MAX_MOSAIC_LAYERS);
    expect(posted[0].body.items).toEqual(hits.slice(0, MAX_MOSAIC_LAYERS).map((h) => h.id).sort());
  });

  it('keep the picture on a sync of the same hits, so a tick does not reload its tiles, and ask the tiler once', async () => {
    const live = browse([hit('a', 'cover')]);
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    const [layer] = live.picturesAt(0);
    const placed = () => live.log.sourcesAdded.filter((id) => id.startsWith('res-tiles-src-1')).length;
    const before = placed();
    syncBrowseMosaic(live.map as never, { items: [hit('a', 'cover')], dataset: byId('cover'), datasets: LIST, selectedIds: ['a'] });
    await Promise.resolve();
    expect(live.picturesAt(0)).toEqual([layer]);
    expect(placed()).toBe(before);
    expect(posted).toHaveLength(1);
  });

  it('change with the hits: other hits are another selection, none are no picture', async () => {
    const live = browse([hit('a', 'cover')]);
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    syncBrowseMosaic(live.map as never, { items: [hit('a', 'cover'), hit('b', 'cover')], dataset: byId('cover'), datasets: LIST, selectedIds: [] });
    await vi.waitFor(() => expect(posted).toHaveLength(2));
    await vi.waitFor(() => expect(urlOf(live, live.picturesAt(0)[0])).toContain(selectionIdOf('cover', [], ['a', 'b'])));
    syncBrowseMosaic(live.map as never, { items: [], dataset: byId('cover'), datasets: LIST, selectedIds: [] });
    expect(live.picturesAt(0)).toEqual([]);
  });

  it('are gone when the view gives way to the full-resolution view, which draws its own picture', async () => {
    const live = browse([hit('a', 'cover')]);
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    syncFocusRaster(live.map as never, { downloaded: {}, render: {}, showDownloaded: true, aoi: null, cropToAoi: false, items: [], dataset: byId('cover'), datasets: LIST, groups: [], mosaics: {} } as never);
    expect(live.stack.filter((id) => id.startsWith('res-tiles-lyr-1'))).toEqual([]);
  });

  it('take the opacity of the view', async () => {
    const live = browse([hit('a', 'cover')]);
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    setViewOpacity(live.map as never, 0.4);
    expect(live.layers.get(live.picturesAt(0)[0])!.paint['raster-opacity']).toBe(0.4);
    setViewOpacity(live.map as never, 1);
  });

  it('stay under the scenes: the overview is the lowest picture of the results', async () => {
    const live = browse([hit('a', 'cover')]);
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    const overview = live.stack.findIndex((id) => id.startsWith('res-tiles-lyr-1'));
    const scenes = live.stack.flatMap((id, at) => (/^[mn]-tiles-lyr-\d+$/.test(id) ? [at] : []));
    expect(overview).toBeGreaterThanOrEqual(0);
    expect(scenes.every((at) => at > overview)).toBe(true);
  });
});

describe('the search results of a dataset with a substitute (swissALTI3D with GLO-30)', () => {
  it('draw a picture at every map zoom from 0 to 14.9, the overview route of the dataset below its first level 13', async () => {
    const live = browse([hit('t', 'terrain')], byId('terrain'));
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(1));
    expect(hole(live)).toEqual([]);
    expect(posted[0].url).toMatch(/\/collections\/terrain\/overview\/footprints$/);
    expect(urlOf(live, live.picturesAt(12)[0])).toContain('/collections/terrain/overview/');
    expect(urlOf(live, live.picturesAt(14)[0])).toContain('/collections/terrain/items/');
  });
});

describe('what stays as it was', () => {
  it('a dataset with neither a pyramid nor a substitute asks for no selection and has nothing below its first level', async () => {
    const live = browse([hit('p', 'plain')], byId('plain'));
    await Promise.resolve();
    expect(posted).toEqual([]);
    expect(live.picturesAt(0)).toEqual([]);
  });

  it('a refusal of the tiler leaves the hits as they were, without an error', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockImplementation(async () => json({ detail: 'refused' }, 501));
    const live = browse([hit('a', 'cover')]);
    await vi.waitFor(() => expect(fetch).toHaveBeenCalled());
    await Promise.resolve();
    expect(live.picturesAt(0)).toEqual([]);
    expect(live.picturesAt(10)).toHaveLength(1);
  });

  it('hits of several datasets are one picture for each', async () => {
    const live = browse([hit('a', 'cover'), hit('r', 'relief')]);
    await vi.waitFor(() => expect(posted).toHaveLength(2));
    await vi.waitFor(() => expect(live.picturesAt(0)).toHaveLength(2));
    expect(posted.map((p) => p.url.split('/')[2]).sort()).toEqual(['cover', 'relief']);
  });
});
