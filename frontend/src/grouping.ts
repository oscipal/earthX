// Group STAC items into time steps, using the grouping key the registry
// names for the dataset instead of BIOMASS-specific knowledge. The key that
// heads the *results list* and the download route's per-group merge (P19) is
// `earthx:viewer.results_group_by` (M3-12, `datasets.ts::resultsGroupByOf`) —
// callers pass it straight to `buildGroups` below, with no fallback logic
// here: the registry states the key that always applies for a dataset, the
// way `group_by` always did, and a genuinely missing property on an item
// still surfaces as `MissingProperty`, same as it always has. Before M3-12
// this file also carried `displayGroupBy`, a runtime fallback from a
// hardcoded `s2:datatake_id` to the registry's own `group_by` — replaced by
// `results_group_by` being a real registry field for every dataset now.
//
// `groupKey` mirrors `earthx.catalog.registry.group_key` part for part
// (docs/plans/m2-07a-frontend-api-suche-quicklooks-zeitleiste.md §5): the
// two must not drift apart, which is why the 12 cases of
// `backend/tests/catalog/test_group_key.py` are repeated in `grouping.test.ts`.

import type { StacItem, TimeStepGroup } from './types';

// An item does not carry a property the grouping key is built from. Its own
// type, and never silently skipped: a key that quietly loses one of its
// parts would merge two groups that do not belong together.
export class MissingProperty extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'MissingProperty';
  }
}

// An ISO 8601 instant with a time part. A bare date (`2026-07-24`) does not
// match, and goes through the text path instead — with the same result,
// because the backend resolves it to the same date (registry.py `_key_part`).
const INSTANT_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/;

function utcDate(instant: Date): string {
  return instant.toISOString().slice(0, 10);
}

// A STAC instant as its UTC date, everything else as its own text — the
// same rule as `registry._key_part`, in the same order: only strings are
// even considered for an instant, so a number never gets read as one.
function keyPart(value: unknown): string {
  if (value instanceof Date) return utcDate(value);
  if (typeof value === 'string') {
    if (INSTANT_PATTERN.test(value)) {
      const parsed = new Date(value);
      if (!Number.isNaN(parsed.getTime())) return utcDate(parsed);
    }
    return value;
  }
  return String(value);
}

export function groupKey(item: StacItem, groupBy: readonly string[]): string[] {
  const properties = item.properties;
  if (!properties || typeof properties !== 'object') {
    throw new MissingProperty(`item ${item.id ?? '?'} carries no properties`);
  }
  const key: string[] = [];
  for (const name of groupBy) {
    if (!(name in properties)) {
      throw new MissingProperty(`item ${item.id ?? '?'} is missing property "${name}"`);
    }
    key.push(keyPart(properties[name]));
  }
  return key;
}

// Groups by key, newest first (the key's UTC-date-first convention sorts
// correctly as text), then stable by the rest of the key. Throws
// `MissingProperty` straight through rather than dropping the offending item
// — a key that quietly loses a part would merge two groups into one.
export function buildGroups(items: StacItem[], groupBy: readonly string[]): TimeStepGroup[] {
  const byKey = new Map<string, TimeStepGroup>();
  for (const item of items) {
    const key = groupKey(item, groupBy);
    const keyId = key.join('\u0000');
    let group = byKey.get(keyId);
    if (!group) {
      group = { key, label: key.join(' · '), items: [] };
      byKey.set(keyId, group);
    }
    group.items.push(item);
  }
  return [...byKey.values()].sort((a, b) => {
    const ka = a.key.join('\u0000');
    const kb = b.key.join('\u0000');
    return ka < kb ? 1 : ka > kb ? -1 : 0;
  });
}

export function groupIndexOfItem(groups: TimeStepGroup[], itemId: string): number {
  return groups.findIndex((g) => g.items.some((it) => it.id === itemId));
}

// `itemIds`, split back into the groups they came from (M3-17: "download
// folgt der Ansicht" needs one merged file per group, P19) — exactly the
// split `store.ts::addCurrentToLayers` (PR #84, F5) already draws for a
// pinned layer, reused here rather than a second, download-specific
// grouping. Buckets keep the order their first member was encountered in
// `itemIds`; an id `groupIndexOfItem` cannot place in any group (should not
// happen for a live search result, but never assumed) shares one bucket with
// every other such id rather than silently joining a group it does not
// belong to.
export function groupItemIdsFor(itemIds: readonly string[], groups: readonly TimeStepGroup[]): string[][] {
  const byGroupIndex = new Map<number, string[]>();
  for (const itemId of itemIds) {
    const idx = groupIndexOfItem(groups as TimeStepGroup[], itemId);
    const bucket = byGroupIndex.get(idx);
    if (bucket) bucket.push(itemId);
    else byGroupIndex.set(idx, [itemId]);
  }
  return [...byGroupIndex.values()];
}

// What the map should show: the expanded-in-the-list group's items, plus any
// selected item that belongs to a different group. `ResultsPanel` only ever
// expands one group at a time, and collapsing it — by switching to another
// group — must only change what the list displays, never make a selected
// quicklook vanish from the map (V-3). An unselected item of a collapsed
// group still drops off, same as before. `null` means every group is
// collapsed (V-11): nothing is "active" to preview, only selected items (if
// any) still show.
export function itemsForMap(
  groups: TimeStepGroup[],
  expandedGroupIndex: number | null,
  selectedIds: readonly string[],
): StacItem[] {
  const active = expandedGroupIndex === null ? [] : (groups[expandedGroupIndex]?.items ?? []);
  if (selectedIds.length === 0) return active;
  const activeIds = new Set(active.map((it) => it.id));
  const pinned = groups.flatMap((g) => g.items).filter((it) => !activeIds.has(it.id) && selectedIds.includes(it.id));
  return pinned.length ? [...active, ...pinned] : active;
}
