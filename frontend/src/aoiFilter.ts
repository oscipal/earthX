// "Filter within AOI only" (DS-03b): the filters of a dataset that depend on the area, measured inside the AOI instead of
// over the whole scene, the way the server answers it (`POST /stac/search` with the reserved `earthx:aoi_…` properties,
// plan `plans/ds/ds-03-wolken-in-aoi.md` §6.5, adr/0021 §6).
//
// Nothing here knows a dataset: which filters have the switch, and under which property the server measures them, is the
// registry's (`within_aoi` on a filter); the classes and the note to their limits are its `earthx:mask`.

import { countPositions } from './geoUtils';
import { LOAD_MORE_NOTE, NO_SCENES_NOTE, type ResultSection } from './sections';
import type { SearchFilterDescription } from './searchFilters';
import type { EarthxMask } from './types';

// The key of the body that carries the AOI to measure when the search itself sends the bounding box of a long AOI (§6.5).
// It belongs to the body of `POST /stac/search` only, never to a URL.
export const AOI_BODY_KEY = 'earthx:aoi';

// The properties the platform computes carry its namespace, which the source never sees (adr/0021 §2.7).
const PLATFORM_NAMESPACE = 'earthx:';

// The one the registry names for the filter on the share of clouds: its classes are the mask's `cloud_classes`.
const CLOUD_SHARE = 'earthx:aoi_cloud_cover';

// What a search checks at most (KE2 of the plan, a constant of the server). The tooltip names it; the answer
// says when it is reached (`limit_reached`).
export const AOI_SCENE_LIMIT = 500;

// Whether a search asks a dataset for a filter inside the AOI (its range stands under a platform property in its query).
type Asked = { queryByCollection?: Readonly<Record<string, Readonly<Record<string, unknown>>>> } | undefined;

const hasPlatformKey = (query: Readonly<Record<string, unknown>>): boolean =>
  Object.keys(query).some((key) => key.startsWith(PLATFORM_NAMESPACE));

export const measuresAoi = (query: Asked, datasetId: string): boolean => {
  const own = query?.queryByCollection?.[datasetId];
  return own !== undefined && hasPlatformKey(own);
};

export const anyMeasuresAoi = (query: Asked): boolean => Object.values(query?.queryByCollection ?? {}).some(hasPlatformKey);

// Whether a registry name is one the server measures (a platform property).
export const isPlatformProperty = (value: unknown): value is string =>
  typeof value === 'string' && value.startsWith(PLATFORM_NAMESPACE) && value.length > PLATFORM_NAMESPACE.length;

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
    .filter(([, query]) => hasPlatformKey(query))
    .map(([collection]) => collection);
  if (alone && filtered.length === 1) counts[filtered[0]] = alone;
  return counts;
}

// The classes the registry counts as clouds, as the tooltip names them, and whether shadows are among the classes that
// are left out (the plan wants the label to say that they do not count).
function classNote(mask: EarthxMask | null | undefined): string {
  const counted = [...(mask?.cloud_classes ?? [])].sort((a, b) => a - b);
  if (counted.length === 0) return '';
  const shadowsLeftOut = (mask?.classes ?? []).some((c) => /shadow/i.test(c.label) && !counted.includes(c.value));
  return ` (classes ${counted.join(', ')}${shadowsLeftOut ? '; cloud shadows do not count' : ''})`;
}

// The filters of a dataset that the switch changes: the ones the registry gives a property to measure inside the AOI.
export const withinFilters = (filters: readonly SearchFilterDescription[]): SearchFilterDescription[] =>
  filters.filter((filter) => filter.withinAoi !== null);

// The tooltip of the switch (§6.11, Otto 31.10.2026): which filters it changes, with the classes of the registry for
// the share of clouds, its note to the limits of the classification, the cost, and that the coverage map keeps the scene.
export function withinAoiTip(filters: readonly SearchFilterDescription[], mask: EarthxMask | null | undefined): string {
  const named = withinFilters(filters).map((filter) => `${filter.title}${filter.withinAoi === CLOUD_SHARE ? classNote(mask) : ''}`);
  return [
    `Measure these filters inside the AOI instead of the whole scene: ${named.join(', ')}. Others are unchanged. Slower: checks up to ${AOI_SCENE_LIMIT} scenes.`,
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
