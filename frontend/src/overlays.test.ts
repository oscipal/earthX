// UI-02b: the catalogue of the overlays and the graticule the browser draws itself.

import { describe, expect, it } from 'vitest';

import { GRATICULE_SOURCE, graticuleData, graticuleLayers, NO_OVERLAYS, OVERLAY_IDS, OVERLAY_PREFIX, OVERLAYS } from './overlays';

describe('the overlay catalogue', () => {
  it('offers labels, a graticule and the relief, all off to begin with', () => {
    expect(OVERLAY_IDS).toEqual(['labels', 'graticule', 'relief']);
    expect(NO_OVERLAYS).toEqual({ labels: false, graticule: false, relief: false });
    expect(Object.keys(OVERLAYS)).toEqual([...OVERLAY_IDS]);
  });

  it('names each in English and says where it comes from', () => {
    expect(OVERLAYS.labels.name).toBe('Labels');
    expect(OVERLAYS.labels.tip).toContain('openfreemap.org');
    expect(OVERLAYS.graticule.name).toBe('Graticule');
    expect(OVERLAYS.graticule.tip).toContain('in the browser');
    expect(OVERLAYS.relief.name).toBe('Relief');
    expect(OVERLAYS.relief.tip).toContain('amazonaws.com');
  });
});

const lines = () => graticuleData().features;
const stepOfLine = (feature: GeoJSON.Feature) => (feature.properties as { step: number }).step;
const coordinates = (feature: GeoJSON.Feature) => (feature.geometry as GeoJSON.LineString).coordinates;
// A meridian has one longitude all along, a parallel one latitude.
const meridians = () => lines().filter((f) => new Set(coordinates(f).map(([lon]) => lon)).size === 1);
const parallels = () => lines().filter((f) => new Set(coordinates(f).map(([, lat]) => lat)).size === 1);

describe('graticuleData', () => {
  it('holds a meridian for every degree of longitude and a parallel for every degree of latitude up to 85°', () => {
    expect(meridians()).toHaveLength(360);
    expect(parallels()).toHaveLength(171);
    expect(lines()).toHaveLength(531);
  });

  it('puts the lines where they belong: the equator, the prime meridian and 30° steps are in the coarsest grid', () => {
    const at = (list: GeoJSON.Feature[], index: 0 | 1, value: number) => list.find((f) => coordinates(f)[0][index] === value)!;
    expect(stepOfLine(at(parallels(), 1, 0))).toBe(30);
    expect(stepOfLine(at(meridians(), 0, 0))).toBe(30);
    expect(stepOfLine(at(meridians(), 0, -60))).toBe(30);
    expect(stepOfLine(at(meridians(), 0, 10))).toBe(10);
    expect(stepOfLine(at(parallels(), 1, -40))).toBe(10);
    expect(stepOfLine(at(meridians(), 0, 35))).toBe(5);
    expect(stepOfLine(at(parallels(), 1, 85))).toBe(5);
    expect(stepOfLine(at(meridians(), 0, 7))).toBe(1);
    expect(stepOfLine(at(parallels(), 1, 48))).toBe(1);
  });

  it('counts the lines of each grid: 30°, 10°, 5° and 1°', () => {
    const count = (step: number) => lines().filter((f) => stepOfLine(f) >= step).length;
    // Meridians -180..150 every 30 (12) and parallels -60..60 every 30 (5).
    expect(count(30)).toBe(17);
    // Every 10°: 36 meridians and 17 parallels (-80..80).
    expect(count(10)).toBe(53);
    // Every 5°: 72 meridians and 35 parallels (-85..85).
    expect(count(5)).toBe(107);
    expect(count(1)).toBe(531);
  });

  it('stays inside what Mercator can draw and gives every line a vertex at least every 5° (a parallel stays straight on the globe)', () => {
    for (const feature of lines()) {
      const points = coordinates(feature);
      for (const [lon, lat] of points) {
        expect(Math.abs(lat)).toBeLessThanOrEqual(85);
        expect(lon).toBeGreaterThanOrEqual(-180);
        expect(lon).toBeLessThanOrEqual(180);
      }
      for (let i = 1; i < points.length; i++) {
        expect(Math.abs(points[i][0] - points[i - 1][0]) + Math.abs(points[i][1] - points[i - 1][1])).toBeLessThanOrEqual(5);
      }
    }
  });

  it('is made once', () => {
    expect(graticuleData()).toBe(graticuleData());
  });
});

describe('graticuleLayers', () => {
  const layers = graticuleLayers();

  it('has one line layer for each grid, from the source of the overlay, with the prefix of the overlays', () => {
    expect(layers.map((l) => l.id)).toEqual(['ov-graticule-30', 'ov-graticule-10', 'ov-graticule-5', 'ov-graticule-1']);
    for (const layer of layers) {
      expect(layer.type).toBe('line');
      expect(layer.id.startsWith(OVERLAY_PREFIX)).toBe(true);
      expect('source' in layer && layer.source).toBe(GRATICULE_SOURCE);
    }
  });

  it('shows 30° below zoom 3, 10° from 3 to 6, 5° from 6 to 8 and 1° from 8 on, each zoom exactly one layer', () => {
    const shown = (zoom: number) => layers.filter((l) => (l.minzoom ?? 0) <= zoom && zoom < (l.maxzoom ?? 24)).map((l) => l.id);
    for (const [zoom, id] of [[0, 30], [2.9, 30], [3, 10], [5.9, 10], [6, 5], [7.9, 5], [8, 1], [20, 1]] as const) {
      expect(shown(zoom)).toEqual([`ov-graticule-${id}`]);
    }
  });

  it('filters the lines of its grid and every coarser one, and none for the finest', () => {
    expect(layers.map((l) => ('filter' in l ? l.filter : undefined))).toEqual([
      ['>=', ['get', 'step'], 30],
      ['>=', ['get', 'step'], 10],
      ['>=', ['get', 'step'], 5],
      undefined,
    ]);
  });
});
