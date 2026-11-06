// The name of a layer as the layer manager and the settings of the layer show it: with the acquisition date in it (NM4-65,
// Otto, 1.11.2026: "das datum gehört in den layer namen, nicht als untertitel"). A name that has the date already stays as it is.
// The layer itself keeps the name it was given (a layer made from a band is named after the band).

import type { MapLayer } from './layers';

export const layerShownName = (layer: Pick<MapLayer, 'name' | 'date'>): string =>
  layer.date && !layer.name.includes(layer.date) ? `${layer.name} · ${layer.date}` : layer.name;
