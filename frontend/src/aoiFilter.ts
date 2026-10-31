// "Within AOI" (DS-03b): the cloud share of a scene measured inside the AOI, the way the server answers it
// (`POST /stac/search` with `earthx:aoi_cloud_cover`, plan `plans/ds/ds-03-wolken-in-aoi.md` §6.5) and the way the
// results list shows it (§6.11, §6.17).
//
// Nothing here knows a dataset: whether a dataset has the switch is the registry's (`within_aoi` on a filter), the
// classes and the note to their limits are its `earthx:mask` (`cloud_classes`, `cloud_note`).

import { countPositions } from './geoUtils';
import { LOAD_MORE_NOTE, NO_SCENES_NOTE, type ResultSection } from './sections';
import type { EarthxMask, StacItem, TimeStepGroup } from './types';

// The filter the platform computes, and the key of the body that carries the AOI to measure when the search itself
// sends the bounding box of a long AOI (§6.5). Both belong to the body of `POST /stac/search` only, never to a URL.
export const AOI_CLOUD_PROPERTY = 'earthx:aoi_cloud_cover';
export const AOI_BODY_KEY = 'earthx:aoi';
const MEASURE_PROPERTY = 'earthx:aoi_measure';

// What a search checks at most (KE2 of the plan, a constant of the server). The tooltip names it; the answer
// says when it is reached (`limit_reached`).
export const AOI_SCENE_LIMIT = 500;

// Whether a search asks a dataset for the cloud share in the AOI (the range stands under `AOI_CLOUD_PROPERTY` in its query).
type Asked = { queryByCollection?: Readonly<Record<string, Readonly<Record<string, unknown>>>> } | undefined;

export const measuresAoi = (query: Asked, datasetId: string): boolean =>
  query?.queryByCollection?.[datasetId]?.[AOI_CLOUD_PROPERTY] !== undefined;

export const anyMeasuresAoi = (query: Asked): boolean =>
  Object.values(query?.queryByCollection ?? {}).some((q) => q[AOI_CLOUD_PROPERTY] !== undefined);

// What the server reports for one dataset, over the whole search up to the answer (`earthx:aoi_filter`).
export interface AoiCounts {
  checked: number;
  found: number;
  unreadable: number;
  limitReached: boolean;
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isCount = (value: unknown): value is number => typeof value === 'number' && Number.isInteger(value) && value >= 0;

// One `earthx:aoi_filter`, or `null` for anything that is not the four fields: a note is a hint, a wrong answer must not
// take the list down.
export function countsFrom(value: unknown): AoiCounts | null {
  if (!isObject(value)) return null;
  const { checked, found, unreadable, limit_reached: limitReached } = value;
  if (!isCount(checked) || !isCount(found) || !isCount(unreadable) || typeof limitReached !== 'boolean') return null;
  return { checked, found, unreadable, limitReached };
}

// The counts of an answer by dataset. A search over several datasets names each one (`earthx:aoi_filter_by_collection`),
// a search over one carries the counts alone (`earthx:aoi_filter`); they belong to the one dataset that was asked with
// the filter. A source that is done is not named again on later pages, so the caller keeps the last it has.
export function aoiCountsOf(
  body: Record<string, unknown>,
  asked: Readonly<Record<string, Readonly<Record<string, unknown>>>> | undefined,
): Record<string, AoiCounts> {
  const counts: Record<string, AoiCounts> = Object.create(null);
  const byCollection = body['earthx:aoi_filter_by_collection'];
  if (isObject(byCollection)) {
    for (const [collection, value] of Object.entries(byCollection)) {
      const read = countsFrom(value);
      if (read) counts[collection] = read;
    }
  }
  const alone = countsFrom(body['earthx:aoi_filter']);
  const filtered = Object.entries(asked ?? {})
    .filter(([, query]) => AOI_CLOUD_PROPERTY in query)
    .map(([collection]) => collection);
  if (alone && filtered.length === 1) counts[filtered[0]] = alone;
  return counts;
}

// What a scene says about itself in the AOI (`earthx:aoi_cloud_cover`, `earthx:aoi_measure`).
export interface AoiMeasure {
  // The share of clouds among the valid pixels, in percent.
  percent: number;
  // The pixel counts the share of a time step is made of; `null` when the answer carried none.
  cloudPixels: number | null;
  dataPixels: number | null;
  // The share of the AOI that has valid pixels, in percent.
  dataPercent: number | null;
}

const isNumber = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value);

export function aoiMeasureOf(item: StacItem): AoiMeasure | null {
  const percent = item.properties[AOI_CLOUD_PROPERTY];
  if (!isNumber(percent)) return null;
  const measure = item.properties[MEASURE_PROPERTY];
  const read = isObject(measure) ? measure : {};
  const count = (value: unknown) => (isNumber(value) && value >= 0 ? value : null);
  return {
    percent,
    cloudPixels: count(read.cloud_pixels),
    dataPixels: count(read.data_pixels),
    dataPercent: isNumber(read.data_percent) ? read.data_percent : null,
  };
}

// The share of clouds of a time step: the cloud pixels of its scenes over their valid pixels (§6.8), so a large scene
// weighs more than a sliver. `null` when no scene of the group has a measure.
export function groupCloudPercent(items: readonly StacItem[]): number | null {
  let cloud = 0;
  let data = 0;
  for (const item of items) {
    const measure = aoiMeasureOf(item);
    if (!measure || measure.cloudPixels === null || measure.dataPixels === null) continue;
    cloud += measure.cloudPixels;
    data += measure.dataPixels;
  }
  return data > 0 ? (cloud / data) * 100 : null;
}

