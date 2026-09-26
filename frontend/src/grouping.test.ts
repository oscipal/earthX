import { describe, expect, it } from 'vitest';

import { buildGroups, groupItemIdsFor, groupKey, itemsForMap, MissingProperty } from './grouping';
import type { StacItem, TimeStepGroup } from './types';

function item(properties: Record<string, unknown>): StacItem {
  return { id: 'an-item', properties, assets: {} };
}

function taggedItem(id: string, datetime: string): StacItem {
  return { id, properties: { datetime }, assets: {} };
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

// V-4: the results list heads groups by day + overpass (`s2:datatake_id` for
// the COG dataset, `eopf:datatake_id` for the Zarr one) instead of day + MGRS
// tile — a display-only change, never affecting which scenes exist (D11).
// Before M3-12 this was `displayGroupBy`, a runtime fallback from a hardcoded
// property name to the registry's `group_by`; the key is now a real registry
// field (`earthx:viewer.results_group_by`, `datasets.ts::resultsGroupByOf`),
// so no fallback logic is left to test here — `buildGroups` groups by
// whichever key its caller passes, day-and-overpass included.
describe('buildGroups with a day-and-overpass key', () => {
  it('two tiles of the same overpass land in one group', () => {
    const a = item({ datetime: '2026-07-24T10:00:00Z', 'grid:code': 'MGRS-32TMS', 's2:datatake_id': 'GS2A_1' });
    const b = item({ datetime: '2026-07-24T10:01:00Z', 'grid:code': 'MGRS-32TNS', 's2:datatake_id': 'GS2A_1' });
    const groups = buildGroups([a, b], ['datetime', 's2:datatake_id']);
    expect(groups).toHaveLength(1);
    expect(groups[0].items.map((it) => it.id)).toEqual(['an-item', 'an-item']);
  });
});

// V-3, finding 2: a selected quicklook must not disappear from the map when
// its time step is no longer the one expanded in ResultsPanel's accordion
// (`activeGroupIndex` switches away from it).
describe('itemsForMap', () => {
  const a1 = taggedItem('a1', '2026-07-25T10:00:00Z');
  const a2 = taggedItem('a2', '2026-07-25T11:00:00Z');
  const b1 = taggedItem('b1', '2026-07-24T10:00:00Z');
  const b2 = taggedItem('b2', '2026-07-24T12:00:00Z');
  // newest first: group 0 = 2026-07-25 (a1, a2), group 1 = 2026-07-24 (b1, b2)
  const groups = buildGroups([a1, a2, b1, b2], ['datetime']);

  it('is just the active group when nothing is selected', () => {
    expect(itemsForMap(groups, 0, [])).toEqual(groups[0].items);
  });

  it('keeps a selected item of a collapsed group, on top of the active group', () => {
    const ids = itemsForMap(groups, 0, ['b1']).map((it) => it.id);
    expect(ids.sort()).toEqual(['a1', 'a2', 'b1']);
  });

  it('leaves a non-selected item of the collapsed group off the map', () => {
    const ids = itemsForMap(groups, 0, ['b1']).map((it) => it.id);
    expect(ids).not.toContain('b2');
  });

  it('does not duplicate an item that is both in the active group and selected', () => {
    const ids = itemsForMap(groups, 0, ['a1']).map((it) => it.id);
    expect(ids).toEqual(['a1', 'a2']);
  });

  it('picks up a selection once its group becomes active, without carrying the old one along by accident', () => {
    const ids = itemsForMap(groups, 1, ['b1']).map((it) => it.id).sort();
    expect(ids).toEqual(['b1', 'b2']);
  });

  it('is empty for an out-of-range active index and no selection', () => {
    expect(itemsForMap(groups, 99, [])).toEqual([]);
  });

  // V-11: every group collapsed (nothing "active" in the results list) must
  // hide quicklooks on the map, same as an out-of-range index — but a
  // selection still shows, exactly like a collapsed-but-valid group would.
  describe('with every group collapsed (null)', () => {
    it('is empty with no selection', () => {
      expect(itemsForMap(groups, null, [])).toEqual([]);
    });

    it('still shows a selected item', () => {
      const ids = itemsForMap(groups, null, ['b1']).map((it) => it.id);
      expect(ids).toEqual(['b1']);
    });

    it('does not fall back to any particular group by accident', () => {
      const ids = itemsForMap(groups, null, []).map((it) => it.id);
      expect(ids).not.toContain('a1');
      expect(ids).not.toContain('b1');
    });
  });
});

// M3-17: "download folgt der Ansicht" reuses this same per-overpass grouping
// (PR #84) rather than a second, download-specific one.
describe('groupItemIdsFor', () => {
  const GROUPS: TimeStepGroup[] = [
    { key: ['a'], label: 'Overpass A', items: [taggedItem('S1', '2026-07-24T10:00:00Z'), taggedItem('S2', '2026-07-24T10:00:01Z')] },
    { key: ['b'], label: 'Overpass B', items: [taggedItem('S3', '2026-07-25T10:00:00Z')] },
  ];

  it('splits ids back into the groups they came from', () => {
    expect(groupItemIdsFor(['S1', 'S2', 'S3'], GROUPS)).toEqual([['S1', 'S2'], ['S3']]);
  });

  it('keeps the order the first member of each group was encountered in', () => {
    expect(groupItemIdsFor(['S3', 'S1', 'S2'], GROUPS)).toEqual([['S3'], ['S1', 'S2']]);
  });

  it('a subset of ids only produces the groups it actually touches', () => {
    expect(groupItemIdsFor(['S1'], GROUPS)).toEqual([['S1']]);
  });

  it('an id no group contains shares one bucket with every other such id', () => {
    expect(groupItemIdsFor(['S1', 'nope1', 'nope2'], GROUPS)).toEqual([['S1'], ['nope1', 'nope2']]);
  });

  it('an empty id list is an empty result', () => {
    expect(groupItemIdsFor([], GROUPS)).toEqual([]);
  });
});
