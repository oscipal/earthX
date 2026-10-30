// A time step that is played arrives over the picture it replaces without being seen, and is shown once its tiles are in
// and `notBefore` has passed (NM4-18). A fake map that keeps its layers and says which sources have all their tiles: what
// is under test is which layers are on it, and how they are drawn, at each moment.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import type { StacItem } from './types';

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};

const [dataset] = datasetsFrom([
  {
    id: 'synthetic',
    title: 'Synthetic dataset',
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    'earthx:default_render': { title: 'Grey', assets: ['data'], rescale: [[0, 1]] as [number, number][], colormap_name: null, expression: null, resampling: 'nearest' },
  },
]);

const scene = (id: string): StacItem => ({ id, bbox: [10, 47, 11, 48], properties: { datetime: '2026-07-24T10:00:00Z' }, assets: {} });

interface FakeLayer {
  id: string;
  source: string;
  paint: Record<string, unknown>;
}

// The layers on the map, in `layers`; a source is loaded once `arrive` has been told, as its tiles are.
function stateMap() {
  const layers = new Map<string, FakeLayer>();
  const sources = new Set<string>();
  const loaded = new Set<string>();
  const handlers = new Map<string, Set<() => void>>();
  const on = (name: string, fn: () => void) => handlers.set(name, (handlers.get(name) ?? new Set()).add(fn));
  const off = (name: string, fn: () => void) => handlers.get(name)?.delete(fn);
  const map = {
    getLayer: (id: string) => layers.get(id),
    getSource: (id: string) => (sources.has(id) ? {} : undefined),
    addSource: (id: string) => sources.add(id),
    removeSource: (id: string) => {
      sources.delete(id);
      loaded.delete(id);
    },
    addLayer: (layer: { id: string; source: string; paint?: Record<string, unknown> }) => layers.set(layer.id, { id: layer.id, source: layer.source, paint: { ...layer.paint } }),
    removeLayer: (id: string) => layers.delete(id),
    setPaintProperty: (id: string, name: string, value: unknown) => {
      layers.get(id)!.paint[name] = value;
    },
    isSourceLoaded: (id: string) => loaded.has(id),
    on,
    off,
    once: (name: string, fn: () => void) => {
      const once = () => {
        off(name, once);
        fn();
      };
      on(name, once);
    },
  };
  return {
    map,
    layers,
    // The tiles of every source on the map have come in.
    arrive: () => sources.forEach((id) => loaded.add(id)),
    fire: (name: string) => [...(handlers.get(name) ?? [])].forEach((fn) => fn()),
    opacity: (id: string) => layers.get(id)?.paint['raster-opacity'],
    ids: () => [...layers.keys()].sort(),
  };
}

const NOW = new Date('2026-10-30T12:00:00Z').getTime();

let L: typeof import('./mapLayers');
beforeEach(async () => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  // The module keeps the picture on the map in its own variables: a fresh one for each case.
  vi.resetModules();
  L = await import('./mapLayers');
});
afterEach(() => vi.useRealTimers());

function step(fake: ReturnType<typeof stateMap>, id: string, hold: { notBefore: number; onShown: () => void } | undefined) {
  L.syncBrowseMosaic(fake.map as never, { items: [scene(id)], dataset, hold });
}

// A picture on the map that is not a held one, as the first step of the playing is.
function showFirst(fake: ReturnType<typeof stateMap>) {
  step(fake, 'first', undefined);
  fake.arrive();
  fake.fire('idle');
}

