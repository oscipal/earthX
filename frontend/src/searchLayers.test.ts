import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { mosaicTemplateOf } from './mosaic';
import type { Mosaics } from './mosaic';
import { cropPasses, fullResolutionLayers, layersOnMap } from './searchLayers';
import { buildSections } from './sections';
import type { Collection, StacItem } from './types';

const DEM: Collection = {
  id: 'dem',
  title: 'Elevation',
  'earthx:capabilities': {
    roi: true,
    time_range: false,
    band_math: true,
    interpolation: true,
    ml_processing: true,
    quad_pol: false,
    single_coverage_product: true,
  },
  'earthx:viewer': {
    group_by: ['start_datetime'],
    min_zoom: 0,
    max_zoom: 15,
    browse: 'full_resolution',
    quicklook_nodata_max: null,
    results_group_by: ['start_datetime'],
  },
  'earthx:default_render': {
    title: 'Elevation',
    assets: ['data'],
    rescale: [[0, 4000]],
    colormap_name: 'terrain',
    expression: null,
    resampling: 'nearest',
  },
};

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 47]]] };

function tile(id: string, start: string, bbox: StacItem['bbox'] = [10, 47, 11, 48]): StacItem {
  return { id, collection: 'dem', bbox, properties: { start_datetime: start }, assets: {} };
}

function sectionFor(collection: Collection, items: StacItem[]) {
  const [dataset] = datasetsFrom([collection]);
  if (!dataset.viewable) throw new Error('fixture must be viewable');
  const { sections } = buildSections(items, [dataset], {
    ignoredFilters: [],
    ignoredFiltersByCollection: {},
    incompleteCollections: [],
  });
  return { dataset, section: sections[0] };
}

