// One band of the data in the view (NM4-45, Otto, 27.10.2026): the dropdown "Band" of the view offers, above the presets, the
// single bands of the dataset. A band is an asset of the item that the tile route reads by `?asset=` (the mosaic route
// takes it too), so choosing one changes the asset the scenes of the image are drawn from; the look of the image says which
// (`AppliedRender.band`), and `DownloadedInfo.baseAsset` remembers the asset the scene was opened with ("RGB" goes back to it).
//
// Nothing here knows a band by name: the item says which of its assets hold one band (`bandSources`), the registry which are
// no bands (`earthx:auxiliary_assets`, the mask layer) and whether the standard picture is a true-colour one.

import { buildTileTemplate } from './api';
import { auxiliaryAssetsOf, bandSources, maskLayerOf, selectableAssets, trueColorOf } from './processingOrder';
import type { AppliedRender, Collection, DownloadedInfo, StacItem } from './types';

// The keys of the assets of `item` that hold one band, in the order of the item: not the pictures made from the bands, not
// the mask layer, and not the asset the standard picture is made from where that is a true-colour one. Only for COG assets,
// whose asset is the band (a Zarr asset needs the variable separator of the dataset, which the view does not fetch).
export function bandAssetsOf(item: StacItem | undefined, collection: Collection | undefined): string[] {
  if (!item || !collection || collection['earthx:format'] !== 'cog') return [];
  const sources = bandSources(item, 'cog', null, collection).filter((source) => source.names.length <= 1);
  const wanted = selectableAssets(sources, auxiliaryAssetsOf(collection), maskLayerOf(collection)?.asset ?? null);
  const standard = collection['earthx:default_render']?.assets[0];
  return trueColorOf(collection) !== null ? wanted.filter((asset) => asset !== standard) : wanted;
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
export const BAND_TIP =
  'The picture of the image: the standard one, one band of the data, or the quick calculation of an index (from zoom 8; for whole scenes start a job in Processing).';
