// The AOI crops a search draws by itself (M3-10, Otto 30.09.2026): a dataset with
// `browse: 'full_resolution'` has no quicklook to show first, so its scenes appear
// straight away as the full-resolution view cut to the AOI. They belong to that
// dataset's results and are on the map only while the dataset is the one chosen in
// the results dropdown; the user can pin them (`store.ts::pinSearchCrops`).

import { clipTileUrl } from './aoiClip';
import { buildTileTemplate } from './api';
import type { DatasetOption } from './datasets';
import { defaultRenderOf } from './datasets';
import type { LayerOverlay, MapLayer } from './layers';
import { buildTileUrl } from './mapLayers';
import { viewOfPass } from './mosaic';
import type { Mosaics, PlannedRaster, SceneEntry } from './mosaic';
import { appliedRenderFrom } from './render';
import type { ResultSection } from './sections';
import type { AppliedRender, TimeStepGroup } from './types';

type ViewableDataset = Extract<DatasetOption, { viewable: true }>;

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
): LayerOverlay[] | null {
  const view = viewOfPass(datasetId, entries, mosaics);
  if (view.kind === 'pending') return null;
  const rasters = view.kind === 'mosaic' ? view.rasters : entries.map(([, info]) => info);
  return rasters.map((raster) => rasterOverlay(raster, render, clip));
}

// The scenes of a group the dataset can draw: those with a bounding box, in the tile URL of its
// standard visualisation.
function groupEntries(dataset: ViewableDataset, asset: string, group: TimeStepGroup): SceneEntry[] {
  const entries: SceneEntry[] = [];
  for (const item of group.items) {
    if (!item.bbox) continue;
    entries.push([
      item.id,
      {
        tileUrl: buildTileTemplate(dataset.id, item.id, asset),
        bounds: item.bbox,
        asset,
        minZoom: dataset.zoom.min,
        maxZoom: dataset.zoom.max,
      },
    ]);
  }
  return entries;
}

// The passes of the AOI crops of these sections that a mosaic can draw, for the store to load.
export function cropPasses(
  datasets: readonly ViewableDataset[],
  sections: readonly ResultSection[],
): { datasetId: string; entries: SceneEntry[] }[] {
  return datasets.flatMap((dataset) => {
    const section = sections.find((x) => x.datasetId === dataset.id);
    const asset = defaultRenderOf(dataset.collection)?.assets[0];
    if (dataset.browse !== 'full_resolution' || !section || !asset) return [];
    return section.groups.map((group) => ({ datasetId: dataset.id, entries: groupEntries(dataset, asset, group) }));
  });
}

// One layer per time-step group of the section, like "Crop & merge to AOI" pins
// them (M3-09 §10): each carries its own overlays and downloads as one file.
// Empty where the dataset names no standard visualisation — the caller says so.
export function fullResolutionLayers(
  dataset: ViewableDataset,
  section: ResultSection,
  aoi: GeoJSON.Geometry,
  batchId: string,
  // What the mosaics of its groups look like once they have loaded. Until then a group is drawn scene by scene.
  mosaics?: Mosaics,
): MapLayer[] {
  const render = defaultRenderOf(dataset.collection);
  const asset = render?.assets[0];
  if (!render || !asset) return [];
  const applied = appliedRenderFrom(render);
  const layers: MapLayer[] = [];
  section.groups.forEach((group, groupIndex) => {
    const entries = groupEntries(dataset, asset, group);
    if (entries.length === 0) return;
    const downloaded = Object.fromEntries(entries);
    const itemIds = Object.keys(downloaded);
    layers.push({
      id: `S${batchId}${layers.length}-${dataset.id}`,
      name: `${dataset.title} · ${group.label}`,
      visible: true,
      opacity: 1,
      overlays:
        overlaysOfPass(dataset.id, entries, mosaics, applied, aoi) ?? overlaysOfPass(dataset.id, entries, undefined, applied, aoi) ?? [],
      restore: {
        focusMode: true,
        downloaded,
        appliedRender: { ...applied },
        activeGroupIndex: groupIndex,
        selectedIds: itemIds,
        itemIds,
        // One group already — the per-group split is this function's own.
        groupItemIds: [itemIds],
        aoi,
        cropToAoi: true,
        datasetId: dataset.id,
      },
    });
  });
  return layers;
}

// What a layer draws, so that the same picture pinned twice has the same key;
// empty for a layer without overlays, which draws nothing and equals nothing.
const pictureOf = (layer: MapLayer): string =>
  layer.overlays.length === 0
    ? ''
    : JSON.stringify(layer.overlays.map((ov) => (ov.kind === 'raster' ? [ov.tileUrl, ov.bounds] : [ov.url, ov.coords])).sort());

// What the map draws besides the browse view: the layers the user pinned — always,
// whatever dataset is chosen — and, under them, the crops of the dataset chosen in
// the dropdown. The crops of every other dataset of the search stay off the map.
// A crop the user has pinned is not drawn a second time (Otto, 20.10.2026): the
// pinned copy is the one the layer manager switches, hidden or not.
export function layersOnMap(pinned: MapLayer[], crops: MapLayer[], chosenDatasetId: string | null): MapLayer[] {
  if (chosenDatasetId === null) return pinned;
  const pinnedPictures = new Set(pinned.map(pictureOf));
  const isPinned = (crop: MapLayer) => pictureOf(crop) !== '' && pinnedPictures.has(pictureOf(crop));
  return [
    ...pinned,
    ...crops.filter((crop) => crop.restore.datasetId === chosenDatasetId && !isPinned(crop)),
  ];
}
