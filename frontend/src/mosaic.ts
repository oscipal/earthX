// One time step (an overpass) drawn as one surface instead of one layer per scene
// (M4-17c, plan `docs/plans/m4/m4-17-mosaik-kachel-pfad.md` §4.6). The tiler reads the
// scenes into a tile itself (`/collections/{dataset}/mosaic/…`); this module decides,
// per pass of a view, which of three things the map does:
//
//   scenes   one raster per scene, as before — one scene, a pass too big for the
//            tiler, or a mosaic the tiler refused;
//   pending  a mosaic that is not described yet: nothing is drawn, because the
//            scenes drawn meanwhile would each ask for tiles the mosaic then replaces;
//   mosaic   the mosaic at every level its dataset is released for (adr/0032 §6.2): what one tile reads is bounded by its
//            budget, and a tile over it shows a part without a mark on the map.
//
// A mosaic is a selection of the tiler (`mosaicSelection.ts`, adr/0032 §10.2). Its key here is logical — dataset, assets and
// the sorted ids of its scenes — and the URL the map draws is the one of the selection created for that key.

import type { MosaicSelection } from './api';
import { selectionKeyOf } from './mosaicSelection';
import type { Bbox, DownloadedInfo, TimeStepGroup } from './types';

// Mirror `earthx.api.mosaic_tiles` (`MIN_MOSAIC_ITEMS`, `MAX_SELECTION_ITEMS`, `MAX_MOSAIC_OPERATOR_ASSETS`,
// `MAX_MOSAIC_REQUEST_BYTES`); the tiler answers `400` or `413` outside them (`414` for the length). A pass of more scenes
// than a selection takes is drawn scene by scene.
export const MIN_MOSAIC_SCENES = 2;
export const MAX_SELECTION_ITEMS = 2000;
// A mosaic tile with steps reads at most this many assets of each scene.
export const MAX_MOSAIC_OPERATOR_ASSETS = 4;
// Path and query of a mosaic request as they arrive at the tiler: the longest a proxy or a CDN in front of it passes.
export const MAX_MOSAIC_REQUEST_BYTES = 7168;

// The bytes of a mosaic tile's request as the tiler counts them (`check_length`): path and query, without the address
// of the API, with the largest tile of `level` in the place of the grid's placeholders (the longest of its tiles).
export function mosaicRequestBytes(tileUrl: string, level: number): number {
  const request = tileUrl.slice(Math.max(0, tileUrl.indexOf('/collections/')));
  const last = String(2 ** level - 1);
  return request.replace('{z}', String(level)).replace('{x}', last).replace('{y}', last).length;
}

export type SceneEntry = [itemId: string, info: DownloadedInfo];

// What the map needs of a raster: `DownloadedInfo` has all of it, so a single scene is one.
// `hideFrom` is the zoom from which the layer is not drawn (MapLibre's layer `maxzoom`, which a
// source's own `maxzoom` is not: above that a source is overzoomed, not hidden). `attribution` is the text the map's
// attribution line carries while the raster is drawn (MapLibre does that for a source's `attribution`): set for the
// picture of a substitute dataset (`overviewSubstitute.ts`) and nowhere else.
export type PlannedRaster = Pick<DownloadedInfo, 'tileUrl' | 'bounds' | 'minZoom' | 'maxZoom'> & {
  hideFrom?: number;
  attribution?: string;
};

// What the TileJSON of a mosaic said, by the mosaic's tile template. `null`: the tiler refused it
// or could not be asked, and the scenes are drawn one by one.
export interface SceneOrder {
  order: string[];
}
// The selection of a pass for the assets an index reads (`indexKeyOf`), which the tile of the index is asked from.
export interface SelectionInfo {
  selection: MosaicSelection;
}
export interface MosaicInfo extends SceneOrder, Pick<DownloadedInfo, 'tileUrl' | 'bounds' | 'minZoom' | 'maxZoom'> {}
// The mosaics of the passes, by the template of each (`mosaicTemplateOf`), and next to them, by `orderKeyOf`, the order
// the tiler gives the scenes of a pass it draws one by one (NM4-24).
export type Mosaics = Record<string, MosaicInfo | SceneOrder | SelectionInfo | null>;

export type PassView =
  | { kind: 'scenes'; order?: readonly string[] }
  | { kind: 'pending' }
  | { kind: 'mosaic'; rasters: [PlannedRaster] };

// The scenes of a view split by the time step each belongs to. A scene no group holds (a layer of an
// earlier search) stands alone: its pass is unknown, and the tiler takes one pass per mosaic.
export function passesOf(entries: SceneEntry[], groups: readonly TimeStepGroup[] | undefined): SceneEntry[][] {
  const passes = new Map<number | string, SceneEntry[]>();
  for (const entry of entries) {
    const index = groups?.findIndex((g) => g.items.some((it) => it.id === entry[0])) ?? -1;
    const key = index >= 0 ? index : `alone ${entry[0]}`;
    const pass = passes.get(key);
    if (pass) pass.push(entry);
    else passes.set(key, [entry]);
  }
  return [...passes.values()];
}

