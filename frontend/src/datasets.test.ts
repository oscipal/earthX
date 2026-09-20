import { describe, expect, it } from 'vitest';

import { datasetsFrom, groupByOf, quicklookAsset } from './datasets';
import type { Collection, StacItem } from './types';

function collection(overrides: Partial<Collection> = {}): Collection {
  return { id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', ...overrides };
}

describe('groupByOf', () => {
  it('reads earthx:viewer.group_by', () => {
    expect(groupByOf(collection({ 'earthx:viewer': { group_by: ['datetime', 'grid:code'] } }))).toEqual([
      'datetime',
      'grid:code',
    ]);
  });

  it('is null when earthx:viewer is missing', () => {
    expect(groupByOf(collection())).toBeNull();
  });

  it('is null when group_by is empty', () => {
    expect(groupByOf(collection({ 'earthx:viewer': { group_by: [] } }))).toBeNull();
  });
});

describe('datasetsFrom', () => {
  it('a dataset without earthx:viewer.group_by is not viewable, and says why', () => {
    const [option] = datasetsFrom([collection()]);
    expect(option.viewable).toBe(false);
    if (!option.viewable) expect(option.reason).toMatch(/group_by/);
  });

  it('the other datasets in the list stay selectable', () => {
    const good = collection({ id: 'sentinel-2-c1-l2a', 'earthx:viewer': { group_by: ['datetime'] } });
    const bad = collection({ id: 'broken-dataset' });
    const options = datasetsFrom([good, bad]);
    expect(options.find((o) => o.id === 'sentinel-2-c1-l2a')?.viewable).toBe(true);
    expect(options.find((o) => o.id === 'broken-dataset')?.viewable).toBe(false);
  });

  it('a viewable dataset carries its group_by', () => {
    const [option] = datasetsFrom([collection({ 'earthx:viewer': { group_by: ['datetime', 'grid:code'] } })]);
    expect(option.viewable).toBe(true);
    if (option.viewable) expect(option.groupBy).toEqual(['datetime', 'grid:code']);
  });
});

function item(assets: StacItem['assets']): StacItem {
  return { id: 'an-item', properties: {}, assets };
}

describe('quicklookAsset', () => {
  it('picks the thumbnail role first', () => {
    const it_ = item({
      overview: { href: 'https://example.test/overview.jpg', roles: ['overview'] },
      thumbnail: { href: 'https://example.test/thumb.jpg', roles: ['thumbnail'] },
    });
    expect(quicklookAsset(it_)?.href).toBe('https://example.test/thumb.jpg');
  });

  it('falls back to overview when there is no thumbnail role', () => {
    const it_ = item({
      overview: { href: 'https://example.test/overview.jpg', roles: ['overview'] },
      data: { href: 'https://example.test/data.tif', roles: ['data'] },
    });
    expect(quicklookAsset(it_)?.href).toBe('https://example.test/overview.jpg');
  });

  it('falls back to the first image/* asset', () => {
    const it_ = item({
      data: { href: 'https://example.test/data.tif', type: 'image/tiff; application=geotiff' },
      other: { href: 'https://example.test/other.json', type: 'application/json' },
    });
    expect(quicklookAsset(it_)?.href).toBe('https://example.test/data.tif');
  });

  it('is null when nothing matches', () => {
    const it_ = item({ other: { href: 'https://example.test/other.json', type: 'application/json' } });
    expect(quicklookAsset(it_)).toBeNull();
  });
});
