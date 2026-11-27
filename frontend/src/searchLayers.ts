// The overlays a pinned layer draws for a pass of scenes: its mosaic, or one raster per scene, under the quicklooks
// of the same scenes.

import { clipTileUrl } from './aoiClip';
import type { DatasetOption } from './datasets';
import type { LayerOverlay } from './layers';
import type { QuickPreset } from './quickPresets';
import { buildTileUrl, scalingOfRaster } from './mapLayers';
import { inStackOrder, overviewOverScenes, stackLikeView, viewOfPass } from './mosaic';
import { overviewRasterOf } from './overviewSubstitute';
import type { Mosaics, PlannedRaster, SceneEntry } from './mosaic';
import { underlayOf } from './underlay';
import { indexChainOf, indexRastersOfPass, viewIndexOf } from './viewIndex';
import type { ImageOverlay } from './underlay';
import type { AppliedRender, StacItem } from './types';

const rasterOverlay = (raster: PlannedRaster, render: AppliedRender, clip: GeoJSON.Geometry | null): LayerOverlay => ({
  kind: 'raster',
  tileUrl: clipTileUrl(buildTileUrl(raster.tileUrl, render, scalingOfRaster(raster)), clip),
  bounds: raster.bounds,
  minZoom: raster.minZoom,
  maxZoom: raster.maxZoom,
  ...(raster.hideFrom === undefined ? {} : { hideFrom: raster.hideFrom }),
  ...(raster.attribution === undefined ? {} : { attribution: raster.attribution }),
});

// The pictures below the first level of the datasets these passes belong to (a substitute's, or a dataset's own pyramid), one for
// each dataset, in the look of the layer (`overviewSubstitute.ts`). They lie at the bottom of the layer, under everything it draws of
// its own. An index in the look is computed on the overview there as on the scenes above (M5-10 part B). With the scenes of the layer
// the picture lies over them only, as the view draws it (`overviewOverScenes`, M5-56); the caller waits for their footprint selection
// (`overviewsWaiting`).
export function overviewOverlaysOf(
  datasetIds: readonly string[],
  datasets: readonly DatasetOption[],
  render: AppliedRender,
  clip: GeoJSON.Geometry | null,
  scenes?: { entries: readonly SceneEntry[]; mosaics: Mosaics | undefined },
): LayerOverlay[] {
  return [...new Set(datasetIds)].flatMap((id) => {
    const dataset = datasets.find((d) => d.id === id);
    const index = dataset ? viewIndexOf(render, dataset.collection) : null;
    const below = overviewRasterOf(dataset, datasets, index ? indexChainOf(index) : null);
    if (!below) return [];
    const raster = scenes ? (overviewOverScenes(below, id, scenes.entries, scenes.mosaics, index !== null) ?? below) : below;
    return [rasterOverlay(raster, render, clip)];
  });
}

// Whether the picture below the first level of one of these datasets waits for the footprint selection of the scenes: a layer is
// pinned or saved once it is there, and not over the whole area meanwhile (M5-56).
export function overviewsWaiting(
  datasetIds: readonly string[],
  datasets: readonly DatasetOption[],
  render: AppliedRender,
  scenes: { entries: readonly SceneEntry[]; mosaics: Mosaics | undefined },
): boolean {
  return [...new Set(datasetIds)].some((id) => {
    const dataset = datasets.find((d) => d.id === id);
    const index = dataset ? viewIndexOf(render, dataset.collection) : null;
    const below = overviewRasterOf(dataset, datasets, index ? indexChainOf(index) : null);
    return below !== null && overviewOverScenes(below, id, scenes.entries, scenes.mosaics, index !== null) === undefined;
  });
}

// The overlays one pass is pinned or cropped as: its mosaic, else one raster per scene (`mosaic.ts`). `null` while the pass's
// mosaic, or the selection an index over it is asked from, is on its way — a pinned layer is a picture and is not made from half of one.
export function overlaysOfPass(
  datasetId: string,
  entries: SceneEntry[],
  mosaics: Mosaics | undefined,
  render: AppliedRender,
  clip: GeoJSON.Geometry | null,
  // The quicklooks under the tiles (`underlaysOf`), which the layer draws where its tiles do not start yet.
  underlays: readonly ImageOverlay[] = [],
  // The index the look names (NM4-14b): the rasters are the tiles that compute it, and no quicklook lies under them.
  index: QuickPreset | null = null,
): LayerOverlay[] | null {
  const view = viewOfPass(datasetId, entries, mosaics);
  if (view.kind === 'pending') return null;
  // Scene by scene the pass lies in the order of the mosaic, as in the crop and the export (NM4-24), not in the order of the ticks.
  const plain = view.kind === 'mosaic' ? view.rasters : stackLikeView(inStackOrder(entries, view.order).map(([, info]) => info));
  const planned = index ? indexRastersOfPass(plain, entries, datasetId, index, mosaics) : null;
  if (planned?.waiting) return null;
  return [...(index ? [] : underlays), ...(planned?.rasters ?? plain).map((raster) => rasterOverlay(raster, render, clip))];
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
