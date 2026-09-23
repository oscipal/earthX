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
  // white) leave the map behind the sphere looking white. Matched to the
  // `background` layer's near-black instead. `drawSky` (the full-screen
  // gradient quad, unconditional whenever `style.sky` is set) isn't gated on
  // `atmosphere-blend` — that value only skips the separate glow/halo pass
  // (`drawAtmosphere`), which stays off here (0) so the globe doesn't pick up
  // a colored rim. In testing this alone still left a white edge in some
  // states (the WebGL canvas clears to fully transparent every frame before
  // the sky is drawn, so anything the sky quad doesn't cover falls through to
  // the page underneath) — `index.css`'s `body { background: #04070a }` is
  // the actual guarantee; this stays as the belt to that braces, since a
  // correctly tinted sky quad is one less transparent frame to fall through.
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
