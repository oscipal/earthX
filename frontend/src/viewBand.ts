// One band of the data in the view (NM4-45, Otto, 27.10.2026): the dropdown "Band" of the view offers, above the presets, the
// single bands of the dataset. A band is an asset of the item that the tile route reads by `?asset=` (the mosaic route
// takes it too), so choosing one changes the asset the scenes of the image are drawn from; the look of the image says which
// (`AppliedRender.band`), and `DownloadedInfo.baseAsset` remembers the asset the scene was opened with ("RGB" goes back to it).
//
// Nothing here knows a band by name: the item says which of its assets hold one band (`bandSources`), the registry which are
// no bands (`earthx:auxiliary_assets`, the mask layer) and whether the standard picture is a true-colour one.

import { buildTileTemplate } from './api';
import { lookOf, type DisplayLook } from './displayLook';
import { fieldNumber } from './numberFormat';
import { auxiliaryAssetsOf, bandSources, maskLayerOf, selectableAssets, trueColorOf } from './processingOrder';
import type { AppliedRender, Collection, DownloadedInfo, StacItem } from './types';
import { rawOf, type BandScaling } from './viewMeasure';

// The keys of the assets of `item` that hold one band, in the order of the item: not the pictures made from the bands, not
// the mask layer, and not the asset the standard picture is made from where that is a true-colour one. For COG assets, whose
// asset is the band, and for chunk references, one array per asset (M5-11: the quantities of a day, only those the day has); a
// Zarr asset needs the variable separator of the dataset, which the view does not fetch.
export function bandAssetsOf(item: StacItem | undefined, collection: Collection | undefined): string[] {
  const format = collection?.['earthx:format'];
  if (!item || !collection || (format !== 'cog' && format !== 'netcdf-refs')) return [];
  const sources = bandSources(item, format, null, collection).filter((source) => source.names.length <= 1);
  const wanted = selectableAssets(sources, auxiliaryAssetsOf(collection), maskLayerOf(collection)?.asset ?? null);
  const standard = collection['earthx:default_render']?.assets[0];
  return trueColorOf(collection) !== null ? wanted.filter((asset) => asset !== standard) : wanted;
}

// The look a band starts with (M5-60): its colormap and range as the collection publishes them for the band (`earthx:bands`,
// `earthx:look`, the form of `x-earthx-looks`, its numbers in the unit of the band). The registry resolves one for every band but a band
// of classes; nothing here derives one. `null` where the collection names none, or one that is not complete.
export function bandLookOf(collection: Collection | undefined, band: string): DisplayLook | null {
  const listed = Array.isArray(collection?.['earthx:bands']) ? collection['earthx:bands'] : [];
  return lookOf(listed.find((one) => one?.name === band)?.['earthx:look']);
}

// The fixed range of a look in the values the tiles of the band draw: the look is physical, the tiles draw what is stored
// (`viewMeasure.ts`); a scaling that cannot be read counts as none (M5-60 A5). `null` for a range that comes from a measure.
export function fixedRangeOf(look: DisplayLook, scaling: BandScaling | null): { vmin: string; vmax: string } | null {
  if (look.scale !== 'fixed' || look.low === undefined || look.high === undefined) return null;
  const one = scaling ?? { scale: 1, offset: 0 };
  return { vmin: fieldNumber(rawOf(look.low, one)), vmax: fieldNumber(rawOf(look.high, one)) };
}

// The asset a scene is drawn from for a look: the band of the look, else the one it was opened with.
export function assetOfLook(info: DownloadedInfo, look: AppliedRender): string {
  return look.band ?? info.baseAsset ?? info.asset;
}

// The scene drawn from `asset`; the same object where it already is.
export function withAsset(id: string, info: DownloadedInfo, asset: string): DownloadedInfo {
  if (info.asset === asset) return info;
  return { ...info, baseAsset: info.baseAsset ?? info.asset, asset, tileUrl: buildTileTemplate(info.datasetId, id, asset) };
}

// The tooltip of the dropdown "Band" of the view.
export const BAND_TIP = 'What the image shows: the standard colours of the dataset or one band of the data. The indices are in Quick processing.';

// What the locked dropdown says where the picture has one band and so nothing to choose.
export const ONE_BAND_TIP = 'This image has one band';
