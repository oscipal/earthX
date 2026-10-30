// Pure logic of the download of whole scenes (NM4-33, plan section 6.14): which files of a scene belong to it, what
// they are called, which way the browser takes them, and the text of `ATTRIBUTION.txt`. Nothing here fetches or
// touches the page; `originalsRun.ts` does, and takes everything it decides from this module.

import type { DownloadPass, OriginalFileLink } from './download';
import { attributionText, isDirectDownloadHref, termsNoticeText } from './download';
import type { ZipJob } from './originalsZip';
import type { Collection, LicenseFlags, StacItem } from './types';

// A file larger than this does not go through the memory of the page when a ZIP cannot be streamed (Otto, 29.10.2026):
// the browser downloads it itself, under the name the source gives it.
export const MAX_FILE_BYTES = 500 * 1024 * 1024;

export const ATTRIBUTION_FILENAME = 'ATTRIBUTION.txt';
export const ITEM_FILENAME = 'item.json';

export interface OriginalEntry {
  asset: string;
  // `<scene id>_<asset><extension of the source>`, the name in the ZIP and of a single file saved by the page.
  name: string;
  href: string;
  size: number | null;
  // `metadata`: a file about the scene (XML, JSON), which a browser shows instead of saving it when it is only linked.
  kind: 'data' | 'metadata';
}

export interface OriginalScene {
  item: StacItem;
  groupLabel: string;
  zipName: string;
  entries: OriginalEntry[];
  // Assets the rule names that the item cannot give as a direct download (not there, not `https`, a foreign host).
  missing: string[];
}

// Letters, digits, dot, dash and underscore only: a name made from a scene id or an asset key never leaves the folder
// the browser saves to, and never needs quoting. Whatever else is there becomes `_`; a leading dot would hide the file.
export function safeName(text: string): string {
  const cleaned = text.replace(/[^A-Za-z0-9._-]/g, '_').replace(/^\.+/, '_');
  return cleaned === '' ? '_' : cleaned;
}

export function fileExtension(href: string): string {
  try {
    const last = new URL(href).pathname.split('/').pop() ?? '';
    return /\.[A-Za-z0-9]{1,5}$/.exec(last)?.[0].toLowerCase() ?? '';
  } catch {
    return '';
  }
}

// The name the source gives the file, for the download the browser makes itself.
export function sourceFileName(href: string): string {
  try {
    return new URL(href).pathname.split('/').pop() || href;
  } catch {
    return href;
  }
}

// Which assets of an item are its original files, read from the collection (Otto, 29.10.2026, Z1 and Z3): the
// raster assets the registry lists with a unit (`earthx:band_units`, a key ending in `*` names a Zarr group and is no
// file), without the pictures made from the bands (`earthx:auxiliary_assets`) unless the default rendering is one,
// then every asset of the item with the STAC role `metadata`. No asset name is written down in the frontend.
export function originalAssetKeys(collection: Collection, item: StacItem): { key: string; kind: 'data' | 'metadata' }[] {
  const auxiliary = new Set(collection['earthx:auxiliary_assets'] ?? []);
  for (const key of collection['earthx:default_render']?.assets ?? []) auxiliary.delete(key);
  const keys: { key: string; kind: 'data' | 'metadata' }[] = Object.keys(collection['earthx:band_units'] ?? {})
    .filter((key) => !key.includes('*') && !auxiliary.has(key))
    .map((key) => ({ key, kind: 'data' }));
  const named = new Set(keys.map((entry) => entry.key));
  for (const [key, asset] of Object.entries(item.assets)) {
    if (!named.has(key) && (asset.roles ?? []).includes('metadata')) keys.push({ key, kind: 'metadata' });
  }
  return keys;
}

export function sceneOriginals(collection: Collection, item: StacItem, groupLabel: string): OriginalScene {
  const hosts = collection['earthx:source']?.asset_hosts ?? [];
  const used = new Set<string>();
  const entries: OriginalEntry[] = [];
  const missing: string[] = [];
  for (const { key, kind } of originalAssetKeys(collection, item)) {
    const asset = item.assets[key];
    if (!asset || !isDirectDownloadHref(asset.href, hosts)) {
      missing.push(key);
      continue;
    }
    const base = `${safeName(item.id)}_${safeName(key)}`;
    let name = `${base}${fileExtension(asset.href)}`;
    for (let n = 2; used.has(name); n += 1) name = `${base}-${n}${fileExtension(asset.href)}`;
    used.add(name);
    const size = asset['file:size'];
    entries.push({ asset: key, name, href: asset.href, size: typeof size === 'number' && size > 0 ? size : null, kind });
  }
  return { item, groupLabel, zipName: `${safeName(item.id)}.zip`, entries, missing };
}

