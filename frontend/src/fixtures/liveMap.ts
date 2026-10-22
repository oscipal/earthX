import type { MapLayer } from '../layers';

// A map that keeps what MapLibre keeps: sources, layers in stacking order (a layer
// added or moved `before` another goes right under it), and what is set on them —
// plus a log of the calls that make MapLibre fetch tiles again (a source added).
export function liveMap(initial: string[] = ['layers-top', 'aoi-fill', 'aoi-line']) {
  const stack = [...initial];
  const sources = new Map<string, Record<string, unknown>>();
  const layers = new Map<
    string,
    { id: string; source?: string; maxzoom?: number; paint: Record<string, unknown>; layout: Record<string, unknown> }
  >();
  const log = { sourcesAdded: [] as string[], sourcesRemoved: [] as string[], moved: [] as string[] };
  const place = (id: string, before?: string) => {
    stack.splice(before ? stack.indexOf(before) : stack.length, 0, id);
  };
  const map = {
    getLayer: (id: string) => (stack.includes(id) ? (layers.get(id) ?? { id }) : undefined),
    getSource: (id: string) => sources.get(id),
    addSource: (id: string, spec: Record<string, unknown>) => {
      sources.set(id, spec);
      log.sourcesAdded.push(id);
    },
    removeSource: (id: string) => {
      sources.delete(id);
      log.sourcesRemoved.push(id);
    },
    addLayer: (
      layer: { id: string; source?: string; maxzoom?: number; paint?: Record<string, unknown>; layout?: Record<string, unknown> },
      before?: string,
    ) => {
      layers.set(layer.id, { id: layer.id, source: layer.source, maxzoom: layer.maxzoom, paint: { ...layer.paint }, layout: { ...layer.layout } });
      place(layer.id, before);
    },
    removeLayer: (id: string) => {
      stack.splice(stack.indexOf(id), 1);
      layers.delete(id);
    },
    moveLayer: (id: string, before?: string) => {
      stack.splice(stack.indexOf(id), 1);
      place(id, before);
      log.moved.push(id);
    },
    setLayoutProperty: (id: string, name: string, value: unknown) => {
      layers.get(id)!.layout[name] = value;
    },
    setPaintProperty: (id: string, name: string, value: unknown) => {
      layers.get(id)!.paint[name] = value;
    },
  };
  const visible = (id: string) => layers.get(id)?.layout.visibility !== 'none';
  // The pinned layers on the map, bottom to top, by the layer they belong to.
  const pinnedOrder = () => stack.filter((id) => id.startsWith('layer-lyr-'));
  return { map, stack, sources, layers, log, visible, pinnedOrder };
}

export function pinned(id: string, url: string, over: Partial<MapLayer> = {}): MapLayer {
  return {
    id,
    name: 'Same name',
    visible: true,
    opacity: 0.8,
    overlays: [{ kind: 'raster', tileUrl: url, bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
    restore: { datasetId: 'optical' } as never,
    ...over,
  };
}

export const lyr = (id: string, n = 0) => `layer-lyr-${id}-${n}`;