describe('fullResolutionLayers', () => {
  it('builds one cropped layer per time-step group', () => {
    const { dataset, section } = sectionFor(DEM, [
      tile('a', '2011-01-01T00:00:00Z'),
      tile('b', '2011-01-01T00:00:00Z'),
      tile('c', '2012-06-01T00:00:00Z'),
    ]);
    const layers = fullResolutionLayers(dataset, section, AOI, 'x');
    expect(layers).toHaveLength(2);
    expect(layers.every((l) => l.visible && l.opacity === 1)).toBe(true);
    expect(new Set(layers.map((l) => l.id)).size).toBe(2);
    expect(layers.map((l) => l.restore.itemIds.sort())).toEqual(
      section.groups.map((g) => g.items.map((i) => i.id).sort()),
    );
  });

  it('clips every tile URL to the AOI and marks the layer cropped and downloadable as a group', () => {
    const { dataset, section } = sectionFor(DEM, [tile('a', '2011-01-01T00:00:00Z')]);
    const [layer] = fullResolutionLayers(dataset, section, AOI, 'x');
    expect(layer.restore).toMatchObject({
      focusMode: true,
      cropToAoi: true,
      datasetId: 'dem',
      aoi: AOI,
      groupItemIds: [['a']],
    });
    const overlay = layer.overlays[0];
    if (overlay.kind !== 'raster') throw new Error('expected a raster overlay');
    expect(overlay.tileUrl).toContain('/collections/dem/items/a/');
    expect(overlay.tileUrl).toContain('colormap_name=terrain');
    expect(overlay.tileUrl.startsWith('earthx-clip://')).toBe(true);
    // The AOI stays in the browser: the URL carries an opaque key, never a coordinate.
    expect(overlay.tileUrl).not.toContain('47');
    expect([overlay.minZoom, overlay.maxZoom]).toEqual([0, 15]);
  });

  it('carries no AOI coordinates in the layer name', () => {
    const { dataset, section } = sectionFor(DEM, [tile('a', '2011-01-01T00:00:00Z')]);
    const [layer] = fullResolutionLayers(dataset, section, AOI, 'x');
    expect(layer.name).toBe('Elevation · 2011-01-01');
  });

  it('skips a scene with no bounding box, and a group left with none', () => {
    const { dataset, section } = sectionFor(DEM, [tile('a', '2011-01-01T00:00:00Z', null), tile('b', '2012-06-01T00:00:00Z')]);
    const layers = fullResolutionLayers(dataset, section, AOI, 'x');
    expect(layers).toHaveLength(1);
    expect(layers[0].restore.itemIds).toEqual(['b']);
  });

  // M4-17c: the tiles of a group of several scenes (the DEM over an AOI) are one mosaic.
  describe('with the mosaics of its groups', () => {
    const SAME_DAY = '2011-01-01T00:00:00Z';
    const twoTiles = () => sectionFor(DEM, [tile('a', SAME_DAY), tile('b', SAME_DAY)]);
    const mosaicOf = (section: ReturnType<typeof sectionFor>['section'], order = ['a', 'b']): Mosaics => {
      const entries = cropPasses([twoTiles().dataset], [section])[0].entries;
      const tileUrl = mosaicTemplateOf('dem', entries) as string;
      return { [tileUrl]: { tileUrl, bounds: [9, 46, 12, 49], minZoom: 8, maxZoom: 15, order } };
    };
    const rasters = (layer: { overlays: ReturnType<typeof fullResolutionLayers>[number]['overlays'] }) =>
      layer.overlays.map((o) => {
        if (o.kind !== 'raster') throw new Error('expected a raster overlay');
        return o;
      });

    it('is one mosaic overlay under the two scenes that step aside from z8, all clipped', () => {
      const { dataset, section } = twoTiles();
      const [layer] = fullResolutionLayers(dataset, section, AOI, 'x', mosaicOf(section));
      const overlays = rasters(layer);
      expect(overlays).toHaveLength(3);
      expect(overlays.every((o) => o.tileUrl.startsWith('earthx-clip://'))).toBe(true);
      expect(overlays.slice(0, 2).map((o) => [o.maxZoom, o.hideFrom])).toEqual([[7, 6.5], [7, 6.5]]);
      expect(overlays[2].tileUrl).toContain('/collections/dem/mosaic/tiles/');
      expect(overlays[2].tileUrl).toContain('colormap_name=terrain');
      expect([overlays[2].minZoom, overlays[2].maxZoom, overlays[2].hideFrom]).toEqual([8, 15, undefined]);
      expect(layer.restore.itemIds.sort()).toEqual(['a', 'b']);
    });

    it('stacks the scenes in the order the mosaic reads them, the first on top', () => {
      const { dataset, section } = twoTiles();
      const [layer] = fullResolutionLayers(dataset, section, AOI, 'x', mosaicOf(section, ['b', 'a']));
      const [bottom, top] = rasters(layer);
      expect(bottom.tileUrl).toContain('/items/a/');
      expect(top.tileUrl).toContain('/items/b/');
    });

    it('is drawn scene by scene until the mosaic has loaded, and when it was refused', () => {
      const { dataset, section } = twoTiles();
      for (const mosaics of [undefined, {}, Object.fromEntries(Object.keys(mosaicOf(section)).map((k) => [k, null]))]) {
        const [layer] = fullResolutionLayers(dataset, section, AOI, 'x', mosaics);
        const overlays = rasters(layer);
        expect(overlays).toHaveLength(2);
        expect(overlays.every((o) => o.hideFrom === undefined && o.tileUrl.includes('/items/'))).toBe(true);
      }
    });

    it('leaves a group of one scene a scene', () => {
      const { dataset, section } = sectionFor(DEM, [tile('a', SAME_DAY)]);
      const [layer] = fullResolutionLayers(dataset, section, AOI, 'x', {});
      expect(rasters(layer)).toHaveLength(1);
    });
  });

  describe('cropPasses', () => {
    it('names the scenes of each group of a dataset with no preview, by group', () => {
      const { dataset, section } = sectionFor(DEM, [
        tile('a', '2011-01-01T00:00:00Z'),
        tile('b', '2011-01-01T00:00:00Z'),
        tile('c', '2012-06-01T00:00:00Z'),
      ]);
      const passes = cropPasses([dataset], [section]);
      expect(passes.map((p) => p.entries.map(([id]) => id).sort())).toEqual([['c'], ['a', 'b']]);
      expect(passes.every((p) => p.datasetId === 'dem')).toBe(true);
    });

    it('names nothing for a dataset that has a quicklook to show first, or no standard visualisation', () => {
      const quicklook = sectionFor({ ...DEM, 'earthx:viewer': { ...DEM['earthx:viewer']!, browse: 'quicklook' } }, [tile('a', '2011-01-01T00:00:00Z')]);
      expect(cropPasses([quicklook.dataset], [quicklook.section])).toEqual([]);
      const bare = sectionFor({ ...DEM, 'earthx:default_render': null }, [tile('a', '2011-01-01T00:00:00Z')]);
      expect(cropPasses([bare.dataset], [bare.section])).toEqual([]);
    });
  });

  it('pins nothing for a dataset that names no standard visualisation', () => {
    const { dataset, section } = sectionFor({ ...DEM, 'earthx:default_render': null }, [tile('a', '2011-01-01T00:00:00Z')]);
    expect(fullResolutionLayers(dataset, section, AOI, 'x')).toEqual([]);
  });

  it('pins nothing for an empty section', () => {
    const { dataset, section } = sectionFor(DEM, []);
    expect(fullResolutionLayers(dataset, section, AOI, 'x')).toEqual([]);
  });
});

