// UI-06: the switch to 3D and back on a stand-in of the map (no WebGL in Vitest), and the flat extent of a tilted map.

import { afterEach, describe, expect, it, vi } from 'vitest';

import { TERRAIN_ATTRIBUTION, TERRAIN_MAXZOOM, TERRAIN_TILES } from './relief';
import { applyTerrain, flatViewBounds, MAX_PITCH, PITCH_3D, TERRAIN_EXAGGERATION, TERRAIN_SOURCE, type TerrainMap } from './terrain';

function handler() {
  let on = false;
  return {
    enable: vi.fn(() => (on = true)),
    disable: vi.fn(() => (on = false)),
    enableRotation: vi.fn(() => (on = true)),
    disableRotation: vi.fn(() => (on = false)),
    get on() {
      return on;
    },
  };
}

// The map as `terrain.ts` uses it: a camera that moves at once, a terrain, sources and the handlers of turning and tilting.
function fakeMap(start: { pitch?: number; bearing?: number } = {}) {
  const state = { pitch: start.pitch ?? 0, bearing: start.bearing ?? 0, maxPitch: 0, terrain: null as unknown, sources: {} as Record<string, unknown> };
  const waiting: (() => void)[] = [];
  const move = (to: { pitch?: number; bearing?: number }) => {
    state.pitch = Math.min(to.pitch ?? state.pitch, state.maxPitch);
    state.bearing = to.bearing ?? state.bearing;
  };
  const map = {
    state,
    // A flight ends when the test says so.
    land: () => waiting.splice(0).forEach((done) => done()),
    getSource: (id: string) => state.sources[id],
    addSource: vi.fn((id: string, source: unknown) => {
      state.sources[id] = source;
    }),
    getTerrain: () => state.terrain,
    setTerrain: vi.fn((terrain: unknown) => {
      state.terrain = terrain;
    }),
    setMaxPitch: vi.fn((max: number) => {
      state.maxPitch = max;
      state.pitch = Math.min(state.pitch, max);
    }),
    getPitch: () => state.pitch,
    getBearing: () => state.bearing,
    easeTo: vi.fn((to: { pitch?: number; bearing?: number }) => move(to)),
    jumpTo: vi.fn((to: { pitch?: number; bearing?: number }) => move(to)),
    once: vi.fn((event: string, done: () => void) => {
      if (event === 'moveend') waiting.push(done);
    }),
    dragRotate: handler(),
    touchZoomRotate: handler(),
    touchPitch: handler(),
    keyboard: handler(),
  };
  return map;
}

const asMap = (map: ReturnType<typeof fakeMap>) => map as unknown as TerrainMap;
const turning = (map: ReturnType<typeof fakeMap>) => [map.dragRotate.on, map.touchZoomRotate.on, map.touchPitch.on, map.keyboard.on];

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('applyTerrain on (UI-06 F5)', () => {
  it('lays the map over its own terrain source, lifts the tilt to 60° and tilts to 50° in a flight', () => {
    const map = fakeMap();
    applyTerrain(asMap(map), true, { animate: true, stillOff: () => false });
    expect(map.state.sources[TERRAIN_SOURCE]).toEqual({ type: 'raster-dem', tiles: [TERRAIN_TILES], encoding: 'terrarium', tileSize: 256, maxzoom: TERRAIN_MAXZOOM, attribution: TERRAIN_ATTRIBUTION });
    expect(map.state.terrain).toEqual({ source: TERRAIN_SOURCE, exaggeration: TERRAIN_EXAGGERATION });
    expect(map.state.maxPitch).toBe(MAX_PITCH);
    expect(map.easeTo).toHaveBeenCalledWith({ pitch: PITCH_3D });
    expect(map.state.pitch).toBe(50);
    expect(turning(map)).toEqual([true, true, true, true]);
  });

  it('has a source without the prefix of a basemap or an overlay, so that a change of the basemap keeps it', () => {
    expect(TERRAIN_SOURCE).toBe('terrain');
    expect(TERRAIN_SOURCE.startsWith('bm-') || TERRAIN_SOURCE.startsWith('ov-')).toBe(false);
  });

  it('jumps without a flight at the start of a visit, and when the system asks for less motion', () => {
    const first = fakeMap();
    applyTerrain(asMap(first), true, { animate: false, stillOff: () => false });
    expect(first.easeTo).not.toHaveBeenCalled();
    expect(first.jumpTo).toHaveBeenCalledWith({ pitch: PITCH_3D });

    vi.stubGlobal('window', { matchMedia: (query: string) => ({ matches: query === '(prefers-reduced-motion: reduce)' }) });
    const calm = fakeMap();
    applyTerrain(asMap(calm), true, { animate: true, stillOff: () => false });
    expect(calm.easeTo).not.toHaveBeenCalled();
    expect(calm.state.pitch).toBe(50);
  });

  it('adds the source and the terrain only once when switched on twice', () => {
    const map = fakeMap();
    applyTerrain(asMap(map), true, { animate: true, stillOff: () => false });
    applyTerrain(asMap(map), true, { animate: true, stillOff: () => false });
    expect(map.addSource).toHaveBeenCalledTimes(1);
    expect(map.setTerrain).toHaveBeenCalledTimes(1);
  });
});

