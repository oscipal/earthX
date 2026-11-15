// The picture below the first level for the hits of a search (adr/0032 Nachtrag 15.11.2026): which hits get one, and the selection that
// masks it. Synthetic collections only.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { FOOTPRINTS_KEPT_MS, footprintSelectionFor, forgetFootprintSelections, hitsOverviewsOf } from './overviewHits';
import type { Collection, StacItem } from './types';

const CAPABILITIES = { roi: true, time_range: false, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
const viewer = (min: number, over: Record<string, unknown> = {}) => ({
  group_by: ['datetime'],
  min_zoom: min,
  max_zoom: 15,
  browse: 'full_resolution' as const,
  quicklook_nodata_max: null,
  results_group_by: ['datetime'],
  overview: 'pyramid' as const,
  overview_resampling: 'average' as const,
  overview_substitute: null,
  ...over,
});
const render = { title: 'Standard', assets: ['data'], rescale: [[0, 100]] as [number, number][], colormap_name: 'viridis', expression: null, resampling: 'nearest' };
const collection = (id: string, min: number, over: Record<string, unknown> = {}, extent: number[] = [-180, -90, 180, 84]): Collection =>
  ({ id, title: id, extent: { spatial: { bbox: [extent] } }, 'earthx:capabilities': CAPABILITIES, 'earthx:viewer': viewer(min, over), 'earthx:default_render': render }) as never;

const LIST = datasetsFrom([
  collection('cover', 5),
  collection('relief', 7),
  collection('terrain', 13, { overview: 'substitute', overview_resampling: null, overview_substitute: 'relief' }, [5.9, 45.7, 10.5, 47.8]),
  collection('plain', 8, { overview: 'own', overview_resampling: null }),
]);
const byId = (id: string) => LIST.find((d) => d.id === id) ?? null;
const hit = (id: string, collectionId: string, bbox: number[] = [10, 47, 11, 48], assets: StacItem['assets'] = {}): StacItem =>
  ({ id, collection: collectionId, bbox, properties: { datetime: '2026-07-24T10:00:00Z' }, assets }) as unknown as StacItem;
const of = (items: StacItem[]) => hitsOverviewsOf(items, (item) => byId(item.collection ?? ''), LIST);

describe('which hits get a picture below the first level', () => {
  it('one for each dataset with a pyramid or a substitute, over its hits, sorted and each once', () => {
    const out = of([hit('b', 'cover'), hit('a', 'cover'), hit('t', 'terrain', [8, 46, 9, 47]), hit('a', 'cover')]);
    expect(out.map((o) => [o.datasetId, o.itemIds])).toEqual([['cover', ['a', 'b']], ['terrain', ['t']]]);
  });

  it('has the levels of the dataset: 0 to one below its first level, hidden from where its own tiles begin', () => {
    const [one] = of([hit('a', 'cover')]);
    expect(one.raster).toMatchObject({ minZoom: 0, maxZoom: 4 });
    expect(one.raster.hideFrom).toBeGreaterThan(4);
    expect(one.raster.hideFrom).toBeLessThan(5);
    const [sub] = of([hit('t', 'terrain', [8, 46, 9, 47])]);
    expect(sub.raster).toMatchObject({ minZoom: 0, maxZoom: 12 });
  });

  it('lies over the hits, not over the dataset: the box of the hits, cut to the extent of the dataset', () => {
    const [two] = of([hit('a', 'cover', [10, 47, 11, 48]), hit('b', 'cover', [12, 40, 13, 41])]);
    expect(two.raster.bounds).toEqual([10, 40, 13, 48]);
    const [cut] = of([hit('t', 'terrain', [5, 45, 20, 50])]);
    expect(cut.raster.bounds).toEqual([5.9, 45.7, 10.5, 47.8]);
  });

  it('reads a box with heights (six numbers)', () => {
    expect(of([hit('a', 'cover', [10, 47, 0, 11, 48, 900])])[0].raster.bounds).toEqual([10, 47, 11, 48]);
  });

  it('has the look of the preview of the hits', () => {
    expect(of([hit('a', 'cover')])[0].render).toMatchObject({ rescale: '0,100', colormapName: 'viridis' });
  });

  it('draws nothing for a dataset that has neither a pyramid nor a substitute', () => {
    expect(of([hit('p', 'plain')])).toEqual([]);
  });

  it('draws nothing for a hit that has a quicklook image (the image is drawn at every level) or no outline', () => {
    const withImage = {
      ...hit('i', 'cover', [10, 47, 11, 48], {
        thumbnail: { href: 'https://img.example/a.png', roles: ['thumbnail'] },
        data: { href: 'https://example.test/data.tif', 'proj:transform': [10, 0, 600000, 0, -10, 5300000], 'proj:shape': [100, 100] },
      } as never),
      properties: { datetime: '2026-07-24T10:00:00Z', 'proj:epsg': 32632 },
    } as StacItem;
    expect(of([withImage])).toEqual([]);
    expect(of([{ ...hit('n', 'cover'), bbox: undefined } as never])).toEqual([]);
  });

  it('draws nothing where the hits lie outside the extent of the dataset', () => {
    expect(of([hit('t', 'terrain', [100, 10, 101, 11])])).toEqual([]);
  });

  it('draws nothing for a hit whose dataset is not known', () => {
    expect(of([hit('a', 'nowhere')])).toEqual([]);
  });
});

describe('the selection of the hits', () => {
  afterEach(() => forgetFootprintSelections());
  const made = () => vi.fn(async (datasetId: string, ids: readonly string[]) => ({ id: `${datasetId}-${ids.join('')}`, tiles: 'https://tiler.test/x/{z}/{x}/{y}' }));

  it('is made once for the same hits, and again for other hits or another dataset', async () => {
    const create = made();
    const [a, b, c, d] = await Promise.all([
      footprintSelectionFor('cover', ['a', 'b'], create),
      footprintSelectionFor('cover', ['a', 'b'], create),
      footprintSelectionFor('cover', ['a'], create),
      footprintSelectionFor('relief', ['a', 'b'], create),
    ]);
    expect(create).toHaveBeenCalledTimes(3);
    expect(a).toBe(b);
    expect([a.id, c.id, d.id]).toEqual(['cover-ab', 'cover-a', 'relief-ab']);
  });

  it('is asked for again after an hour, which renews it at the tiler', async () => {
    const create = made();
    let at = 1000;
    await footprintSelectionFor('cover', ['a'], create, () => at);
    at += FOOTPRINTS_KEPT_MS - 1;
    await footprintSelectionFor('cover', ['a'], create, () => at);
    expect(create).toHaveBeenCalledTimes(1);
    at += 2;
    await footprintSelectionFor('cover', ['a'], create, () => at);
    expect(create).toHaveBeenCalledTimes(2);
  });

  it('is not kept after a failure: the next sync asks again', async () => {
    const create = vi.fn().mockRejectedValueOnce(new Error('refused')).mockResolvedValue({ id: 'x', tiles: 't' });
    await expect(footprintSelectionFor('cover', ['a'], create)).rejects.toThrow('refused');
    await Promise.resolve();
    await expect(footprintSelectionFor('cover', ['a'], create)).resolves.toMatchObject({ id: 'x' });
    expect(create).toHaveBeenCalledTimes(2);
  });
});
