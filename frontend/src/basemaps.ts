// The basemaps of the "Basemap" menu (UI-02a, `docs/plans/vp3/ui-02-basemap-projektion.md` §6). Pure data and
// the local styles; `mapStyles.ts` puts one under the app's own layers.
//
// The browser loads these tiles from the provider itself, not through the platform (UI-02 §6.7): the tooltip of
// each entry says where from. Satellite stays on Esri World Imagery without a key for now; it has to be replaced or
// licensed before commercial use (Otto, 27.10.2026, M6).

import type { StyleSpecification } from 'maplibre-gl';

export type BasemapId = 'satellite' | 'streets' | 'grey' | 'outlines';

export const BASEMAP_IDS: readonly BasemapId[] = ['satellite', 'streets', 'grey', 'outlines'];
export const DEFAULT_BASEMAP: BasemapId = 'satellite';

// Every source and layer of a basemap carries this prefix in the running style, so that a basemap can be taken
// away again without touching the app's own layers (`mapStyles.ts::composeStyle`).
export const BASEMAP_PREFIX = 'bm-';

const ESRI_IMAGERY =
  'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}';
export const ESRI_ATTRIBUTION = 'Imagery © Esri, Maxar, Earthstar Geographics, and the GIS User Community';

// `latest` always points to the TileJSON in use (OpenFreeMap README, "Tile versions").
const OPENFREEMAP_TILES = 'https://tiles.openfreemap.org/planet/latest';
const OPENFREEMAP_STYLES = 'https://tiles.openfreemap.org/styles';
// The wording the OpenFreeMap README asks for.
export const OPENFREEMAP_ATTRIBUTION =
  '<a href="https://openfreemap.org" target="_blank" rel="noopener noreferrer">OpenFreeMap</a> ' +
  '<a href="https://www.openmaptiles.org/" target="_blank" rel="noopener noreferrer">© OpenMapTiles</a> ' +
  'Data from <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>';

export interface Basemap {
  id: BasemapId;
  name: string;
  // Where the tiles come from; shown as the tooltip of the entry.
  tip: string;
  // A style the app builds itself, or the address of a published one (fetched when chosen).
  style: StyleSpecification | string;
}

// A style of its own: nothing but the layers and sources the basemap draws (the prefix is added by `composeStyle`).
function localStyle(name: string, sources: StyleSpecification['sources'], layers: StyleSpecification['layers']): StyleSpecification {
  return { version: 8, name, sources, layers };
}

function satelliteStyle(): StyleSpecification {
  return localStyle(
    'satellite',
    {
      satellite: { type: 'raster', tiles: [ESRI_IMAGERY], tileSize: 256, maxzoom: 19, attribution: ESRI_ATTRIBUTION },
    },
    [{ id: 'satellite', type: 'raster', source: 'satellite' }],
  );
}

// Coasts and borders only: the sea as a faint area (its edge is the coast: an outline drawn along the polygons
// of the tiles would show the seams between tiles), country borders, and regional borders from zoom 4. Colours that
// read on both the dark and the white backdrop.
function outlinesStyle(): StyleSpecification {
  const source = 'openmaptiles';
  return localStyle(
    'outlines',
    { [source]: { type: 'vector', url: OPENFREEMAP_TILES, attribution: OPENFREEMAP_ATTRIBUTION } },
    [
      { id: 'water', type: 'fill', source, 'source-layer': 'water', paint: { 'fill-color': 'rgba(90, 150, 210, 0.3)' } },
      {
        id: 'boundary-region',
        type: 'line',
        source,
        'source-layer': 'boundary',
        minzoom: 4,
        filter: ['all', ['>=', ['get', 'admin_level'], 3], ['<=', ['get', 'admin_level'], 4], ['!=', ['get', 'maritime'], 1]],
        paint: { 'line-color': '#7f93a6', 'line-width': 0.8, 'line-dasharray': [3, 2] },
      },
      {
        id: 'boundary-country',
        type: 'line',
        source,
        'source-layer': 'boundary',
        filter: ['all', ['==', ['get', 'admin_level'], 2], ['!=', ['get', 'maritime'], 1]],
        paint: { 'line-color': '#9db0c2', 'line-width': ['interpolate', ['linear'], ['zoom'], 0, 0.6, 8, 1.4] },
      },
    ],
  );
}

export const BASEMAPS: Record<BasemapId, Basemap> = {
  satellite: {
    id: 'satellite',
    name: 'Satellite',
    tip: 'Esri World Imagery. Tiles load from arcgisonline.com.',
    style: satelliteStyle(),
  },
  streets: {
    id: 'streets',
    name: 'Streets',
    tip: 'OpenStreetMap data, OSM Liberty style (CC BY 4.0). Tiles load from openfreemap.org.',
    style: `${OPENFREEMAP_STYLES}/liberty`,
  },
  grey: {
    id: 'grey',
    name: 'Grey',
    tip: 'OpenStreetMap data, Positron style (CC BY 4.0). Tiles load from openfreemap.org.',
    style: `${OPENFREEMAP_STYLES}/positron`,
  },
  outlines: {
    id: 'outlines',
    name: 'Outlines',
    tip: 'Coasts and borders only, from OpenStreetMap data. Tiles load from openfreemap.org.',
    style: outlinesStyle(),
  },
};
