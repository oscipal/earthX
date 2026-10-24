// One time step (an overpass) drawn as one surface instead of one layer per scene
// (M4-17c, plan `docs/plans/m4/m4-17-mosaik-kachel-pfad.md` §4.6). The tiler reads the
// scenes into a tile itself (`/collections/{dataset}/mosaic/…`); this module decides,
// per pass of a view, which of three things the map does:
//
//   scenes   one raster per scene, as before — one scene, a pass too big for the
//            tiler, a dataset released below z8 only, or a mosaic the tiler refused;
//   pending  a mosaic that is not described yet: nothing is drawn, because the
//            scenes drawn meanwhile would each ask for tiles the mosaic then replaces;
//   mosaic   the mosaic from its first level up and, below it, the single scenes
//            stacked in the order the mosaic reads them (`earthx:order`), so the
//            scene on top of an overlap does not change when the map zooms across z8.

import { buildMosaicTileTemplate } from './api';
import type { DownloadedInfo, TimeStepGroup } from './types';

// Mirror `earthx.api.mosaic_tiles` (`MIN_MOSAIC_ZOOM`, `MAX_ITEMS`); the tiler answers `400`
// outside them. They are not read from the TileJSON, which comes only after the URL is built.
export const MIN_MOSAIC_ZOOM = 8;
export const MAX_MOSAIC_SCENES = 64;

// A source's `minzoom`/`maxzoom` are tile levels, a layer's `maxzoom` is a map zoom. MapLibre rounds the map zoom
// for a raster source and asks 256-px tiles for the level above it (`placeRaster`), so tile level L is first
// asked at map zoom L - 1.5: from there the mosaic is loaded and the scenes under it have to be out of sight.
const TILE_LEVEL_AHEAD = 1.5;

export type SceneEntry = [itemId: string, info: DownloadedInfo];

// What the map needs of a raster: `DownloadedInfo` has all of it, so a single scene is one.
// `hideFrom` is the zoom from which the layer is not drawn (MapLibre's layer `maxzoom`, which a
// source's own `maxzoom` is not: above that a source is overzoomed, not hidden).
export type PlannedRaster = Pick<DownloadedInfo, 'tileUrl' | 'bounds' | 'minZoom' | 'maxZoom'> & { hideFrom?: number };

// What the TileJSON of a mosaic said, by the mosaic's tile template. `null`: the tiler refused it
// or could not be asked, and the scenes are drawn one by one.
export interface MosaicInfo extends Pick<DownloadedInfo, 'tileUrl' | 'bounds' | 'minZoom' | 'maxZoom'> {
  order: string[];
}
export type Mosaics = Record<string, MosaicInfo | null>;

export type PassView =
  | { kind: 'scenes' }
  | { kind: 'pending' }
  | { kind: 'mosaic'; rasters: PlannedRaster[] }; // bottom to top

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

export function isMosaicPass(entries: SceneEntry[]): boolean {
  const asset = entries[0]?.[1].asset;
  return (
    entries.length >= 2 &&
    entries.length <= MAX_MOSAIC_SCENES &&
    entries.every(([, info]) => info.asset === asset && info.maxZoom >= MIN_MOSAIC_ZOOM)
  );
}

// The mosaic's tile template — also its key in `Mosaics` — or `null` for a pass that is no mosaic.
export function mosaicTemplateOf(datasetId: string, entries: SceneEntry[]): string | null {
  return isMosaicPass(entries) ? buildMosaicTileTemplate(datasetId, entries.map(([id]) => id), entries[0][1].asset) : null;
}

// Of all the mosaics known, those the passes of this view ask for: the view is drawn again when one of
// those changes, not when the TileJSON of another view comes in.
export function mosaicsOfView(
  mosaics: Mosaics,
  datasetId: string | null,
  entries: SceneEntry[],
  groups: readonly TimeStepGroup[] | undefined,
): Mosaics {
  const picked: Mosaics = {};
  for (const pass of passesOf(entries, groups)) {
    const template = datasetId ? mosaicTemplateOf(datasetId, pass) : null;
    if (template && template in mosaics) picked[template] = mosaics[template];
  }
  return picked;
}

export function sameMosaics(a: Mosaics, b: Mosaics): boolean {
  const keys = Object.keys(a);
  return keys.length === Object.keys(b).length && keys.every((k) => k in b && a[k] === b[k]);
}

export function viewOfPass(datasetId: string | null, entries: SceneEntry[], mosaics: Mosaics | undefined): PassView {
  const template = datasetId && mosaics ? mosaicTemplateOf(datasetId, entries) : null;
  if (!template || !mosaics) return { kind: 'scenes' };
  const mosaic = mosaics[template];
  if (mosaic === undefined) return { kind: 'pending' };
  if (mosaic === null) return { kind: 'scenes' };
  const rank = new Map(mosaic.order.map((id, i) => [id, i]));
  const rankOf = (id: string) => rank.get(id) ?? mosaic.order.length;
  const below: PlannedRaster[] = entries
    .filter(([, info]) => info.minZoom < mosaic.minZoom)
    .sort(([a], [b]) => rankOf(a) - rankOf(b))
    .reverse() // the first the mosaic reads ends up topmost
    .map(([, info]) => ({
      tileUrl: info.tileUrl,
      bounds: info.bounds,
      minZoom: info.minZoom,
      maxZoom: mosaic.minZoom - 1, // `isMosaicPass`: every scene is released at least to z8
      hideFrom: mosaic.minZoom - TILE_LEVEL_AHEAD,
    }));
  return { kind: 'mosaic', rasters: [...below, mosaic] };
}

// A time step too big for one mosaic is drawn scene by scene, and the map draws only so many of those.
export function oversizeNote(passes: SceneEntry[][], notDrawn: number): string | null {
  const biggest = Math.max(0, ...passes.map((pass) => pass.length));
  if (biggest <= MAX_MOSAIC_SCENES) return null;
  return `A time step of ${biggest} scenes is more than one mosaic takes (${MAX_MOSAIC_SCENES}); its scenes are drawn one by one${
    notDrawn > 0 ? `, ${notDrawn} of them not at all` : ''
  }.`;
}
