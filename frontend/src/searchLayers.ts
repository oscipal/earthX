// The overlays a pinned layer draws for a pass of scenes: its mosaic, or one raster per scene, under the quicklooks
// of the same scenes.

import { clipTileUrl } from './aoiClip';
import type { DatasetOption } from './datasets';
import type { LayerOverlay } from './layers';
import type { IndexPreset } from './indexPresets';
import { buildTileUrl } from './mapLayers';
import { inStackOrder, stackLikeView, viewOfPass } from './mosaic';
import type { Mosaics, PlannedRaster, SceneEntry } from './mosaic';
import { underlayOf } from './underlay';
import { indexRastersOfPass } from './viewIndex';
import type { ImageOverlay } from './underlay';
import type { AppliedRender, StacItem } from './types';

const rasterOverlay = (raster: PlannedRaster, render: AppliedRender, clip: GeoJSON.Geometry | null): LayerOverlay => ({
  kind: 'raster',
  tileUrl: clipTileUrl(buildTileUrl(raster.tileUrl, render), clip),
  bounds: raster.bounds,
  minZoom: raster.minZoom,
  maxZoom: raster.maxZoom,
  ...(raster.hideFrom === undefined ? {} : { hideFrom: raster.hideFrom }),
});

// The overlays one pass is pinned or cropped as: its mosaic and the scenes below the mosaic's first
// level, else one raster per scene (`mosaic.ts`). `null` while the pass's mosaic is on its way — a
// pinned layer is a picture and is not made from half of one.
export function overlaysOfPass(
  datasetId: string,
  entries: SceneEntry[],
  mosaics: Mosaics | undefined,
  render: AppliedRender,
  clip: GeoJSON.Geometry | null,
  // The quicklooks under the tiles (`underlaysOf`), which the layer draws where its tiles do not start yet.
  underlays: readonly ImageOverlay[] = [],
  // The index the look names (NM4-14b): the rasters are the tiles that compute it, and no quicklook lies under them.
  index: IndexPreset | null = null,
): LayerOverlay[] | null {
  const view = viewOfPass(datasetId, entries, mosaics);
  if (view.kind === 'pending') return null;
  // Scene by scene the pass lies in the order of the mosaic, as in the crop and the export (NM4-24), not in the order of the ticks.
  const plain = view.kind === 'mosaic' ? view.rasters : stackLikeView(inStackOrder(entries, view.order).map(([, info]) => info));
  const rasters = index ? indexRastersOfPass(plain, entries, datasetId, index).rasters : plain;
  return [...(index ? [] : underlays), ...rasters.map((raster) => rasterOverlay(raster, render, clip))];
}

// The quicklooks of these scenes, bottom to top like the view lays them (`underlay.ts`).
export function underlaysOf(
  entries: SceneEntry[],
  items: readonly StacItem[],
  dataset: DatasetOption | null | undefined,
  clip: GeoJSON.Geometry | null,
): ImageOverlay[] {
  return stackLikeView(entries).flatMap(([id]) => {
    const item = items.find((it) => it.id === id);
    const underlay = item && underlayOf(item, dataset, clip);
    return underlay ? [underlay] : [];
  });
}
