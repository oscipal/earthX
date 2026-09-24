// Pure logic for M2-07d (download from the layer manager): which layers can
// be downloaded, the request `POST /collections/{dataset}/download` needs,
// and the attribution / terms text shown before the crop is requested
// (adr/0003 §11.2: the notice belongs on the download, not only in a footer).

import type { DatasetOption } from './datasets';
import { defaultRenderOf } from './datasets';
import { bboxToPolygon } from './geoUtils';
import type { MapLayer } from './layers';
import type { LicenseFlags, StacItem } from './types';

export interface DownloadRequestInfo {
  datasetId: string;
  items: string[];
  assets: string[];
  aoi: GeoJSON.Geometry;
}

// A layer can be downloaded once there is something to cut the source data
// to. Three cases (V-6 added the second, M3-09 the third):
// - Viewed at full resolution, cropped to the AOI ("Crop to AOI"): the asset
//   is whichever one was actually fetched per item, the crop is `restore.aoi`.
// - Viewed at full resolution, showing the whole selection uncropped ("View
//   full selection", M3-09 P19 "Download folgt der Ansicht"): the download
//   follows what was shown, not the drawn AOI, and no AOI is needed at all.
//   Only a single whole scene is in scope here (P19's "eine ganze Szene
//   gewählt") — several whole scenes downloaded individually, straight from
//   the source without a merge, is M3-17's job. The scene's own bbox stands
//   in for the AOI on today's crop route, which for one rectangular scene is
//   a no-op crop rather than a real one.
// - A quicklook-only layer, pinned straight from the results list without
//   ever switching into full-resolution viewing: the crop route reads the
//   source's own pixels regardless of what the browser has fetched so far
//   (same reasoning as `downloadRequestForSelection`, V-4), so the asset is
//   the dataset's default visualisation asset, and the AOI is required as
//   before — there is no "view" to follow here, only a search AOI.
// Either way the scenes come from `restore.itemIds`, captured when the
// layer was pinned — not from the live search results, which may have moved
// on by the time someone opens the layer manager to download it.
export function downloadRequestFor(layer: MapLayer, datasets: DatasetOption[]): DownloadRequestInfo | null {
  const { restore } = layer;
  if (!restore.datasetId || restore.itemIds.length === 0) return null;
  if (restore.focusMode) {
    const entries = Object.entries(restore.downloaded).filter(([id]) => restore.itemIds.includes(id));
    if (entries.length === 0) return null;
    const assets = [...new Set(entries.map(([, info]) => info.asset))];
    if (!restore.cropToAoi) {
      if (entries.length !== 1) return null;
      const [, info] = entries[0];
      return { datasetId: restore.datasetId, items: restore.itemIds, assets, aoi: bboxToPolygon(info.bounds) };
    }
    if (!restore.aoi) return null;
    return { datasetId: restore.datasetId, items: restore.itemIds, assets, aoi: restore.aoi };
  }
  if (!restore.aoi) return null;
  const dataset = datasets.find((d) => d.id === restore.datasetId);
  const asset = dataset?.viewable ? defaultRenderOf(dataset.collection)?.assets[0] : undefined;
  if (!asset) return null;
  return { datasetId: restore.datasetId, items: restore.itemIds, assets: [asset], aoi: restore.aoi };
}

export function canDownloadLayer(layer: MapLayer, datasets: DatasetOption[]): boolean {
  return downloadRequestFor(layer, datasets) !== null;
}

// The same request, built directly from a selection of quicklooks instead of
// a pinned, already-full-resolution layer (V-4: "download a selected
// quicklook" — the original data over the existing crop route, not the
// preview image). Needs no prior "View full resolution": the crop route
// reads the source's own pixels regardless of what the browser has fetched
// so far, so the asset is the dataset's default visualisation asset, the
// same one `quicklookPlan`'s tile fallback and `enterFocus` use.
export function downloadRequestForSelection(
  dataset: DatasetOption | undefined,
  items: StacItem[],
  aoi: GeoJSON.Geometry | null,
): DownloadRequestInfo | null {
  if (!aoi || !dataset || !dataset.viewable || items.length === 0) return null;
  const asset = defaultRenderOf(dataset.collection)?.assets[0];
  if (!asset) return null;
  return { datasetId: dataset.id, items: items.map((it) => it.id), assets: [asset], aoi };
}

// `{year}` is the only placeholder the registry's attribution texts use
// (backend/earthx/catalog/registry.py — filled where data leaves the
// platform, never stored pre-filled). A crop always counts as modified data
// (access/download.py: "a crop is treated as modified data throughout"), so
// the modified text is shown here, the unmodified one only as a fallback if
// a dataset defines no modified text.
export function attributionText(flags: LicenseFlags | null | undefined, year: number): string | null {
  const text = flags?.attribution_modified ?? flags?.attribution_unmodified ?? null;
  return text ? text.replaceAll('{year}', String(year)) : null;
}

// The terms notice in the given language, falling back to English and then to
// whatever language the dataset does carry — the registry only guarantees a
// German text (backend/earthx/catalog/registry.py, `TermsOfUse.__post_init__`).
// `{terms_url}` is filled here: `earthx:license_flags` on the collection
// carries the raw registry text, the same placeholder the backend fills only
// when it writes the notice file that ships inside the ZIP.
export function termsNoticeText(flags: LicenseFlags | null | undefined, language = 'en'): string | null {
  const notice = flags?.terms_notice;
  if (!notice) return null;
  const text = notice[language] ?? notice.en ?? Object.values(notice)[0] ?? null;
  if (!text) return null;
  return flags?.terms_url ? text.replaceAll('{terms_url}', flags.terms_url) : text;
}

// Download tier follows the onboarding checklist (KLAERUNGEN B11): a crop
// hands out the source's pixels, so it needs the same licence tier as an
// operator, a job or the datacube. The backend enforces this too (403) — this
// is only so the dialog can say why the button is disabled instead of the
// user finding out after a failed request.
export function canExportLicense(flags: LicenseFlags | null | undefined): boolean {
  return flags?.tier === 'processing';
}
