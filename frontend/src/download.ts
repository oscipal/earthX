// Pure logic for M2-07d/M3-17 (download from the layer manager or the current
// selection): which layers can be downloaded, whether that means the AOI crop
// or the original files straight from the source, the request
// `POST /collections/{dataset}/download` needs, and the attribution / terms
// text shown before either one starts (adr/0003 §11.2: the notice belongs on
// the download, not only in a footer).

import type { ResolutionFactor } from './api';
import type { DatasetOption } from './datasets';
import { defaultRenderOf } from './datasets';
import type { MapLayer } from './layers';
import type { LicenseFlags, StacItem } from './types';

// `groups` (M3-17, replacing the flat `items` list): item ids per group, in
// the same shape `DownloadRequest.groups` in `api/tiler.py` expects — one
// merged file per group, separate groups as separate files in the same ZIP
// (P19). A single group is simply a list of one, the shape every download
// had before M3-17.
export interface DownloadRequestInfo {
  datasetId: string;
  groups: string[][];
  assets: string[];
  aoi: GeoJSON.Geometry;
}

// Which of the three P19 outcomes a download follows (M3-17 plan §4): the AOI
// crop, one merged file per group; the original files, straight from the
// source; or disabled, with the reason to show in the button's tooltip
// (M3-09's "Crop & merge to AOI" already has this pattern for a missing AOI).
export type DownloadOutcomeKind = 'crop' | 'originals' | 'disabled';

export const DRAW_AOI_TO_DOWNLOAD = 'Draw an AOI to download';

// The single decision table of M3-17 plan §4, as one pure function: what a
// download follows depends on which full-resolution view (if any) is active,
// whether an AOI is drawn, and whether the dataset is a single file (COG) or
// a store with no one file to link (`earthx:format`, anything but `'cog'`
// counts as the latter — an unset or unrecognised value is never assumed
// linkable).
//
// `cropToAoi` is `null` outside full-resolution viewing (browsing the results
// list, or a layer pinned straight from a quicklook, M2-07d's "quicklook-only
// layer") — there is no "Crop & merge"/"View full selection" choice to read,
// so it falls back to whether an AOI happens to be drawn, same as P19's rule
// for a whole scene with no full-resolution view entered at all.
export function decideDownloadOutcome(params: {
  cropToAoi: boolean | null;
  hasAoi: boolean;
  isCog: boolean;
}): DownloadOutcomeKind {
  const { cropToAoi, hasAoi, isCog } = params;
  if (cropToAoi === false) {
    // "View full selection": a whole COG scene is always its own original
    // file, regardless of whether an AOI happens to be drawn too (P19) — only
    // a source with no single file to link (Zarr) still needs the AOI crop.
    if (isCog) return 'originals';
    return hasAoi ? 'crop' : 'disabled';
  }
  if (hasAoi) return 'crop';
  return isCog ? 'originals' : 'disabled';
}

// `earthx:format` (architekturplan.md 5.1, M3-17): only `'cog'` counts as a
// single file the browser may link straight to the source. `undefined`/`null`
// (a dataset onboarded before M3-17) and any other value (`'zarr'`,
// `'legacy'`, an unrecognised future one) are all treated the same as Zarr —
// never assumed to be one linkable file without the registry saying so.
export function isCogFormat(dataset: DatasetOption | undefined): boolean {
  return dataset?.collection['earthx:format'] === 'cog';
}

// `earthx:source.asset_hosts` (D12) — the hosts a `href` on this dataset's own
// items may legitimately point at. Empty (not `undefined`/`null`, KLAERUNGEN
// B10's "no default" already governs the registry field) when the collection
// carries none, which then lets no link through — the same conservative
// direction as `isCogFormat`.
export function assetHostsOf(dataset: DatasetOption | undefined): string[] {
  return dataset?.collection['earthx:source']?.asset_hosts ?? [];
}

// A `href` is only ever shown as a direct download link when it is `https`
// and on a host this dataset's own registry entry names (D12) — never a
// `javascript:`/`data:` scheme, a bare `s3://` address `readers` alone can
// resolve, or a host a *different* dataset's items happen to live on. Items
// arrive federated from foreign sources (architekturplan.md 5.2); nothing
// about their `assets` shape is trusted further than this.
export function isDirectDownloadHref(href: string, assetHosts: readonly string[]): boolean {
  let url: URL;
  try {
    url = new URL(href);
  } catch {
    return false;
  }
  return url.protocol === 'https:' && assetHosts.includes(url.hostname);
}

// One clickable original file (M3-17 plan §6, F2 option 1): the dialog lists
// these instead of triggering one big download — no CORS is needed for a
// plain `<a href download>` (M3-09 §7, fund 2), and the browser is never
// asked to fetch more than one large file into memory at once.
export interface OriginalFileLink {
  itemId: string;
  groupLabel: string;
  asset: string;
  href: string;
}