// Time steps, and the scenes of a pass drawn one by one, come first on top: the first one wins where
// they overlap ("first valid pixel wins", M3-09, like the download's mosaic). The map takes them
// bottom to top, so this is the order to hand it. The view, a layer pinned from it and a pinned
// preview all lay their pictures with it, or the same selection would stack differently in each.
export function stackLikeView<T>(firstOnTop: readonly T[]): T[] {
  return [...firstOnTop].reverse();
}

// The key of the order of a pass's scenes in `Mosaics`: the one the tiler gives where there is no mosaic to follow, because
// the pass is too big for a selection or the tiler refused it.
export function orderKeyOf(datasetId: string, entries: SceneEntry[]): string | null {
  return entries.length >= MIN_MOSAIC_SCENES ? `order|${selectionKeyOf(datasetId, [entries[0][1].asset], entries.map(([id]) => id))}` : null;
}

export function isMosaicPass(entries: SceneEntry[]): boolean {
  const asset = entries[0]?.[1].asset;
  return (
    entries.length >= MIN_MOSAIC_SCENES &&
    entries.length <= MAX_SELECTION_ITEMS &&
    entries.every(([, info]) => info.asset === asset)
  );
}

// The mosaic's key in `Mosaics`, or `null` for a pass that is no mosaic.
export function mosaicKeyOf(datasetId: string, entries: SceneEntry[]): string | null {
  return isMosaicPass(entries) ? `mosaic|${selectionKeyOf(datasetId, [entries[0][1].asset], entries.map(([id]) => id))}` : null;
}

// The key of the selection of a pass for the assets an index reads: what the selection of the mosaic with steps is made from.
export function indexKeyOf(datasetId: string, assets: readonly string[], entries: SceneEntry[]): string {
  return `index|${selectionKeyOf(datasetId, assets, entries.map(([id]) => id))}`;
}

// Of all the mosaics known, those the passes of this view ask for: the view is drawn again when one of
// those changes, not when the TileJSON of another view comes in.
export function mosaicsOfView(
  mosaics: Mosaics,
  datasetId: string | null,
  entries: SceneEntry[],
  groups: readonly TimeStepGroup[] | undefined,
  indexAssets: readonly string[] | null = null,
): Mosaics {
  const picked: Mosaics = {};
  for (const pass of passesOf(entries, groups)) {
    const keys = datasetId ? [mosaicKeyOf(datasetId, pass), orderKeyOf(datasetId, pass), indexAssets && isMosaicPass(pass) ? indexKeyOf(datasetId, indexAssets, pass) : null] : [];
    for (const key of keys) {
      if (key && key in mosaics) picked[key] = mosaics[key];
    }
  }
  return picked;
}

export function sameMosaics(a: Mosaics, b: Mosaics): boolean {
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((k) => k in b && a[k] === b[k]);
}

// The scenes of a pass drawn one by one, in the order the tiler gave them, when it did (the others keep their place).
const scenesInOrder = (order: Mosaics[string] | undefined): PassView => (order && 'order' in order ? { kind: 'scenes', order: order.order } : { kind: 'scenes' });

export function viewOfPass(datasetId: string | null, entries: SceneEntry[], mosaics: Mosaics | undefined): PassView {
  const key = datasetId && mosaics ? mosaicKeyOf(datasetId, entries) : null;
  const asked = datasetId && mosaics ? orderKeyOf(datasetId, entries) : null;
  const order = asked && mosaics ? mosaics[asked] : null;
  if (!key || !mosaics) return scenesInOrder(order);
  const mosaic = mosaics[key];
  if (mosaic === undefined) return { kind: 'pending' };
  if (mosaic === null || !('tileUrl' in mosaic)) return scenesInOrder(order);
  return { kind: 'mosaic', rasters: [mosaic] };
}

// The scenes of a pass first on top, as the view stacks them: in the order the tiler gave for the pass when it did, else in the
// order of the selection. A scene the order does not name goes after the ones it names.
export function inStackOrder<T extends SceneEntry>(entries: readonly T[], order: readonly string[] | undefined): T[] {
  if (!order) return [...entries];
  const rank = new Map(order.map((id, i) => [id, i]));
  const rankOf = (id: string) => rank.get(id) ?? order.length;
  return [...entries].sort(([a], [b]) => rankOf(a) - rankOf(b));
}

// The scenes of a pass first on top: for a pass drawn scene by scene, in the order the tiler gave (`inStackOrder`).
export function orderedPass(datasetId: string | null, entries: SceneEntry[], mosaics: Mosaics | undefined): SceneEntry[] {
  const view = viewOfPass(datasetId, entries, mosaics);
  return view.kind === 'scenes' ? inStackOrder(entries, view.order) : entries;
}

// The scenes of a pass drawn one by one, of which the map draws only so many: those whose outline meets the part of the world in
// view first, in the order they have, then the others (`adr/0032` §10.4). Without a view the order alone counts.
export function chosenByView<T extends SceneEntry>(entries: readonly T[], view: Bbox | null, limit: number): T[] {
  const meets = ([, info]: SceneEntry) =>
    view !== null && info.bounds[0] <= view[2] && info.bounds[2] >= view[0] && info.bounds[1] <= view[3] && info.bounds[3] >= view[1];
  return [...entries.filter((entry) => meets(entry)), ...entries.filter((entry) => !meets(entry))].slice(0, Math.max(0, limit));
}
