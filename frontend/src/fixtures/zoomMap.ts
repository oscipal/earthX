import { watchSubstituteHold } from '../mapLayers';
import { tileLevelAhead } from '../tileSize';
import { liveMap } from './liveMap';

// `raster-opacity` at a map zoom: a number, or a zoom step (`['step', ['zoom'], below, from, above]`).
function opacityAt(opacity: unknown, zoom: number): number {
  if (typeof opacity === 'number') return opacity;
  const [, , below, from, above] = opacity as [string, unknown, number, number, number];
  return zoom < from ? below : above;
}

// A `liveMap` that also says what MapLibre would draw at a map zoom, and holds back "the map is idle" until the test
// lets it: tiles that load late are tiles the test has not yet called idle for. Until then the substitute of a dataset is drawn
// over its own first level too (`mapLayers.ts::substituteHold`).
//
// A raster source is asked for level L from map zoom L - 1.5 (256-px tiles) or L - 0.5 (512-px ones,
// `tileSize.ts::tileLevelAhead`) and never below; a layer's `maxzoom` hides it from there; an image is drawn at the
// opacity its expression gives at that zoom.
export function zoomMap(initial?: string[]) {
  const live = liveMap(initial);
  const waiting: (() => void)[] = [];
  Object.assign(live.map, {
    once: (event: string, listener: () => void) => {
      if (event === 'idle') waiting.push(listener);
    },
  });
  // The events a map fires that the page listens to (`watchSubstituteHold`); every source has all its tiles.
  const handlers = new Map<string, ((event: { sourceId?: string }) => void)[]>();
  Object.assign(live.map, {
    on: (name: string, handler: (event: { sourceId?: string }) => void) => handlers.set(name, [...(handlers.get(name) ?? []), handler]),
    isSourceLoaded: () => true,
  });
  watchSubstituteHold(live.map as never);
  const idle = () => {
    waiting.splice(0).forEach((listener) => listener());
    handlers.get('idle')?.forEach((handler) => handler({}));
  };
  const drawsAt = (id: string, zoom: number): boolean => {
    const layer = live.layers.get(id);
    if (!layer?.source || !live.visible(id)) return false;
    const source = live.sources.get(layer.source) as { type: string; minzoom?: number; tileSize?: number } | undefined;
    if (!source) return false;
    if (layer.maxzoom !== undefined && zoom >= layer.maxzoom) return false;
    // MapLibre's own tile size for a raster source that names none is 512.
    if (source.type === 'raster' && zoom < (source.minzoom ?? 0) - tileLevelAhead(source.tileSize ?? 512)) return false;
    return opacityAt(layer.paint['raster-opacity'], zoom) > 0;
  };
  // The map layers that show something at this zoom, bottom to top.
  const picturesAt = (zoom: number): string[] => live.stack.filter((id) => drawsAt(id, zoom));
  // Every half level from 0 to 20, zooming in and then out again.
  const sweep = (): number[] => {
    const up = Array.from({ length: 41 }, (_, i) => i / 2);
    return [...up, ...[...up].reverse()];
  };
  // The attribution of the sources MapLibre puts into the attribution line at this zoom: those of a source one of whose layers is not
  // hidden there (`Style.update`: `layer.isHidden(zoom)` is the layer's `maxzoom`, `minzoom` and `visibility`; the control reads
  // `source.attribution` of every source `used` that way, maplibre-gl 6.16).
  const attributionAt = (zoom: number): string[] => {
    const shown = new Set<string>();
    for (const [id, layer] of live.layers) {
      if (!layer.source || !live.visible(id) || (layer.maxzoom !== undefined && zoom >= layer.maxzoom)) continue;
      const attribution = (live.sources.get(layer.source) as { attribution?: string } | undefined)?.attribution;
      if (attribution) shown.add(attribution);
    }
    return [...shown];
  };
  return { ...live, idle, picturesAt, attributionAt, sweep };
}
