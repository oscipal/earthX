import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import { fullResolutionLayers, layersOnMap } from './searchLayers';
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

  it('copes with nothing pinned and nothing cropped', () => {
    expect(layersOnMap([], [], 'dem')).toEqual([]);
  });
});
