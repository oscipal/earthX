// Pure logic for M2-07d (download from the layer manager): which layers can
// be downloaded, the request `POST /collections/{dataset}/download` needs,
// and the attribution / terms text shown before the crop is requested
// (adr/0003 §11.2: the notice belongs on the download, not only in a footer).

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

// A layer can be downloaded once it has been viewed at full resolution (a
// `raster` overlay backed by `store.downloaded`, M2-07b) over a drawn AOI. A
// quicklook-only layer carries neither an asset key nor a crop AOI — only a
// thumbnail URL and the item's own footprint — so there is nothing to crop.
export function downloadRequestFor(layer: MapLayer): DownloadRequestInfo | null {
  const { restore } = layer;
  if (!restore.focusMode || !restore.datasetId || !restore.aoi) return null;
  const entries = Object.entries(restore.downloaded);
  if (entries.length === 0) return null;
  const items = entries.map(([id]) => id);
  const assets = [...new Set(entries.map(([, info]) => info.asset))];
  return { datasetId: restore.datasetId, items, assets, aoi: restore.aoi };
}

export function canDownloadLayer(layer: MapLayer): boolean {
  return downloadRequestFor(layer) !== null;
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
