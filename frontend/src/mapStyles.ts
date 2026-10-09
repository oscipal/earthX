// Single hand-authored MapLibre style: satellite/aerial imagery basemap.
// Esri "World Imagery" XYZ tiles (no API key required). The dark HUD panels
// are drawn as HTML overlays on top of this imagery.

import type { StyleSpecification } from 'maplibre-gl';

const ESRI_IMAGERY =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';

// The colour behind the globe and behind the imagery comes from the theme token
// `--map-bg` (`index.css`): dark in the tech theme, white in the light one. A
// style paints with plain values and cannot read a CSS variable, so the token is
// read off the app element and put into the style — at creation and on every
// theme switch (`applyMapBackground`).
export const MAP_BACKGROUND_TOKEN = '--map-bg';

export function mapBackgroundOf(element: Element | null): string | undefined {
  if (!element) return undefined;
  const value = getComputedStyle(element).getPropertyValue(MAP_BACKGROUND_TOKEN).trim();
  return value || undefined;
}

// What MapLibre paints behind the globe (V-1's projection switch, D27):
// `sky`'s defaults (`sky-color` a light blue, `horizon-color`/`fog-color`
// white) leave the map behind the sphere looking white. Set to the token colour
// instead. `drawSky` (the full-screen gradient quad, unconditional whenever
// `style.sky` is set) isn't gated on `atmosphere-blend` — that value only skips
// the separate glow/halo pass (`drawAtmosphere`), which stays off here (0) so the
// globe doesn't pick up a colored rim. The WebGL canvas clears to transparent
// every frame before the sky is drawn, so anything the sky quad does not cover
// falls through to the page: `.app`'s own background (the same token) is the
// actual guarantee, this is the belt to that braces.
function skyOf(background: string) {
  return {
    'sky-color': background,
    'horizon-color': background,
    'fog-color': background,
    'atmosphere-blend': 0,
  };
}

// `background` is the resolved token colour; without one (no DOM to read it from)
// the style gets no explicit colour of its own beyond MapLibre's defaults.
export function baseMapStyle(background?: string): StyleSpecification {
  const style: StyleSpecification = {
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
      { id: 'background', type: 'background', paint: background ? { 'background-color': background } : {} },
      { id: 'satellite', type: 'raster', source: 'satellite' },
    ],
  };
  if (background) style.sky = skyOf(background);
  return style;
}

// Re-tints a map that is already up (a theme switch): the `background` layer and
// the globe's sky.
export function applyMapBackground(
  map: { getLayer(id: string): unknown; setPaintProperty(layer: string, prop: string, value: unknown): void; setSky(sky: object): void },
  background: string,
): void {
  if (map.getLayer('background')) map.setPaintProperty('background', 'background-color', background);
  map.setSky(skyOf(background));
}
