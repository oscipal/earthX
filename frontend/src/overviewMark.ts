// Whether the map shows an overview instead of the originals (Otto, 16.11.2026, UI-08; replaces the correction to `adr/0032` F12 of
// 11.11.2026): below the first level of a dataset the map draws the pyramid of the dataset (GLO-30, WorldCover), the picture that stands
// in for it (swissALTI3D, BEV: GLO-30) or a picture computed from either (a preview, an index). All of them come from the overview route
// of the tiler (`api.ts::buildOverviewTileTemplate`, the footprint selection of the hits). The map says it with the one mark "Overview"
// over the map, as for a job's result drawn coarser than its pixels (`PreviewBadge.tsx`): same mark, same place, same tooltip.
//
// The map is asked, not the store: a source of the overview route with a layer that is switched on, not fully transparent and drawn at the
// zoom of the map. The basemap and every other source never match the route.

import type { Map as MapLibreMap } from 'maplibre-gl';
import { useAppStore } from './store';

// The tiles of the overview of a dataset, with or without the id of a footprint selection.
const OVERVIEW_TILES = /\/collections\/[^/?]+\/overview\/(?:[0-9a-f]{32}\/)?tiles\//u;

export function isOverviewTileUrl(url: string): boolean {
  return OVERVIEW_TILES.test(url);
}

type MarkMap = Pick<MapLibreMap, 'getLayersOrder' | 'getLayer' | 'getLayoutProperty' | 'getPaintProperty' | 'getZoom' | 'getSource'> & {
  on: (type: string, listener: () => void) => unknown;
};

// The tile URLs of a source of the map. Only a tiled source (`raster`, `vector`) holds them in `tiles`; an image source (a quicklook,
// `type: 'image'`) keeps its loaded tiles there, keyed by tile id, and has no URL of the overview route (UI-10).
function tileUrlsOf(source: unknown): readonly string[] {
  const tiles = (source as { tiles?: unknown } | null | undefined)?.tiles;
  return Array.isArray(tiles) ? tiles.filter((url): url is string => typeof url === 'string') : [];
}

// Whether a layer of the map that is shown at its zoom draws tiles of the overview route.
export function showsOverview(map: MarkMap): boolean {
  const zoom = map.getZoom();
  for (const id of map.getLayersOrder()) {
    const layer = map.getLayer(id);
    if (!layer || layer.type !== 'raster' || map.getLayoutProperty(id, 'visibility') === 'none') continue;
    if (zoom < layer.minzoom || zoom >= layer.maxzoom) continue;
    if (map.getPaintProperty(id, 'raster-opacity') === 0) continue;
    if (tileUrlsOf(map.getSource(layer.source)).some(isOverviewTileUrl)) return true;
  }
  return false;
}

// Tells `onChange` whenever the answer changes: after a change of the style (layers added, removed, switched), of a source and of the
// zoom.
export function watchOverviewMark(map: MarkMap, onChange: (shown: boolean) => void): void {
  let told: boolean | null = null;
  const tell = () => {
    const shown = showsOverview(map);
    if (shown === told) return;
    told = shown;
    onChange(shown);
  };
  for (const type of ['styledata', 'sourcedata', 'zoomend', 'moveend', 'idle']) map.on(type, tell);
}

export function setMapOverview(shown: boolean): void {
  if (useAppStore.getState().mapOverview !== shown) useAppStore.setState({ mapOverview: shown });
}
