// The entry "Results" of the layer manager (NM4-59, Otto, 30.10.2026): the search results, the view and the live preview
// as one entry among the pinned layers. Its place is `resultsAt`, the number of pinned layers above it (0: on top). The
// list of layers stays as it is; these functions keep the place right when the list changes.

import type { MapLayer } from './layers';

// New layers always come onto the top of the list, over "Results" too (Otto, 30.10.2026, zu #249): "Results" keeps the
// layers that were above it, and the new ones go above them.
export const resultsAtAfterAdding = (resultsAt: number, added: number): number => resultsAt + added;

// Layers left the list: "Results" moves up by those of them that were above it.
export const resultsAtAfterRemoving = (before: readonly MapLayer[], resultsAt: number, kept: (layer: MapLayer) => boolean): number =>
  resultsAt - before.slice(0, resultsAt).filter((layer) => !kept(layer)).length;

// A place inside the list: from 0 (on top) to below the last layer.
export const clampResultsAt = (resultsAt: number, layers: readonly MapLayer[]): number => Math.max(0, Math.min(resultsAt, layers.length));

// One step up or down for a row, a layer by its id or "Results" (`null`): a layer next to "Results" changes places with it.
// `null` where the row is at the end of the list, or not in it. Without search results the list has no row "Results"
// (`listed` false), and a layer only changes places with the layer next to it.
export function moveEntry(
  layers: readonly MapLayer[],
  resultsAt: number,
  id: string | null,
  dir: 'up' | 'down',
  listed = true,
): { layers: MapLayer[]; resultsAt: number } | null {
  const at = clampResultsAt(resultsAt, layers);
  if (id === null) {
    if (!listed) return null;
    const next = dir === 'up' ? at - 1 : at + 1;
    return next < 0 || next > layers.length ? null : { layers: [...layers], resultsAt: next };
  }
  const i = layers.findIndex((layer) => layer.id === id);
  if (i < 0) return null;
  if (listed && dir === 'up' && i === at) return { layers: [...layers], resultsAt: at + 1 };
  if (listed && dir === 'down' && i === at - 1) return { layers: [...layers], resultsAt: at - 1 };
  const j = dir === 'up' ? i - 1 : i + 1;
  if (j < 0 || j >= layers.length) return null;
  const moved = [...layers];
  [moved[i], moved[j]] = [moved[j], moved[i]];
  return { layers: moved, resultsAt: at };
}
