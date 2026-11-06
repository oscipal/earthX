// The Data catalogue (UI-05 §4, Otto 06.11.2026): every dataset of `/stac/collections`, in groups, with what a STAC
// browser shows about it. Every value comes from the collection (P10); what a collection does not carry is "—", never a
// guess. Which datasets are in "Search and area" is `addedDatasetIds` in the store, saved per browser (`preferences.ts`).

import type { DatasetOption } from './datasets';
import { maturityLabel, maturityNote } from './datasets';
import { utcDay } from './dateBounds';
import { indexPresetsOf } from './indexPresets';
import { formatNumber } from './numberFormat';
import { shownUnit, trueColorOf } from './processingOrder';
import type { Collection } from './types';

// The groups in the order of the registry field `category` (UI-05 F1). A collection without one, or with one this viewer
// does not know, is in "Other" at the end: listed, so that the gap shows.
export const CATEGORIES = [
  { id: 'optical', title: 'Optical' },
  { id: 'radar', title: 'Radar' },
  { id: 'elevation', title: 'Elevation' },
  { id: 'land_cover', title: 'Land cover' },
  { id: 'weather_climate', title: 'Weather and climate' },
] as const;
export const OTHER_CATEGORY = { id: 'other', title: 'Other' } as const;

// How many datasets a first visit adds (UI-05 F3): as many as one page of "Search and area" holds.
export const FIRST_VISIT_DATASETS = 6;

export const NONE = '—';
// "Last checked" stays "—" until M5-24 adds the date of the health checks under `earthx:health` (`adr/0025` §6.6).
export const NOT_CHECKED = 'Not checked yet';

export interface CatalogueGroup {
  id: string;
  title: string;
  datasets: DatasetOption[];
}

function categoryOf(collection: Collection): string {
  const category = collection['earthx:category'];
  return CATEGORIES.some((c) => c.id === category) ? (category as string) : OTHER_CATEGORY.id;
}

const byTitle = (a: DatasetOption, b: DatasetOption): number => (a.title < b.title ? -1 : a.title > b.title ? 1 : 0);

// The groups that hold a dataset, in the order of `CATEGORIES`, each sorted by title.
export function catalogueGroups(datasets: readonly DatasetOption[]): CatalogueGroup[] {
  return [...CATEGORIES, OTHER_CATEGORY].flatMap(({ id, title }) => {
    const members = datasets.filter((d) => categoryOf(d.collection) === id).sort(byTitle);
    return members.length > 0 ? [{ id, title, datasets: members }] : [];
  });
}

// What reading the assets needs, where it is more than nothing (`adr/0027` W0): such a dataset is a catalogue entry with
// a link and is never added to "Search and area".
export function accountOf(collection: Collection): string | null {
  const account = collection['earthx:access']?.account;
  return typeof account === 'string' && account !== '' && account !== 'none' ? account : null;
}

// A prototype source (`adr/0024` R8): only `unclear` marks one, with the note of what is unclear.
export function prototypeNote(collection: Collection): string | null {
  if (collection['earthx:legal_status'] !== 'unclear') return null;
  const note = collection['earthx:legal_note'];
  return typeof note === 'string' && note.trim() !== '' ? note : 'The legal status of this source is not cleared';
}

// Why a dataset cannot go into "Search and area", or `null` where it can.
export function notAddableReason(dataset: DatasetOption): string | null {
  if (accountOf(dataset.collection)) return 'This source needs an account: open it at the source';
  if (!dataset.viewable) return `Not viewable: ${dataset.reason}`;
  return null;
}

// The datasets of a first visit (UI-05 F3, Otto 06.11.2026): those that can be added, in the order of the catalogue, at
// most six.
export function firstVisitDatasets(datasets: readonly DatasetOption[]): string[] {
  return catalogueGroups(datasets)
    .flatMap((group) => group.datasets)
    .filter((d) => notAddableReason(d) === null)
    .slice(0, FIRST_VISIT_DATASETS)
    .map((d) => d.id);
}

