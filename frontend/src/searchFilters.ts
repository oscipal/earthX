// The search filters of a dataset (DS-02c): what the registry offers (`earthx:search_filters` of the collection),
// what the user has put into the fields, and the `query` the search and the coverage send for it.
//
// Nothing here knows a dataset or a property: the registry names the properties, the kind (a range or a choice
// of values), the bounds, the labels and the unit, and this reads them as data (DS-02 plan §6.3, "Kein
// datensatzspezifischer Code"). The server checks every request against the same registry and answers `400` to
// anything else (plan §6.4), so a filter this sends is always one the dataset offers; the checks below are there
// to tell the user what is wrong before "Search" is pressed, not to stand in for the server's.

import type { Collection } from './types';

export interface FilterValue {
  value: string;
  label: string;
}

export interface SearchFilterDescription {
  // The STAC property as the source names it (`eo:cloud_cover`): the key of the query.
  property: string;
  kind: 'range' | 'values';
  title: string;
  // The tooltip.
  description: string;
  unit: string | null;
  // `range` only.
  minimum: number;
  maximum: number;
  integer: boolean;
  // `values` only.
  values: FilterValue[];
}

// What stands in the fields. A range keeps the text of its two fields, so that half a number the user is typing is
// not turned into something else under the cursor; empty means "no bound". A choice keeps the ticked values; none
// ticked means "no filter".
export type FilterInput = { kind: 'range'; from: string; to: string } | { kind: 'values'; values: string[] };

// By property.
export type FilterInputs = Record<string, FilterInput>;

// `{property: {gte, lte}}` or `{property: {in: [...]}}`, the form of the STAC query extension.
export type FilterQuery = Record<string, Record<string, number | string[]>>;

// A collection is not changed once it is loaded, and the store reads its filters on every change of state (whether
// "Search" may be pressed): read each one once.
const read = new WeakMap<Collection, SearchFilterDescription[]>();

// The filters of a dataset, in the order of the registry. An entry that is not complete is left out rather than
// guessed at, like every other registry field the viewer reads (`datasets.ts`): a filter with a made-up bound
// would send the server a value it answers with `400`.
export function searchFiltersOf(collection: Collection): SearchFilterDescription[] {
  const known = read.get(collection);
  if (known) return known;
  const raw = collection['earthx:search_filters'];
  const seen = new Set<string>();
  const found: SearchFilterDescription[] = [];
  for (const entry of Array.isArray(raw) ? raw : []) {
    const description = describe(entry);
    if (!description || seen.has(description.property)) continue;
    seen.add(description.property);
    found.push(description);
  }
  read.set(collection, found);
  return found;
}

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isText = (value: unknown): value is string => typeof value === 'string' && value !== '';

function describe(entry: unknown): SearchFilterDescription | null {
  if (!isObject(entry)) return null;
  const { property, kind, title, description, unit } = entry;
  if (!isText(property) || !isText(title) || !isText(description)) return null;
  if (unit !== null && unit !== undefined && !isText(unit)) return null;
  const common = { property, title, description, unit: unit ?? null };
  if (kind === 'range') {
    const { minimum, maximum } = entry;
    if (typeof minimum !== 'number' || typeof maximum !== 'number') return null;
    if (!Number.isFinite(minimum) || !Number.isFinite(maximum) || minimum >= maximum) return null;
    return { ...common, kind, minimum, maximum, integer: entry.type === 'integer', values: [] };
  }
  if (kind === 'values') {
    const options = entry.oneOf;
    if (!Array.isArray(options)) return null;
    const values: FilterValue[] = [];
    for (const option of options) {
      if (!isObject(option) || !isText(option.const) || !isText(option.title)) return null;
      values.push({ value: option.const, label: option.title });
    }
    if (values.length < 2 || new Set(values.map((v) => v.value)).size !== values.length) return null;
    return { ...common, kind, minimum: 0, maximum: 0, integer: false, values };
  }
  return null;
}

// Whether the user has put anything into the fields of this filter.
export function isSet(input: FilterInput | undefined): boolean {
  if (!input) return false;
  return input.kind === 'range' ? input.from.trim() !== '' || input.to.trim() !== '' : input.values.length > 0;
}

// What is wrong with the fields of a range, or `null`. `field` names the field to mark; a range whose start is above
// its end marks both. Short texts, the bounds are in the placeholders (plan §6.7).
export interface FilterError {
  field: 'from' | 'to' | 'both';
  message: string;
}

const NUMBER = /^[+-]?(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i;

// `null` for an empty field (no bound), `NaN` for text that is no finite number.
function bound(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === '') return null;
  if (!NUMBER.test(trimmed)) return Number.NaN;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : Number.NaN;
}

function boundError(filter: SearchFilterDescription, value: number | null): string | null {
  if (value === null) return null;
  if (Number.isNaN(value)) return 'Enter a number';
  if (value < filter.minimum || value > filter.maximum) return `Between ${filter.minimum} and ${filter.maximum}`;
  if (filter.integer && !Number.isInteger(value)) return 'Whole numbers only';
  return null;
}

export function filterError(filter: SearchFilterDescription, input: FilterInput | undefined): FilterError | null {
  if (!input || input.kind !== 'range' || filter.kind !== 'range') return null;
  const from = bound(input.from);
  const to = bound(input.to);
  const fromError = boundError(filter, from);
  if (fromError) return { field: 'from', message: fromError };
  const toError = boundError(filter, to);
  if (toError) return { field: 'to', message: toError };
  if (from !== null && to !== null && from > to) return { field: 'both', message: 'From is above to' };
  return null;
}

// The filters of a dataset the user has put something into, whether or not it is right yet.
export function setFilters(filters: SearchFilterDescription[], inputs: FilterInputs | undefined): SearchFilterDescription[] {
  return filters.filter((filter) => isSet(inputs?.[filter.property]));
}

// Whether any filter of the dataset has fields that are wrong.
export function hasFilterError(filters: SearchFilterDescription[], inputs: FilterInputs | undefined): boolean {
  return filters.some((filter) => filterError(filter, inputs?.[filter.property]) !== null);
}

// The `query` for the filters the user has set and got right: a filter with a wrong field is not sent (the search
// itself is held back until it is right, `hasFilterError`; the coverage map has nothing to wait for, so it simply
// goes without). `{}` when nothing is set.
export function filterQuery(filters: SearchFilterDescription[], inputs: FilterInputs | undefined): FilterQuery {
  const query: FilterQuery = {};
  for (const filter of filters) {
    const input = inputs?.[filter.property];
    if (!input || !isSet(input) || filterError(filter, input)) continue;
    if (input.kind === 'range' && filter.kind === 'range') {
      const from = bound(input.from);
      const to = bound(input.to);
      const operators: Record<string, number> = {};
      if (from !== null) operators.gte = from;
      if (to !== null) operators.lte = to;
      query[filter.property] = operators;
    } else if (input.kind === 'values' && filter.kind === 'values') {
      // In the order of the registry, and only values it offers.
      const values = filter.values.map((v) => v.value).filter((value) => input.values.includes(value));
      if (values.length > 0) query[filter.property] = { in: values };
    }
  }
  return query;
}

export const isEmptyQuery = (query: FilterQuery | undefined): boolean => !query || Object.keys(query).length === 0;

// `{collection: query}` for the datasets that have a filter set; the `query_by_collection` of the search.
export type FilterQueryByCollection = Record<string, FilterQuery>;