// The scenes of a selection, in the order of its passes; a scene in two passes comes once.
export function scenesOf(collection: Collection, passes: readonly DownloadPass[]): OriginalScene[] {
  const seen = new Set<string>();
  const scenes: OriginalScene[] = [];
  for (const pass of passes) {
    for (const item of pass.items) {
      if (seen.has(item.id)) continue;
      seen.add(item.id);
      scenes.push(sceneOriginals(collection, item, pass.label));
    }
  }
  return scenes;
}

// The addresses at the source, for "Save link list" and the list under the rows: every file of the scenes, so a
// download manager gets the same files the ZIP holds.
export function linksOf(scenes: readonly OriginalScene[]): OriginalFileLink[] {
  return scenes.flatMap((scene) =>
    scene.entries.map((entry) => ({
      itemId: scene.item.id,
      groupLabel: scene.groupLabel,
      asset: entry.asset,
      href: entry.href,
    })),
  );
}

// How the files get to the user (plan section 6.14.5): `zip` one stream of STORE ZIPs through a service worker,
// `files` each file through the page and saved under its own name (where the browser cannot stream), `navigate` the
// browser downloads each file itself (the source gives no CORS, so the page may not read it).
export type Way = 'zip' | 'files' | 'navigate';

export function chooseWay(cors: boolean | null | undefined, canStream: boolean): Way {
  if (cors !== true) return 'navigate';
  return canStream ? 'zip' : 'files';
}

export function sceneItemJson(item: StacItem): string {
  return `${JSON.stringify(item, null, 2)}\n`;
}

// The attribution names the year of the scenes (NM4-01); a scene without a date leaves it unknown, and nothing is
// downloaded then rather than a file with a year made up.
export function attributionBlocker(flags: LicenseFlags | null | undefined, years: string | null): string | null {
  const text = flags?.attribution_unmodified ?? flags?.attribution_modified;
  if (text?.includes('{year}') && years === null) {
    return 'A scene has no acquisition date, so the attribution cannot name its year.';
  }
  return null;
}

export interface SavedFile {
  itemId: string;
  asset: string;
  // The name the file has once saved: ours in the ZIP and for single files, the source's for a download the browser
  // makes itself.
  name: string;
}

// `ATTRIBUTION.txt`: the same parts, in the same order, as the notice of the crop ZIP (`access/download.py`,
// `build_notice_text`), for original files: the unmodified attribution, the terms, the citation, the scenes, which
// file is which asset, what is missing, and when.
export function attributionFileText(args: {
  collection: Collection;
  scenes: readonly OriginalScene[];
  files: readonly SavedFile[];
  years: string | null;
  now: Date;
}): string {
  const { collection, scenes, files, years, now } = args;
  const flags = collection['earthx:license_flags'];
  const lines = [collection.title ?? collection.id];
  const attribution = attributionText(flags, years, false);
  if (attribution) lines.push(attribution);
  const terms = termsNoticeText(flags, 'en');
  if (terms) lines.push(terms);
  if (flags?.terms_url && !terms?.includes(flags.terms_url)) lines.push(flags.terms_url);
  if (collection['sci:citation']) lines.push(collection['sci:citation']);
  if (collection['sci:doi']) lines.push(`DOI: https://doi.org/${collection['sci:doi']}`);
  lines.push(`${scenes.length === 1 ? 'Scene' : 'Scenes'}: ${scenes.map((scene) => scene.item.id).join(', ')}`);
  lines.push(
    ['Files:', ...files.map((file) => `  ${file.name} (${file.itemId}, asset ${file.asset})`)].join('\n'),
  );
  const gaps = scenes.filter((scene) => scene.missing.length > 0);
  if (gaps.length > 0) {
    lines.push(
      [
        'Not included, because the source gives no direct link for them:',
        ...gaps.map((scene) => `  ${scene.item.id}: ${scene.missing.join(', ')}`),
      ].join('\n'),
    );
  }
  lines.push(
    `These are the original files, as the source holds them. Your browser downloaded them straight from the source; nothing passed through the platform. ${ITEM_FILENAME} is the STAC item as the platform gave it.`,
  );
  lines.push(`Generated: ${now.toISOString().replace(/\.\d{3}Z$/, 'Z')}`);
  return `${lines.join('\n\n')}\n`;
}

// The job for the service worker: one ZIP for one scene. Every entry needs its size by now (`file:size` or a `HEAD`).
export function zipJobOf(scene: OriginalScene, attribution: string, sizes: ReadonlyMap<string, number>): ZipJob {
  return {
    zipName: scene.zipName,
    texts: [
      { name: ATTRIBUTION_FILENAME, content: attribution },
      { name: ITEM_FILENAME, content: sceneItemJson(scene.item) },
    ],
    files: scene.entries.map((entry) => ({ name: entry.name, url: entry.href, size: sizes.get(entry.href) ?? 0 })),
  };
}

export function savedFilesOf(scenes: readonly OriginalScene[], named: (entry: OriginalEntry) => string): SavedFile[] {
  return scenes.flatMap((scene) =>
    scene.entries.map((entry) => ({ itemId: scene.item.id, asset: entry.asset, name: named(entry) })),
  );
}
