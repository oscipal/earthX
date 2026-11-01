// The full-resolution view of a pinned layer (M4-28, Otto 20.10.2026). A click on
// a layer's name puts its scenes into the view (`store.ts::selectLayer`). As long
// as the view still shows exactly what that layer pinned, the layer is the picture:
// it stays at its place in the list and follows its eye. Once anything differs —
// other scenes, a new stretch, another AOI under "Crop to AOI" — the view is its own
// picture again, drawn above the layers.

import type { MapLayer } from './layers';
import type { AppliedRender, DownloadedInfo } from './types';

export interface ViewState {
  viewLayerId: string | null;
  focusMode: boolean;
  downloaded: Record<string, DownloadedInfo>;
  appliedRender: AppliedRender;
  cropToAoi: boolean;
  aoi: GeoJSON.Geometry | null;
  showDownloaded: boolean;
}

export function sameRender(a: AppliedRender, b: AppliedRender): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]) as Set<keyof AppliedRender>;
  return [...keys].every((k) => (a[k] || '') === (b[k] || ''));
}

// The pinned layer the view was opened from and still shows the scenes of — whatever look it has now (NM4-50): the settings
// of the view are the settings of this layer, "Save" keeps the look for it. `null` for a view that is no layer's.
export function layerOfView(layers: readonly MapLayer[], s: Omit<ViewState, 'appliedRender' | 'showDownloaded'>): MapLayer | null {
  if (!s.focusMode || s.viewLayerId === null) return null;
  const layer = layers.find((l) => l.id === s.viewLayerId);
  if (!layer?.restore.focusMode) return null;
  const r = layer.restore;
  const ids = Object.keys(s.downloaded);
  if (ids.length !== Object.keys(r.downloaded).length || !ids.every((id) => id in r.downloaded)) return null;
  if (s.cropToAoi !== r.cropToAoi) return null;
  if (s.cropToAoi && JSON.stringify(s.aoi) !== JSON.stringify(r.aoi)) return null;
  return layer;
}

// The pinned layer whose picture the view is, or `null`.
export function viewLayerOf(layers: readonly MapLayer[], s: ViewState): MapLayer | null {
  const layer = layerOfView(layers, s);
  return layer && sameRender(s.appliedRender, layer.restore.appliedRender) ? layer : null;
}

// The list the layer manager draws: the layer that is the view also goes with the
// view's own "Hide image" switch.
export function layersForMap(layers: MapLayer[], viewLayer: MapLayer | null, showDownloaded: boolean): MapLayer[] {
  if (!viewLayer || showDownloaded) return layers;
  return layers.map((l) => (l === viewLayer ? { ...l, visible: false } : l));
}

// Whether the view's own tiles are drawn: not when a layer draws them, and not when
// the layer it is has been switched off.
export function viewShown(viewLayer: MapLayer | null, showDownloaded: boolean): boolean {
  return showDownloaded && (viewLayer === null || viewLayer.visible);
}

// Whether the image the view shows is only temporary (Otto, 1.11.2026): no layer holds it as it looks now. A layer holds an image
// when it was made of exactly its scenes, cut the same way, and has the look the image has (what the fields ask for included): "Add to
// layers" takes the mark off the image it pinned, and a change of the look, of the scenes or of the crop puts it back; "Add all to
// layers" takes it off every image it pinned, so that a step that was not changed shows none.
export function isTemporaryImage(
  layers: readonly MapLayer[],
  image: { ids: readonly string[]; datasetId: string },
  look: AppliedRender,
  view: { cropToAoi: boolean; aoi: GeoJSON.Geometry | null },
): boolean {
  return !layers.some((layer) => {
    const r = layer.restore;
    if (layer.derived || !r.focusMode || r.datasetId !== image.datasetId || r.cropToAoi !== view.cropToAoi) return false;
    if (view.cropToAoi && JSON.stringify(r.aoi) !== JSON.stringify(view.aoi)) return false;
    if (r.itemIds.length !== image.ids.length || !image.ids.every((id) => r.itemIds.includes(id))) return false;
    return sameRender(r.appliedRender, look);
  });
}
