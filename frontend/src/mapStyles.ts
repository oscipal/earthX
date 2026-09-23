// Single hand-authored MapLibre style: satellite/aerial imagery basemap.
// Esri "World Imagery" XYZ tiles (no API key required). The dark HUD panels
// are drawn as HTML overlays on top of this imagery.

import type { StyleSpecification } from 'maplibre-gl';

const ESRI_IMAGERY =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

const satelliteStyle: StyleSpecification = {
  version: 8,
  name: 'biomass-satellite',
  sources: {
    satellite: {
      type: 'raster',
      tiles: [ESRI_IMAGERY],
      tileSize: 256,
      maxzoom: 19,
      attribution:
        'Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#04070a' } },
    { id: 'satellite', type: 'raster', source: 'satellite' },
  ],
  // What MapLibre paints behind the globe (V-1's projection switch, D27):
  // `sky`'s defaults (`sky-color` a light blue, `horizon-color`/`fog-color`
  // white) show through the atmosphere blend and leave the map behind the
  // sphere looking white — visible on the flat map too, past the edge of the
  // world. Matched to the `background` layer's near-black instead, with the
  // atmosphere blended out rather than tinting it, so the globe sits on a
  // black field the way the HUD's own dark theme does.
  sky: {
    'sky-color': '#04070a',
    'horizon-color': '#04070a',
    'fog-color': '#04070a',
    'atmosphere-blend': 0,
  },
};

export function baseMapStyle(): StyleSpecification {
  // Return a deep copy so MapLibre never mutates our source-of-truth object.
  return structuredClone(satelliteStyle);
}
