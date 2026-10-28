// The terrain shading (NM4-35, `docs/plans/querschnitt/nm4-35-relief.md` §6): MapLibre draws a `hillshade` layer in the
// browser from elevation tiles it loads itself, from AWS Terrain Tiles (Terrarium PNG, no key). It serves the overlay
// "Relief" over every basemap and the basemap "Relief" alone. The tiles do not pass through the platform, like those of
// the basemaps (UI-02 §6.7).

import type { StyleSpecification } from 'maplibre-gl';

import { OVERLAY_PREFIX } from './overlays';

type Layer = StyleSpecification['layers'][number];
type Source = StyleSpecification['sources'][string];

export const TERRAIN_TILES = 'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png';
// The tiles hold nothing finer than the 30 m models above zoom 12 and show stripes from zoom 15 (§6.4): from 13
// MapLibre stretches the tiles of zoom 12.
export const TERRAIN_MAXZOOM = 12;

// The credit in the corner is short; the link leads to the full list the publishers of the tiles keep, because the
// licences of some sources do not say that a link may stand in for their words (§6.11).
export const TERRAIN_ATTRIBUTION_URL = 'https://github.com/tilezen/joerd/blob/master/docs/attribution.md';
export const TERRAIN_ATTRIBUTION = `<a href="${TERRAIN_ATTRIBUTION_URL}" target="_blank" rel="noopener noreferrer">Terrain: USGS, NOAA, EU-DEM (Copernicus) and others</a>`;

// The overlay's source and layer in the running style.
export const RELIEF_OVERLAY_ID = `${OVERLAY_PREFIX}relief`;

export function reliefSource(): Source {
  return { type: 'raster-dem', tiles: [TERRAIN_TILES], encoding: 'terrarium', tileSize: 256, maxzoom: TERRAIN_MAXZOOM, attribution: TERRAIN_ATTRIBUTION };
}

// Light from the north-west at 45° as maps usually have it, fixed to the map (it cannot turn or tilt here). The
// overlay is light-handed so that the imagery under it stays readable; the basemap is the shading alone, so firmer.
const LOOKS = {
  overlay: { exaggeration: 0.5, shadow: 'rgba(0, 0, 0, 0.45)', highlight: 'rgba(255, 255, 255, 0.25)' },
  basemap: { exaggeration: 0.6, shadow: 'rgba(0, 0, 0, 0.6)', highlight: 'rgba(255, 255, 255, 0.6)' },
} as const;

export function reliefLayer(id: string, source: string, look: keyof typeof LOOKS): Layer {
  const { exaggeration, shadow, highlight } = LOOKS[look];
  return {
    id,
    type: 'hillshade',
    source,
    paint: {
      'hillshade-method': 'standard',
      'hillshade-illumination-direction': 315,
      'hillshade-illumination-altitude': 45,
      'hillshade-illumination-anchor': 'map',
      'hillshade-exaggeration': exaggeration,
      'hillshade-shadow-color': shadow,
      'hillshade-highlight-color': highlight,
      'hillshade-accent-color': 'rgba(0, 0, 0, 0.15)',
    },
  };
}