describe('a time step that is played', () => {
  it('lies out of sight over the picture on the map, which stays until the step has arrived', () => {
    const fake = stateMap();
    showFirst(fake);
    expect(fake.ids()).toEqual(['m-tiles-lyr-0']);
    const onShown = vi.fn();
    step(fake, 'second', { notBefore: NOW, onShown });
    expect(fake.ids()).toEqual(['m-tiles-lyr-0', 'n-tiles-lyr-0']);
    expect(fake.opacity('n-tiles-lyr-0')).toBe(0);
    expect(fake.opacity('m-tiles-lyr-0')).toBe(1);
    // A frame with the tiles still on their way changes nothing.
    fake.fire('render');
    expect(fake.ids()).toEqual(['m-tiles-lyr-0', 'n-tiles-lyr-0']);
    expect(fake.opacity('n-tiles-lyr-0')).toBe(0);
    expect(onShown).not.toHaveBeenCalled();
  });

  it('is shown with the old picture taken away in the same moment, once its tiles are in', () => {
    const fake = stateMap();
    showFirst(fake);
    const onShown = vi.fn();
    step(fake, 'second', { notBefore: NOW, onShown });
    fake.arrive();
    fake.fire('render');
    expect(fake.ids()).toEqual(['n-tiles-lyr-0']);
    expect(fake.opacity('n-tiles-lyr-0')).toBe(1);
    expect(onShown).toHaveBeenCalledTimes(1);
    // Said once: later frames do not say it again.
    fake.fire('render');
    expect(onShown).toHaveBeenCalledTimes(1);
  });

  it('does not fade in: the opacity changes at once, as the old picture goes at once', () => {
    const fake = stateMap();
    showFirst(fake);
    step(fake, 'second', { notBefore: NOW, onShown: vi.fn() });
    expect(fake.layers.get('n-tiles-lyr-0')?.paint['raster-opacity-transition']).toEqual({ duration: 0, delay: 0 });
  });

  it('waits for the minimum time of the picture before it, if its tiles are in sooner', () => {
    const fake = stateMap();
    showFirst(fake);
    const onShown = vi.fn();
    step(fake, 'second', { notBefore: NOW + 1400, onShown });
    fake.arrive();
    fake.fire('render');
    expect(fake.ids()).toEqual(['m-tiles-lyr-0', 'n-tiles-lyr-0']);
    vi.advanceTimersByTime(1399);
    expect(onShown).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(fake.ids()).toEqual(['n-tiles-lyr-0']);
    expect(onShown).toHaveBeenCalledTimes(1);
  });

  it('is not shown by the tiles of anything else on the map: only its own count', () => {
    const fake = stateMap();
    showFirst(fake);
    const onShown = vi.fn();
    step(fake, 'second', { notBefore: NOW, onShown });
    // `idle` is the map as a whole (the basemap too); it says nothing about the step.
    fake.fire('idle');
    expect(onShown).not.toHaveBeenCalled();
    expect(fake.ids()).toEqual(['m-tiles-lyr-0', 'n-tiles-lyr-0']);
  });

  it('is dropped when the next step is asked for before it has arrived; the picture on the map stays', () => {
    const fake = stateMap();
    showFirst(fake);
    const second = vi.fn();
    const third = vi.fn();
    step(fake, 'second', { notBefore: NOW, onShown: second });
    step(fake, 'third', { notBefore: NOW, onShown: third });
    expect(fake.ids()).toEqual(['m-tiles-lyr-0', 'n-tiles-lyr-0']);
    expect(fake.opacity('m-tiles-lyr-0')).toBe(1);
    expect(fake.opacity('n-tiles-lyr-0')).toBe(0);
    // The layer that is on its way is the third step's: its source is the one that has to arrive.
    expect(fake.layers.get('n-tiles-lyr-0')?.source).toBe('n-tiles-src-0');
    fake.arrive();
    fake.fire('render');
    expect(fake.ids()).toEqual(['n-tiles-lyr-0']);
    expect(second).not.toHaveBeenCalled();
    expect(third).toHaveBeenCalledTimes(1);
  });

  it('takes the place of the picture on the map at once when nothing was drawn before it', () => {
    const fake = stateMap();
    const onShown = vi.fn();
    step(fake, 'first', { notBefore: NOW + 5000, onShown });
    // Nothing to hold it over: it is drawn as any other, and said to be there once the map is at rest.
    expect(fake.opacity('m-tiles-lyr-0')).toBe(1);
    fake.arrive();
    fake.fire('idle');
    expect(onShown).toHaveBeenCalledTimes(1);
  });

  it('is shown after all, when it has not arrived by the time the map gives up on the picture before it', () => {
    const fake = stateMap();
    showFirst(fake);
    const onShown = vi.fn();
    step(fake, 'second', { notBefore: NOW, onShown });
    vi.advanceTimersByTime(10_000);
    expect(fake.ids()).toEqual(['n-tiles-lyr-0']);
    expect(fake.opacity('n-tiles-lyr-0')).toBe(1);
    expect(onShown).toHaveBeenCalledTimes(1);
  });

  it('waits another round after a step was dropped, not the rest of the time of the one before', () => {
    const fake = stateMap();
    showFirst(fake);
    step(fake, 'second', { notBefore: NOW, onShown: vi.fn() });
    vi.advanceTimersByTime(8000);
    const third = vi.fn();
    step(fake, 'third', { notBefore: NOW, onShown: third });
    vi.advanceTimersByTime(8000);
    expect(third).not.toHaveBeenCalled();
    expect(fake.opacity('m-tiles-lyr-0')).toBe(1);
    vi.advanceTimersByTime(2001);
    expect(third).toHaveBeenCalledTimes(1);
  });

  it('is said to be there at once when it draws nothing at all', () => {
    const fake = stateMap();
    showFirst(fake);
    const onShown = vi.fn();
    L.syncBrowseMosaic(fake.map as never, { items: [], dataset, hold: { notBefore: NOW, onShown } });
    expect(fake.ids()).toEqual([]);
    expect(onShown).toHaveBeenCalledTimes(1);
  });
});

describe('a step that is not played', () => {
  it('is laid as it always was: in sight, and the picture before it goes when it has loaded', () => {
    const fake = stateMap();
    showFirst(fake);
    step(fake, 'second', undefined);
    expect(fake.opacity('n-tiles-lyr-0')).toBe(1);
    expect(fake.layers.get('n-tiles-lyr-0')?.paint['raster-opacity-transition']).toBeUndefined();
    expect(fake.ids()).toEqual(['m-tiles-lyr-0', 'n-tiles-lyr-0']);
    fake.arrive();
    fake.fire('idle');
    expect(fake.ids()).toEqual(['n-tiles-lyr-0']);
  });

  it('shows a step that was on its way, as it is, when it takes over: the playing has stopped', () => {
    const fake = stateMap();
    showFirst(fake);
    step(fake, 'second', { notBefore: NOW, onShown: vi.fn() });
    step(fake, 'third', undefined);
    // The second is in sight (and the first gone), and the third is drawn over it as any step is.
    expect(fake.opacity('n-tiles-lyr-0')).toBe(1);
    expect(fake.opacity('m-tiles-lyr-0')).toBe(1);
    expect(fake.ids()).toEqual(['m-tiles-lyr-0', 'n-tiles-lyr-0']);
  });
});
