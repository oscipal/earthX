// The legends of the layers (M5-62, Otto 24.11.2026): what each layer drawn with a colour scale or as classes shows, from the tile URL
// the map draws it with, so it changes with the tiles: classes as a list (colour, value, name), a band with a colour scale as a bar with
// its ends and unit, a colour picture (RGB) and a picture drawn as it is nothing. The legend over the map shows one of them, chosen in its
// head among the visible layers, in the order of the layer manager (the topmost first, the view of the search where the entry "Search
// results" stands); the layer manager shows each layer's own under its row.

import { classesOfBand, type BandClass } from './bandClasses';
import { buildTileUrl } from './mapLayers';
import type { DatasetOption } from './datasets';
import { layerShownName } from './layerName';
import type { MapLayer } from './layers';
import { registryUnit, shownUnit } from './processingOrder';
import type { AppliedRender, DownloadedInfo } from './types';
import { physicalOf, type BandScaling } from './viewMeasure';

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
// as it is. The ends of a bar are physical (M5-60): the tiles of a band draw the stored values, which `scaling` turns into physical
// ones; a step or an expression computes in physical values already.
export function legendOfTile(tileUrl: string, classes: readonly BandClass[] | null, unit: string | null, scaling: BandScaling | null = null): LegendContent | null {
  const query = tileUrl.includes('?') ? tileUrl.slice(tileUrl.indexOf('?') + 1) : '';
  const params = new URLSearchParams(query);
  const rescale = params.getAll('rescale');
  const colour = params.getAll('bidx').length > 1 || (params.get('bidx') ?? '').includes(',') || rescale.length > 1;
  if (colour) return null;
  if (rescale.length === 0) return classes && (params.has('colormap') || params.has('colormap_name')) ? { kind: 'classes', classes } : null;
  const [low, high] = rescale[0].split(',').map(Number);
  if (!Number.isFinite(low) || !Number.isFinite(high)) return null;
  const stored = scaling !== null && !params.has('op') && !params.has('expression');
  const [min, max] = stored ? [physicalOf(low, scaling), physicalOf(high, scaling)] : [low, high];
  return { kind: 'bar', colormap: params.getAll('colormap_name').at(-1) ?? '', min, max, unit };
}

// The raster a layer draws, its first: every scene of a layer is drawn alike.
const rasterOf = (layer: MapLayer): string | null => {
  const raster = layer.overlays.find((o) => o.kind === 'raster');
  return raster && raster.kind === 'raster' && typeof raster.tileUrl === 'string' ? raster.tileUrl : null;
};

// The scaling of the asset a scene is drawn from, where the item states one.
const scalingOf = (scene: DownloadedInfo): BandScaling | null => scene.scalings?.[scene.asset] ?? null;

// The unit of a band of a dataset where it is physical; an index drawn by its expression has none.
function datasetUnit(dataset: DatasetOption | undefined, asset: string, tileUrl: string): string | null {
  if (!dataset || new URLSearchParams(tileUrl.split('?')[1] ?? '').has('expression')) return null;
  return shownUnit(registryUnit(dataset.collection, asset));
}

// The legend of one layer, visible or not; `null` where it has none.
export function layerLegend(layer: MapLayer, datasets: readonly DatasetOption[]): LegendEntry | null {
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
    content = legendOfTile(tileUrl, classes, scene ? datasetUnit(dataset, scene.asset, tileUrl) : null, scene ? scalingOf(scene) : null);
  }
  return content ? { id: layer.id, title: layerShownName(layer), content } : null;
}

// The view of the search, where no layer draws it: drawn with the look of the view (`mapLayers.ts::addTiles`).
function viewLegend(downloaded: Record<string, DownloadedInfo>, render: AppliedRender, datasets: readonly DatasetOption[]): LegendEntry | null {
  const scene = Object.values(downloaded)[0];
  if (!scene || typeof scene.tileUrl !== 'string') return null;
  const dataset = datasets.find((d) => d.id === scene.datasetId);
  const tileUrl = buildTileUrl(scene.tileUrl, render, scalingOf(scene));
  const content = legendOfTile(tileUrl, dataset ? classesOfBand(dataset.collection, scene.asset) : null, datasetUnit(dataset, scene.asset, tileUrl), scalingOf(scene));
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

// What the layers are, for the legend over the map: their order, which are shown, where "Search results" stands and which legends there
// are. A layer added, removed, shown, hidden or moved, or a view opened or closed, makes another one.
export function layersSignature(layers: readonly MapLayer[], resultsAt: number, entries: readonly LegendEntry[]): string {
  return [layers.map((layer) => `${layer.id}:${layer.visible ? 1 : 0}`).join(','), resultsAt, entries.map((entry) => entry.id).join(',')].join('|');
}

// What the legend over the map shows, and the layers as they were when it was chosen.
export interface LegendChoice {
  chosen: string | null;
  signature: string;
}

export const NO_CHOICE: LegendChoice = { chosen: null, signature: '' };

// The legend to show (Otto, 24.11.2026): the topmost visible layer with a legend. One chosen in the dropdown holds until the layers
// change (`layersSignature`); then it is the topmost again.
export function chooseLegend(previous: LegendChoice, entries: readonly LegendEntry[], signature: string): LegendChoice {
  const topmost = entries[0]?.id ?? null;
  if (signature !== previous.signature) return { chosen: topmost, signature };
  const kept = previous.chosen !== null && entries.some((entry) => entry.id === previous.chosen);
  return { chosen: kept ? previous.chosen : topmost, signature };
}

// Where the legend stands (UI-12, Otto 25.11.2026: it never goes away). `open`: at the bottom left of the map as it was; `folded`: there, but
// only its title, where the map is too low for it below the buttons at the top (a click opens it all the same); `docked`: its title at the
// left end of the status line, where an open panel would cover its place (a narrow window) or not even the title fits; it opens upwards.
export type LegendPlace = 'open' | 'folded' | 'docked';

export function legendPlace({ covered, room, head, full }: { covered: boolean; room: number; head: number; full: number }): LegendPlace {
  if (covered || room < head) return 'docked';
  return room < full ? 'folded' : 'open';
}
