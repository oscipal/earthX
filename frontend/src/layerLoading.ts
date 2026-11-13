// Which map layers are loading (plan M5-30 §8.7, Otto, 13.11.2026): a layer whose tiles are on their way, or whose mosaic the page is still
// waiting for, shows a mark in its row of the layer manager once that has lasted a moment (`components/LoadingMark.tsx`), and one mark on the
// map itself whenever any of them is loading (`components/MapLoadingMark.tsx`). The map says which of its raster sources have tiles in
// flight; `ownerOfSource` says which row each belongs to.

import type { Map as MapLibreMap } from 'maplibre-gl';
import { ownerOfSource, RESULTS_OWNER } from './mapLayers';
import { passesOf, viewOfPass } from './mosaic';
import { shownViewOf, useAppStore, type AppState } from './store';

// The sources a viewer can see now: those with a layer that is switched on and drawn at the zoom of the map. MapLibre loads no tile for
// another source, but one whose layer was hidden or left the zoom range while its tiles were on their way is not loading for anyone.
function visibleSources(map: MapLibreMap): ReadonlySet<string> {
  const zoom = map.getZoom();
  const sources = new Set<string>();
  for (const id of map.getLayersOrder()) {
    const layer = map.getLayer(id);
    if (!layer || map.getLayoutProperty(id, 'visibility') === 'none') continue;
    if (zoom < layer.minzoom || zoom >= layer.maxzoom) continue;
    sources.add(layer.source);
  }
  return sources;
}

// The rows whose tiles are in flight, from the first tile a source asks for to the moment it has all of them (a tile that failed counts
// as done: MapLibre's `isSourceLoaded`), at the first load and after every move or zoom of the map, which ask for new tiles. The map's rest
// (`idle`) ends all of it, which is also what ends a source whose last tile failed: that tile fires no `sourcedata`. The basemap and every
// other source that belongs to no row is not looked at, nor is a source whose layers are hidden or out of their zoom range.
export function watchLayerLoading(map: MapLibreMap, onChange: (owners: readonly string[]) => void): void {
  const loading = new Set<string>();
  let told = '';
  const tell = () => {
    const seen = loading.size > 0 ? visibleSources(map) : null;
    const owners = [...new Set([...loading].filter((id) => seen?.has(id)).map((id) => ownerOfSource(id)).filter((owner): owner is string => owner !== null))].sort();
    const text = owners.join('\n');
    if (text === told) return;
    told = text;
    onChange(owners);
  };
  const settle = () => {
    for (const id of loading) if (!map.getSource(id) || map.isSourceLoaded(id)) loading.delete(id);
    tell();
  };
  map.on('sourcedataloading', (event) => {
    if (event.sourceId && ownerOfSource(event.sourceId) !== null) {
      loading.add(event.sourceId);
      tell();
    }
  });
  map.on('sourcedata', settle);
  map.on('sourcedataabort', settle);
  map.on('error', settle);
  map.on('styledata', settle);
  map.on('zoomend', settle);
  map.on('moveend', settle);
  map.on('idle', () => {
    loading.clear();
    tell();
  });
}

// Whether the view waits for a mosaic it has not been given yet: the selection of its scenes is being made at the tiler, and the map draws
// no tile of that pass until it is (`mosaic.ts`, `pending`). A mosaic the tiler refused is not waited for; the scenes are drawn one by one.
export function viewWaitsForMosaic(s: Pick<AppState, 'focusMode' | 'showDownloaded' | 'downloaded' | 'sections' | 'openSectionId' | 'datasetId' | 'items' | 'groups' | 'datasets' | 'shownImage' | 'mosaics'>): boolean {
  if (!s.focusMode || !s.showDownloaded) return false;
  const view = shownViewOf(s);
  return passesOf(Object.entries(view.downloaded), view.groups).some((pass) => viewOfPass(view.dataset?.id ?? null, pass, s.mosaics).kind === 'pending');
}

// Whether the row `owner` of the layer manager is loading now, before any delay (`useLayerLoading`).
export const isOwnerLoading = (s: AppState, owner: string): boolean =>
  s.mapLoading.includes(owner) || (owner === RESULTS_OWNER && viewWaitsForMosaic(s));

// Whether anything the map draws is loading now, before any delay: a row of the layer manager, or the view waiting for its mosaic. The mark
// on the map (`components/MapLoadingMark.tsx`) shows it whether the layer manager is open or not, and whatever rows it has.
export const isMapLoading = (s: AppState): boolean => s.mapLoading.length > 0 || viewWaitsForMosaic(s);

export function setMapLoading(owners: readonly string[]): void {
  useAppStore.setState({ mapLoading: [...owners] });
}
