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
