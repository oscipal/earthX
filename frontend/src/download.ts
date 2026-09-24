// Pure logic for M2-07d (download from the layer manager): which layers can
// be downloaded, the request `POST /collections/{dataset}/download` needs,
// and the attribution / terms text shown before the crop is requested
// (adr/0003 §11.2: the notice belongs on the download, not only in a footer).

import type { ResolutionFactor } from './api';
import type { DatasetOption } from './datasets';
import { defaultRenderOf } from './datasets';
import type { MapLayer } from './layers';
import type { LicenseFlags, StacItem } from './types';

export interface DownloadRequestInfo {
  datasetId: string;
  items: string[];
  assets: string[];
  aoi: GeoJSON.Geometry;
}

// A layer can be downloaded once it has an AOI to crop (a layer pinned
// before any AOI was drawn has nothing to cut the source data to). Two
// cases (V-6 added the second):
// - Viewed at full resolution first (a `raster` overlay backed by
//   `store.downloaded`, M2-07b): the asset is whichever one was actually
//   fetched, per item.
// - A quicklook-only layer, pinned straight from the results list without
//   ever switching into full-resolution viewing: the crop route reads the
//   source's own pixels regardless of what the browser has fetched so far
//   (same reasoning as `downloadRequestForSelection`, V-4), so the asset is
//   the dataset's default visualisation asset.
// Either way the scenes come from `restore.itemIds`, captured when the
// layer was pinned — not from the live search results, which may have moved
// on by the time someone opens the layer manager to download it.
//
// M3-09 (Otto's review of PR #84, 24.09.2026): a "View full selection"
// (`restore.cropToAoi === false`) layer's download does *not* follow the
// view here, unlike the map's own AOI clip. P19 requires the *original*
// file for a whole COG scene — straight from the source through the
// browser, bypassing the platform entirely — and, for Zarr, no download at
// all without an AOI (button disabled, "Draw an AOI to download"). Routing
// an uncropped download through this same crop endpoint would instead crop
// it to the AOI, which is exactly what P19 rules out (a whole, unclipped
// scene). Building the real behaviour needs a source-format distinction
// (COG vs. Zarr) that
// is not yet available to the frontend without dataset-specific branching —
// that is M3-17's job (see its note in
// `plans/m3-dritte-quelle-und-interface.md`). `restore.cropToAoi` still
// drives the *map's* clip (`store.ts`, `mapLayers.ts`) — only the download
// side of it was reverted here.
export function downloadRequestFor(layer: MapLayer, datasets: DatasetOption[]): DownloadRequestInfo | null {
  const { restore } = layer;
  if (!restore.datasetId || !restore.aoi || restore.itemIds.length === 0) return null;
  if (restore.focusMode) {
    const entries = Object.entries(restore.downloaded).filter(([id]) => restore.itemIds.includes(id));
    if (entries.length === 0) return null;
    const assets = [...new Set(entries.map(([, info]) => info.asset))];
    return { datasetId: restore.datasetId, items: restore.itemIds, assets, aoi: restore.aoi };
  }
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

// The asset's own ground sample distance, in metres/pixel, the same order
// `access/download.py::_asset_gsd` tries on the backend: the asset's own
// `gsd`, then its pixel size read off `proj:transform` (a plain STAC item
// carries no `raster:bands` the frontend already parses). `null` when
// neither is present — the resolution dialog then shows the factor alone,
// never a guessed number (F10c, M3-18 §10).
function assetGsdMeters(item: StacItem, asset: string): number | null {
  const stacAsset = item.assets[asset];
  if (!stacAsset) return null;
  if (typeof stacAsset.gsd === 'number' && stacAsset.gsd > 0) return stacAsset.gsd;
  const transform = stacAsset['proj:transform'];
  if (Array.isArray(transform) && typeof transform[0] === 'number' && transform[0] > 0) {
    return transform[0];
  }
  return null;
}

// The label the download dialog shows for one resolution choice (F10c,
// M3-18 §10) — "Native (10 m)"/"2× (20 m)" where a metre figure can be read
// off any of the given items, "Native"/"2×" otherwise. The finest (smallest)
// gsd among the items is used, matching the backend's own worst-case pixel
// estimate (`plan_outputs`) — never a number that could understate the result.
export function resolutionOptionLabel(items: StacItem[], asset: string, factor: ResolutionFactor): string {
  const label = factor === 1 ? 'Native' : `${factor}×`;
  const gsds = items.map((item) => assetGsdMeters(item, asset)).filter((gsd): gsd is number => gsd !== null);
  if (gsds.length === 0) return label;
  const meters = Math.min(...gsds) * factor;
  const rounded = meters >= 10 ? Math.round(meters) : Math.round(meters * 10) / 10;
  return `${label} (${rounded} m)`;
}

// Download tier follows the onboarding checklist (KLAERUNGEN B11): a crop
// hands out the source's pixels, so it needs the same licence tier as an
// operator, a job or the datacube. The backend enforces this too (403) — this
// is only so the dialog can say why the button is disabled instead of the
// user finding out after a failed request.
export function canExportLicense(flags: LicenseFlags | null | undefined): boolean {
  return flags?.tier === 'processing';
}
