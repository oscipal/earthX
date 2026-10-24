// UI-01a (Befund Punkt 10): the order of the list is the order of the map. Each case here
// failed against the code before UI-01a: a budget of overlays that ran short at the top of
// the list.

import { describe, expect, it } from 'vitest';

import type { LayerOverlay } from './layers';
import { syncLayers } from './mapLayers';
import { liveMap, lyr, pinned } from './fixtures/liveMap';

type Live = ReturnType<typeof liveMap>;

const raster = (tileUrl: string): LayerOverlay => ({
  kind: 'raster',
  tileUrl,
  bounds: [10, 47, 11, 48],
  minZoom: 8,
  maxZoom: 14,
});

const layersOf = (live: Live, id: string) => [...live.layers.keys()].filter((k) => k.startsWith(`layer-lyr-${id}-`));

describe('syncLayers: the budget of overlays counts from the top of the list', () => {
  const big = (id: string, n: number) => pinned(id, 'unused', { overlays: Array.from({ length: n }, (_, i) => raster(`https://t/${id}/${i}`)) });
  const four = (order = ['a', 'b', 'c', 'd']) => order.map((id) => big(id, 65));

  it('draws the layers on top whole and cuts the bottom one', () => {
    const live = liveMap();
    const notDrawn = syncLayers(live.map as never, four());
    expect([layersOf(live, 'a').length, layersOf(live, 'b').length, layersOf(live, 'c').length, layersOf(live, 'd').length]).toEqual([
      65, 65, 65, 5,
    ]);
    expect(notDrawn).toBe(60);
  });

  it('draws a layer whole once it is moved to the top, and cuts the one now at the bottom', () => {
    const live = liveMap();
    syncLayers(live.map as never, four());
    syncLayers(live.map as never, four(['d', 'a', 'b', 'c']));
    expect([layersOf(live, 'd').length, layersOf(live, 'c').length]).toEqual([65, 5]);
  });

  it('keeps the top overlays of a layer that is cut, which is the mosaic of a pinned time step', () => {
    const live = liveMap();
    const notDrawn = syncLayers(live.map as never, [big('m', 205)]);
    expect(live.layers.has(lyr('m', 204))).toBe(true);
    expect(live.layers.has(lyr('m', 5))).toBe(true);
    expect(live.layers.has(lyr('m', 4))).toBe(false);
    expect(notDrawn).toBe(5);
  });

  it('says nothing when every overlay fits', () => {
    expect(syncLayers(liveMap().map as never, four().slice(0, 3))).toBe(0);
  });
});