describe('layersOnMap', () => {
  function layer(id: string, datasetId: string | null) {
    return { id, name: id, visible: true, opacity: 1, overlays: [], restore: { datasetId } as never };
  }
  const pinned = [layer('p1', 'optical'), layer('p2', 'dem')];
  const crops = [layer('c1', 'dem'), layer('c2', 'dem'), layer('c3', 'other-full-resolution')];

  it("draws the pinned layers, and under them the crops of the chosen dataset only", () => {
    expect(layersOnMap(pinned, crops, 'dem').map((l) => l.id)).toEqual(['p1', 'p2', 'c1', 'c2']);
  });

  it('draws no crop when the chosen dataset has none', () => {
    expect(layersOnMap(pinned, crops, 'optical').map((l) => l.id)).toEqual(['p1', 'p2']);
  });

  it('draws only the pinned layers when no dataset is chosen', () => {
    expect(layersOnMap(pinned, crops, null).map((l) => l.id)).toEqual(['p1', 'p2']);
  });

  describe('a crop that is pinned already', () => {
    const raster = (url: string) => [
      { kind: 'raster' as const, tileUrl: url, bounds: [0, 0, 1, 1] as [number, number, number, number], minZoom: 0, maxZoom: 12 },
    ];
    const withPicture = (id: string, url: string, visible = true) => ({ ...layer(id, 'dem'), overlays: raster(url), visible });

    it('is not drawn a second time', () => {
      const copy = withPicture('pinned', 'https://t/dem/1');
      const crop = withPicture('crop', 'https://t/dem/1');
      expect(layersOnMap([copy], [crop], 'dem').map((l) => l.id)).toEqual(['pinned']);
    });

    it('is not drawn either when the pinned copy is switched off', () => {
      const copy = withPicture('pinned', 'https://t/dem/1', false);
      expect(layersOnMap([copy], [withPicture('crop', 'https://t/dem/1')], 'dem').map((l) => l.id)).toEqual(['pinned']);
    });

    it('is drawn again once its copy is gone', () => {
      expect(layersOnMap([], [withPicture('crop', 'https://t/dem/1')], 'dem').map((l) => l.id)).toEqual(['crop']);
    });

    it('stays when what is pinned is another picture, or only part of it', () => {
      const crops = [withPicture('crop', 'https://t/dem/1')];
      expect(layersOnMap([withPicture('other', 'https://t/dem/2')], crops, 'dem').map((l) => l.id)).toEqual(['other', 'crop']);
      const two = { ...withPicture('two', 'https://t/dem/1'), overlays: [...raster('https://t/dem/1'), ...raster('https://t/dem/2')] };
      expect(layersOnMap([two], crops, 'dem').map((l) => l.id)).toEqual(['two', 'crop']);
    });
  });

  it('copes with nothing pinned and nothing cropped', () => {
    expect(layersOnMap([], [], 'dem')).toEqual([]);
  });
});
