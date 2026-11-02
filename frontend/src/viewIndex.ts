// The quick calculation of an index in the view (NM4-14b, review of Otto 31.10.2026): the dropdown "Index" of the view
// draws an index of the scenes at once through the tile route with an operator (`band_math` Version 2: the tile of a scene,
// or the mosaic of a pass, NM4-04), with no job. The choice is part of the look of the image (`AppliedRender.index`), so
// "Apply to all", "Add to layers" and the step from one image to the next carry it like they carry the colormap.
//
// Nothing here knows an index: the registry names it (`indexPresets.ts`). Where the tile route cannot take the index (too
// many bands for a mosaic, a request longer than the tiler passes) nothing is drawn and `indexBlockOf` says why: the view
// never falls back to a raw band behind the person's back.

import { buildMosaicOperatorTileTemplate, buildOperatorStatisticsUrl, buildOperatorTileTemplate, type TileStep } from './api';
import { indexPresetsOf, presetRange, type IndexPreset } from './indexPresets';
import {
  MAX_MOSAIC_OPERATOR_ASSETS,
  MAX_MOSAIC_REQUEST_BYTES,
  mosaicRequestBytes,
  passesOf,
  viewOfPass,
  type Mosaics,
  type PlannedRaster,
  type SceneEntry,
} from './mosaic';
import { canonicalJson } from './processing';
import { firstZoomOf } from './tileSize';
import type { AppliedRender, Collection, TimeStepGroup } from './types';

// The names an expression reads, in the order it first names them (a preset names no function). The registry checks that
// each is a band of the dataset, and the assets of Sentinel-2 are called like their bands.
const IDENTIFIER = /(?<![A-Za-z0-9_])[A-Za-z_][A-Za-z0-9_]*/gu;

export function assetsOfExpression(expression: string): string[] {
  return [...new Set(expression.match(IDENTIFIER) ?? [])];
}

// The steps of the tile: one Band math, which names the band it adds like the index.
function stepsOf(preset: IndexPreset): TileStep[] {
  return [{ op: 'band_math', opVersion: 2, paramsJson: canonicalJson({ expression: preset.expression, name: preset.name }) }];
}

// The preset a look names, among the presets of the dataset; `null` for a look without an index (or one the dataset lacks).
export function viewIndexOf(look: AppliedRender, collection: Collection | undefined): IndexPreset | null {
  if (!look.index) return null;
  return indexPresetsOf(collection).find((preset) => preset.name === look.index) ?? null;
}

// The look of an image that shows the index: its range and colormap, no band.
export function indexLookOf(preset: IndexPreset): AppliedRender {
  const { vmin, vmax, colormap } = presetRange(preset);
  return { index: preset.name, colormapName: colormap, rescale: `${vmin},${vmax}` };
}

// The text of the tooltip of the dropdown for an index: its title and formula (the same as the tooltip of the preset).
export const INDEX_TIP = 'Quick calculation of an index of the scenes shown, from zoom 8. For whole scenes start a job in Processing.';

export type IndexBlock = 'zoom' | 'assets' | 'length';

// The short note in the view, and the explanation in its tooltip.
export const indexNote = (block: IndexBlock, name: string): string =>
  block === 'zoom' ? `Zoom in to compute ${name}` : `${name} cannot be computed here`;
export const indexNoteTip = (block: IndexBlock): string =>
  block === 'zoom'
    ? 'The quick calculation works from zoom 8. For whole scenes start a job in Processing.'
    : 'The tile server cannot take this many scenes or bands in one request. Zoom in to fewer scenes, or start a job in Processing.';

// The raster of the index for one raster of the view: a scene's tile for the raster of a scene, the mosaic's for the
// mosaic of the pass; or why the tile route cannot take it.
export function indexRasterOf(raster: PlannedRaster, entries: SceneEntry[], datasetId: string, preset: IndexPreset): PlannedRaster | IndexBlock {
  const assets = assetsOfExpression(preset.expression);
  const scene = entries.find(([, info]) => info.tileUrl === raster.tileUrl);
  if (scene) return { ...raster, tileUrl: buildOperatorTileTemplate(datasetId, scene[0], assets, stepsOf(preset), preset.name) };
  if (assets.length > MAX_MOSAIC_OPERATOR_ASSETS) return 'assets';
  const tileUrl = buildMosaicOperatorTileTemplate(datasetId, entries.map(([id]) => id), assets, stepsOf(preset), preset.name);
  return mosaicRequestBytes(tileUrl, raster.maxZoom) > MAX_MOSAIC_REQUEST_BYTES ? 'length' : { ...raster, tileUrl };
}

// What the map draws for a pass under the index: its rasters bottom to top, or `blocked`. `null`: the mosaic of the pass is not
// known yet (the same wait as without an index).
export function indexRastersOfPass(
  rasters: readonly PlannedRaster[],
  entries: SceneEntry[],
  datasetId: string,
  preset: IndexPreset,
): { rasters: PlannedRaster[]; block: IndexBlock | null } {
  const made = rasters.map((raster) => indexRasterOf(raster, entries, datasetId, preset));
  const block = made.find((one): one is IndexBlock => typeof one === 'string') ?? null;
  return { rasters: block ? [] : (made as PlannedRaster[]), block };
}

// Why the index of the shown image cannot be drawn now, or `null` where it can: first what zooming does not mend (the
// request the tile route cannot take), then the zoom below which MapLibre asks for no tile of it (the scenes' own level while the mosaic is not known).
export function indexBlockOf(args: {
  datasetId: string;
  entries: SceneEntry[];
  groups: readonly TimeStepGroup[] | undefined;
  mosaics: Mosaics | undefined;
  preset: IndexPreset;
  mapZoom: number;
}): IndexBlock | null {
  const { datasetId, entries, groups, mosaics, preset, mapZoom } = args;
  let lowest = Infinity;
  for (const pass of passesOf(entries, groups)) {
    const view = viewOfPass(datasetId, pass, mosaics);
    // A mosaic that is not known yet draws nothing, and the zoom note is true of its scenes all the same.
    const rasters = view.kind === 'mosaic' ? view.rasters : pass.map(([, info]) => info);
    const planned = view.kind === 'pending' ? { rasters, block: null } : indexRastersOfPass(rasters, pass, datasetId, preset);
    if (planned.block) return planned.block;
    for (const raster of planned.rasters) lowest = Math.min(lowest, firstZoomOf(raster.minZoom, raster.tileUrl));
  }
  return lowest !== Infinity && mapZoom < lowest ? 'zoom' : null;
}

// The statistics of the index over one scene, for "auto-scale": the same tile route with the same step.
export function indexStatisticsUrl(datasetId: string, itemId: string, preset: IndexPreset): string {
  return buildOperatorStatisticsUrl(datasetId, itemId, assetsOfExpression(preset.expression), stepsOf(preset), preset.name);
}