// Whole percent; under one percent "<1 %" (the plan), and a clear AOI stays "0 %".
export function cloudText(percent: number): string {
  if (percent === 0) return '0 %';
  if (percent < 1) return '<1 %';
  return `${Math.round(percent)} %`;
}

// A cloud sign that stays a sign: the text form, not the colour emoji some systems draw for U+2601.
export const CLOUD_SIGN = '☁︎';

// The classes the registry counts as clouds, as the tooltip names them, and whether shadows are among the classes that
// are left out (the plan wants the label to say that they do not count).
function classNote(mask: EarthxMask | null | undefined): string {
  const counted = [...(mask?.cloud_classes ?? [])].sort((a, b) => a - b);
  if (counted.length === 0) return '';
  const shadowsLeftOut = (mask?.classes ?? []).some((c) => /shadow/i.test(c.label) && !counted.includes(c.value));
  return ` (classes ${counted.join(', ')}${shadowsLeftOut ? '; cloud shadows do not count' : ''})`;
}

// What the tooltip of a value says (§6.11).
export function cloudValueTip(mask: EarthxMask | null | undefined, measure: AoiMeasure | null, percent: number): string {
  const covered = measure?.dataPercent != null ? Math.round(measure.dataPercent) : 100;
  const base = `Clouds in AOI: ${cloudText(percent)} of the AOI's valid pixels${classNote(mask)}.`;
  return covered < 100 ? `${base} Measured on ${covered} % of the AOI.` : base;
}

// The tooltip of the switch "Within AOI" (§6.11), with the registry's note to the limits of the classification.
export function withinAoiTip(mask: EarthxMask | null | undefined): string {
  return [
    `Limit applies to clouds inside the AOI${classNote(mask)}, measured on each scene. Slower: checks up to ${AOI_SCENE_LIMIT} scenes.`,
    mask?.cloud_note ?? '',
    'The coverage map shows the scene filter only.',
  ]
    .filter(Boolean)
    .join(' ');
}

export const LOCK_NEEDS_INPUT = 'Draw an AOI and set a date range first';
export const LOCK_NEEDS_AREA = 'Draw an area to use this filter';
export const LOCK_TOO_MANY = 'The area has too many points for this filter';

// The most positions the server measures in (`earthx:aoi`, plan §6.5; Otto, 31.10.2026: checked here first, the server's
// `400` stays as the safeguard).
export const MAX_AOI_POSITIONS = 20_000;

// Why "Within AOI" cannot be used right now, or `null` (§6.5, §6.17). The server needs an area and a date range with both
// ends; a point is no area, and more than `MAX_AOI_POSITIONS` positions are too many to measure in. A long AOI below that is no
// reason: the search then sends its bounding box and the AOI beside it.
export function withinAoiLock(s: {
  aoi: GeoJSON.Geometry | null;
  aoiPoint: GeoJSON.Point | null;
  dateFrom: string;
  dateTo: string;
}): string | null {
  if (!s.aoi || !s.dateFrom || !s.dateTo) return LOCK_NEEDS_INPUT;
  if (s.aoiPoint) return LOCK_NEEDS_AREA;
  if (countPositions((s.aoi as { coordinates?: unknown }).coordinates) > MAX_AOI_POSITIONS) return LOCK_TOO_MANY;
  return null;
}

// The hints under the name of a dataset in the head of the results (§6.9 KE5, §6.17). The date the limit was reached at
// is not named: the answer does not carry it.
export function limitNote(counts: AoiCounts): string {
  return `Checked ${counts.checked} scenes. Narrow the date range to search further.`;
}

export function unreadableNote(counts: AoiCounts): string {
  return `${counts.unreadable} ${counts.unreadable === 1 ? 'scene' : 'scenes'} could not be checked`;
}

export const NONE_WITHIN_NOTE = 'No scenes within the AOI limit in this date range';

// The notes of a section whose dataset was searched with the limit. They replace "No scenes for this area." (which does
// not say that scenes were left out) and, while the search still walks on, "Load more to see if there are any." (it asks
// the user for what the search does by itself).
export function aoiNotes(section: ResultSection, counts: AoiCounts | undefined, walking: boolean): string[] {
  const kept = section.notes.filter((note) => note !== NO_SCENES_NOTE && !(walking && note === LOAD_MORE_NOTE));
  const added: string[] = [];
  const nothing = section.items.length === 0 && !section.incomplete && section.groupingError === null;
  if (nothing && !walking && !kept.includes(LOAD_MORE_NOTE)) added.push(NONE_WITHIN_NOTE);
  if (counts?.limitReached) added.push(limitNote(counts));
  if (counts && counts.unreadable > 0) added.push(unreadableNote(counts));
  return [...kept, ...added];
}

// The order of the time steps in the list: by date as the search gives them, or by the share of clouds (least first;
// a step without a value last; equal values keep the order by date).
export type ResultSort = 'date' | 'clouds';

export function sortedGroupIndices(groups: readonly TimeStepGroup[], sort: ResultSort): number[] {
  const order = groups.map((_, i) => i);
  if (sort !== 'clouds') return order;
  const values = groups.map((group) => groupCloudPercent(group.items));
  return order.sort((a, b) => {
    const va = values[a];
    const vb = values[b];
    if (va === null && vb === null) return a - b;
    if (va === null) return 1;
    if (vb === null) return -1;
    return va - vb || a - b;
  });
}
