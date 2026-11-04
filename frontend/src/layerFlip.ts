// "Flip through layers" (NM4-65 part 9, Otto, 31.10.2026): while it is on, the layer that was clicked or stepped to is drawn on
// the map over all the others, without moving in the list; ↑/↓ or the mouse wheel over the list step to the next one. The
// eye is respected: a layer that is switched off, and one whose results are gone, draws nothing, so the flipping passes them by
// (to see one, switch it on). At the ends of the list it stops.

import type { MapLayer } from './layers';

// Whether the map would draw the layer at all.
export const flippable = (layer: MapLayer): boolean => layer.visible && !layer.result?.expired && !layer.result?.deleted;

// The layer to start with: `preferred` where it can be drawn, else the first one that can.
export function flipStart(layers: readonly MapLayer[], preferred: string | null): string | null {
  const wanted = layers.find((layer) => layer.id === preferred && flippable(layer));
  return (wanted ?? layers.find(flippable))?.id ?? null;
}

// The layer `dir` steps from `current` (1 down the list, -1 up), the drawable ones only; `current` itself at an end of the list
// and where there is no other. From a layer that is not in the list (or cannot be drawn) the first step goes to the nearest
// drawable layer in that direction from where it stood, else the first or the last.
export function flipNext(layers: readonly MapLayer[], current: string | null, dir: 1 | -1): string | null {
  const drawable = layers.filter(flippable);
  if (drawable.length === 0) return null;
  const at = layers.findIndex((layer) => layer.id === current);
  if (at < 0) return (dir === 1 ? drawable[0] : drawable[drawable.length - 1]).id;
  for (let i = at + dir; i >= 0 && i < layers.length; i += dir) if (flippable(layers[i])) return layers[i].id;
  return flippable(layers[at]) ? layers[at].id : (dir === 1 ? drawable[drawable.length - 1] : drawable[0]).id;
}

// What the map is told: the flipped layer while flipping is on and the layer is still in the list.
export function flipIdOf(s: { flipThrough: boolean; flipLayerId: string | null; layers: readonly MapLayer[] }): string | null {
  return s.flipThrough && s.flipLayerId !== null && s.layers.some((layer) => layer.id === s.flipLayerId) ? s.flipLayerId : null;
}
