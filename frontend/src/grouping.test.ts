import { describe, expect, it } from 'vitest';

import { buildGroups, groupKey, MissingProperty } from './grouping';
import type { StacItem } from './types';

function item(properties: Record<string, unknown>): StacItem {
  return { id: 'an-item', properties, assets: {} };
}

const SENTINEL_2_GROUP_BY = ['datetime', 'grid:code'];

// The 12 cases of backend/tests/catalog/test_group_key.py, mirrored one to
// one (plan §6.1) so group_key and this implementation cannot drift apart.
describe('an instant becomes its UTC date', () => {
  it('the time of day drops out of the key', () => {
    expect(groupKey(item({ datetime: '2026-07-24T10:38:17.453000Z' }), ['datetime'])).toEqual([
      '2026-07-24',
    ]);
  });

  it('two scenes of the same day land in one group', () => {
    const morning = item({ datetime: '2026-07-24T10:38:17Z', 'grid:code': 'MGRS-32TMS' });
    const evening = item({ datetime: '2026-07-24T22:01:03Z', 'grid:code': 'MGRS-32TMS' });
    expect(groupKey(morning, SENTINEL_2_GROUP_BY)).toEqual(groupKey(evening, SENTINEL_2_GROUP_BY));
  });

  it('the date is the one in UTC, not the local one', () => {
    const utc = item({ datetime: '2026-07-24T23:30:00Z', 'grid:code': 'MGRS-32TMS' });
    const local = item({ datetime: '2026-07-25T01:30:00+02:00', 'grid:code': 'MGRS-32TMS' });
    expect(groupKey(utc, SENTINEL_2_GROUP_BY)).toEqual(['2026-07-24', 'MGRS-32TMS']);
    expect(groupKey(local, SENTINEL_2_GROUP_BY)).toEqual(['2026-07-24', 'MGRS-32TMS']);
  });

  it('a second across midnight is another day', () => {
    expect(groupKey(item({ datetime: '2026-07-24T23:59:59Z' }), ['datetime'])).toEqual(['2026-07-24']);
    expect(groupKey(item({ datetime: '2026-07-25T00:00:00Z' }), ['datetime'])).toEqual(['2026-07-25']);
  });

  it('an instant that is already a Date is read the same way', () => {
    const parsed = item({ datetime: new Date('2026-07-24T23:30:00Z') });
    expect(groupKey(parsed, ['datetime'])).toEqual(['2026-07-24']);
  });
});

describe('everything else is its own text', () => {
  it('a grid code is carried over unchanged', () => {
    expect(groupKey(item({ 'grid:code': 'MGRS-32TMS' }), ['grid:code'])).toEqual(['MGRS-32TMS']);
  });

  it('a bare date stays the date it is', () => {
    expect(groupKey(item({ acquired: '2026-07-24' }), ['acquired'])).toEqual(['2026-07-24']);
  });

  it('a number becomes its text rather than a type error', () => {
    expect(groupKey(item({ orbit: 137 }), ['orbit'])).toEqual(['137']);
  });

  it('the parts keep the order the registry names', () => {
    const scene = item({ datetime: '2026-07-24T10:00:00Z', 'grid:code': 'MGRS-32TMS' });
    expect(groupKey(scene, SENTINEL_2_GROUP_BY)).toEqual(['2026-07-24', 'MGRS-32TMS']);
    expect(groupKey(scene, ['grid:code', 'datetime'])).toEqual(['MGRS-32TMS', '2026-07-24']);
  });
});

describe('a missing property is an error', () => {
  it('a property the item does not carry', () => {
    expect(() =>
      groupKey(item({ datetime: '2026-07-24T10:00:00Z' }), SENTINEL_2_GROUP_BY),
    ).toThrow(/grid:code/);
  });

  it('an item without properties at all', () => {
    const noProps = { id: 'an-item', properties: undefined, assets: {} } as unknown as StacItem;
    expect(() => groupKey(noProps, SENTINEL_2_GROUP_BY)).toThrow(MissingProperty);
  });
});

it('the key of the registered dataset is the acquisition day per tile', () => {
  const scene = item({ datetime: '2026-07-24T10:38:17.453000Z', 'grid:code': 'MGRS-32TMS' });
  expect(groupKey(scene, SENTINEL_2_GROUP_BY)).toEqual(['2026-07-24', 'MGRS-32TMS']);
});

describe('buildGroups', () => {
  it('sorts newest first, then stably by the rest of the key', () => {
    const a = item({ datetime: '2026-07-24T10:00:00Z', 'grid:code': 'MGRS-32TMS' });
    const b = item({ datetime: '2026-07-25T10:00:00Z', 'grid:code': 'MGRS-32TMS' });
    const c = item({ datetime: '2026-07-25T10:00:00Z', 'grid:code': 'MGRS-31TCJ' });
    const groups = buildGroups([a, b, c], SENTINEL_2_GROUP_BY);
    expect(groups.map((g) => g.key)).toEqual([
      ['2026-07-25', 'MGRS-32TMS'],
      ['2026-07-25', 'MGRS-31TCJ'],
      ['2026-07-24', 'MGRS-32TMS'],
    ]);
  });

  it('an empty input yields an empty list', () => {
    expect(buildGroups([], SENTINEL_2_GROUP_BY)).toEqual([]);
  });

  it('a missing property comes out of buildGroups rather than being swallowed', () => {
    const good = item({ datetime: '2026-07-24T10:00:00Z', 'grid:code': 'MGRS-32TMS' });
    const bad = item({ datetime: '2026-07-24T10:00:00Z' });
    expect(() => buildGroups([good, bad], SENTINEL_2_GROUP_BY)).toThrow(MissingProperty);
  });

  it('the label is the key parts joined in order', () => {
    const scene = item({ datetime: '2026-07-24T10:00:00Z', 'grid:code': 'MGRS-32TMS' });
    const [group] = buildGroups([scene], SENTINEL_2_GROUP_BY);
    expect(group.label).toBe('2026-07-24 · MGRS-32TMS');
  });
});
