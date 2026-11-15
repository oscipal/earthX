// The picture below the first level for the hits of a search (adr/0032 Nachtrag 15.11.2026, Otto: "a picture never disappears, in
// any view"). A scene of a dataset with a pyramid or a substitute (GLO-30, WorldCover, swissALTI3D) is drawn from the first level
// of the dataset on by its own tiles. Below it the view draws the picture of the dataset — its pyramid, or its substitute's — on the
// overview route of a footprint selection, which the tiler masks to the footprints of the hits that are shown: MapLibre cannot clip
// a raster by polygons, so the masking is the server's. The look is that of the scenes' previews; there is no mark on the map.

import { createFootprintSelection } from './api';
import type { FootprintSelection } from './api';
import { quicklookPlan } from './datasets';
import type { DatasetOption } from './datasets';
import type { PlannedRaster } from './mosaic';
import { overviewRasterOf } from './overviewSubstitute';
import type { AppliedRender, Bbox, StacItem } from './types';

// What the view draws below the first level of one dataset for its hits: the hits (a selection), the picture's levels and extent.
export interface HitsOverview {
  datasetId: string;
  // The ids of the hits that are drawn, sorted.
  itemIds: string[];
  // The levels and attribution of the picture (`overviewSubstitute.ts`); its bounds are cut to the hits.
  raster: PlannedRaster;
  render: AppliedRender;
}

// West, south, east, north of an item (a bbox of six numbers has the heights in between).
const flat = (bbox: readonly number[]): Bbox | null => {
  const box = bbox.length >= 6 ? [bbox[0], bbox[1], bbox[3], bbox[4]] : bbox.slice(0, 4);
  return box.length === 4 && box.every(Number.isFinite) ? (box as Bbox) : null;
};

// The picture for each dataset that has one, over the hits whose preview is a tile layer (a hit with a quicklook image draws the image at every
// level already). The datasets without a pyramid or a substitute, and the hits with no outline, draw nothing here. The look is that of the
// first hit's preview, which is the registry's default for the dataset.
export function hitsOverviewsOf(
  items: readonly StacItem[],
  datasetOf: (item: StacItem) => DatasetOption | null,
  datasets: readonly DatasetOption[] | undefined,
): HitsOverview[] {
  const found = new Map<string, { dataset: DatasetOption; ids: string[]; box: Bbox; render: AppliedRender }>();
  for (const item of items) {
    const dataset = datasetOf(item);
    const plan = dataset && quicklookPlan(item, dataset);
    const box = item.bbox ? flat(item.bbox) : null;
    if (!dataset || plan?.kind !== 'tiles' || !box) continue;
    const kept = found.get(dataset.id);
    if (!kept) {
      found.set(dataset.id, { dataset, ids: [item.id], box, render: plan.render });
      continue;
    }
    kept.ids.push(item.id);
    kept.box = [Math.min(kept.box[0], box[0]), Math.min(kept.box[1], box[1]), Math.max(kept.box[2], box[2]), Math.max(kept.box[3], box[3])];
  }
  return [...found.values()].flatMap(({ dataset, ids, box, render }) => {
    const raster = overviewRasterOf(dataset, datasets);
    if (!raster) return [];
    const [west, south, east, north] = [Math.max(box[0], raster.bounds[0]), Math.max(box[1], raster.bounds[1]), Math.min(box[2], raster.bounds[2]), Math.min(box[3], raster.bounds[3])];
    if (west > east || south > north) return [];
    return [{ datasetId: dataset.id, itemIds: [...new Set(ids)].sort(), raster: { ...raster, bounds: [west, south, east, north] as Bbox }, render }];
  });
}

// A selection is created once for the same hits and asked for again after this long, which renews it at the tiler (its term is seven days).
export const FOOTPRINTS_KEPT_MS = 60 * 60 * 1000;
const kept = new Map<string, { at: number; selection: Promise<FootprintSelection> }>();

// The footprint selection of these hits: the same hits give the same promise for an hour. A failure is not kept, the next sync asks again.
export function footprintSelectionFor(
  datasetId: string,
  itemIds: readonly string[],
  create: typeof createFootprintSelection = createFootprintSelection,
  now: () => number = Date.now,
): Promise<FootprintSelection> {
  const key = `${datasetId}\u0000${itemIds.join('\u0000')}`;
  const found = kept.get(key);
  if (found && now() - found.at < FOOTPRINTS_KEPT_MS) return found.selection;
  const selection = create(datasetId, itemIds);
  kept.set(key, { at: now(), selection });
  selection.catch(() => kept.get(key)?.selection === selection && kept.delete(key));
  return selection;
}

export function forgetFootprintSelections(): void {
  kept.clear();
}
