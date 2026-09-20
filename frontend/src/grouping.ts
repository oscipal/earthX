// Group STAC items into time steps, using the grouping key the registry
// names for the dataset (`earthx:viewer.group_by`, architekturplan.md 5.1)
// instead of BIOMASS-specific knowledge.
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
