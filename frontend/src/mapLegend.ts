// The legend over the map (M5-62, Otto 24.11.2026): one for each visible layer that is drawn with a colour scale or as classes, in
// the order of the layer manager (the topmost first), the view of the search where the entry "Search results" stands. What a legend
// shows comes from the tile URL the map draws the layer with, so it changes with the tiles: classes as a list (colour, value, name), a
// band with a colour scale as a bar with its ends and unit, a colour picture (RGB) and a picture drawn as it is not at all.

import { classesOfBand, type BandClass } from './bandClasses';
import { buildTileUrl } from './mapLayers';
import type { DatasetOption } from './datasets';
import { layerShownName } from './layerName';
import type { MapLayer } from './layers';
import { registryUnit, shownUnit } from './processingOrder';
import type { AppliedRender, DownloadedInfo } from './types';

export type LegendContent =
  | { kind: 'classes'; classes: readonly BandClass[] }
  // `colormap` is the tiler's name, `_r` for a reversed one; '' is the grey scale of a band drawn without one.
  | { kind: 'bar'; colormap: string; min: number; max: number; unit: string | null };

export interface LegendEntry {
  // The layer's id, or `VIEW_LEGEND` for the view of the search.
  id: string;
  title: string;
  content: LegendContent;
}

export const VIEW_LEGEND = 'view';

// What the tiles of `tileUrl` show: `classes` where they are drawn in the colours of classes the data names (a class table or the
// colours of the classes as `colormap`), a bar where one band is stretched over a range, nothing for a colour picture or a band drawn
// as it is.
export function legendOfTile(tileUrl: string, classes: readonly BandClass[] | null, unit: string | null): LegendContent | null {
  const query = tileUrl.includes('?') ? tileUrl.slice(tileUrl.indexOf('?') + 1) : '';
  const params = new URLSearchParams(query);
  const rescale = params.getAll('rescale');
  const colour = params.getAll('bidx').length > 1 || (params.get('bidx') ?? '').includes(',') || rescale.length > 1;
  if (colour) return null;
  if (rescale.length === 0) return classes && (params.has('colormap') || params.has('colormap_name')) ? { kind: 'classes', classes } : null;
  const [min, max] = rescale[0].split(',').map(Number);
  if (!Number.isFinite(min) || !Number.isFinite(max)) return null;
  return { kind: 'bar', colormap: params.getAll('colormap_name').at(-1) ?? '', min, max, unit };
}

// The raster a layer draws, its first: every scene of a layer is drawn alike.
const rasterOf = (layer: MapLayer): string | null => {
  const raster = layer.overlays.find((o) => o.kind === 'raster');
  return raster && raster.kind === 'raster' ? raster.tileUrl : null;
};

// The unit of a band of a dataset where it is physical; an index drawn by its expression has none.
function datasetUnit(dataset: DatasetOption | undefined, asset: string, tileUrl: string): string | null {
  if (!dataset || new URLSearchParams(tileUrl.split('?')[1] ?? '').has('expression')) return null;
  return shownUnit(registryUnit(dataset.collection, asset));
}

function layerLegend(layer: MapLayer, datasets: readonly DatasetOption[]): LegendEntry | null {
  const tileUrl = rasterOf(layer);
  if (!tileUrl) return null;
  let content: LegendContent | null;
  if (layer.result) {
    if (layer.result.expired || layer.result.deleted) return null;
    content = legendOfTile(tileUrl, layer.result.legend ?? null, shownUnit(layer.result.unit ?? null));
  } else {
    const scene = Object.values(layer.restore.downloaded ?? {})[0];
    const dataset = scene ? datasets.find((d) => d.id === scene.datasetId) : undefined;
    const classes = scene && dataset ? classesOfBand(dataset.collection, scene.asset) : null;
    content = legendOfTile(tileUrl, classes, scene ? datasetUnit(dataset, scene.asset, tileUrl) : null);
  }
  return content ? { id: layer.id, title: layerShownName(layer), content } : null;
}

// The view of the search, where no layer draws it: drawn with the look of the view (`mapLayers.ts::addTiles`).
function viewLegend(downloaded: Record<string, DownloadedInfo>, render: AppliedRender, datasets: readonly DatasetOption[]): LegendEntry | null {
  const scene = Object.values(downloaded)[0];
  if (!scene) return null;
  const dataset = datasets.find((d) => d.id === scene.datasetId);
  const tileUrl = buildTileUrl(scene.tileUrl, render);
  const content = legendOfTile(tileUrl, dataset ? classesOfBand(dataset.collection, scene.asset) : null, datasetUnit(dataset, scene.asset, tileUrl));
  return content ? { id: VIEW_LEGEND, title: dataset?.title ?? scene.datasetId, content } : null;
}

export interface LegendState {
  // The layers in the order of the manager, the topmost first, as the map draws them (`viewLayer.ts::layersForMap`).
  layers: readonly MapLayer[];
  // Where the entry "Search results" stands among them, the view of the search with it.
  resultsAt: number;
  datasets: readonly DatasetOption[];
  // The view of the search where it is shown on the map and no layer draws it; `null` otherwise.
  view: { downloaded: Record<string, DownloadedInfo>; render: AppliedRender } | null;
}

// Every legend over the map, the topmost layer first. A hidden layer has none.
export function legendEntries({ layers, resultsAt, datasets, view }: LegendState): LegendEntry[] {
  const of = (list: readonly MapLayer[]) => list.flatMap((layer) => (layer.visible ? [layerLegend(layer, datasets)] : [])).filter((e): e is LegendEntry => e !== null);
  const shown = view ? viewLegend(view.downloaded, view.render, datasets) : null;
  return [...of(layers.slice(0, resultsAt)), ...(shown ? [shown] : []), ...of(layers.slice(resultsAt))];
}
