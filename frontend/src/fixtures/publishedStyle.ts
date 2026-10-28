// A made-up map style in the shape a style server publishes (UI-02a): a vector source named by a TileJSON address,
// its own background, a sprite, glyphs, a camera and a sky of its own. It is not a copy of any provider's style.

import type { StyleSpecification } from 'maplibre-gl';

export function publishedStyle(): StyleSpecification {
  return {
    version: 8,
    name: 'made up',
    center: [8, 47],
    zoom: 5,
    sprite: 'https://styles.example/sprite',
    glyphs: 'https://styles.example/fonts/{fontstack}/{range}.pbf',
    sky: { 'sky-color': '#ff00ff' },
    projection: { type: 'mercator' },
    sources: {
      openmaptiles: { type: 'vector', url: 'https://tiles.example/planet', attribution: 'the TileJSON says this' },
      photos: { type: 'raster', tiles: ['https://tiles.example/photos/{z}/{x}/{y}.png'], attribution: 'a raster source of its own' },
    },
    layers: [
      { id: 'background', type: 'background', paint: { 'background-color': '#f0e9d8' } },
      { id: 'aoi-fill', type: 'fill', source: 'openmaptiles', 'source-layer': 'landcover', paint: { 'fill-color': '#cdebb0' } },
      { id: 'place-label', type: 'symbol', source: 'openmaptiles', 'source-layer': 'place', layout: { 'text-field': '{name}', 'text-font': ['Sans'] } },
      { id: 'photos', type: 'raster', source: 'photos' },
    ],
  };
}

// What the app lays on a map besides its basemap: the area of interest, a picture of a scene, the drawing tool; and
// the globe, which the user chose.
export function appLayers(): Pick<StyleSpecification, 'sources' | 'layers' | 'projection'> {
  const empty: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };
  return {
    sources: {
      'aoi-src': { type: 'geojson', data: empty },
      'm-img-src-0': { type: 'image', url: 'data:image/png;base64,AAAA', coordinates: [[0, 1], [1, 1], [1, 0], [0, 0]] },
      'td-polygon': { type: 'geojson', data: empty },
    },
    layers: [
      { id: 'layers-top', type: 'background', layout: { visibility: 'none' } },
      { id: 'm-img-lyr-0', type: 'raster', source: 'm-img-src-0' },
      { id: 'overlays-base', type: 'background', layout: { visibility: 'none' } },
      { id: 'aoi-fill', type: 'fill', source: 'aoi-src' },
      { id: 'aoi-line', type: 'line', source: 'aoi-src' },
      { id: 'td-polygon', type: 'fill', source: 'td-polygon' },
    ],
    projection: { type: 'globe' },
  };
}
