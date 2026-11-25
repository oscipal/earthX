// @vitest-environment jsdom
// UI-12 (5) and (6), Otto 18.11.2026: an AOI that comes in another way than drawing ends the tool chosen for drawing, and an AOI
// "Point" is a point on the map, not the square around it.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Map as MapLibreMap } from 'maplibre-gl';

import { liveMap } from './fixtures/liveMap';
import { bboxToPolygon, bufferPointToPolygon } from './geoUtils';
import { ensureBaseLayers } from './mapLayers';
import { useAppStore } from './store';

const PLACE = bboxToPolygon([7.29, 46.91, 7.5, 46.99]);
const POINT: GeoJSON.Point = { type: 'Point', coordinates: [7.44, 46.95] };
const state = () => useAppStore.getState();

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  useAppStore.setState({ aoi: null, aoiPoint: null, lastAoi: null, lastAoiPoint: null, toolMode: 'none', dock: 'controls' });
});
afterEach(() => vi.unstubAllGlobals());

describe('a tool chosen for drawing', () => {
  it.each(['rectangle', 'polygon', 'point'] as const)('"%s" ends when a place or a file gives the AOI', (tool) => {
    state().setToolMode(tool);
    expect(state().toolMode).toBe(tool);
    state().setAoi(PLACE);
    expect(state().toolMode).toBe('none');
    expect(state().aoi).toBe(PLACE);
  });

  it('stays while the AOI is only taken away', () => {
    state().setAoi(PLACE);
    state().setToolMode('rectangle');
    state().setAoi(null);
    expect(state().toolMode).toBe('rectangle');
  });

  it('ends with "Last AOI" as well', () => {
    state().setAoi(PLACE);
    state().clearAoi();
    state().setToolMode('rectangle');
    state().useLastAoi();
    expect(state().toolMode).toBe('none');
  });
});

describe('an AOI "Point"', () => {
  it('keeps the point itself beside the square, also for "Last AOI"', () => {
    state().setAoi(bufferPointToPolygon(7.44, 46.95, 0.05), POINT);
    expect(state().aoiPoint).toEqual(POINT);
    state().clearAoi();
    expect(state().aoiPoint).toBeNull();
    state().useLastAoi();
    expect(state().aoiPoint).toEqual(POINT);
  });

  it('has a layer of its own on the map that draws a point, above the outline of an area', () => {
    const live = liveMap([]);
    const added: { id: string; type?: string; filter?: unknown }[] = [];
    const addLayer = live.map.addLayer;
    live.map.addLayer = (layer, before) => {
      added.push(layer as { id: string; type?: string; filter?: unknown });
      addLayer(layer, before);
    };
    ensureBaseLayers(live.map as unknown as MapLibreMap);
    const point = added.find((l) => l.id === 'aoi-point');
    expect(point?.type).toBe('circle');
    expect(point?.filter).toEqual(['==', ['geometry-type'], 'Point']);
    expect(live.stack.indexOf('aoi-point')).toBeGreaterThan(live.stack.indexOf('aoi-line'));
  });
});