// The saved datasets that are still there and can still be added, in their order, once each. A dataset that left the
// registry (`RETIRED`) is not among `/stac/collections`, so it goes like an unknown one.
export function knownDatasets(ids: readonly string[], datasets: readonly DatasetOption[]): string[] {
  const addable = new Set(datasets.filter((d) => notAddableReason(d) === null).map((d) => d.id));
  return [...new Set(ids)].filter((id) => addable.has(id));
}

export const isHttps = (url: unknown): url is string => typeof url === 'string' && /^https:\/\/[^/\s]/u.test(url);

export interface LinkText {
  text: string;
  href: string | null;
}

export interface CatalogueRow {
  label: string;
  values: LinkText[];
  // An explanation behind an (i) beside the value.
  tip?: string;
}

const plain = (text: string): LinkText[] => [{ text, href: null }];
const link = (text: string, url: unknown): LinkText => ({ text, href: isHttps(url) ? url : null });

function providersRow(collection: Collection): LinkText[] {
  const providers = Array.isArray(collection.providers) ? collection.providers : [];
  const shown = providers.flatMap((p) => {
    if (!p || typeof p.name !== 'string' || p.name === '') return [];
    const roles = Array.isArray(p.roles) ? p.roles.filter((r) => typeof r === 'string') : [];
    return [link(roles.length > 0 ? `${p.name} · ${roles.join(', ')}` : p.name, p.url)];
  });
  return shown.length > 0 ? shown : plain(NONE);
}

// The host of the source's endpoint, linked to the endpoint, and the collection there.
export function sourceRow(collection: Collection): LinkText[] {
  const source = collection['earthx:source'];
  const endpoint = source?.endpoint;
  if (!isHttps(endpoint) || !URL.canParse(endpoint)) return plain(NONE);
  const host = new URL(endpoint).host;
  const id = source?.source_collection_id;
  return [link(typeof id === 'string' && id !== '' ? `${host} · ${id}` : host, endpoint)];
}

function licenseRows(collection: Collection): CatalogueRow[] {
  const flags = collection['earthx:license_flags'];
  if (!flags) return [{ label: 'License', values: plain(NONE) }, { label: 'Attribution', values: plain(NONE) }];
  const tiers: Record<string, string> = { catalog: 'Catalogue', display: 'Display', processing: 'Processing' };
  const license = [link(flags.name || flags.spdx_id || NONE, flags.url)];
  if (tiers[flags.tier]) license.push({ text: tiers[flags.tier], href: null });
  if (isHttps(flags.terms_url)) license.push(link('Terms', flags.terms_url));
  const year = (text: string | null) => (text ? text.replaceAll('{year}', '[year]') : null);
  const attribution = [year(flags.attribution_unmodified), year(flags.attribution_modified)].filter((t): t is string => !!t);
  return [
    { label: 'License', values: license },
    { label: 'Attribution', values: attribution.length > 0 ? attribution.map((text) => ({ text, href: null })) : plain(NONE) },
  ];
}

const degrees = (value: number, positive: string, negative: string): string =>
  `${formatNumber(Math.abs(value))}° ${value < 0 ? negative : positive}`;

// "180° W – 180° E · 60° S – 84° N" from the first box of the extent.
export function spatialExtentText(collection: Collection): string {
  const box = collection.extent?.spatial?.bbox?.[0];
  if (!Array.isArray(box) || box.length !== 4 || !box.every((v) => typeof v === 'number' && Number.isFinite(v))) return NONE;
  const [west, south, east, north] = box;
  return `${degrees(west, 'E', 'W')} – ${degrees(east, 'E', 'W')} · ${degrees(south, 'N', 'S')} – ${degrees(north, 'N', 'S')}`;
}

// "2015-06-27 – today", in UTC days; "No time axis" before it where a chosen period cannot narrow the dataset.
export function temporalExtentText(collection: Collection): string {
  const interval = collection.extent?.temporal?.interval?.[0];
  const [start, end] = Array.isArray(interval) ? interval : [undefined, undefined];
  const from = typeof start === 'string' ? utcDay(start) : null;
  const to = end === null ? 'today' : typeof end === 'string' ? utcDay(end) : null;
  if (!from && !to) return NONE;
  const span = `${from ?? NONE} – ${to ?? NONE}`;
  return collection['earthx:capabilities']?.time_range === false ? `No time axis · ${span}` : span;
}

