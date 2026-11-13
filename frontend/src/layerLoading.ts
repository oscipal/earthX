// Which map layers are loading (plan M5-30 §8.7, Otto, 13.11.2026): a layer whose tiles are on their way, or whose mosaic the page is still
// waiting for, shows a mark in its row of the layer manager once that has lasted a moment (`components/LoadingMark.tsx`). The map says
// which of its raster sources have tiles in flight; `ownerOfSource` says which row each belongs to.

import type { Map as MapLibreMap } from 'maplibre-gl';
import { ownerOfSource, RESULTS_OWNER } from './mapLayers';
import { passesOf, viewOfPass } from './mosaic';
import { shownViewOf, useAppStore, type AppState } from './store';

// The rows whose tiles are in flight, from the first tile a source asks for to the moment it has all of them (a tile that failed counts
// as done: MapLibre's `isSourceLoaded`). The map's rest (`idle`) ends all of it, which is also what ends a source whose last tile failed:
// that tile fires no `sourcedata`. The basemap and every other source that belongs to no row is not looked at.
export function watchLayerLoading(map: MapLibreMap, onChange: (owners: readonly string[]) => void): void {
  const loading = new Set<string>();
  let told = '';
  const tell = () => {
    const owners = [...new Set([...loading].map((id) => ownerOfSource(id)).filter((owner): owner is string => owner !== null))].sort();
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
  map.on('error', settle);
  map.on('styledata', settle);
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

export function setMapLoading(owners: readonly string[]): void {
  useAppStore.setState({ mapLoading: [...owners] });
}
