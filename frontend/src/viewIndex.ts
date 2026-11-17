// The quick processing in the view (NM4-14b, review of Otto 31.10.2026; M5-14): a preset of the dataset — an index, a composite of three
// expressions, a step of an operator — is drawn from the scenes at once through the tile route with its steps (the tile of a scene, or
// the mosaic of a pass, NM4-04), with no job. The choice is part of the look of the image (`AppliedRender.index`), so "Apply to all",
// "Add to layers" and the step from one image to the next carry it like they carry the colormap.
//
// Nothing here knows a preset: the registry names it (`quickPresets.ts`). Where the tile route cannot take it (too many bands for a
// mosaic, a request longer than the tiler passes) nothing is drawn and `indexBlockOf` says why: the view never falls back to a raw band
// behind the person's back.

import { buildMosaicOperatorTileTemplate, buildOperatorStatisticsUrl, buildOperatorTileTemplate, type MosaicSelection } from './api';
import { presetOfLook, shownBandsOf, tileStepsOf, type QuickPreset } from './quickPresets';
import {
  indexKeyOf,
  MAX_MOSAIC_OPERATOR_ASSETS,
  MAX_MOSAIC_REQUEST_BYTES,
  mosaicRequestBytes,
  passesOf,
  viewOfPass,
  type Mosaics,
  type PlannedRaster,
  type SceneEntry,
} from './mosaic';
import type { OverviewChain } from './overviewSubstitute';
import { firstZoomOf } from './tileSize';
import type { AppliedRender, Collection, TimeStepGroup } from './types';

export { assetsOfExpression } from './quickPresets';

// The preset as the overview below the first level computes it (M5-10 part B): the same steps, the band or bands they add shown.
export function indexChainOf(preset: QuickPreset): OverviewChain {
  return { steps: tileStepsOf(preset), band: shownBandsOf(preset) };
}

// The preset a look names, among the presets of the dataset; `null` for a look without one (or one the dataset lacks).
export function viewIndexOf(look: AppliedRender, collection: Collection | undefined): QuickPreset | null {
  return presetOfLook(look, collection);
}

// The text of the tooltip of the dropdown for an index: its title and formula (the same as the tooltip of the preset).
export const INDEX_TIP = 'Quick calculation of an index of the scenes shown. For whole scenes start a job in Processing.';

export type IndexBlock = 'zoom' | 'assets' | 'length';

// The short note in the view, and the explanation in its tooltip.
export const indexNote = (block: IndexBlock, name: string): string =>
  block === 'zoom' ? `Zoom in to compute ${name}` : `${name} cannot be computed here`;
export const indexNoteTip = (block: IndexBlock): string =>
  block === 'zoom'
    ? 'The quick calculation starts at the zoom where the image does. For whole scenes start a job in Processing.'
    : 'The tile server cannot take this many scenes or bands in one request. Zoom in to fewer scenes, or start a job in Processing.';

// The id a selection has, as long as it is not known: the length of the request does not depend on it.
const SOME_SELECTION: MosaicSelection = {
  id: '0'.repeat(32),
  datasetId: '',
  tiles: `/collections/-/mosaic/${'0'.repeat(32)}/tiles/WebMercatorQuad/{z}/{x}/{y}`,
  tilejson: '',
};

// The raster of the index for one raster of the view: a scene's tile for the raster of a scene, the mosaic's for the
// mosaic of the pass; or why the tile route cannot take it. `waiting`: the selection of the pass for the assets of the index is
// not created yet (`store.ts::fetchMosaics`), and nothing is drawn meanwhile.
export function indexRasterOf(
  raster: PlannedRaster,
  entries: SceneEntry[],
  datasetId: string,
  preset: QuickPreset,
  mosaics?: Mosaics,
): PlannedRaster | IndexBlock | 'waiting' {
  const { assets } = preset;
  const steps = tileStepsOf(preset);
  const band = shownBandsOf(preset);
  const scene = entries.find(([, info]) => info.tileUrl === raster.tileUrl);
  if (scene) return { ...raster, tileUrl: buildOperatorTileTemplate(datasetId, scene[0], assets, steps, band) };
  if (assets.length > MAX_MOSAIC_OPERATOR_ASSETS) return 'assets';
  if (mosaicRequestBytes(buildMosaicOperatorTileTemplate(SOME_SELECTION, steps, band), raster.maxZoom) > MAX_MOSAIC_REQUEST_BYTES) return 'length';
  const made = mosaics?.[indexKeyOf(datasetId, assets, entries)];
  if (made === undefined) return 'waiting';
  // The tiler did not take the selection of these assets: the index cannot be computed over this mosaic.
  if (made === null || !('selection' in made)) return 'assets';
  return { ...raster, tileUrl: buildMosaicOperatorTileTemplate(made.selection, steps, band) };
}

// What the map draws for a pass under the index: its rasters bottom to top, or `blocked`; `waiting` where a selection is not
// created yet (the same wait as without an index).
export function indexRastersOfPass(
  rasters: readonly PlannedRaster[],
  entries: SceneEntry[],
  datasetId: string,
  preset: QuickPreset,
  mosaics?: Mosaics,
): { rasters: PlannedRaster[]; block: IndexBlock | null; waiting: boolean } {
  const made = rasters.map((raster) => indexRasterOf(raster, entries, datasetId, preset, mosaics));
  const block = made.find((one): one is IndexBlock => one !== 'waiting' && typeof one === 'string') ?? null;
  const waiting = made.includes('waiting');
  return { rasters: block || waiting ? [] : (made as PlannedRaster[]), block, waiting };
}

// Why the index of the shown image cannot be drawn now, or `null` where it can: first what zooming does not mend (the
// request the tile route cannot take), then the zoom below which MapLibre asks for no tile of it (the scenes' own level while the mosaic is not known).
export function indexBlockOf(args: {
  datasetId: string;
  entries: SceneEntry[];
  groups: readonly TimeStepGroup[] | undefined;
  mosaics: Mosaics | undefined;
  preset: QuickPreset;
  mapZoom: number;
  // The index is drawn below the first level from the overview (M5-10 part B): zooming in is no condition then.
  overview?: boolean;
}): IndexBlock | null {
  const { datasetId, entries, groups, mosaics, preset, mapZoom, overview = false } = args;
  let lowest = Infinity;
  for (const pass of passesOf(entries, groups)) {
    const view = viewOfPass(datasetId, pass, mosaics);
    // A mosaic that is not known yet draws nothing, and the zoom note is true of its scenes all the same.
    const rasters = view.kind === 'mosaic' ? view.rasters : pass.map(([, info]) => info);
    const planned = view.kind === 'pending' ? { rasters, block: null, waiting: true } : indexRastersOfPass(rasters, pass, datasetId, preset, mosaics);
    if (planned.block) return planned.block;
    for (const raster of planned.waiting ? rasters : planned.rasters) lowest = Math.min(lowest, firstZoomOf(raster.minZoom, raster.tileUrl));
  }
  return lowest !== Infinity && mapZoom < lowest && !overview ? 'zoom' : null;
}

// The statistics of the index over one scene, for "auto-scale": the same tile route with the same step.
export function indexStatisticsUrl(datasetId: string, itemId: string, preset: QuickPreset): string {
  return buildOperatorStatisticsUrl(datasetId, itemId, preset.assets, tileStepsOf(preset), shownBandsOf(preset));
}
