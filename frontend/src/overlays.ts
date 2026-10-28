// The overlays of the "Basemap" menu (UI-02b, `docs/plans/vp3/ui-02-basemap-projektion.md` §6.5): names on the map and
// a graticule. They lie over the app's own pictures and under the area of interest and the drawing (Otto, 27.10.2026,
// question 7), on every basemap. `mapStyles.ts::composeStyle` puts them there.

import type { StyleSpecification } from 'maplibre-gl';

export type OverlayId = 'labels' | 'graticule';
export type Overlays = Record<OverlayId, boolean>;

export const OVERLAY_IDS: readonly OverlayId[] = ['labels', 'graticule'];
export const NO_OVERLAYS: Overlays = { labels: false, graticule: false };

// Every source and layer of an overlay carries this prefix in the running style (`bm-` is the basemap's).
export const OVERLAY_PREFIX = 'ov-';

export const OVERLAYS: Record<OverlayId, { name: string; tip: string }> = {
  labels: { name: 'Labels', tip: 'Names of places, waters and roads. Tiles and fonts load from openfreemap.org.' },
  graticule: { name: 'Graticule', tip: 'Lines of latitude and longitude, drawn in the browser.' },
};

export const GRATICULE_SOURCE = `${OVERLAY_PREFIX}graticule`;

type Layer = StyleSpecification['layers'][number];

// The spacing of the lines by zoom: 30° below zoom 3, 10° below 6, 5° below 8 and 1° above. Every line is in the
// coarsest of these grids that holds it, and says so in `step`, so that one source serves all four layers.
const GRATICULE_BANDS: { step: number; minzoom?: number; maxzoom?: number }[] = [
  { step: 30, maxzoom: 3 },
  { step: 10, minzoom: 3, maxzoom: 6 },
  { step: 5, minzoom: 6, maxzoom: 8 },
  { step: 1, minzoom: 8 },
];

// Mercator ends at about 85.05° and a line to the pole would not draw; a vertex every 5° keeps a parallel straight
// on the globe too.
const LIMIT = 85;
const VERTEX_EVERY = 5;

const stepOf = (degrees: number): number => GRATICULE_BANDS.find(({ step }) => degrees % step === 0)?.step ?? 1;

function range(from: number, to: number, by: number): number[] {
  const values: number[] = [];
  for (let value = from; value <= to; value += by) values.push(value);
  return values;
}

let graticule: GeoJSON.FeatureCollection | undefined;

// Meridians every degree from 180° W to 179° E, parallels every degree from 85° S to 85° N.
export function graticuleData(): GeoJSON.FeatureCollection {
  if (graticule) return graticule;
  const features: GeoJSON.Feature[] = [
    ...range(-180, 179, 1).map((lon): GeoJSON.Feature => ({
      type: 'Feature',
      properties: { step: stepOf(Math.abs(lon)) },
      geometry: { type: 'LineString', coordinates: range(-LIMIT, LIMIT, VERTEX_EVERY).map((lat) => [lon, lat]) },
    })),
    ...range(-LIMIT, LIMIT, 1).map((lat): GeoJSON.Feature => ({
      type: 'Feature',
      properties: { step: stepOf(Math.abs(lat)) },
      geometry: { type: 'LineString', coordinates: range(-180, 180, VERTEX_EVERY).map((lon) => [lon, lat]) },
    })),
  ];
  graticule = { type: 'FeatureCollection', features };
  return graticule;
}

export function graticuleLayers(): Layer[] {
  return GRATICULE_BANDS.map(({ step, minzoom, maxzoom }): Layer => ({
    id: `${OVERLAY_PREFIX}graticule-${step}`,
    type: 'line',
    source: GRATICULE_SOURCE,
    ...(minzoom === undefined ? {} : { minzoom }),
    ...(maxzoom === undefined ? {} : { maxzoom }),
    ...(step === 1 ? {} : { filter: ['>=', ['get', 'step'], step] }),
    // Mid grey: it reads on the dark and on the white backdrop and on imagery.
    paint: { 'line-color': 'rgba(150, 165, 180, 0.55)', 'line-width': ['interpolate', ['linear'], ['zoom'], 0, 0.5, 10, 0.9] },
  }));
}
