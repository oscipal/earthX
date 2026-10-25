import { TILE_LEVEL_AHEAD } from '../mosaic';
import { liveMap } from './liveMap';

// `raster-opacity` at a map zoom: a number, or a zoom step (`['step', ['zoom'], below, from, above]`).
function opacityAt(opacity: unknown, zoom: number): number {
  if (typeof opacity === 'number') return opacity;
  const [, , below, from, above] = opacity as [string, unknown, number, number, number];
  return zoom < from ? below : above;
}

// A `liveMap` that also says what MapLibre would draw at a map zoom, and holds back "the map is idle" until the test
// lets it: tiles that load late are tiles the test has not yet called idle for.
//
// A raster source is asked for level L from map zoom L - 1.5 (`mosaic.ts::TILE_LEVEL_AHEAD`) and never below; a layer's
// `maxzoom` hides it from there; an image is drawn at the opacity its expression gives at that zoom.
export function zoomMap(initial?: string[]) {
  const live = liveMap(initial);
  const waiting: (() => void)[] = [];
  Object.assign(live.map, {
    once: (event: string, listener: () => void) => {
      if (event === 'idle') waiting.push(listener);
    },
  });
  const idle = () => waiting.splice(0).forEach((listener) => listener());
  const drawsAt = (id: string, zoom: number): boolean => {
    const layer = live.layers.get(id);
    if (!layer?.source || !live.visible(id)) return false;
    const source = live.sources.get(layer.source) as { type: string; minzoom?: number } | undefined;
    if (!source) return false;
    if (layer.maxzoom !== undefined && zoom >= layer.maxzoom) return false;
    if (source.type === 'raster' && zoom < (source.minzoom ?? 0) - TILE_LEVEL_AHEAD) return false;
    return opacityAt(layer.paint['raster-opacity'], zoom) > 0;
  };
  // The map layers that show something at this zoom, bottom to top.
  const picturesAt = (zoom: number): string[] => live.stack.filter((id) => drawsAt(id, zoom));
  // Every half level from 0 to 20, zooming in and then out again.
  const sweep = (): number[] => {
    const up = Array.from({ length: 41 }, (_, i) => i / 2);
    return [...up, ...[...up].reverse()];
  };
  return { ...live, idle, picturesAt, sweep };
}
