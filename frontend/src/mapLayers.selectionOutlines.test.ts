// Every selected scene is outlined on the map, whatever their number (plan M5-30 §8.7, Otto, 13.11.2026: with 124 selected
// swissALTI3D scenes only part of the outlines were drawn). The cap of `MAX_MOSAIC_LAYERS` is for raster layers, which cost a
// source and a layer each; an outline is a feature of one GeoJSON source.

import { describe, expect, it } from 'vitest';

import { MAX_SELECTION_ITEMS } from './mosaic';
import { syncHighlight, syncSelectionHighlight } from './mapLayers';
import type { StacItem, TimeStepGroup } from './types';

// A row of 1 km tiles along a parallel, one degree-hundredth apart.
const scenes = (n: number): StacItem[] =>
  Array.from({ length: n }, (_, i) => ({
    id: `tile-${i}`,
    bbox: [7 + i * 0.01, 47, 7.0 + i * 0.01 + 0.009, 47.009] as [number, number, number, number],
    properties: {},
    assets: {},
  }));

function published() {
  let fc: GeoJSON.FeatureCollection | undefined;
  const map = { getSource: (id: string) => (id === 'mosaicsel-src' ? { setData: (d: GeoJSON.FeatureCollection) => (fc = d) } : undefined) };
  return { map, features: () => fc?.features ?? [] };
}

const ids = (features: GeoJSON.Feature[]) => features.map((f) => f.properties?.id);

describe('the outlines of the selected scenes', () => {
  it.each([1, 40, 41, 124, 500, MAX_SELECTION_ITEMS])('draws one outline for each of %i selected scenes', (n) => {
    const all = scenes(n);
    const { map, features } = published();
    syncSelectionHighlight(map as never, all, all.map((it) => it.id));
    expect(features()).toHaveLength(n);
    expect(ids(features())).toEqual(all.map((it) => it.id));
  });

  it('outlines only the selected ones of many scenes', () => {
    const all = scenes(124);
    const selected = all.filter((_, i) => i % 3 === 0).map((it) => it.id);
    const { map, features } = published();
    syncSelectionHighlight(map as never, all, selected);
    expect(ids(features())).toEqual(selected);
  });

  it('draws the outlines of a selection beyond the first forty also through `syncHighlight` while browsing', () => {
    const all = scenes(124);
    const { map, features } = published();
    syncHighlight(map as never, { items: all, selectedIds: all.map((it) => it.id), focusMode: false, cropToAoi: false, aoi: null, downloaded: {}, groups: undefined });
    expect(features()).toHaveLength(124);
  });

  it('draws the outline of each pass of a cropped view, however many scenes make a pass', () => {
    const all = scenes(124);
    const groups: TimeStepGroup[] = [{ key: ['a'], label: 'a', items: all }];
    const aoi: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[6, 46], [9, 46], [9, 48], [6, 48], [6, 46]]] };
    const { map, features } = published();
    syncHighlight(map as never, { items: all, selectedIds: all.map((it) => it.id), focusMode: true, cropToAoi: true, aoi, downloaded: Object.fromEntries(all.map((it) => [it.id, {}])) as never, groups });
    const outline = features()[0].geometry;
    // One merged ring over all 124 tiles, which lie side by side: its extent is that of the last tile, not of the fortieth.
    const lons = (outline.type === 'Polygon' ? outline.coordinates.flat() : outline.type === 'MultiPolygon' ? outline.coordinates.flat(2) : []).map((p) => p[0]);
    expect(Math.max(...lons)).toBeCloseTo(7 + 123 * 0.01 + 0.009, 6);
  });

  it('draws nothing for a scene without a footprint and nothing for an empty selection', () => {
    const { map, features } = published();
    syncSelectionHighlight(map as never, [{ id: 'x', properties: {}, assets: {} } as StacItem], ['x']);
    expect(features()).toHaveLength(0);
    syncSelectionHighlight(map as never, scenes(5), []);
    expect(features()).toHaveLength(0);
  });
});