export function resolutionText(collection: Collection): string {
  const gsd = collection.summaries?.gsd;
  const metres = Array.isArray(gsd) ? gsd.filter((v) => typeof v === 'number' && Number.isFinite(v) && v > 0) : [];
  return metres.length > 0 ? `${metres.map(formatNumber).join(', ')} m` : NONE;
}

function bandsText(collection: Collection): string {
  const units = collection['earthx:band_units'];
  if (!units || typeof units !== 'object') return NONE;
  const auxiliary = collection['earthx:auxiliary_assets'] ?? [];
  const mask = collection['earthx:mask']?.asset;
  const bands = Object.entries(units)
    .filter(([key]) => !auxiliary.includes(key) && key !== mask)
    .map(([key, unit]) => {
      const shown = shownUnit(unit);
      return shown ? `${key} · ${shown}` : key;
    });
  return bands.length > 0 ? bands.join(', ') : NONE;
}

const OPERATORS: [string, string][] = [
  ['band_math', 'Band math'],
  ['masking', 'Mask by class'],
  ['value_masking', 'Mask by value'],
  ['normalization', 'Normalize'],
  ['reprojection', 'Reproject and resample'],
  ['interpolation', 'Interpolation'],
];

function processingText(collection: Collection): string {
  const capabilities = collection['earthx:capabilities'] as Record<string, unknown> | undefined;
  const offered = OPERATORS.filter(([key]) => capabilities?.[key] === true).map(([, title]) => title);
  return offered.length > 0 ? offered.join(', ') : NONE;
}

function doiRow(collection: Collection): LinkText[] {
  const doi = collection['sci:doi'];
  const values: LinkText[] = typeof doi === 'string' && doi !== '' ? [link(doi, `https://doi.org/${doi}`)] : [];
  const citation = collection['sci:citation'];
  if (typeof citation === 'string' && citation !== '') values.push({ text: citation, href: null });
  return values.length > 0 ? values : plain(NONE);
}

// The rows of the details of one dataset (UI-05 §4.3), in the order of a STAC browser.
export function catalogueRows(dataset: DatasetOption): CatalogueRow[] {
  const c = dataset.collection;
  const region = c['earthx:source']?.data_region;
  const maturity = maturityLabel(c);
  // As "Quick processing" offers them: the indices, and "Enhance contrast" where the dataset has a true-colour picture.
  const quick = [...indexPresetsOf(c).map((p) => p.title), ...(trueColorOf(c) ? ['Enhance contrast'] : [])];
  return [
    { label: 'Description', values: plain(typeof c.description === 'string' && c.description !== '' ? c.description : NONE) },
    { label: 'Provider', values: providersRow(c) },
    { label: 'Source', values: sourceRow(c) },
    ...licenseRows(c),
    { label: 'Spatial extent', values: plain(spatialExtentText(c)) },
    { label: 'Temporal extent', values: plain(temporalExtentText(c)) },
    { label: 'Resolution', values: plain(resolutionText(c)) },
    { label: 'Bands', values: plain(bandsText(c)) },
    ...(c['earthx:mask'] ? [{ label: 'Mask', values: plain(c['earthx:mask'].asset) }] : []),
    { label: 'Data region', values: plain(typeof region === 'string' && region !== '' ? region : NONE) },
    { label: 'DOI', values: doiRow(c) },
    { label: 'Last checked', values: plain(NONE), tip: NOT_CHECKED },
    {
      label: 'Maturity',
      values: plain(maturity ?? (c['earthx:maturity'] === 'stable' ? 'stable' : NONE)),
      ...(maturityNote(c) ? { tip: maturityNote(c)! } : {}),
    },
    { label: 'Processing', values: plain(processingText(c)) },
    { label: 'Quick processing', values: plain(dataset.viewable && quick.length > 0 ? quick.join(', ') : NONE) },
  ];
}
