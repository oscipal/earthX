// The AOI crops a search draws by itself (M3-10, Otto 30.09.2026): a dataset with
// `browse: 'full_resolution'` has no quicklook to show first, so its scenes appear
// straight away as the full-resolution view cut to the AOI. They belong to that
// dataset's results and are on the map only while the dataset is the one chosen in
// the results dropdown; the user can pin them (`store.ts::pinSearchCrops`).

import { clipTileUrl } from './aoiClip';
import { buildTileTemplate } from './api';
import type { DatasetOption } from './datasets';
import { defaultRenderOf } from './datasets';
import type { MapLayer } from './layers';
import { buildTileUrl } from './mapLayers';
import { appliedRenderFrom } from './render';
import type { ResultSection } from './sections';
import type { DownloadedInfo } from './types';

type ViewableDataset = Extract<DatasetOption, { viewable: true }>;

// One layer per time-step group of the section, like "Crop & merge to AOI" pins
// them (M3-09 §10): each carries its own overlays and downloads as one file.
// Empty where the dataset names no standard visualisation — the caller says so.
export function fullResolutionLayers(
  dataset: ViewableDataset,
  section: ResultSection,
  aoi: GeoJSON.Geometry,
  batchId: string,
): MapLayer[] {
  const render = defaultRenderOf(dataset.collection);
  const asset = render?.assets[0];
  if (!render || !asset) return [];
  const applied = appliedRenderFrom(render);
  const layers: MapLayer[] = [];
  section.groups.forEach((group, groupIndex) => {
    const downloaded: Record<string, DownloadedInfo> = {};
    for (const item of group.items) {
      if (!item.bbox) continue;
      downloaded[item.id] = {
        tileUrl: buildTileTemplate(dataset.id, item.id, asset),
        bounds: item.bbox,
        asset,
        minZoom: dataset.zoom.min,
        maxZoom: dataset.zoom.max,
      };
    }
    const itemIds = Object.keys(downloaded);
    if (itemIds.length === 0) return;
    layers.push({
      id: `S${batchId}${layers.length}-${dataset.id}`,
      name: `${dataset.title} · ${group.label}`,
      visible: true,
      opacity: 1,
      overlays: Object.values(downloaded).map((info) => ({
        kind: 'raster' as const,
        tileUrl: clipTileUrl(buildTileUrl(info.tileUrl, applied), aoi),
        bounds: info.bounds,
        minZoom: info.minZoom,
        maxZoom: info.maxZoom,
      })),
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

// What the map draws besides the browse view: the layers the user pinned — always,
// whatever dataset is chosen — and, under them, the crops of the dataset chosen in
// the dropdown. The crops of every other dataset of the search stay off the map.
export function layersOnMap(pinned: MapLayer[], crops: MapLayer[], chosenDatasetId: string | null): MapLayer[] {
  if (chosenDatasetId === null) return pinned;
  return [...pinned, ...crops.filter((crop) => crop.restore.datasetId === chosenDatasetId)];
}