describe('applyTerrain off (UI-06 F5, D27 in 2D)', () => {
  it('turns north and lies flat in a flight, then takes the terrain away and locks the tilt again', () => {
    const map = fakeMap();
    applyTerrain(asMap(map), true, { animate: true, stillOff: () => false });
    map.state.bearing = 40;
    applyTerrain(asMap(map), false, { animate: true, stillOff: () => true });
    expect(map.easeTo).toHaveBeenLastCalledWith({ pitch: 0, bearing: 0 });
    expect(turning(map)).toEqual([false, false, false, false]);
    // The terrain stays until the flight has ended: taken away at a tilt, the map would jump.
    expect(map.state.terrain).not.toBeNull();
    map.land();
    expect(map.state.terrain).toBeNull();
    expect(map.state.maxPitch).toBe(0);
    expect([map.state.pitch, map.state.bearing]).toEqual([0, 0]);
  });

  it('leaves the terrain when 3D is switched on again before the flight back has ended', () => {
    const map = fakeMap();
    applyTerrain(asMap(map), true, { animate: true, stillOff: () => false });
    let off = true;
    applyTerrain(asMap(map), false, { animate: true, stillOff: () => off });
    off = false;
    applyTerrain(asMap(map), true, { animate: true, stillOff: () => off });
    map.land();
    expect(map.state.terrain).not.toBeNull();
    expect(map.state.maxPitch).toBe(MAX_PITCH);
  });

  it('settles at once when the map is already flat and facing north, and on a map that never had a terrain', () => {
    const map = fakeMap();
    applyTerrain(asMap(map), false, { animate: true, stillOff: () => true });
    expect(map.easeTo).not.toHaveBeenCalled();
    expect(map.setTerrain).not.toHaveBeenCalled();
    expect(map.state.maxPitch).toBe(0);
  });

  it('jumps back without a flight when asked to', () => {
    const map = fakeMap({ pitch: 0, bearing: 30 });
    map.state.terrain = { source: TERRAIN_SOURCE };
    applyTerrain(asMap(map), false, { animate: false, stillOff: () => true });
    expect(map.jumpTo).toHaveBeenCalledWith({ pitch: 0, bearing: 0 });
    expect(map.state.terrain).toBeNull();
  });
});

describe('flatViewBounds (UI-06 F10)', () => {
  // The flat box of a map 1024 × 512 px at zoom 1 is the world from west to east.
  it('is the world across at zoom 1 for a map 1024 px wide', () => {
    const [west, , east] = flatViewBounds([0, 0], 1, 1024, 512, 0);
    expect(west).toBeCloseTo(-180, 6);
    expect(east).toBeCloseTo(180, 6);
  });

  it('is the box around the centre, as wide as the map at that zoom', () => {
    const [west, south, east, north] = flatViewBounds([10, 47], 8, 512, 512, 0);
    // 512 px are 360 / 2^8 degrees of longitude at zoom 8.
    expect(east - west).toBeCloseTo(360 / 256, 6);
    expect((west + east) / 2).toBeCloseTo(10, 6);
    expect(south).toBeLessThan(47);
    expect(north).toBeGreaterThan(47);
  });

  it('grows with a turn to hold the turned map, the same at 90° as a map on its side', () => {
    const straight = flatViewBounds([10, 47], 8, 800, 400, 0);
    const turned = flatViewBounds([10, 47], 8, 800, 400, 45);
    expect(turned[2] - turned[0]).toBeGreaterThan(straight[2] - straight[0]);
    const side = flatViewBounds([10, 47], 8, 800, 400, 90);
    const upright = flatViewBounds([10, 47], 8, 400, 800, 0);
    side.forEach((value, i) => expect(value).toBeCloseTo(upright[i], 6));
  });

  it('is the world across when the map is wider than the world, and keeps the latitudes in the map', () => {
    const [west, south, east, north] = flatViewBounds([170, 80], 0.5, 4000, 4000, 0);
    expect([west, east]).toEqual([-180, 180]);
    expect(north).toBeLessThanOrEqual(85.06);
    expect(south).toBeGreaterThanOrEqual(-85.06);
  });

  it('gives finite numbers for a centre at the pole and at the date line', () => {
    for (const center of [[0, 90], [0, -90], [180, 0], [-180, 0]] as [number, number][]) {
      expect(flatViewBounds(center, 3, 800, 600, 10).every(Number.isFinite)).toBe(true);
    }
  });
});