// Built straight from already-fetched STAC items (never triggers a fetch
// itself, V-4/M2-07d's own rule of keeping this module pure) — `groups`
// carries a label per group (the results list's own group label, or a plain
// "Group N" for a pinned layer, which does not keep the label around).
export function originalFileLinks(
  groups: readonly { label: string; items: readonly StacItem[] }[],
  assets: readonly string[],
  assetHosts: readonly string[],
): OriginalFileLink[] {
  const links: OriginalFileLink[] = [];
  for (const group of groups) {
    for (const item of group.items) {
      for (const asset of assets) {
        const href = item.assets[asset]?.href;
        if (href && isDirectDownloadHref(href, assetHosts)) {
          links.push({ itemId: item.id, groupLabel: group.label, asset, href });
        }
      }
    }
  }
  return links;
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
// Only ever called once `decideDownloadOutcomeForLayer` below has already
// said this layer's download follows the crop (M3-17): a "View full
// selection" COG layer's download is the *originals* outcome instead, built
// separately once the dialog has fetched the items (`store.ts`).
//
// `restore.groupItemIds` (M3-17, PR #84's own per-overpass grouping reused,
// not a new one) splits `itemIds` back into the groups the results list drew
// them from, one merged file per group (P19) — a layer pinned before M3-17
// carries no `groupItemIds` and falls back to one group of everything, the
// flat shape every download had before.
export function downloadRequestFor(layer: MapLayer, datasets: DatasetOption[]): DownloadRequestInfo | null {
  const { restore } = layer;
  if (!restore.datasetId || !restore.aoi || restore.itemIds.length === 0) return null;
  const groups = restore.groupItemIds.length > 0 ? restore.groupItemIds : [restore.itemIds];
  if (restore.focusMode) {
    const entries = Object.entries(restore.downloaded).filter(([id]) => restore.itemIds.includes(id));
    if (entries.length === 0) return null;
    const assets = [...new Set(entries.map(([, info]) => info.asset))];
    return { datasetId: restore.datasetId, groups, assets, aoi: restore.aoi };
  }
  const dataset = datasets.find((d) => d.id === restore.datasetId);
  const asset = dataset?.viewable ? defaultRenderOf(dataset.collection)?.assets[0] : undefined;
  if (!asset) return null;
  return { datasetId: restore.datasetId, groups, assets: [asset], aoi: restore.aoi };
}

// The outcome (§4) for a pinned layer: `cropToAoi` only means anything while
// the layer was pinned from full-resolution viewing (`restore.focusMode`) —
// a quicklook-only layer reads like browsing the results list, `null`.
export function decideDownloadOutcomeForLayer(layer: MapLayer, datasets: DatasetOption[]): DownloadOutcomeKind {
  const { restore } = layer;
  const dataset = datasets.find((d) => d.id === restore.datasetId);
  return decideDownloadOutcome({
    cropToAoi: restore.focusMode ? restore.cropToAoi : null,
    hasAoi: !!restore.aoi,
    isCog: isCogFormat(dataset),
  });
}

export function canDownloadLayer(layer: MapLayer, datasets: DatasetOption[]): boolean {
  if (layer.restore.itemIds.length === 0) return false;
  const kind = decideDownloadOutcomeForLayer(layer, datasets);
  if (kind === 'disabled') return false;
  if (kind === 'crop') return downloadRequestFor(layer, datasets) !== null;
  // 'originals': the exact reachable links are only known once the dialog
  // fetches the items (`store.ts`) — here, a viewable dataset is enough to
  // offer the button at all.
  const dataset = datasets.find((d) => d.id === layer.restore.datasetId);
  return !!dataset?.viewable;
}

// The same request, built directly from a selection of quicklooks instead of
// a pinned, already-full-resolution layer (V-4: "download a selected
// quicklook" — the original data over the existing crop route, not the
// preview image). Needs no prior "View full resolution": the crop route
// reads the source's own pixels regardless of what the browser has fetched
// so far, so the asset is the dataset's default visualisation asset, the
// same one `quicklookPlan`'s tile fallback and `enterFocus` use.
//
// `groups` (M3-17): item ids per group (`grouping.ts::groupItemIdsFor`,
// built by the caller from the results list's own grouping — no new,
// download-specific grouping here). Only ever called once
// `decideDownloadOutcome` has already said the selection's download follows
// the crop; browsing with no AOI at all is the *originals* outcome instead.
export function downloadRequestForSelection(
  dataset: DatasetOption | undefined,
  groups: string[][],
  aoi: GeoJSON.Geometry | null,
): DownloadRequestInfo | null {
  const nonEmptyGroups = groups.filter((group) => group.length > 0);
  if (!aoi || !dataset || !dataset.viewable || nonEmptyGroups.length === 0) return null;
  const asset = defaultRenderOf(dataset.collection)?.assets[0];
  if (!asset) return null;
  return { datasetId: dataset.id, groups: nonEmptyGroups, assets: [asset], aoi };
}

// `{year}` is the only placeholder the registry's attribution texts use
// (backend/earthx/catalog/registry.py — filled where data leaves the
// platform, never stored pre-filled). A crop always counts as modified data
// (access/download.py: "a crop is treated as modified data throughout"), so
// the modified text is shown here, the unmodified one only as a fallback if
// a dataset defines no modified text.
// `modified` (M3-17): the AOI crop always counts as modified data (unchanged
// reasoning, above); the *original* files are not, so the download dialog
// shows the unmodified text for that outcome (M3-17 plan §6) — `false` picks
// `attribution_unmodified` first, falling back the other way where a dataset
// only defines one of the two texts.
export function attributionText(
  flags: LicenseFlags | null | undefined,
  year: number,
  modified = true,
): string | null {
  const text = modified
    ? (flags?.attribution_modified ?? flags?.attribution_unmodified ?? null)
    : (flags?.attribution_unmodified ?? flags?.attribution_modified ?? null);
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
